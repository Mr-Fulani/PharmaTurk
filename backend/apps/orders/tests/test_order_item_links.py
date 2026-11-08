"""Позиции заказа в админке: превью товара и ссылки «На сайте / В источнике / В админке»."""

from decimal import Decimal
from itertools import count

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Product, ProductImage
from apps.orders.admin import OrderItemAdmin, OrderItemInline
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
