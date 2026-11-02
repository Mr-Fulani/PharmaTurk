"""TD-017: запасные ветки заказов отвечают как раньше, но оставляют причину в журнале."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase, override_settings
from rest_framework import serializers as drf_serializers

from apps.catalog.currency_models import ProductVariantPrice
from apps.catalog.models import ClothingProduct, ElectronicsProduct, ShoeProduct, ShoeVariant
from apps.catalog.utils.currency_converter import currency_converter
from apps.orders import cart_reminders, services, tasks
from apps.orders.admin import PromoCodeAdmin
from apps.orders.models import Cart, CartItem, PromoCode
from apps.orders.serializers import (
    CartItemSerializer,
    CartSerializer,
    OrderItemSerializer,
    OrderSerializer,
    SourcingRequestCreateSerializer,
    _serialize_translations_qs,
    ensure_product_from_variant,
)
from apps.orders.views import _get_product_price_for_currency

SERIALIZER_LOG = "apps.orders.serializers"


def _broken(*args, **kwargs):
    raise RuntimeError("boom")


def _no_images():
    return SimpleNamespace(
        filter=lambda **kwargs: SimpleNamespace(first=lambda: None),
        first=lambda: None,
    )


def _product(**overrides):
    data = dict(
        pk=1,
        price=Decimal("10"),
        old_price=None,
        currency="RUB",
        product_type="medicines",
        slug="aspirin",
        main_image="",
        images=_no_images(),
        external_data={},
        get_all_prices=lambda: {},
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def _cart_item(**overrides):
    data = dict(
        pk=2,
        product=_product(),
        price=Decimal("7"),
        currency="RUB",
        quantity=2,
        is_payable=True,
        source_offer_id=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


class SerializerCase(SimpleTestCase):
    def assert_logged(self, cm, *places):
        text = "\n".join(cm.output)
        for place in places:
            self.assertIn(f"fallback {place} ", text)
        self.assertIn("RuntimeError: boom", text)


@patch.object(currency_converter, "convert_price", side_effect=RuntimeError("boom"))
@patch("apps.catalog.utils.product_markup.get_effective_product_markup", return_value=(Decimal("0"), None))
class CartItemPriceFallbackTests(SerializerCase):
    def test_saved_price_used_when_conversion_fails(self, *_):
        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            price = CartItemSerializer().get_price(_cart_item())

        self.assertEqual(price, Decimal("7"))
        self.assert_logged(cm, "cart_item.live_price", "cart_item.saved_price_conversion")

    def test_stored_prices_failure_keeps_product_price(self, *_):
        item = _cart_item(product=_product(get_all_prices=_broken))

        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            result = CartItemSerializer()._get_base_price(item)

        self.assertEqual(result, (Decimal("10"), "RUB"))
        self.assert_logged(cm, "cart_item.base_price")

    def test_observed_price_returned_without_conversion(self, *_):
        item = _cart_item(
            source_offer_id=5,
            observed_public_price=Decimal("30"),
            observed_public_currency="TRY",
        )

        with override_settings(SOURCE_OFFER_CART_ENFORCEMENT_ENABLED=True):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                price = CartItemSerializer().get_price(item)

        self.assertEqual(price, Decimal("30"))
        self.assert_logged(cm, "cart_item.observed_price_conversion")

    def test_old_price_returned_as_stored(self, *_):
        item = _cart_item(product=_product(old_price=Decimal("20")))

        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            self.assertEqual(CartItemSerializer().get_old_price(item), Decimal("20"))

        self.assert_logged(cm, "cart_item.old_price")

    def test_jewelry_price_empty(self, *_):
        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            data = CartItemSerializer()._get_jewelry_price_data(_product(), "USD")

        self.assertIsNone(data)
        self.assert_logged(cm, "cart_item.jewelry_price")

    def test_converted_and_final_prices_empty(self, *_):
        cases = {
            "get_converted_price_rub": "cart_item.converted_price_rub",
            "get_converted_price_usd": "cart_item.converted_price_usd",
            "get_final_price_rub": "cart_item.final_price_rub",
            "get_final_price_usd": "cart_item.final_price_usd",
        }
        for method, place in cases.items():
            with self.subTest(method=method), self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertIsNone(getattr(CartItemSerializer(), method)(_cart_item()))
                self.assert_logged(cm, place)

    def test_prices_in_currencies_skips_failed_currency(self, *_):
        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            prices = CartItemSerializer().get_prices_in_currencies(_cart_item())

        self.assertEqual(prices, {})
        self.assertEqual(len(cm.output), 6)

    def test_margin_is_zero(self, *_):
        with patch.object(currency_converter, "get_margin_rate", side_effect=_broken):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertEqual(CartItemSerializer().get_margin_percent_applied(_cart_item()), 0)

        self.assert_logged(cm, "cart_item.margin_percent")


class CartItemLookupFallbackTests(SerializerCase):
    def test_base_product_image_failure_returns_no_image(self):
        item = _cart_item(product=_product(product_type="electronics"))

        with patch.object(ElectronicsProduct, "objects", MagicMock(filter=_broken)):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertIsNone(CartItemSerializer().get_product_image_url(item))

        self.assert_logged(cm, "cart_item.image_base_product")

    def test_first_variant_image_failure_returns_no_image(self):
        item = _cart_item(
            product=_product(product_type="clothing", external_data={"source_type": "books"})
        )
        # Первый запрос — базовая модель по типу, второй — запасной поиск первого варианта.
        manager = MagicMock()
        manager.filter.side_effect = [
            MagicMock(**{"prefetch_related.return_value.first.return_value": None}),
            RuntimeError("boom"),
        ]

        with patch.object(ClothingProduct, "objects", manager):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertIsNone(CartItemSerializer().get_product_image_url(item))

        self.assert_logged(cm, "cart_item.image_first_variant")

    def test_domain_image_failure_returns_no_image(self):
        class BrokenDomain(SimpleNamespace):
            @property
            def domain_item(self):
                raise RuntimeError("boom")

        item = _cart_item(
            product=BrokenDomain(
                pk=1, main_image="", images=_no_images(), product_type="medicines",
                slug="aspirin", external_data={},
            )
        )

        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            self.assertIsNone(CartItemSerializer().get_product_image_url(item))

        self.assert_logged(cm, "cart_item.image_domain")

    def test_parent_slug_failure_returns_none(self):
        item = _cart_item(
            product=_product(
                external_data={"source_variant_slug": "red", "source_type": "shoes"}
            )
        )

        with patch.object(ShoeVariant, "objects", MagicMock(filter=_broken)):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertIsNone(CartItemSerializer().get_product_parent_slug(item))

        self.assert_logged(cm, "cart_item.parent_slug")


class CartTotalsFallbackTests(SerializerCase):
    def test_total_uses_saved_price_of_broken_item(self):
        cart = SimpleNamespace(pk=3, items=SimpleNamespace(all=lambda: [_cart_item()]))

        with patch.object(CartItemSerializer, "get_price", side_effect=_broken):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertEqual(CartSerializer().get_total_amount(cart), 14.0)

        self.assert_logged(cm, "cart.total_amount")

    def test_final_amount_counts_failed_parts_as_zero(self):
        cart = SimpleNamespace(pk=3)

        with patch.object(CartSerializer, "get_total_amount", side_effect=_broken), patch.object(
            CartSerializer, "get_discount_amount", side_effect=_broken
        ):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertEqual(CartSerializer().get_final_amount(cart), 0.0)

        self.assert_logged(cm, "cart.final_amount_total", "cart.final_amount_discount")

    @patch.object(currency_converter, "convert_price", side_effect=RuntimeError("boom"))
    @patch("apps.catalog.currency_models.GlobalCurrencySettings.load")
    def test_free_shipping_threshold_stays_in_usd(self, load, _convert):
        load.return_value = SimpleNamespace(free_shipping_min_subtotal_usd=Decimal("50"))

        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            self.assertEqual(CartSerializer().get_free_shipping_threshold(SimpleNamespace(pk=3)), 50.0)

        self.assert_logged(cm, "cart.free_shipping_threshold")

    @patch.object(currency_converter, "convert_price", side_effect=RuntimeError("boom"))
    @patch("apps.orders.shipping_pricing.product_is_free_shipping_eligible", return_value=True)
    @patch("apps.orders.shipping_pricing.calculate_item_shipping_costs_usd")
    @patch("apps.catalog.currency_models.GlobalCurrencySettings.load")
    def test_shipping_keeps_usd_cost_and_no_free_shipping(self, load, costs, *_):
        load.return_value = SimpleNamespace(free_shipping_min_subtotal_usd=Decimal("10"))
        costs.return_value = {"air": 5, "sea": 0, "ground": 0}
        cart = SimpleNamespace(pk=3, items=SimpleNamespace(all=lambda: [_cart_item()]))

        with patch.object(CartSerializer, "get_shipping_requires_quote", return_value=False), patch.object(
            CartSerializer, "get_total_amount", return_value=100.0
        ):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                options = CartSerializer().get_shipping_options(cart)

        self.assertEqual(options, {"air": 5.0, "sea": 0.0, "ground": 0.0})
        self.assert_logged(cm, "cart.shipping_cost_conversion", "cart.free_shipping")


class OrderMoneyFallbackTests(SerializerCase):
    def test_order_item_amounts_stay_in_order_currency(self):
        item = SimpleNamespace(
            pk=4, price=Decimal("10"), total=Decimal("20"), order=SimpleNamespace(currency="TRY")
        )

        with patch.object(OrderItemSerializer, "_convert_money", side_effect=_broken):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                self.assertEqual(OrderItemSerializer().get_price(item), Decimal("10"))
                self.assertEqual(OrderItemSerializer().get_total(item), Decimal("20"))

        self.assert_logged(cm, "order_item.price", "order_item.total")

    def test_order_item_image_failure_returns_no_image(self):
        product = _product(images=SimpleNamespace(filter=_broken))

        with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
            self.assertIsNone(
                OrderItemSerializer().get_product_image_url(SimpleNamespace(pk=4, product=product))
            )

        self.assert_logged(cm, "order_item.image")

    def test_order_amounts_stay_in_order_currency(self):
        order = SimpleNamespace(
            pk=5,
            currency="TRY",
            subtotal_amount=Decimal("1"),
            shipping_amount=Decimal("2"),
            discount_amount=Decimal("3"),
            total_amount=Decimal("4"),
        )

        with patch.object(OrderSerializer, "_convert_money", side_effect=_broken):
            with self.assertLogs(SERIALIZER_LOG, "WARNING") as cm:
                serializer = OrderSerializer()
                self.assertEqual(serializer.get_subtotal_amount(order), Decimal("1"))
                self.assertEqual(serializer.get_shipping_amount(order), Decimal("2"))
                self.assertEqual(serializer.get_discount_amount(order), Decimal("3"))
                self.assertEqual(serializer.get_total_amount(order), Decimal("4"))

        self.assert_logged(
            cm,
            "order.subtotal_amount",
            "order.shipping_amount",
            "order.discount_amount",
            "order.total_amount",
        )


class NarrowedExceptTests(SimpleTestCase):
    def test_object_without_all_gives_no_translations(self):
        self.assertEqual(_serialize_translations_qs(object()), [])
        self.assertEqual(services._serialize_translations_qs(object()), [])

    def test_unexpected_translation_error_is_not_hidden(self):
        translations = MagicMock()
        translations.all.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            _serialize_translations_qs(translations)
        with self.assertRaises(RuntimeError):
            services._serialize_translations_qs(translations)

    def test_unreadable_upload_is_validation_error(self):
        upload = SimpleNamespace(content_type="image/png", read=MagicMock(side_effect=OSError("disk")))

        with self.assertRaises(drf_serializers.ValidationError):
            SourcingRequestCreateSerializer().validate_image(upload)

    def test_broken_image_bytes_are_validation_error(self):
        upload = SimpleNamespace(content_type="image/png", read=lambda size: b"not an image")

        with self.assertRaises(drf_serializers.ValidationError):
            SourcingRequestCreateSerializer().validate_image(upload)


class ModelFallbackTests(SimpleTestCase):
    def test_invalid_amount_gives_zero_discount(self):
        promo = PromoCode(discount_type="percent", discount_value=Decimal("10"))

        with self.assertLogs("apps.orders.models", "WARNING") as cm:
            self.assertEqual(promo.calculate_discount("bad"), 0.0)

        self.assertIn("'bad'", cm.output[0])

    def test_invalid_fixed_value_gives_zero_discount(self):
        promo = PromoCode(discount_type="fixed", discount_value=Decimal("10"))

        with patch.object(PromoCode, "get_fixed_discount_value", return_value="bad"), patch.object(
            PromoCode, "get_max_discount", return_value=None
        ):
            with self.assertLogs("apps.orders.models", "WARNING") as cm:
                self.assertEqual(promo.calculate_discount(100), 0.0)

        self.assertIn("'bad'", cm.output[0])

    def test_cart_total_uses_saved_price(self):
        item = _cart_item(product=_product(get_all_prices=_broken))
        items = SimpleNamespace(all=lambda: [item])

        with patch.object(Cart, "items", items):
            with self.assertLogs("apps.orders.models", "WARNING") as cm:
                self.assertEqual(Cart(currency="RUB").total_amount, Decimal("14"))

        self.assertIn("RuntimeError: boom", cm.output[0])

    def test_cart_item_total_uses_saved_price(self):
        with patch.object(CartItem, "product", _product(get_all_prices=_broken)):
            with self.assertLogs("apps.orders.models", "WARNING") as cm:
                item = CartItem(currency="RUB", price=Decimal("7"), quantity=2)
                self.assertEqual(item.total, Decimal("14"))

        self.assertIn("RuntimeError: boom", cm.output[0])


class ProductPriceHelperTests(SimpleTestCase):
    @patch.object(currency_converter, "convert_price", side_effect=RuntimeError("boom"))
    @patch("apps.catalog.utils.product_markup.apply_product_markup", return_value=Decimal("11"))
    def test_broken_prices_and_conversion_fall_back_to_product_price(self, markup, _convert):
        product = _product(get_all_prices=_broken)

        with self.assertLogs("apps.orders.views", "WARNING") as cm:
            price = _get_product_price_for_currency(product, "USD")

        self.assertEqual(price, Decimal("11"))
        markup.assert_called_once_with(Decimal("10"), product)
        self.assertEqual(len(cm.output), 2)
        self.assertIn("RuntimeError: boom", cm.output[1])

    @patch("apps.catalog.utils.product_markup.apply_product_markup", side_effect=RuntimeError("boom"))
    def test_no_price_and_broken_markup_gives_zero(self, _markup):
        with self.assertLogs("apps.orders.views", "WARNING") as cm:
            price = _get_product_price_for_currency(_product(price=None), "USD")

        self.assertEqual(price, Decimal("0"))
        self.assertIn("RuntimeError: boom", cm.output[0])


class AdminAndSettingsFallbackTests(SimpleTestCase):
    def test_admin_overview_skips_failed_currency(self):
        promo = SimpleNamespace(pk=6, get_min_amount=_broken)
        admin = PromoCodeAdmin(PromoCode, AdminSite())

        with self.assertLogs("apps.orders.admin", "WARNING") as cm:
            self.assertEqual(admin.money_overview(promo), "")

        self.assertEqual(len(cm.output), 5)

    @patch("apps.settings.models.FooterSettings.objects")
    def test_cart_reminder_goes_without_manager_button(self, footer):
        footer.first.side_effect = RuntimeError("boom")

        with self.assertLogs("apps.orders.cart_reminders", "WARNING") as cm:
            self.assertEqual(cart_reminders._manager_url(), "")

        self.assertIn("RuntimeError: boom", cm.output[0])

    @patch("apps.settings.models.FooterSettings.objects")
    def test_receipt_built_without_footer_contacts(self, footer):
        footer.first.side_effect = RuntimeError("boom")
        order = MagicMock(
            number="N-1",
            currency="RUB",
            subtotal_amount=Decimal("1"),
            shipping_amount=Decimal("0"),
            discount_amount=Decimal("0"),
            total_amount=Decimal("1"),
            shipping_address_text="Istanbul",
            comment="",
            promo_code=None,
        )
        order.items.all.return_value = []

        with self.assertLogs("apps.orders.services", "WARNING") as cm:
            receipt = services.build_order_receipt_payload(order)

        self.assertNotIn("telegram_url", receipt["seller"])
        self.assertIn("RuntimeError: boom", cm.output[0])


class NotificationFallbackTests(SimpleTestCase):
    def _backend(self, **kwargs):
        return tasks.IPv4EmailBackend(host="smtp.test", port=587, **kwargs)

    @patch("apps.orders.tasks.socket.getaddrinfo", side_effect=OSError("no dns"))
    def test_silent_smtp_failure_is_logged(self, _dns):
        with self.assertLogs("apps.orders.tasks", "WARNING") as cm:
            self.assertFalse(self._backend(fail_silently=True).open())

        self.assertIn("OSError", cm.output[0])

    @patch("apps.orders.tasks.socket.getaddrinfo", side_effect=OSError("no dns"))
    def test_smtp_failure_still_raises_by_default(self, _dns):
        with self.assertRaises(OSError):
            self._backend().open()

    @override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID="admin-chat")
    @patch("apps.orders.tasks.requests.post")
    @patch("apps.orders.models.SourcingRequest.objects.get")
    def test_unreadable_photo_keeps_text_notification(self, get_request, post):
        get_request.return_value = SimpleNamespace(
            pk=8,
            image=SimpleNamespace(open=MagicMock(side_effect=OSError("r2"))),
            source_url="",
            comment="",
            quantity=1,
            contact_name="Иван",
            contact_phone="+7999",
            contact_email="",
            contact_channel="phone",
            contact_username="",
        )
        post.return_value = SimpleNamespace(ok=True, status_code=200)

        with self.assertLogs("apps.orders.tasks", "WARNING") as cm:
            tasks.notify_sourcing_request_telegram.run(8)

        self.assertIn("OSError", cm.output[0])
        self.assertTrue(post.call_args.args[0].endswith("sendMessage"))


@pytest.mark.django_db
def test_variant_price_failure_keeps_variant_price(caplog):
    base = ShoeProduct.objects.create(
        name="Shoe", slug="fallback-shoe", price=Decimal("100"), currency="TRY"
    )
    variant = ShoeVariant.objects.create(
        product=base,
        name="Белые",
        slug="fallback-shoe-white",
        price=Decimal("200"),
        currency="TRY",
    )

    with patch.object(ProductVariantPrice.objects, "filter", side_effect=_broken):
        with caplog.at_level("WARNING", logger=SERIALIZER_LOG):
            product = ensure_product_from_variant(variant, "shoes", "shoes")

    assert product.price == Decimal("200")
    assert "fallback variant_price " in caplog.text
    assert "RuntimeError: boom" in caplog.text
