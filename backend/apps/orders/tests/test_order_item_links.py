"""Удобства админки заказов: превью и ссылки позиций, состав в списке, связь с клиентом,
другие заявки клиента, подсветка «висит долго»."""

from datetime import timedelta
from decimal import Decimal
from itertools import count

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Product, ProductImage
from apps.orders.admin import OrderAdmin, OrderItemInline
from apps.orders.contacts import whatsapp_number
from apps.orders.models import Order, OrderItem
from apps.users.models import User

_seq = count(1)


@pytest.fixture(autouse=True)
def site(settings):
    settings.FRONTEND_SITE_URL = "https://mudaroba.com"


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def _product(product_type="medicines", **extra):
    n = next(_seq)
    data = dict(name=f"Товар {n}", slug=f"il-{n}-tovar", product_type=product_type, price=Decimal("100"), currency="RUB")
    data.update(extra)
    return Product.objects.create(**data)


def _item(product=None, **extra):
    n = next(_seq)
    order = Order.objects.create(
        number=f"IL{n:06d}", total_amount=Decimal("100"), currency="RUB",
        contact_name="Клиент", contact_phone="+79990001122", payment_method="manager",
    )
    data = dict(order=order, product=product, product_name="Товар", price=Decimal("100"), quantity=1, total=Decimal("100"))
    data.update(extra)
    return OrderItem.objects.create(**data)


def _inline():
    return OrderItemInline(Order, AdminSite())


@pytest.mark.django_db
def test_links_open_site_source_and_admin_in_new_tab():
    product = _product(external_url="https://www.ilacfiyati.com/old")
    item = _item(product, source_url="https://www.ilacfiyati.com/ilaclar/parol")

    html = str(_inline().item_links(item))

    assert f'href="https://mudaroba.com/product/{product.slug}"' in html
    assert 'href="https://www.ilacfiyati.com/ilaclar/parol"' in html  # снимок при оформлении важнее
    assert f'href="/admin/catalog/product/{product.pk}/change/"' in html
    assert html.count('target="_blank" rel="noopener noreferrer"') == 3
    assert "На сайте" in html and "В источнике" in html and "В админке" in html


@pytest.mark.django_db
def test_site_link_follows_frontend_path_for_typed_products():
    product = _product("shoes", slug="shoes-nike-air")
    html = str(_inline().item_links(_item(product)))
    assert 'href="https://mudaroba.com/product/shoes/nike-air"' in html


@pytest.mark.django_db
def test_old_item_without_snapshot_uses_product_link_and_skips_unsafe_urls():
    product = _product(external_url="https://www.flo.com.tr/urun/1")
    assert 'href="https://www.flo.com.tr/urun/1"' in str(_inline().item_links(_item(product)))

    bad = _item(_product(external_url=""), source_url="")
    bad.source_url = "javascript:alert(1)"
    assert "javascript" not in str(_inline().item_links(bad))


@pytest.mark.django_db
def test_deleted_product_shows_dash_without_error():
    item = _item(None, source_url="")
    inline = _inline()
    assert inline.item_preview(item) == "—"
    assert inline.item_links(item) == "—"
    assert inline.item_preview(None) == "—"
    assert inline.item_links(None) == "—"


@pytest.mark.django_db
def test_preview_uses_main_image_then_gallery():
    inline = _inline()
    with_main = _product(main_image="https://img.example.test/main.jpg")
    assert 'src="https://img.example.test/main.jpg"' in str(inline.item_preview(_item(with_main)))

    gallery = _product()
    ProductImage.objects.create(product=gallery, image_url="https://img.example.test/first.jpg", sort_order=0)
    ProductImage.objects.create(product=gallery, image_url="https://img.example.test/main2.jpg", sort_order=1, is_main=True)
    assert 'src="https://img.example.test/main2.jpg"' in str(inline.item_preview(_item(gallery)))

    assert inline.item_preview(_item(_product())) == "—"


@pytest.mark.django_db
def test_inline_has_no_query_per_item(rf):
    order = _item(_product()).order
    for _ in range(3):
        product = _product()
        ProductImage.objects.create(product=product, image_url="https://img.example.test/g.jpg")
        OrderItem.objects.create(order=order, product=product, product_name="Товар", price=Decimal("1"), quantity=1, total=Decimal("1"))
    request = rf.get("/")
    request.user = User(is_superuser=True, is_staff=True)
    inline = _inline()

    with CaptureQueriesContext(connection) as queries:
        rows = list(inline.get_queryset(request).filter(order=order))
        for row in rows:
            inline.item_preview(row)
            inline.item_links(row)

    assert len(rows) == 4
    assert len(queries) == 2  # позиции с товаром + фото галерей


