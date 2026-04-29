import pytest

from apps.catalog.models import Product, ProductAttributeValue
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
def test_accessory_enrichment_maps_type_and_material_from_lcw_data():
    service = ScraperIntegrationService()
    category, product_type = resolve_category_and_product_type("Kemer")
    product = Product.objects.create(
        name="Kemer - LC WAIKIKI - 249,99 TL",
        slug="kemer-lcw-24999",
        category=category,
        product_type=product_type,
        price=249.99,
        currency="TRY",
        external_id="lcw-4375410",
        description=(
            "Suni deri dokulu erkek kemer, metal tokalıdır ve kenarlarında dikiş detayları bulunur. "
            "Ayarlanabilir tasarıma sahiptir."
        ),
        external_data={},
    )
    scraped = ScrapedProduct(
        name=product.name,
        description=product.description,
        category="Kemer",
        brand="LC Waikiki",
        external_id=product.external_id,
        source="lcw",
        attributes={
            "ürün_tipi": "Kemer",
            "kumaş": "Suni Deri",
        },
    )

    prepared_attrs = service._prepare_scraped_attributes(scraped, product.product_type)

    assert prepared_attrs["accessory_type"] == "Пояс / ремень"
    assert prepared_attrs["material"] == "Искусственная кожа"

    updated = service._update_product_attributes(product, prepared_attrs)
    assert updated is True

    accessory = product.accessory_item
    accessory.refresh_from_db()

    attrs = {
        row.attribute_key.slug: row
        for row in ProductAttributeValue.objects.filter(
            object_id=accessory.pk,
            content_type__model=accessory._meta.model_name,
        ).select_related("attribute_key")
    }
    assert accessory.accessory_type == ""
    assert accessory.material == ""
    assert attrs["accessory-type"].value_ru == "Пояс / ремень"
    assert attrs["material"].value_ru == "Искусственная кожа"


def test_accessory_enrichment_uses_description_material_fallback():
    service = ScraperIntegrationService()
    scraped = ScrapedProduct(
        name="LCW ACCESSORIES Hakiki Deri Erkek Kemer",
        description="Hakiki deri erkek kemer metal tokalıdır.",
        category="Kemer",
        brand="LC Waikiki",
        external_id="lcw-belt-2",
        source="lcw",
    )

    prepared_attrs = service._prepare_scraped_attributes(scraped, "accessories")

    assert prepared_attrs["accessory_type"] == "Пояс / ремень"
    assert prepared_attrs["material"] == "Натуральная кожа"
