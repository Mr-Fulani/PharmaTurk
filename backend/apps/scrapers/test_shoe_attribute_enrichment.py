import pytest

from apps.catalog.models import Category, Product, ProductAttributeValue
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
def test_parser_shoe_attributes_do_not_create_dynamic_facets():
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

    assert updated is False

    shoe = product.shoe_item
    shoe.refresh_from_db()

    assert not ProductAttributeValue.objects.filter(
        object_id=shoe.pk,
        content_type__model=shoe._meta.model_name,
    ).exists()
