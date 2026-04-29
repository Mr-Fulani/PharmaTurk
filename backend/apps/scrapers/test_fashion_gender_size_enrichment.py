import pytest

from apps.catalog.models import Product
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("category_value", "product_type", "description", "expected_gender", "expected_size"),
    [
        ("Kep Şapka", "headwear", "Nakış detaylı erkek kep şapka günlük kullanım için uygundur.", "men", "Standart"),
        ("Boxer", "underwear", "Erkek boxer esnek kumaşı ile gün boyu konfor sağlar.", "men", "M"),
    ],
)
def test_gendered_fashion_enrichment_updates_gender_and_single_size(
    category_value,
    product_type,
    description,
    expected_gender,
    expected_size,
):
    service = ScraperIntegrationService()
    category, resolved_type = resolve_category_and_product_type(category_value)
    assert resolved_type == product_type

    product = Product.objects.create(
        name=f"LCW {category_value}",
        slug=f"lcw-{product_type}",
        category=category,
        product_type=product_type,
        price=100,
        currency="TRY",
        external_id=f"lcw-{product_type}-1",
        description=description,
        external_data={},
    )
    scraped = ScrapedProduct(
        name=product.name,
        description=description,
        category=category_value,
        brand="LC Waikiki",
        external_id=product.external_id,
        source="lcw",
        attributes={
            "cinsiyet": "Erkek",
            "fashion_variants": [
                {
                    "external_id": f"{product_type}-var-1",
                    "sizes": [{"size": expected_size, "is_available": True, "stock_quantity": 1000}],
                }
            ],
        },
    )

    prepared_attrs = service._prepare_scraped_attributes(scraped, product.product_type)

    assert prepared_attrs["gender"] == expected_gender
    assert prepared_attrs["default_size"] == expected_size

    updated = service._update_product_attributes(product, prepared_attrs)
    assert updated is True

    domain = product.domain_item
    domain.refresh_from_db()

    assert domain.gender == expected_gender
    assert getattr(domain, "size") == expected_size
