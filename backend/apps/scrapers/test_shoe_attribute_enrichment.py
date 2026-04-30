import pytest

from apps.catalog.models import Category, Product, ProductAttributeValue
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
def test_shoe_attributes_are_saved_as_dynamic_attributes():
    service = ScraperIntegrationService()
    category = Category.objects.create(
        name="Обувь",
        slug="shoes",
        description="Обувь",
    )
    product = Product.objects.create(
        name="Женские кеды",
        slug="women-shoes-1",
        description="Кеды",
        category=category,
        product_type="shoes",
        price=1499,
        currency="TRY",
        external_id="shoe-1",
        external_data={},
    )

    updated = service._update_product_attributes(
        product,
        {
            "malzeme": "Suni deri",
            "baglama_sekli": "Bağcık",
            "taban_malzeme": "Kauçuk",
        },
    )

    assert updated is True

    shoe = product.shoe_item
    shoe.refresh_from_db()

    attrs = {
        row.attribute_key.slug: row
        for row in ProductAttributeValue.objects.filter(
            object_id=shoe.pk,
            content_type__model=shoe._meta.model_name,
        ).select_related("attribute_key")
    }
    assert attrs["material"].value_ru == "Искусственная кожа"
    assert attrs["closure-type"].value_ru == "Шнуровка"
    assert attrs["sole-material"].value_ru == "Каучук"
