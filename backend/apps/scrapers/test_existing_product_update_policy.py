import pytest

from apps.catalog.models import Brand, Product
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
def test_repeat_scrape_preserves_semantic_fields_but_updates_price_and_stock():
    service = ScraperIntegrationService()
    old_brand = Brand.objects.create(name="Edited Brand")

    product = Product.objects.create(
        name="Edited Product",
        slug="edited-product",
        description="Agent-written description",
        category=None,
        product_type="",
        brand=old_brand,
        price=100,
        currency="TRY",
        stock_quantity=5,
        is_available=True,
        external_id="repeat-1",
        external_url="https://example.com/original",
        external_data={},
    )

    scraped = ScrapedProduct(
        name="Parser Product",
        description="Parser description that should not overwrite",
        price=149.99,
        currency="TRY",
        category="Parfüm",
        brand="Parser Brand",
        url="https://example.com/parser",
        external_id=product.external_id,
        stock_quantity=1000,
        is_available=True,
        source="lcw",
        attributes={"ürün_tipi": "Parfüm"},
    )

    status, updated_product = service._update_existing_product(None, scraped, product)
    updated_product.refresh_from_db()

    assert status == "updated"
    assert updated_product.description == "Agent-written description"
    assert updated_product.brand_id == old_brand.id
    assert float(updated_product.price) == 149.99
    assert updated_product.stock_quantity == 1000
    assert updated_product.external_url == "https://example.com/parser"


@pytest.mark.django_db
def test_repeat_scrape_does_not_overwrite_existing_domain_gender_and_size():
    service = ScraperIntegrationService()
    category, product_type = resolve_category_and_product_type("Kep Şapka")
    product = Product.objects.create(
        name="Existing Cap",
        slug="existing-cap",
        category=category,
        product_type=product_type,
        price=100,
        currency="TRY",
        external_id="headwear-repeat-1",
        external_data={},
    )
    headwear = service._get_headwear_product(product)
    headwear.gender = "women"
    headwear.size = "XS"
    headwear.save()

    changed = service._update_product_attributes(
        product,
        {
            "gender": "men",
            "default_size": "Standart",
            "fashion_variants": [
                {
                    "external_id": "headwear-var-1",
                    "images": [],
                    "sizes": [{"size": "Standart", "is_available": True, "stock_quantity": 1000}],
                    "price": 100,
                    "currency": "TRY",
                    "is_available": True,
                }
            ],
        },
    )

    headwear.refresh_from_db()

    assert changed is True
    assert headwear.gender == "women"
    assert headwear.size == "XS"


@pytest.mark.django_db
def test_fashion_variant_gallery_gets_generated_alt_text():
    service = ScraperIntegrationService()
    category, product_type = resolve_category_and_product_type("Kep Şapka")
    product = Product.objects.create(
        name="Existing Cap",
        slug="existing-cap-alt",
        category=category,
        product_type=product_type,
        price=100,
        currency="TRY",
        external_id="headwear-alt-1",
        external_data={},
    )

    changed = service._update_product_attributes(
        product,
        {
            "fashion_variants": [
                {
                    "external_id": "headwear-var-alt-1",
                    "display_name": "Existing Cap",
                    "color": "Siyah",
                    "images": [
                        "https://example.com/cap-1.jpg",
                        "https://example.com/cap-2.jpg",
                    ],
                    "sizes": [{"size": "Standart", "is_available": True, "stock_quantity": 1000}],
                    "price": 100,
                    "currency": "TRY",
                    "is_available": True,
                }
            ],
        },
    )

    headwear = service._get_headwear_product(product)
    variant = headwear.variants.get(external_id="headwear-var-alt-1")
    images = list(variant.images.order_by("sort_order"))

    assert changed is True
    assert [img.alt_text for img in images] == [
        "Existing Cap - Черный - Siyah",
        "Existing Cap - Черный - Siyah - фото 2",
    ]


@pytest.mark.django_db
def test_clear_product_domain_cache_covers_all_supported_domain_relations():
    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="Cache Probe",
        slug="cache-probe",
        product_type="electronics",
        price=100,
        currency="TRY",
        external_id="cache-probe-1",
        external_data={},
    )
    product._state.fields_cache = {
        "electronics_item": object(),
        "furniture_item": object(),
        "underwear_item": object(),
        "book_item": object(),
    }

    service._clear_product_domain_cache(product)

    assert product._state.fields_cache == {}
