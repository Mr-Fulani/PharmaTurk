import uuid

import pytest

from apps.catalog.models import (
    Brand,
    Category,
    CategoryType,
    ClothingProduct,
    ClothingVariant,
    Product,
)
from apps.scrapers.models import ProductDuplicateCandidate
from apps.scrapers.services import DeduplicationService


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_category(name: str, type_slug: str = "accessories"):
    category_type = CategoryType.objects.create(name=f"{name} type", slug=_unique_slug(type_slug))
    return Category.objects.create(name=name, slug=_unique_slug(name.lower()), category_type=category_type)


def _make_brand(name: str):
    return Brand.objects.create(name=name, slug=_unique_slug(name.lower().replace(" ", "-")))


def _make_product(
    *,
    name: str,
    brand=None,
    category=None,
    product_type: str = "accessories",
    external_id: str = "",
    external_url: str = "",
    barcode: str = "",
    sku: str = "",
    source: str = "",
    main_image: str = "",
):
    external_data = {"source": source} if source else {}
    return Product.objects.create(
        name=name,
        slug=_unique_slug(name.lower().replace(" ", "-")),
        brand=brand,
        category=category,
        product_type=product_type,
        external_id=external_id,
        external_url=external_url,
        external_data=external_data,
        barcode=barcode,
        sku=sku,
        main_image=main_image,
        price=100,
        currency="TRY",
    )


@pytest.mark.django_db
def test_find_duplicates_does_not_flag_name_only_matches_without_context():
    category_one = _make_category("Категория 1")
    category_two = _make_category("Категория 2")
    brand_one = _make_brand("Brand One")
    brand_two = _make_brand("Brand Two")

    _make_product(
        name="Premium Case",
        brand=brand_one,
        category=category_one,
        source="api",
    )
    _make_product(
        name="  premium   case ",
        brand=brand_two,
        category=category_two,
        source="lcw",
    )

    duplicates = DeduplicationService().find_duplicates()

    assert duplicates == []


@pytest.mark.django_db
def test_find_duplicates_uses_strong_identifiers_even_if_names_differ():
    category = _make_category("Гаджеты")
    brand = _make_brand("Brand Barcode")

    left = _make_product(
        name="Travel Adapter Black",
        brand=brand,
        category=category,
        barcode="8690001112223",
        source="api",
    )
    right = _make_product(
        name="Universal Adapter",
        brand=brand,
        category=category,
        barcode="8690001112223",
        source="scraper",
    )

    duplicates = DeduplicationService().find_duplicates()

    assert len(duplicates) == 1
    candidate = duplicates[0]
    assert {candidate["canonical_product"].pk, candidate["duplicate_product"].pk} == {left.pk, right.pk}
    assert "Совпадает штрихкод" in candidate["reasons"]


@pytest.mark.django_db
def test_find_duplicates_ignores_shadow_variant_products():
    category = _make_category("Головные уборы")
    brand = _make_brand("Variant Brand")

    _make_product(
        name="Classic Cap",
        brand=brand,
        category=category,
        external_id="CAP-100",
        source="api",
    )
    Product.objects.create(
        name="Classic Cap / Blue / M",
        slug=_unique_slug("classic-cap-variant"),
        brand=brand,
        category=category,
        product_type="headwear",
        external_id="CAP-100",
        external_data={"source": "scraper", "source_variant_id": "var-100"},
        price=100,
        currency="TRY",
    )

    duplicates = DeduplicationService().find_duplicates()

    assert duplicates == []


@pytest.mark.django_db
def test_store_candidates_creates_pending_review_records_without_merging_products():
    category = _make_category("Чехлы")
    brand = _make_brand("Case Brand")

    canonical = _make_product(
        name="Phone Case Pro",
        brand=brand,
        category=category,
        external_id="EXT-100",
        source="api",
    )
    duplicate = _make_product(
        name="Phone Case Pro",
        brand=brand,
        category=category,
        external_id="EXT-100",
        source="lcw",
    )

    service = DeduplicationService()
    duplicates = service.find_duplicates()
    result = service.store_candidates(duplicates)

    assert result == {"created": 1, "updated": 0}
    candidate = ProductDuplicateCandidate.objects.get()
    assert candidate.status == "pending"
    assert candidate.canonical_product_id == canonical.id
    assert candidate.duplicate_product_id == duplicate.id
    assert Product.objects.filter(pk=canonical.pk).exists()
    assert Product.objects.filter(pk=duplicate.pk).exists()


