from types import SimpleNamespace
from decimal import Decimal

import pytest
from rest_framework import serializers

from apps.catalog import serializers as catalog_serializers
from apps.catalog.currency_models import GlobalCurrencySettings, MarginSettings
from apps.catalog.utils.currency_converter import currency_converter


class _Variants:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _MarginCardSerializer(catalog_serializers._SimpleDomainMixin, serializers.Serializer):
    id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    old_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    currency = serializers.CharField()
    price_formatted = serializers.CharField(required=False)
    old_price_formatted = serializers.CharField(required=False, allow_null=True)
    variants = serializers.SerializerMethodField()
    active_variant_price = serializers.CharField(required=False, allow_null=True)
    active_variant_currency = serializers.CharField(required=False, allow_null=True)
    active_variant_old_price_formatted = serializers.CharField(required=False, allow_null=True)

    def get_main_image_url(self, obj):
        return None

    def get_images(self, obj):
        return []

    def get_variants(self, obj):
        return [
            {
                "id": variant.pk,
                "price": variant.price,
                "old_price": variant.old_price,
                "currency": variant.currency,
                "price_formatted": f"{variant.price} {variant.currency}",
                "old_price_formatted": f"{variant.old_price} {variant.currency}",
            }
            for variant in obj.variants.all()
        ]

    def _get_active_variant(self, obj):
        rows = obj.variants.all()
        return rows[0] if rows else None


def test_simple_domain_payload_never_exposes_unmarked_variant_price(monkeypatch):
    monkeypatch.setattr(
        catalog_serializers,
        "_public_price",
        lambda amount, currency, request: (
            (amount * 2 if amount is not None else None),
            "RUB",
        ),
    )
    variant = SimpleNamespace(pk=7, price=120, old_price=150, currency="TRY")
    product = SimpleNamespace(
        id=1,
        price=100,
        old_price=130,
        currency="TRY",
        variants=_Variants([variant]),
    )

    data = _MarginCardSerializer(product).data

    assert data["price"] == 200
    assert data["price_formatted"] == "200 RUB"
    assert data["old_price_formatted"] == "260 RUB"
    assert data["active_variant_price"] == "240 RUB"
    assert data["active_variant_currency"] == "RUB"
    assert data["active_variant_old_price_formatted"] == "300 RUB"
    assert data["variants"][0]["price"] == 240
    assert data["variants"][0]["old_price"] == 300
    assert data["variants"][0]["currency"] == "RUB"


@pytest.mark.django_db
def test_saved_global_margin_is_visible_without_process_restart():
    MarginSettings.objects.filter(currency_pair="TRY-TRY").delete()
    settings = GlobalCurrencySettings.load()
    settings.default_margin_percentage = Decimal("10")
    settings.save()
    assert currency_converter.convert_price(100, "TRY", "TRY", True)[2] == Decimal("110")

    settings.default_margin_percentage = Decimal("30")
    settings.save()
    assert currency_converter.convert_price(100, "TRY", "TRY", True)[2] == Decimal("130")


def test_brand_markup_overrides_category_and_stacks_on_currency_margin(monkeypatch):
    monkeypatch.setattr(
        catalog_serializers,
        "_public_price",
        lambda amount, currency, request: (
            (Decimal(str(amount)) * Decimal("1.30") if amount is not None else None),
            "RUB",
        ),
    )
    product = SimpleNamespace(
        id=2,
        price=Decimal("100"),
        old_price=None,
        currency="TRY",
        brand=SimpleNamespace(margin_percent=Decimal("20")),
        category=SimpleNamespace(margin_percent=Decimal("10")),
        variants=_Variants([]),
    )

    data = _MarginCardSerializer(product).data

    # 100 + 30% валютной маржи = 130; затем +20% бренда = 156.
    assert data["price"] == Decimal("156.00")
    assert data["product_markup_percent"] == Decimal("20")
    assert data["product_markup_source"] == "brand"


def test_category_markup_is_used_when_brand_markup_is_zero(monkeypatch):
    monkeypatch.setattr(
        catalog_serializers,
        "_public_price",
        lambda amount, currency, request: (
            Decimal(str(amount)) if amount is not None else None,
            "RUB",
        ),
    )
    product = SimpleNamespace(
        id=3,
        price=Decimal("100"),
        old_price=None,
        currency="TRY",
        brand=SimpleNamespace(margin_percent=Decimal("0")),
        category=SimpleNamespace(margin_percent=Decimal("15")),
        variants=_Variants([]),
    )

    data = _MarginCardSerializer(product).data

    assert data["price"] == Decimal("115.00")
    assert data["product_markup_source"] == "category"
