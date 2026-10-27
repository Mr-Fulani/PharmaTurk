from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.test import APIRequestFactory

from apps.catalog.models import Category, ClothingProduct, ClothingVariant, ShoeProduct, ShoeVariant
from apps.catalog.serializers import ClothingVariantSerializer, ShoeVariantSerializer
from apps.catalog.utils.currency_converter import currency_converter


@pytest.fixture
def fake_rates(monkeypatch):
    def convert_price(amount, from_currency, to_currency, apply_margin=True):
        amount = Decimal(str(amount))
        converted = amount if from_currency == to_currency else amount * Decimal("2")
        with_margin = converted * (Decimal("1.10") if apply_margin else Decimal("1"))
        return amount, converted, with_margin.quantize(Decimal("0.01"))

    monkeypatch.setattr(currency_converter, "convert_price", convert_price)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "product_model, variant_model, serializer_class",
    [
        (ClothingProduct, ClothingVariant, ClothingVariantSerializer),
        (ShoeProduct, ShoeVariant, ShoeVariantSerializer),
    ],
    ids=["clothing", "shoes"],
)
def test_variant_old_price_uses_same_currency_as_price(fake_rates, product_model, variant_model, serializer_class):
    """Карточка FLO показывала «976 RUB» зачёркнутой под 1 442 RUB: old_price варианта оставался в лирах."""
    suffix = uuid4().hex[:8]
    category = Category.objects.create(name=f"Variants {suffix}", slug=f"variants-{suffix}")
    product = product_model.objects.create(
        name="Sandalet", slug=f"sandalet-{suffix}", category=category,
        price=Decimal("100"), currency="TRY", is_active=True,
    )
    variant = variant_model.objects.create(
        product=product, name="Sandalet - Kahverengi", color="Kahverengi",
        price=Decimal("100"), old_price=Decimal("120"), currency="TRY",
    )
    request = APIRequestFactory().get("/", HTTP_X_CURRENCY="RUB")

    data = serializer_class(variant, context={"request": request}).data

    assert data["currency"] == "RUB"
    assert Decimal(data["price"]) == Decimal("220.00")
    assert Decimal(data["old_price"]) == Decimal("264.00")