@pytest.mark.django_db
def test_merge_candidate_requires_manual_approval():
    category = _make_category("Наушники")
    brand = _make_brand("Audio Brand")
    canonical = _make_product(
        name="Wireless Earbuds",
        brand=brand,
        category=category,
        external_id="AUDIO-1",
        source="api",
    )
    duplicate = _make_product(
        name="Wireless Earbuds",
        brand=brand,
        category=category,
        external_id="AUDIO-1",
        source="parser",
    )
    candidate = ProductDuplicateCandidate.objects.create(
        pair_key=f"{canonical.pk}:{duplicate.pk}",
        canonical_product=canonical,
        duplicate_product=duplicate,
        canonical_product_name=canonical.name,
        duplicate_product_name=duplicate.name,
        score=100.0,
        reasons=["Совпадает внешний ID"],
        signals={"external_id": "AUDIO-1"},
        status="pending",
    )

    success = DeduplicationService().merge_candidate(candidate)

    assert success is False
    assert Product.objects.filter(pk=duplicate.pk).exists()
    candidate.refresh_from_db()
    assert candidate.status == "pending"


@pytest.mark.django_db
def test_merge_candidate_merges_only_after_approval():
    category = _make_category("Парфюм")
    brand = _make_brand("Perfume Brand")
    canonical = _make_product(
        name="Rose Oud",
        brand=brand,
        category=category,
        external_id="PERF-1",
        source="api",
        main_image="https://example.com/api-main.jpg",
    )
    duplicate = _make_product(
        name="Rose Oud",
        brand=brand,
        category=category,
        external_id="PERF-1",
        source="parser",
        main_image="https://example.com/scraped-main.jpg",
        external_url="https://shop.example.com/rose-oud",
    )
    candidate = ProductDuplicateCandidate.objects.create(
        pair_key=f"{canonical.pk}:{duplicate.pk}",
        canonical_product=canonical,
        duplicate_product=duplicate,
        canonical_product_name=canonical.name,
        duplicate_product_name=duplicate.name,
        score=100.0,
        reasons=["Совпадает внешний ID"],
        signals={"external_id": "PERF-1"},
        status="approved",
    )

    success = DeduplicationService().merge_candidate(candidate)

    assert success is True
    assert Product.objects.filter(pk=duplicate.pk).exists() is False
    canonical.refresh_from_db()
    candidate.refresh_from_db()
    assert candidate.status == "merged"
    assert canonical.external_data["additional_images"] == ["https://example.com/scraped-main.jpg"]
    assert canonical.external_data["scraped_sources"][0]["source"] == "parser"


@pytest.mark.django_db
def test_merge_candidate_deletes_duplicate_domain_product_with_variants():
    category = _make_category("Одежда")
    brand = _make_brand("Domain Brand")
    canonical = _make_product(
        name="Linen Shirt",
        brand=brand,
        category=category,
        external_id="LINEN-1",
        source="api",
    )
    duplicate_domain = ClothingProduct.objects.create(
        name="Linen Shirt",
        slug=_unique_slug("linen-shirt"),
        brand=brand,
        category=category,
        price=110,
        currency="TRY",
        external_id="LINEN-1",
        external_url="https://shop.example.com/linen-shirt",
        external_data={"source": "scraper"},
        main_image="https://shop.example.com/linen-shirt.jpg",
    )
    duplicate_domain.refresh_from_db()
    duplicate_base = duplicate_domain.base_product
    assert duplicate_base is not None

    variant = ClothingVariant.objects.create(
        product=duplicate_domain,
        name="Linen Shirt Blue M",
        slug=_unique_slug("linen-shirt-blue-m"),
        color="Blue",
        size="M",
        external_id="LINEN-1-BLUE-M",
        external_data={"source": "scraper", "source_variant_id": "LINEN-1-BLUE-M"},
        price=110,
        currency="TRY",
        is_available=True,
    )

    candidate = ProductDuplicateCandidate.objects.create(
        pair_key=f"{canonical.pk}:{duplicate_base.pk}",
        canonical_product=canonical,
        duplicate_product=duplicate_base,
        canonical_product_name=canonical.name,
        duplicate_product_name=duplicate_base.name,
        score=110.0,
        reasons=["Совпадает внешний ID", "Совпадает бренд"],
        signals={"external_id": "LINEN-1", "brand_id": brand.pk},
        status="approved",
    )

    success = DeduplicationService().merge_candidate(candidate)

    assert success is True
    assert Product.objects.filter(pk=duplicate_base.pk).exists() is False
    assert ClothingProduct.objects.filter(pk=duplicate_domain.pk).exists() is False
    assert ClothingVariant.objects.filter(pk=variant.pk).exists() is False
    candidate.refresh_from_db()
    canonical.refresh_from_db()
    assert candidate.status == "merged"
    assert canonical.external_data["additional_images"] == ["https://shop.example.com/linen-shirt.jpg"]
