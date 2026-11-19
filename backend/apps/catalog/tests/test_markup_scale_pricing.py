"""Шкала наценки подключена к ценам: без выбранной шкалы всё как раньше,
с выбранной — одна и та же цена на карточке, в «Списке заявки», заявке, фиде и админке."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.db.models import ProtectedError
from rest_framework.test import APIRequestFactory

from apps.catalog.currency_models import (
    GlobalCurrencySettings,
    MarkupScale,
    MarkupScaleStep,
    ProductPrice,
)
from apps.catalog.models import Brand, Category, Product
from apps.catalog.pricing_serializers import apply_product_markup_to_payload
from apps.catalog.serializers import (
    ProductCardSerializer,
    ProductSerializer,
    serialize_product_for_card,
)
from apps.catalog.services.yml_feed import _MarkupResolver
from apps.catalog.utils.currency_converter import currency_converter
from apps.catalog.utils.product_markup import (
    apply_product_markup,
    explain_product_markup,
    get_effective_product_markup,
)
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.orders.serializers import CartSerializer
from apps.orders.services import build_order_receipt_payload
from apps.orders.views import _get_product_price_for_currency


STEPS = [(0, 100), (5000, 50), (10000, 20)]


def make_scale(name="Общая", steps=STEPS):
    scale = MarkupScale.objects.create(name=name)
    for price_from, percent in steps:
        MarkupScaleStep.objects.create(scale=scale, price_from=price_from, percent=percent)
    return scale


@pytest.fixture
def converter(monkeypatch):
    """1 лира = 2 рубля, валютная наценка пары 10 %; снимки цен не строятся."""
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    def convert_price(amount, from_currency, to_currency, apply_margin=True):
        amount = Decimal(str(amount))
        converted = amount if from_currency == to_currency else amount * Decimal("2")
        with_margin = converted * (Decimal("1.10") if apply_margin else Decimal("1"))
        return amount, converted, with_margin.quantize(Decimal("0.01"))

    monkeypatch.setattr(currency_converter, "convert_price", convert_price)
    monkeypatch.setattr(currency_converter, "get_margin_rate", lambda *args: Decimal("10"))


@pytest.fixture
def category(converter):
    return Category.objects.create(name="Scaled", slug="scaled", margin_percent=Decimal("15"))


def make_product(category, price="100", slug="scaled-product", **extra):
    return Product.objects.create(
        name="Scaled product",
        slug=slug,
        product_type="accessories",
        category=category,
        price=Decimal(price),
        currency="TRY",
        is_active=True,
        is_available=True,
        **extra,
    )


def rub_request():
    return APIRequestFactory().get("/", HTTP_X_CURRENCY="RUB")


def card_price(product, currency="RUB"):
    request = APIRequestFactory().get("/", HTTP_X_CURRENCY=currency)
    return ProductCardSerializer(product, context={"request": request}).data["price"]


def cart_price(product):
    cart = Cart.objects.create(session_key=f"scale-cart-{product.pk}", currency="RUB")
    CartItem.objects.create(
        cart=cart, product=product, quantity=1, price=Decimal("100"), currency="TRY"
    )
    return CartSerializer(cart, context={"request": rub_request()}).data["items"][0]["price"]


@pytest.mark.django_db
def test_scale_that_is_not_selected_changes_no_price(category):
    product = make_product(category)
    # 100 лир × курс 2 × валютная наценка 10 % × наценка категории 15 %
    expected = Decimal("253.00")
    assert card_price(product) == expected

    make_scale()
    product = Product.objects.get(pk=product.pk)

    assert card_price(product) == expected
    assert cart_price(product) == expected
    assert _get_product_price_for_currency(product, "RUB") == expected
    assert get_effective_product_markup(product) == (Decimal("15.00"), "category")


@pytest.mark.django_db
def test_category_scale_gives_one_price_everywhere(category):
    category.markup_scale = make_scale()
    category.save()
    product = make_product(category)
    request = rub_request()
    expected = Decimal("440.00")  # 100 лир × 2 × 1,10 × ступень 100 %

    assert ProductSerializer(product, context={"request": request}).data["price"] == expected
    assert card_price(product) == expected
    assert serialize_product_for_card(product, request)["price"] == expected
    assert cart_price(product) == expected
    assert _get_product_price_for_currency(product, "RUB") == expected
    assert _MarkupResolver().price_with_markup(Decimal("220"), product) == expected
    assert get_effective_product_markup(product) == (Decimal("100"), "category")


@pytest.mark.django_db
def test_dearer_source_price_is_not_cheaper_for_customer(category):
    category.markup_scale = make_scale()
    category.save()
    below = make_product(category, price="4990", slug="below-threshold")
    above = make_product(category, price="5010", slug="above-threshold")

    # в лирах: 4 990 × 1,10 × 2 и 5 010 × 1,10 × (10 000 / 5 010); без планки было бы 8 266,50
    assert card_price(below, "TRY") == Decimal("10978.00")
    assert card_price(above, "TRY") == Decimal("11000.00")


@pytest.mark.django_db
def test_scale_is_inherited_and_brand_percent_is_stronger(category):
    category.markup_scale = make_scale()
    category.save()
    child = Category.objects.create(name="Scaled child", slug="scaled-child", parent=category)
    own_percent = Category.objects.create(
        name="Own percent", slug="own-percent", parent=category, margin_percent=Decimal("40")
    )
    brand = Brand.objects.create(name="Scale brand", slug="scale-brand", margin_percent=Decimal("30"))

    assert get_effective_product_markup(make_product(child, slug="in-child")) == (Decimal("100"), "category")
    assert get_effective_product_markup(make_product(own_percent, slug="own")) == (Decimal("40.00"), "category")
    assert get_effective_product_markup(
        make_product(child, slug="branded", brand=brand)
    ) == (Decimal("30.00"), "brand")


@pytest.mark.django_db
def test_global_scale_skips_medicines_and_services(converter):
    settings = GlobalCurrencySettings.load()
    settings.default_margin_percentage = Decimal("15")
    settings.markup_scale = make_scale()
    settings.save()

    def item(product_type):
        return SimpleNamespace(
            brand=None, category=None, price=Decimal("100"), currency="TRY", product_type=product_type
        )

    assert get_effective_product_markup(item("shoes")) == (Decimal("100"), "global")
    assert get_effective_product_markup(item("medicines")) == (Decimal("15.00"), "global")
    assert get_effective_product_markup(item("service")) == (Decimal("15.00"), "global")
    # без цены источника шкала неприменима — действует процент
    no_price = item("shoes")
    no_price.price = None
    assert get_effective_product_markup(no_price) == (Decimal("15.00"), "global")

    settings.markup_scale = None
    settings.save()
    assert get_effective_product_markup(item("shoes")) == (Decimal("15.00"), "global")


@pytest.mark.django_db
def test_source_price_in_other_currency_is_compared_in_lira(category):
    category.markup_scale = make_scale()
    category.save()
    product = make_product(category)

    # 3 000 «рублей» по курсу заглушки — 6 000 лир: вторая ступень с нижней планкой 10 000
    result = explain_product_markup(product, Decimal("3000"), "RUB")
    assert result.scale.step_percent == Decimal("50")
    assert result.scale.floor_applied is True
    assert apply_product_markup(Decimal("100"), product, Decimal("4000"), "RUB") == Decimal("150.00")


@pytest.mark.django_db
def test_each_variant_gets_markup_by_its_own_source_price(category):
    category.markup_scale = make_scale()
    category.save()
    variants = [SimpleNamespace(pk=1, price=Decimal("8000"), currency="TRY")]
    obj = SimpleNamespace(
        brand=None,
        category=category,
        price=Decimal("1000"),
        currency="TRY",
        product_type="clothing",
        variants=SimpleNamespace(all=lambda: variants),
    )
    payload = {
        "price": Decimal("1000"),
        "old_price": Decimal("1500"),
        "price_formatted": "1000 TRY",
        "active_variant_price": "8000 TRY",
        "variants": [
            {"id": 1, "price": Decimal("8000"), "old_price": Decimal("9000"), "price_formatted": "8000 TRY"},
            {"id": 404, "price": Decimal("1000")},
        ],
    }

    data = apply_product_markup_to_payload(
        payload, obj, active_base=lambda: (Decimal("8000"), "TRY")
    )

    assert data["price"] == Decimal("2000.00")
    assert data["old_price"] == Decimal("3000.00")  # тот же процент, что у текущей цены
    assert data["price_formatted"] == "2000.00 TRY"
    assert data["active_variant_price"] == "12000.00 TRY"
    assert data["variants"][0]["price"] == Decimal("12000.00")
    assert data["variants"][0]["old_price"] == Decimal("13500.00")
    assert data["variants"][0]["price_formatted"] == "12000.00 TRY"
    assert data["variants"][1]["price"] == Decimal("2000.00")  # вариант не найден — процент товара
    assert data["product_markup_percent"] == Decimal("100.00")
    assert data["product_markup_source"] == "category"


@pytest.mark.django_db
def test_existing_order_keeps_its_price_after_scale_is_enabled(category):
    product = make_product(category)
    order = Order.objects.create(
        number="SCALE-SNAPSHOT",
        subtotal_amount=Decimal("253.00"),
        total_amount=Decimal("253.00"),
        currency="RUB",
        contact_name="Customer",
        contact_phone="+900000000000",
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        price=Decimal("253.00"),
        quantity=1,
        total=Decimal("253.00"),
    )

    category.markup_scale = make_scale()
    category.save()

    receipt = build_order_receipt_payload(order)
    assert receipt["items"][0]["price"] == Decimal("253.00")
    assert receipt["totals"]["total"] == Decimal("253.00")
    assert card_price(Product.objects.get(pk=product.pk)) == Decimal("440.00")


@pytest.mark.django_db
def test_editing_scale_is_visible_at_once_and_used_scale_cannot_be_deleted(category):
    scale = make_scale()
    category.markup_scale = scale
    category.save()
    product = make_product(category)
    assert card_price(product) == Decimal("440.00")

    step = scale.steps.get(price_from=0)
    step.percent = Decimal("50")
    step.save()
    assert card_price(Product.objects.get(pk=product.pk)) == Decimal("330.00")

    with pytest.raises(ProtectedError):
        scale.delete()


@pytest.mark.django_db
def test_price_admin_explains_where_markup_came_from(category):
    category.markup_scale = make_scale()
    category.save()
    product = make_product(category)
    price_admin = admin.site._registry[ProductPrice]

    def row(base_price):
        return SimpleNamespace(
            product=product, base_currency="TRY", base_price=Decimal(base_price),
            try_price=Decimal(base_price), rub_price=None,
        )

    assert price_admin.effective_product_markup_display(row("8000")) == (
        "50% — шкала «Общая» (категория), ступень от 5000 лир: 50%, процент ступени"
    )
    assert price_admin.effective_product_markup_display(row("6000")) == (
        "66.67% — шкала «Общая» (категория), ступень от 5000 лир: 50%, "
        "сработало правило «не дешевле предыдущей ступени»"
    )
    # цена в админке — по цене источника строки, а не товара: 6 000 × 1,10 → не дешевле 10 000 × 1,10
    assert price_admin.public_try_price(row("6000")) == Decimal("11000.00")
