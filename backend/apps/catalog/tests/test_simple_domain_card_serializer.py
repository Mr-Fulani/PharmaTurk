from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.catalog import serializers as catalog_serializers
from apps.catalog.serializers import (
    MedicineProductSerializer,
    ProductCardSerializer,
    ProductSerializer,
    SimpleDomainCardSerializer,
)
from apps.catalog.views import MedicineProductViewSet, ProductViewSet


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _MedicineCard(SimpleNamespace):
    _domain_product_type = "medicines"


def test_simple_domain_card_serializer_builds_only_the_card_contract(monkeypatch):
    price_calls = []

    def public_price(amount, currency, request):
        price_calls.append(amount)
        return (Decimal(str(amount)) * 2 if amount is not None else None), "RUB"

    monkeypatch.setattr(catalog_serializers, "_public_price", public_price)
    monkeypatch.setattr(
        catalog_serializers,
        "_effective_product_markup",
        lambda product: (Decimal("0"), None),
    )

    image = SimpleNamespace(
        pk=11,
        image_file=None,
        image_url="https://cdn.example/card.webp",
        video_url="",
        video_file=None,
        alt_text="Medicine package",
        sort_order=2,
        is_main=True,
    )
    translation = SimpleNamespace(
        locale="ru",
        name="Карточка",
        description="Короткое описание",
    )
    product = _MedicineCard(
        pk=7,
        base_product_id=70,
        name="Card product",
        slug="card-product",
        description="Description",
        price=Decimal("100"),
        old_price=Decimal("130"),
        currency="TRY",
        main_image_file=None,
        main_image="",
        gallery_images=_Rows([image]),
        images=_Rows([]),
        translations=_Rows([translation]),
        base_product=None,
        brand_id=9,
        brand=None,
        category=None,
        is_available=True,
        is_featured=False,
        is_new=True,
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
    )
    data = SimpleDomainCardSerializer(product).data

    assert price_calls == [Decimal("100"), Decimal("130")]
    assert data["price"] == Decimal("200")
    assert data["price_formatted"] == "200 RUB"
    assert data["old_price_formatted"] == "260 RUB"
    assert data["brand_id"] == 9
    assert data["product_type"] == "medicines"
    assert data["main_image_url"] == "https://cdn.example/card.webp"
    assert data["images"] == [{
        "id": 11,
        "image_url": "https://cdn.example/card.webp",
        "alt_text": "Medicine package",
        "sort_order": 2,
        "is_main": True,
    }]
    assert data["translations"] == [{
        "locale": "ru",
        "name": "Карточка",
        "description": "Короткое описание",
    }]
    assert "category" not in data
    assert "brand" not in data
    assert "dynamic_attributes" not in data
    assert "meta_title" not in data
    assert "usage_instructions" not in data


def test_medicine_view_uses_lean_serializer_only_for_card_lists():
    view = MedicineProductViewSet()
    view.request = Request(APIRequestFactory().get("/", {"view": "card"}))
    view.action = "list"
    assert view.get_serializer_class() is SimpleDomainCardSerializer

    view.action = "retrieve"
    assert view.get_serializer_class() is MedicineProductSerializer


def test_generic_product_card_serializer_drops_expensive_detail_calculations():
    fields = set(ProductCardSerializer().fields)

    assert {
        "id", "name", "slug", "price", "currency", "images", "translations",
        "brand_id", "rating", "reviews_count",
    }.issubset(fields)
    assert fields.isdisjoint({
        "category", "brand", "dynamic_attributes", "meta_title",
        "prices_in_currencies", "price_breakdown", "converted_price_rub",
        "converted_price_usd", "final_price_rub", "final_price_usd",
    })


def test_generic_product_view_uses_card_serializer_only_when_requested():
    view = ProductViewSet()
    view.request = Request(APIRequestFactory().get("/", {"view": "card"}))
    view.action = "list"
    assert view.get_serializer_class() is ProductCardSerializer

    view.request = Request(APIRequestFactory().get("/"))
    assert view.get_serializer_class() is ProductSerializer


def test_generic_product_queryset_prefetches_authors_through_book_domain():
    view = ProductViewSet()
    view.request = Request(APIRequestFactory().get("/", {"view": "card"}))
    view.action = "list"

    queryset = view.get_queryset()

    assert "book_item__book_authors__author" in queryset._prefetch_related_lookups
    assert "book_authors__author" not in queryset._prefetch_related_lookups