@pytest.mark.django_db
def test_order_and_item_pages_show_links(client, plain_static):
    me = User.objects.create_user(username="il-admin", email="il@example.test", password="x", is_staff=True, is_superuser=True)
    product = _product(main_image="https://img.example.test/main.jpg")
    item = _item(product, source_url="https://www.superstep.com.tr/urun/1")
    client.force_login(me)

    for url in (
        f"/admin/orders/order/{item.order.pk}/change/",
        "/admin/orders/orderitem/",
        f"/admin/orders/orderitem/{item.pk}/change/",
    ):
        page = client.get(url)
        assert page.status_code == 200, url
        html = page.content.decode()
        assert f"https://mudaroba.com/product/{product.slug}" in html, url
        assert "https://www.superstep.com.tr/urun/1" in html, url
        assert "https://img.example.test/main.jpg" in html, url


@pytest.mark.django_db
def test_variant_item_links_to_variant_page_not_shadow_slug():
    """Расцветка в заказе — теневой Product «<тип>-<вариант>»; на сайте открывается вариант."""
    shadow = _product("furniture", slug="furniture-sofa-grey", external_data={"source_variant_slug": "sofa-grey"})
    html = str(_inline().item_links(_item(shadow)))
    assert 'href="https://mudaroba.com/product/sofa-grey"' in html

    jewelry = _product("jewelry", slug="ring-gold", external_data={"source_variant_slug": "ring-gold-17"})
    assert 'href="https://mudaroba.com/product/jewelry/ring-gold"' in str(_inline().item_links(_item(jewelry)))


# ─── Список и страница заказа: состав, связь, другие заявки, «висит долго» ────

PS = Order.ProcessingStatus


def _order(**extra):
    n = next(_seq)
    data = dict(
        number=f"IO{n:06d}", total_amount=Decimal("100"), currency="RUB",
        contact_name="Клиент", contact_phone="+79990001122", payment_method="manager",
    )
    data.update(extra)
    return Order.objects.create(**data)


def _order_admin():
    return OrderAdmin(Order, AdminSite())


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9122476866", "79122476866"),
        ("89122476866", "79122476866"),
        ("+7 (912) 247-68-66", "79122476866"),
        ("79122476866", "79122476866"),
        ("+90 532 123 45 67", "905321234567"),
        ("05321234567", ""),  # код страны неясен
        ("12345", ""),
        ("", ""),
    ],
)
def test_whatsapp_number_rules(raw, expected):
    assert whatsapp_number(raw) == expected


@pytest.mark.django_db
def test_contact_links_by_channel_and_fields():
    tg = _order(contact_channel="telegram", contact_username="@ivan_petrov", contact_phone="9122476866",
                contact_email="ivan@example.test")
    html = str(_order_admin().contact_links(tg))
    assert 'href="https://t.me/ivan_petrov" target="_blank" rel="noopener noreferrer" style="font-weight:700' in html
    assert 'href="https://wa.me/79122476866" target="_blank"' in html
    assert 'href="tel:+79122476866"' in html
    assert 'href="mailto:ivan@example.test"' in html

    unclear = _order(contact_channel="phone", contact_phone="0532 123 45 67", contact_email="x@mudaroba.local")
    html = str(_order_admin().contact_links(unclear))
    assert "wa.me" not in html and "t.me" not in html and "mailto:" not in html  # служебный email не показываем
    assert 'href="tel:05321234567"' in html

    wa_nick = _order(contact_channel="whatsapp", contact_username="+90 532 123 45 67", contact_phone="05321234567")
    assert 'href="https://wa.me/905321234567"' in str(_order_admin().contact_links(wa_nick))


