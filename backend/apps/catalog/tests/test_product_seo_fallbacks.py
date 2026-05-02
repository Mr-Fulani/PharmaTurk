import pytest

from apps.catalog.models import Brand, Category, Product
from apps.catalog.serializers import ProductSerializer


pytestmark = pytest.mark.django_db


def test_product_serializer_generates_seo_fallbacks(settings):
    settings.SITE_NAME = "Mudaroba"

    category = Category.objects.create(name="Медицина", slug="medicines")
    brand = Brand.objects.create(name="Bayer", slug="bayer")
    product = Product.objects.create(
        name="Аспирин 500",
        slug="aspirin-500",
        category=category,
        brand=brand,
        product_type="medicines",
        description="",
    )

    data = ProductSerializer(product).data

    assert data["meta_title"] == "Аспирин 500 | Медицина | Mudaroba"
    assert "Купить Аспирин 500" in data["meta_description"]
    assert "Bayer" in data["meta_description"]
    assert data["og_title"] == data["meta_title"]
    assert data["og_description"] == data["meta_description"]
    assert "Аспирин 500" in data["meta_keywords"]
