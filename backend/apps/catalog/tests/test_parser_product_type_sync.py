import pytest

from apps.catalog.models import AccessoryProduct, PerfumeryProduct, Product
from apps.catalog.services import CatalogNormalizer
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.vapi.client import ProductData


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("category_value", "expected_type", "domain_model"),
    [
        ("Parfüm", "perfumery", PerfumeryProduct),
        ("Kemer", "accessories", AccessoryProduct),
    ],
)
def test_normalizer_updates_existing_product_type_and_creates_domain(
    category_value,
    expected_type,
    domain_model,
):
    category, _ = resolve_category_and_product_type(category_value)
    product = Product.objects.create(
        name=f"Existing {expected_type}",
        slug=f"existing-{expected_type}",
        category=category,
        product_type="",
        price=10,
        currency="TRY",
        external_id=f"existing-{expected_type}",
        external_data={"source": "scraper"},
    )

    normalizer = CatalogNormalizer()
    payload = ProductData(
        id=product.external_id,
        name=product.name,
        description="desc",
        price=10.0,
        currency="TRY",
        category=category_value,
        brand="LCW ACCESSORIES",
        images=[],
        url="https://example.com/product",
        availability=True,
        metadata={"source": "scraper", "attributes": {}},
    )

    updated = normalizer.normalize_product(payload)
    updated.refresh_from_db()

    assert updated.product_type == expected_type
    assert domain_model.objects.filter(base_product=updated).exists()
