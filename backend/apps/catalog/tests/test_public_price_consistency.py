from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient, APIRequestFactory

from apps.catalog.models import Category, Favorite, Product
from apps.catalog.serializers import (
    FavoriteSerializer,
    ProductSerializer,
    serialize_product_for_card,
)
from apps.catalog.utils.currency_converter import currency_converter
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.orders.serializers import CartSerializer
from apps.orders.services import build_order_receipt_payload


@pytest.fixture
def public_product(monkeypatch):
    # Product.save() normally builds snapshots. Keeping them absent here proves
    # that every public surface calculates from the same current base price.
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)

    category = Category.objects.create(
        name="Public price",
        slug="public-price",
        margin_percent=Decimal("15"),
    )
    product = Product.objects.create(
        name="Consistent product",
        slug="consistent-product",
        product_type="accessories",
        category=category,
        price=Decimal("100"),
        currency="TRY",
        is_active=True,
        is_available=True,
        is_featured=True,
    )

    def convert_price(amount, from_currency, to_currency, apply_margin=True):
        amount = Decimal(str(amount))
        converted = amount if from_currency == to_currency else amount * Decimal("2")
        with_margin = converted * (Decimal("1.10") if apply_margin else Decimal("1"))
        return amount, converted, with_margin.quantize(Decimal("0.01"))

    monkeypatch.setattr(currency_converter, "convert_price", convert_price)
    monkeypatch.setattr(currency_converter, "get_margin_rate", lambda *args: Decimal("10"))
    monkeypatch.setattr(
        currency_converter,
        "get_price_breakdown",
        lambda *args: {
            "converted_price": Decimal("200"),
            "margin_rate": Decimal("10"),
            "final_price": Decimal("220"),
        },
    )
    return product


@pytest.mark.django_db
def test_cards_favorites_recommendations_and_featured_share_public_price(public_product):
    request = APIRequestFactory().get("/", HTTP_X_CURRENCY="RUB")
    expected = Decimal("253.00")  # 100 × rate 2 × pair margin 10% × category 15%

    assert ProductSerializer(public_product, context={"request": request}).data["price"] == expected
    assert serialize_product_for_card(public_product, request)["price"] == expected

    favorite = Favorite.objects.create(
        session_key="public-price-favorite",
        content_type=ContentType.objects.get_for_model(Product),
        object_id=public_product.pk,
    )
    favorite_data = FavoriteSerializer(
        favorite, context={"request": request}
    ).data["product"]
    assert favorite_data["price"] == expected

    response = APIClient().get(
        "/api/catalog/products/featured",
        {"limit": 20},
        HTTP_X_CURRENCY="RUB",
    )
    assert response.status_code == 200
    row = next(item for item in response.data if item["id"] == public_product.pk)
    assert row["price"] == expected


@pytest.mark.django_db
def test_cart_uses_public_price_but_receipt_keeps_order_price(public_product):
    request = APIRequestFactory().get("/", HTTP_X_CURRENCY="RUB")
    cart = Cart.objects.create(session_key="public-price-cart", currency="RUB")
    CartItem.objects.create(
        cart=cart,
        product=public_product,
        quantity=2,
        price=Decimal("100"),
        currency="TRY",
    )

    cart_data = CartSerializer(cart, context={"request": request}).data
    assert cart_data["items"][0]["price"] == Decimal("253.00")
    assert cart_data["items"][0]["total"] == Decimal("506.00")
    assert Decimal(str(cart_data["total_amount"])) == Decimal("506.00")

    order = Order.objects.create(
        number="PRICE-SNAPSHOT",
        subtotal_amount=Decimal("506.00"),
        total_amount=Decimal("506.00"),
        currency="RUB",
        contact_name="Customer",
        contact_phone="+900000000000",
    )
    OrderItem.objects.create(
        order=order,
        product=public_product,
        product_name=public_product.name,
        price=Decimal("253.00"),
        quantity=2,
        total=Decimal("506.00"),
    )

    public_product.category.margin_percent = Decimal("30")
    public_product.category.save(update_fields=["margin_percent"])

    receipt = build_order_receipt_payload(order)
    assert receipt["items"][0]["price"] == Decimal("253.00")
    assert receipt["items"][0]["total"] == Decimal("506.00")
    assert receipt["totals"]["total"] == Decimal("506.00")
