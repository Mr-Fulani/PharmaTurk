"""
Тесты единого resolve товара и зеркала canonical_path с frontend (urls.ts / product.ts).
Интеграционные тесты эндпоинта помечены django_db — в локали нужна доступная БД (Docker).
"""

import uuid
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from rest_framework import status

from apps.catalog.models import (
    AccessoryProduct,
    AutoPartProduct,
    AutoPartVariant,
    BookProduct,
    BookVariant,
    Brand,
    Category,
    GlobalAttributeKey,
    HeadwearProduct,
    HeadwearVariant,
    IslamicClothingProduct,
    IslamicClothingVariant,
    IncenseProduct,
    MedicalEquipmentProduct,
    MedicineProduct,
    PerfumeryProduct,
    ProductAttributeValue,
    PerfumeryVariant,
    SportsProduct,
    SportsVariant,
    SupplementProduct,
    TablewareProduct,
    UnderwearProduct,
    UnderwearVariant,
)
from django.contrib.contenttypes.models import ContentType
from apps.catalog.serializers import (
    AccessoryProductSerializer,
    AutoPartProductSerializer,
    AutoPartProductDetailSerializer,
    IncenseProductSerializer,
    MedicalEquipmentProductSerializer,
    MedicineProductSerializer,
    PerfumeryProductSerializer,
    SportsProductDetailSerializer,
    SportsProductSerializer,
    SupplementProductSerializer,
    TablewareProductSerializer,
)
from apps.catalog.services.product_resolve import (
    BASE_PRODUCT_TYPES,
    TYPES_NEEDING_PATH,
    build_canonical_path,
    build_resolve_response,
    deduplicate_slug,
    needs_type_in_path,
)


class TestDeduplicateSlug:
    def test_double_half(self):
        assert deduplicate_slug("foo-bar-foo-bar") == "foo-bar"

    def test_underscore_normalized(self):
        assert deduplicate_slug("a_b") == "a-b"


class TestCanonicalPath:
    def test_medicines_short(self):
        assert build_canonical_path("medicines", "x") == "/product/x"

    def test_clothing_strips_repeated_prefix(self):
        assert build_canonical_path("clothing", "clothing-shirt") == "/product/clothing/shirt"

    def test_uslugi_segment(self):
        assert build_canonical_path("uslugi", "svc") == "/product/uslugi/svc"

    def test_jewelry_long(self):
        assert build_canonical_path("jewelry", "ring") == "/product/jewelry/ring"

    def test_bags_base_short(self):
        assert build_canonical_path("bags", "my-bag") == "/product/my-bag"


class TestListsMatchFrontendProductTs:
    """Должно совпадать с frontend/src/lib/product.ts — при изменении обновить оба."""

    def test_types_needing_path(self):
        expected = frozenset(
            {
                "clothing",
                "shoes",
                "electronics",
                "jewelry",
                "uslugi",
                "headwear",
                "underwear",
                "islamic-clothing",
            }
        )
        assert TYPES_NEEDING_PATH == expected

    def test_base_product_types(self):
        expected = frozenset(
            {
                "medicines",
                "supplements",
                "medical-equipment",
                "furniture",
                "tableware",
                "accessories",
                "books",
                "perfumery",
                "sports",
                "auto-parts",
                "incense",
                "bags",
                "watches",
                "cosmetics",
                "toys",
                "home-textiles",
                "stationery",
                "pet-supplies",
            }
        )
        assert BASE_PRODUCT_TYPES == expected

    def test_base_disjoint_from_path_types(self):
        assert not (BASE_PRODUCT_TYPES & TYPES_NEEDING_PATH)

    def test_needs_type_in_path(self):
        assert needs_type_in_path("clothing") is True
        assert needs_type_in_path("medicines") is False
        assert needs_type_in_path("") is False


class TestBuildResolveResponse:
    def test_404_when_unresolved(self):
        req = RequestFactory().get("/")
        with patch(
            "apps.catalog.services.product_resolve.resolve_product_payload",
            return_value=None,
        ):
            resp = build_resolve_response(req, "nope")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_200_shape(self):
        req = RequestFactory().get("/")
        payload = {"id": 1, "slug": "item", "product_type": "medicines"}
        with patch(
            "apps.catalog.services.product_resolve.resolve_product_payload",
            return_value=(payload, "generic_product", "medicines"),
        ):
            resp = build_resolve_response(req, "item")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["product_type"] == "medicines"
        assert resp.data["canonical_path"] == "/product/item"
        assert resp.data["payload"] == payload
        assert resp.data["source"] == "generic_product"