@pytest.mark.django_db
def test_client_orders_count_link_and_filter(client, plain_static):
    me = User.objects.create_user(username="io-admin", email="io@example.test", password="x", is_staff=True, is_superuser=True)
    buyer = User.objects.create_user(username="io-buyer", email="buyer@example.test", password="x")
    current = _order(user=buyer, contact_phone="+7 912 247-68-66", contact_username="ivan_petrov",
                     contact_channel="telegram", contact_email="Ivan@Example.test")
    same = [
        _order(user=buyer, contact_phone="1111111111"),            # тот же пользователь
        _order(contact_phone="8 (912) 247 68 66"),                  # тот же номер в другом виде
        _order(contact_channel="telegram", contact_username="@IVAN_PETROV", contact_phone="1"),  # ник без регистра и @
        _order(contact_email="ivan@example.test", contact_phone="2"),
    ]
    _order(contact_phone="+7 999 000 11 22")  # чужая
    _order(contact_channel="whatsapp", contact_username="ivan_petrov", contact_phone="3")  # ник в другом канале

    html = str(_order_admin().client_orders_link(current))
    assert "У этого клиента ещё 4 заявки" in html
    assert f'href="/admin/orders/order/?client_of={current.pk}" target="_blank"' in html

    client.force_login(me)
    page = client.get(f"/admin/orders/order/?client_of={current.pk}")
    assert page.status_code == 200
    assert {o.pk for o in page.context["cl"].result_list} == {o.pk for o in same}

    alone = _order(contact_phone="5", contact_channel="", contact_username="")
    assert str(_order_admin().client_orders_link(alone)) == "Других заявок нет"

    # Заглушки вместо номера не склеивают чужих клиентов
    stub = _order(contact_phone="0000000000")
    _order(contact_phone="+0 000 000 0000")
    assert str(_order_admin().client_orders_link(stub)) == "Других заявок нет"

    # Неверный ?client_of не роняет список
    for bad in ("abc", "999999999"):
        assert client.get(f"/admin/orders/order/?client_of={bad}").status_code in (200, 302)


@pytest.mark.django_db
def test_stale_badge_for_old_new_and_quiet_in_progress():
    admin = _order_admin()
    old_new = _order()
    fresh_new = _order()
    quiet = _order(processing_status=PS.IN_PROGRESS)
    busy = _order(processing_status=PS.IN_PROGRESS)
    done = _order(processing_status=PS.DONE)
    Order.objects.filter(pk__in=[old_new.pk, done.pk]).update(created_at=timezone.now() - timedelta(hours=30))
    Order.objects.filter(pk__in=[quiet.pk, done.pk]).update(updated_at=timezone.now() - timedelta(days=4))
    rows = {o.pk: str(admin.processing_badge(o)) for o in Order.objects.all()}

    assert "висит 30 ч" in rows[old_new.pk]
    assert "висит 4 д" in rows[quiet.pk]
    for order in (fresh_new, busy, done):
        assert "висит" not in rows[order.pk]


@pytest.mark.django_db
def test_items_summary_shows_three_and_more_without_query_per_order(rf):
    for _ in range(3):
        order = _order()
        for i in range(5):
            product = _product(main_image=f"https://img.example.test/{i}.jpg")
            OrderItem.objects.create(order=order, product=product, product_name=f"Позиция {i}",
                                     price=Decimal("1"), quantity=i + 1, total=Decimal("1"))
    request = rf.get("/")
    request.user = User(is_superuser=True, is_staff=True)
    admin = _order_admin()

    with CaptureQueriesContext(connection) as queries:
        rows = [str(admin.items_summary(o)) for o in admin.get_queryset(request)]

    assert len(queries) == 3  # заказы + позиции с товаром + фото галерей
    html = rows[0]
    assert "Позиция 0 ×1" in html and "Позиция 2 ×3" in html and "Позиция 3" not in html
    assert "+2" in html
    assert 'src="https://img.example.test/0.jpg"' in html


@pytest.mark.django_db
def test_order_list_queries_do_not_grow_with_rows(client, plain_static):
    """Вся страница списка: число запросов не зависит от числа заявок (Состав, Ввоз, Связь)."""
    me = User.objects.create_user(username="io-n1", email="n1@example.test", password="x", is_staff=True, is_superuser=True)
    client.force_login(me)

    def add_orders(n):
        for _ in range(n):
            order = _order(contact_channel="telegram", contact_username="ivan_petrov")
            for _ in range(2):
                product = _product()
                ProductImage.objects.create(product=product, image_url="https://img.example.test/g.jpg")
                OrderItem.objects.create(order=order, product=product, product_name="Товар", price=Decimal("1"),
                                         quantity=1, total=Decimal("1"))

    def count_queries():
        with CaptureQueriesContext(connection) as queries:
            assert client.get("/admin/orders/order/").status_code == 200
        return len(queries)

    add_orders(2)
    few = count_queries()
    add_orders(5)
    assert count_queries() == few


@pytest.mark.django_db
def test_order_list_renders_new_columns(client, plain_static):
    me = User.objects.create_user(username="io-list", email="iol@example.test", password="x", is_staff=True, is_superuser=True)
    order = _order(contact_channel="telegram", contact_username="ivan_petrov")
    OrderItem.objects.create(order=order, product=_product(), product_name="Парацетамол", price=Decimal("1"),
                             quantity=2, total=Decimal("2"))
    client.force_login(me)
    html = client.get("/admin/orders/order/").content.decode()
    assert "Парацетамол ×2" in html
    assert "https://t.me/ivan_petrov" in html
    page = client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()
    assert "Других заявок нет" in page and "https://t.me/ivan_petrov" in page
