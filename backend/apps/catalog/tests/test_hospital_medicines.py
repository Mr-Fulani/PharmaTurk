"""Больничные препараты (docs/HOSPITAL_MEDICINES.md): с ценой — как обычное лекарство, без цены — «цена по запросу»."""

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


def _medicine(slug, *, is_hospital=False, price=Decimal("120"), **extra):
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    medicine = MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, active_ingredient="Sodium chloride",
        atc_code="B05XA03", price=price, old_price=Decimal("150") if price else None, currency="TRY",
        is_active=True, is_hospital=is_hospital, **extra,
    )
    medicine.refresh_from_db()
    return medicine


def test_api_shows_hospital_medicine_with_price_like_any_other():
    """Цену не скрываем (19.11.2026): у больничного с ценой она видна везде, отметка — справочная."""
    _medicine("izotonik", is_hospital=True)
    _medicine("parol")
    client = APIClient()

    detail = client.get("/api/catalog/medicines/products/izotonik").json()
    regular = client.get("/api/catalog/medicines/products/parol").json()
    assert detail["is_hospital"] is True and not regular.get("is_hospital")
    for field in ("price", "price_formatted", "old_price", "old_price_formatted"):
        assert detail[field] is not None and detail[field] == regular[field]

    cards = {row["slug"]: row for row in client.get("/api/catalog/medicines/products", {"view": "card"}).json()["results"]}
    assert cards["izotonik"]["is_hospital"] is True and "is_hospital" not in cards["parol"]
    assert cards["izotonik"]["price"] is not None and cards["izotonik"]["price"] == cards["parol"]["price"]

    search = {row["slug"]: row for row in client.get("/api/catalog/products", {"search": "o", "view": "card"}).json()["results"]}
    assert search["izotonik"]["is_hospital"] is True
    assert search["izotonik"]["price"] is not None and search["izotonik"]["price"] == search["parol"]["price"]

    analogs = {row["slug"]: row for row in client.get("/api/catalog/medicines/products/parol/analogs").json()["results"]}
    assert analogs["izotonik"]["is_hospital"] is True
    assert analogs["izotonik"]["price"] and analogs["izotonik"]["original_price"] == 120


def test_api_shows_hospital_medicine_without_price_on_request():
    _medicine("izotonik", is_hospital=True, price=None)
    _medicine("parol")
    client = APIClient()

    detail = client.get("/api/catalog/medicines/products/izotonik").json()
    assert detail["is_hospital"] is True
    assert detail["price"] is None and detail["price_formatted"] is None

    cards = {row["slug"]: row for row in client.get("/api/catalog/medicines/products", {"view": "card"}).json()["results"]}
    assert cards["izotonik"]["is_hospital"] is True and cards["izotonik"].get("price") is None

    analogs = {row["slug"]: row for row in client.get("/api/catalog/medicines/products/parol/analogs").json()["results"]}
    assert analogs["izotonik"]["is_hospital"] is True
    assert analogs["izotonik"]["price"] is None and analogs["izotonik"]["original_price"] is None

    assert client.post("/api/catalog/medicines/products/izotonik/market-check").status_code == 404


def test_hospital_medicine_featured_and_recommended_only_with_price():
    priced = _medicine("izotonik", is_hospital=True, is_featured=True)
    priceless = _medicine("ringer", is_hospital=True, is_featured=True, price=None)
    regular = _medicine("parol", is_featured=True)

    featured = {row["slug"] for row in APIClient().get("/api/catalog/products/medicine-reference", {"limit": 20}).json()}
    assert {"parol", "izotonik"} <= featured and "ringer" not in featured

    recommended = set(public_recommendation_products().values_list("id", flat=True))
    assert {regular.base_product_id, priced.base_product_id} <= recommended
    assert priceless.base_product_id not in recommended

    sitemap = APIClient().get("/api/catalog/sitemap-products", {"domain": "medicines"}).json()["results"]
    assert {"izotonik", "ringer", "parol"} <= {row["slug"] for row in sitemap}


def test_hospital_medicine_ranks_by_price_like_any_other():
    priced = _medicine("izotonik", is_hospital=True)
    priceless = _medicine("ringer", is_hospital=True, price=None)
    regular = _medicine("parol")
    recompute_sort_ranks(MedicineProduct)
    for medicine in (priced, priceless, regular):
        medicine.refresh_from_db()
    assert priced.sort_rank == regular.sort_rank > priceless.sort_rank


def test_request_list_counts_hospital_item_with_price():
    from apps.orders.models import CartItem

    hospital = _medicine("izotonik", is_hospital=True)

    cart_data = APIClient().post(
        "/api/orders/cart/add/", {"product_id": hospital.base_product_id, "product_type": "medicines", "quantity": 2},
        format="json",
    ).json()
    item = cart_data["items"][0]
    assert item["price_on_request"] is False and item["product_is_hospital"] is True
    assert Decimal(str(item["price"])) > 0
    assert Decimal(str(item["total"])) == Decimal(str(item["price"])) * 2
    assert Decimal(str(cart_data["total_amount"])) > 0
    assert CartItem.objects.get().price > 0


def test_request_list_has_priceless_hospital_item_without_sum():
    from apps.orders.models import Cart, CartItem
    from apps.orders.serializers import CartSerializer

    hospital = _medicine("izotonik", is_hospital=True, price=None)
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
    CartItem.objects.create(cart=cart, product=hospital.base_product, quantity=1, price=Decimal("0"))
    CartItem.objects.create(cart=cart, product=regular.base_product, quantity=1, price=Decimal("1"))
    rows = {row["product"]: row for row in CartSerializer(cart, context={}).data["items"]}
    assert rows[hospital.base_product_id]["price_on_request"] is True
    assert not rows[regular.base_product_id]["price_on_request"]
    total = CartSerializer(cart, context={}).get_total_amount(cart)
    assert Decimal(str(total)) == Decimal(str(rows[regular.base_product_id]["price"]))


def test_receipt_shows_price_on_request_instead_of_zero():
    from apps.orders.models import Order, OrderItem
    from apps.orders.services import render_receipt_html

    hospital = _medicine("izotonik", is_hospital=True, price=None)
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