@pytest.mark.django_db
def test_resolve_api_unknown_slug_404():
    """Полный путь API: без товара в БД — 404 (нужна PostgreSQL/SQLite из настроек)."""
    from rest_framework.test import APIClient

    client = APIClient()
    slug = f"___missing_resolve_{uuid.uuid4().hex}___"
    response = client.get(f"/api/catalog/products/resolve/{slug}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_perfumery_serializer_exposes_product_type_and_dynamic_attributes():
    category = Category.objects.create(name="Парфюмерия", slug=f"perfumery-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"LCW {uuid.uuid4().hex[:6]}", slug=f"lcw-{uuid.uuid4().hex[:8]}")
    product = PerfumeryProduct.objects.create(
        name="Parfum Test",
        slug=f"parfum-test-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=100,
        currency="TRY",
        gender="",
        is_active=True,
    )

    data = PerfumeryProductSerializer(product).data

    assert data["product_type"] == "perfumery"
    assert "dynamic_attributes" in data


@pytest.mark.django_db
def test_accessory_serializer_exposes_dynamic_attributes():
    category = Category.objects.create(name="Аксессуары", slug=f"accessories-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"ACC {uuid.uuid4().hex[:6]}", slug=f"acc-{uuid.uuid4().hex[:8]}")
    product = AccessoryProduct.objects.create(
        name="Bag Test",
        slug=f"bag-test-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=100,
        currency="TRY",
        is_active=True,
    )
    key = GlobalAttributeKey.objects.create(
        slug=f"material-{uuid.uuid4().hex[:8]}",
        name="Материал",
    )
    ProductAttributeValue.objects.create(
        content_type=ContentType.objects.get_for_model(AccessoryProduct),
        object_id=product.pk,
        attribute_key=key,
        value="Кожа",
        sort_order=0,
    )

    data = product.__class__.objects.get(pk=product.pk)
    serialized = AccessoryProductSerializer(data).data

    assert "dynamic_attributes" in serialized
    assert len(serialized["dynamic_attributes"]) == 1
    assert serialized["dynamic_attributes"][0]["key"] == key.slug
    assert serialized["dynamic_attributes"][0]["key_display"] == "Материал"
    assert serialized["dynamic_attributes"][0]["value"] == "Кожа"
    assert serialized["dynamic_attributes"][0]["sort_order"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("product_model", "serializer_class", "extra_fields"),
    [
        (MedicineProduct, MedicineProductSerializer, {"prescription_required": False}),
        (SupplementProduct, SupplementProductSerializer, {}),
        (MedicalEquipmentProduct, MedicalEquipmentProductSerializer, {}),
        (TablewareProduct, TablewareProductSerializer, {}),
        (IncenseProduct, IncenseProductSerializer, {}),
        (SportsProduct, SportsProductSerializer, {}),
        (SportsProduct, SportsProductDetailSerializer, {}),
        (AutoPartProduct, AutoPartProductSerializer, {}),
        (AutoPartProduct, AutoPartProductDetailSerializer, {}),
    ],
)
def test_remaining_product_serializers_expose_dynamic_attributes(
    product_model,
    serializer_class,
    extra_fields,
):
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name=f"Категория {suffix}", slug=f"category-{suffix}")
    brand = Brand.objects.create(name=f"Brand {suffix}", slug=f"brand-{suffix}")
    product = product_model.objects.create(
        name=f"Product {suffix}",
        slug=f"product-{suffix}",
        category=category,
        brand=brand,
        price=100,
        currency="TRY",
        is_active=True,
        **extra_fields,
    )
    key = GlobalAttributeKey.objects.create(
        slug=f"attribute-{suffix}",
        name="Атрибут",
    )
    ProductAttributeValue.objects.create(
        content_type=ContentType.objects.get_for_model(product_model),
        object_id=product.pk,
        attribute_key=key,
        value="Значение",
        sort_order=0,
    )

    serialized = serializer_class(product).data

    assert "dynamic_attributes" in serialized
    assert len(serialized["dynamic_attributes"]) == 1
    assert serialized["dynamic_attributes"][0]["key"] == key.slug
    assert serialized["dynamic_attributes"][0]["key_display"] == "Атрибут"
    assert serialized["dynamic_attributes"][0]["value"] == "Значение"
    assert serialized["dynamic_attributes"][0]["sort_order"] == 0


@pytest.mark.django_db
def test_resolve_api_underwear_variant_slug_returns_all_variants():
    from rest_framework.test import APIClient

    category = Category.objects.create(name="Нижнее бельё", slug=f"underwear-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"LCW UW {uuid.uuid4().hex[:6]}", slug=f"lcw-uw-{uuid.uuid4().hex[:8]}")
    product = UnderwearProduct.objects.create(
        name="Комплект белья",
        slug=f"underwear-set-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=199,
        currency="TRY",
        is_active=True,
    )
    first_variant = UnderwearVariant.objects.create(
        product=product,
        name="Красный",
        slug=f"underwear-red-{uuid.uuid4().hex[:8]}",
        color="red",
        price=199,
        currency="TRY",
        is_active=True,
        sort_order=0,
    )
    second_variant = UnderwearVariant.objects.create(
        product=product,
        name="Черный",
        slug=f"underwear-black-{uuid.uuid4().hex[:8]}",
        color="black",
        price=209,
        currency="TRY",
        is_active=True,
        sort_order=1,
    )

    client = APIClient()
    response = client.get(f"/api/catalog/products/resolve/{first_variant.slug}")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["product_type"] == "underwear"
    assert response.data["canonical_path"] == f"/product/underwear/{product.slug}"
    payload = response.data["payload"]
    assert payload["slug"] == product.slug
    assert payload["active_variant_slug"] == first_variant.slug
    assert payload["default_variant_slug"] == first_variant.slug
    assert [variant["slug"] for variant in payload["variants"]] == [first_variant.slug, second_variant.slug]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("product_model", "variant_model", "slug_prefix", "product_type"),
    [
        (HeadwearProduct, HeadwearVariant, "headwear", "headwear"),
        (IslamicClothingProduct, IslamicClothingVariant, "islamic", "islamic-clothing"),
        (BookProduct, BookVariant, "book", "books"),
        (PerfumeryProduct, PerfumeryVariant, "perfume", "perfumery"),
    ],
)
def test_resolve_api_variant_slug_redirect_contract_for_variant_domains(
    product_model,
    variant_model,
    slug_prefix,
    product_type,
):
    from rest_framework.test import APIClient

    category = Category.objects.create(name=f"{slug_prefix} category", slug=f"{slug_prefix}-cat-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"{slug_prefix} brand", slug=f"{slug_prefix}-brand-{uuid.uuid4().hex[:8]}")
    product = product_model.objects.create(
        name=f"{slug_prefix} product",
        slug=f"{slug_prefix}-product-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=199,
        currency="TRY",
        is_active=True,
    )

    variant_kwargs = {
        "product": product,
        "name": f"{slug_prefix} variant",
        "slug": f"{slug_prefix}-variant-{uuid.uuid4().hex[:8]}",
        "price": 205,
        "currency": "TRY",
        "is_active": True,
        "sort_order": 0,
    }
    if product_type in {"headwear", "islamic-clothing"}:
        variant_kwargs["color"] = "black"
    if product_type == "books":
        variant_kwargs["format_type"] = "paperback"
    if product_type == "perfumery":
        variant_kwargs["volume"] = "50 ml"

    variant = variant_model.objects.create(**variant_kwargs)

    client = APIClient()
    response = client.get(f"/api/catalog/products/resolve/{variant.slug}")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["product_type"] == product_type
    payload = response.data["payload"]
    assert payload["slug"] == product.slug
    assert payload["active_variant_slug"] == variant.slug
    assert payload["default_variant_slug"] == variant.slug
    assert payload["variants"][0]["slug"] == variant.slug


@pytest.mark.django_db
def test_sports_serializer_exposes_active_variant_contract():
    category = Category.objects.create(name="Sports", slug=f"sports-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"Sport Brand {uuid.uuid4().hex[:6]}", slug=f"sport-brand-{uuid.uuid4().hex[:8]}")
    product = SportsProduct.objects.create(
        name="Sports Product",
        slug=f"sports-product-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=100,
        old_price=150,
        currency="TRY",
        is_active=True,
    )
    first_variant = SportsVariant.objects.create(
        product=product,
        color="blue",
        size="M",
        sku="SP-1",
        price=110,
        old_price=160,
        stock_quantity=3,
        is_available=True,
    )
    SportsVariant.objects.create(
        product=product,
        color="red",
        size="L",
        sku="SP-2",
        price=120,
        stock_quantity=1,
        is_available=True,
    )

    data = SportsProductDetailSerializer(product, context={"active_variant_slug": f"sports-variant-{first_variant.pk}"}).data

    assert data["default_variant_slug"] == f"sports-variant-{first_variant.pk}"
    assert data["active_variant_slug"] == f"sports-variant-{first_variant.pk}"
    assert data["active_variant_currency"] == "TRY"
    assert data["active_variant_stock_quantity"] == 3
    assert data["variants"][0]["slug"] == f"sports-variant-{first_variant.pk}"
    assert data["variants"][0]["sizes"][0]["size"] == "M"


@pytest.mark.django_db
def test_auto_part_serializer_exposes_active_variant_contract():
    category = Category.objects.create(name="Auto", slug=f"auto-{uuid.uuid4().hex[:8]}")
    brand = Brand.objects.create(name=f"Auto Brand {uuid.uuid4().hex[:6]}", slug=f"auto-brand-{uuid.uuid4().hex[:8]}")
    product = AutoPartProduct.objects.create(
        name="Auto Part",
        slug=f"auto-part-{uuid.uuid4().hex[:8]}",
        category=category,
        brand=brand,
        price=300,
        old_price=350,
        currency="TRY",
        is_active=True,
    )
    first_variant = AutoPartVariant.objects.create(
        product=product,
        condition="new",
        sku="AP-1",
        manufacturer="OEM",
        price=310,
        old_price=360,
        stock_quantity=4,
        is_available=True,
    )

    data = AutoPartProductDetailSerializer(product, context={"active_variant_slug": f"auto-part-variant-{first_variant.pk}"}).data

    assert data["default_variant_slug"] == f"auto-part-variant-{first_variant.pk}"
    assert data["active_variant_slug"] == f"auto-part-variant-{first_variant.pk}"
    assert data["active_variant_currency"] == "TRY"
    assert data["active_variant_stock_quantity"] == 4
    assert data["variants"][0]["slug"] == f"auto-part-variant-{first_variant.pk}"
