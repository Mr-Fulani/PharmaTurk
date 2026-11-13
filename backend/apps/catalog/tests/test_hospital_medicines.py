"""Больничные препараты (docs/HOSPITAL_MEDICINES.md): справочная карточка «Больничный препарат · цена по запросу»."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, MedicineProduct, Product
from apps.catalog.services.catalog_sort_rank import recompute_sort_ranks
from apps.recommendations.selectors import public_recommendation_products

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_currency_refresh(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


def _medicine(slug, *, is_hospital=False, **extra):
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    medicine = MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, active_ingredient="Sodium chloride",
        atc_code="B05XA03", price=Decimal("120"), old_price=Decimal("150"), currency="TRY",
        is_active=True, is_hospital=is_hospital, **extra,
    )
    medicine.refresh_from_db()
    return medicine


def test_api_shows_hospital_medicine_without_price():
    _medicine("izotonik", is_hospital=True)
    _medicine("parol")
    client = APIClient()

    detail = client.get("/api/catalog/medicines/products/izotonik").json()
    assert detail["is_hospital"] is True
    assert detail["price"] is None and detail["price_formatted"] is None
    assert detail["old_price"] is None and detail["old_price_formatted"] is None
    regular = client.get("/api/catalog/medicines/products/parol").json()
    assert regular["price"] is not None and not regular.get("is_hospital")

    cards = {row["slug"]: row for row in client.get("/api/catalog/medicines/products", {"view": "card"}).json()["results"]}
    assert cards["izotonik"]["is_hospital"] is True and cards["izotonik"].get("price") is None
    assert cards["parol"].get("price") is not None and "is_hospital" not in cards["parol"]

    search = {row["slug"]: row for row in client.get("/api/catalog/products", {"search": "o", "view": "card"}).json()["results"]}
    assert search["izotonik"]["is_hospital"] is True and search["izotonik"].get("price") is None
    assert search["parol"].get("price") is not None

    analogs = {row["slug"]: row for row in client.get("/api/catalog/medicines/products/parol/analogs").json()["results"]}
    assert analogs["izotonik"]["is_hospital"] is True
    assert analogs["izotonik"]["price"] is None and analogs["izotonik"]["original_price"] is None

    assert client.post("/api/catalog/medicines/products/izotonik/market-check").status_code == 404


def test_hospital_medicine_in_sitemap_but_not_featured_or_recommended():
    hospital = _medicine("izotonik", is_hospital=True, is_featured=True)
    regular = _medicine("parol", is_featured=True)

    featured = {row["slug"] for row in APIClient().get("/api/catalog/products/featured", {"limit": 20}).json()}
    assert "parol" in featured and "izotonik" not in featured

    recommended = set(public_recommendation_products().values_list("id", flat=True))
    assert regular.base_product_id in recommended and hospital.base_product_id not in recommended

    sitemap = APIClient().get("/api/catalog/sitemap-products", {"domain": "medicines"}).json()["results"]
    assert {"izotonik", "parol"} <= {row["slug"] for row in sitemap}


def test_hospital_medicine_ranks_with_priceless_in_section():
    hospital = _medicine("izotonik", is_hospital=True)
    regular = _medicine("parol")
    recompute_sort_ranks(MedicineProduct)
    hospital.refresh_from_db()
    regular.refresh_from_db()
    assert regular.sort_rank > hospital.sort_rank


def test_request_list_has_hospital_item_without_sum():
    from apps.orders.models import Cart, CartItem
    from apps.orders.serializers import CartItemSerializer, CartSerializer

    hospital = _medicine("izotonik", is_hospital=True)
    regular = _medicine("parol")
    client = APIClient()

    cart_data = client.post(
        "/api/orders/cart/add/", {"product_id": hospital.base_product_id, "product_type": "medicines", "quantity": 2},
        format="json",
    ).json()
    item = cart_data["items"][0]
    assert item["price_on_request"] is True and item["product_is_hospital"] is True
    assert Decimal(str(item["price"])) == 0 and Decimal(str(item["total"])) == 0
    assert Decimal(str(cart_data["total_amount"])) == 0
    assert CartItem.objects.get().price == 0

    cart = Cart.objects.create(session_key="s-hosp")
    CartItem.objects.create(cart=cart, product=hospital.base_product, quantity=1, price=Decimal("999"))
    CartItem.objects.create(cart=cart, product=regular.base_product, quantity=1, price=Decimal("1"))
    rows = {row["product"]: row for row in CartSerializer(cart, context={}).data["items"]}
    assert rows[hospital.base_product_id]["price_on_request"] is True
    assert not rows[regular.base_product_id]["price_on_request"]
    total = CartSerializer(cart, context={}).get_total_amount(cart)
    assert Decimal(str(total)) == Decimal(str(rows[regular.base_product_id]["price"]))
    assert CartItemSerializer(context={}).get_price(cart.items.get(product=hospital.base_product)) == 0


def test_receipt_shows_price_on_request_instead_of_zero():
    from apps.orders.models import Order, OrderItem
    from apps.orders.services import render_receipt_html

    hospital = _medicine("izotonik", is_hospital=True)
    order = Order.objects.create(
        number="REQ-HOSP", subtotal_amount=Decimal("0"), total_amount=Decimal("0"), currency="RUB",
        contact_name="Customer", contact_phone="+900000000000",
    )
    OrderItem.objects.create(
        order=order, product=hospital.base_product, product_name="IZOTONIK", price=Decimal("0"),
        quantity=1, total=Decimal("0"),
    )
    html = render_receipt_html(order)
    assert "по запросу" in html
    assert "on request" in render_receipt_html(order, locale="en")
