"""Ссылки в уведомлении менеджеру о заявке: заявка в админке, у позиции — админка, сайт, источник."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.catalog.models import MedicineProduct, Product, ProductSourceOffer, SupplementProduct
from apps.orders.models import Order, OrderItem, SourcingRequest
from apps.orders.tasks import (
    TELEGRAM_CUT_NOTICE,
    TELEGRAM_MESSAGE_LIMIT,
    _order_item_links,
    _tg_length,
    notify_new_order_telegram,
    notify_sourcing_request_telegram,
)

ADMIN = "https://site.test"
SITE = "https://shop.test"


@pytest.fixture(autouse=True)
def telegram_settings(settings):
    settings.TELEGRAM_BOT_TOKEN = "test-token"
    settings.TELEGRAM_CHAT_ID = "admin-chat"
    settings.TELEGRAM_ORDERS_CHAT_ID = ""
    settings.SITE_URL = ADMIN
    settings.FRONTEND_SITE_URL = SITE


def _product(**kwargs):
    kwargs.setdefault("slug", f"tovar-{uuid4().hex}")
    kwargs.setdefault("product_type", "accessories")
    kwargs.setdefault("name", "Товар")
    return Product.objects.create(price=Decimal("10"), currency="TRY", **kwargs)


def _order(*products, comment="", source_url=""):
    order = Order.objects.create(
        number=f"REQ{uuid4().hex[:10]}", total_amount=Decimal("100"), currency="RUB",
        contact_name="Клиент", contact_phone="+79990001122", payment_method="manager", comment=comment,
    )
    for product in products:
        OrderItem.objects.create(
            order=order, product=product, product_name=product.name, price=Decimal("100"),
            quantity=1, total=Decimal("100"), source_url=source_url,
        )
    return order


def _send(order):
    with (
        patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=None),
        patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None)),
        patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(status_code=200, ok=True)) as post,
    ):
        # Готовый итог проверки лекарств: без него задача пошла бы к источникам по сети
        notify_new_order_telegram.run(order_id=order.id, drug_checks={})
    return [call.kwargs["json"]["text"] for call in post.call_args_list]


def _link(url, label):
    return f'<a href="{url}">{label}</a>'


@pytest.mark.django_db
def test_supplement_gets_order_link_and_item_links():
    slug = f"cacicol-{uuid4().hex}"
    supplement = SupplementProduct.objects.create(
        name="CACICOL", slug=slug, external_url="https://www.ilacfiyati.com/bad/cacicol?a=1&b=2"
    )
    supplement.refresh_from_db()
    order = _order(supplement.base_product)

    (text,) = _send(order)

    header, _buyer, _title, item = text.split("\n\n")[:4]
    assert header == (
        f"📝 <b>Новая заявка</b> <code>{order.number}</code>\n"
        + _link(ADMIN + reverse("admin:orders_order_change", args=[order.pk]), "Открыть заявку в админке")
    )
    assert item == (
        "1. <b>CACICOL</b>\n1 шт. · 100.00 RUB\n🔗 "
        + _link(ADMIN + reverse("admin:catalog_supplementproduct_change", args=[supplement.pk]), "В админке")
        + " · " + _link(f"{SITE}/product/{slug}", "На сайте")
        + " · " + _link("https://www.ilacfiyati.com/bad/cacicol?a=1&amp;b=2", "Источник")
    )


@pytest.mark.django_db
def test_medicine_keeps_check_line_and_gets_links():
    slug = f"parol-{uuid4().hex}"
    medicine = MedicineProduct.objects.create(name="PAROL", slug=slug, external_url="https://ilacfiyati.com/ilaclar/parol")
    medicine.refresh_from_db()

    (text,) = _send(_order(medicine.base_product))

    lines = text.split("\n\n")[3].split("\n")
    assert lines[-2].startswith("🔎 <a href=")
    assert lines[-1] == (
        "🔗 "
        + _link(ADMIN + reverse("admin:catalog_medicineproduct_change", args=[medicine.pk]), "В админке")
        + " · " + _link(f"{SITE}/product/{slug}", "На сайте")
        + " · " + _link("https://ilacfiyati.com/ilaclar/parol", "Источник")
    )


@pytest.mark.django_db
def test_product_without_source_and_hidden_product():
    plain = _product(name="Без источника")
    hidden = _product(name="Скрытый", is_active=False, external_url="https://www.flo.com.tr/urun/a")

    (text,) = _send(_order(plain, hidden))

    first, second = text.split("\n\n")[3:5]
    assert first.split("\n")[-1] == (
        "🔗 " + _link(ADMIN + reverse("admin:catalog_product_change", args=[plain.pk]), "В админке")
        + " · " + _link(f"{SITE}/product/{plain.slug}", "На сайте")
    )
    assert second.split("\n")[-1] == (
        "🔗 " + _link(ADMIN + reverse("admin:catalog_product_change", args=[hidden.pk]), "В админке")
        + " · " + _link("https://www.flo.com.tr/urun/a", "Источник")
    )


@pytest.mark.django_db
def test_source_is_checkout_link_then_product_link_then_first_offer():
    with_offers = _product()
    for path in ("b", "a"):
        ProductSourceOffer.objects.create(
            product=with_offers, parser_key="flo", canonical_url=f"https://www.flo.com.tr/urun/{path}",
            variant_key=path, size_key=path,
        )
    with_link = _product(external_url="https://www.zara.com/tr/x")
    order = _order(with_offers, with_link)
    OrderItem.objects.filter(order=order, product=with_link).update(source_url="https://www.zara.com/tr/x?v1=7")

    lines = _order_item_links(list(order.items.all()))

    assert _link("https://www.flo.com.tr/urun/a", "Источник") in lines[0]
    assert _link("https://www.zara.com/tr/x?v1=7", "Источник") in lines[1]


@pytest.mark.django_db
def test_ordered_colour_opens_the_card_by_variant_slug():
    colour = _product(
        product_type="shoes", slug=f"shoes-{uuid4().hex}", external_data={"source_variant_slug": "krossovki-belye"}
    )

    (line,) = _order_item_links(list(_order(colour).items.all()))

    assert _link(f"{SITE}/product/shoes/krossovki-belye", "На сайте") in line


@pytest.mark.django_db
def test_item_without_product_has_no_links():
    order = _order(_product())
    OrderItem.objects.filter(order=order).update(product=None)

    (text,) = _send(order)

    assert "🔗" not in text
    assert "Открыть заявку в админке" in text


@pytest.mark.django_db
def test_queries_do_not_grow_with_items():
    def supplement():
        record = SupplementProduct.objects.create(name="БАД", slug=f"bad-{uuid4().hex}")
        record.refresh_from_db()
        return record.base_product

    def queries(order):
        items = list(order.items.all())
        with CaptureQueriesContext(connection) as captured:
            lines = _order_item_links(items)
        assert all("В админке" in line for line in lines)
        return len(captured)

    one = queries(_order(supplement()))
    many = queries(_order(*(supplement() for _ in range(6))))

    assert many == one <= 3


@pytest.mark.django_db
def test_long_order_keeps_links_and_closed_tags_in_every_part():
    products = [_product(name=f"Товар {index}", external_url=f"https://www.flo.com.tr/urun/{index}") for index in range(20)]

    texts = _send(_order(*products, comment="слово " * 1000))

    assert len(texts) > 1
    assert sum(text.count("🔗") for text in texts) == 20
    for text in texts:
        assert _tg_length(text) <= TELEGRAM_MESSAGE_LIMIT
        assert text.count("<a ") == text.count("</a>")


@pytest.mark.django_db
def test_item_links_are_dropped_before_the_order_text_is_cut():
    products = [_product(name=f"Товар {index}", external_url=f"https://www.flo.com.tr/urun/{index}") for index in range(40)]
    words = [f"слово{index}" for index in range(1650)]
    order = _order(*products, comment=" ".join(words))

    texts = _send(order)

    joined = " ".join(texts)
    assert "🔗" not in joined
    assert "Открыть заявку в админке" in texts[0]
    # Без строк ссылок заявка помещается целиком
    assert TELEGRAM_CUT_NOTICE not in joined
    assert words[-1] in joined
    assert "40. <b>Товар 39</b>" in joined


@pytest.mark.django_db
def test_sourcing_request_links_to_the_request_in_admin():
    request = SourcingRequest.objects.create(
        source_url="https://example.com/item_1", contact_name="Анна", contact_phone="+79990001122",
        contact_channel="whatsapp",
    )
    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(ok=True, status_code=200)) as post:
        notify_sourcing_request_telegram.run(request.pk)

    assert post.call_args.kwargs["json"]["text"].startswith(
        f"🔎 <b>Новая заявка на поиск товара</b> <code>{request.pk}</code>\n"
        + _link(ADMIN + reverse("admin:orders_sourcingrequest_change", args=[request.pk]), "Открыть заявку в админке")
    )
