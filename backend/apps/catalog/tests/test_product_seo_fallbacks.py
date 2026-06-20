import pytest

from apps.catalog.models import (
    Brand,
    Category,
    ClothingProduct,
    ClothingVariant,
    ClothingVariantImage,
    Product,
    ProductImage,
)
from apps.catalog.serializers import ClothingProductSerializer, ProductSerializer


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


def test_product_list_serializer_includes_ordered_card_gallery():
    product = Product.objects.create(
        name="Gallery product",
        slug="gallery-product",
        product_type="accessories",
    )
    second = ProductImage.objects.create(
        product=product,
        image_url="https://cdn.example.com/second.jpg",
        sort_order=20,
    )
    main = ProductImage.objects.create(
        product=product,
        image_url="https://cdn.example.com/main.jpg",
        sort_order=30,
        is_main=True,
    )

    data = ProductSerializer(product).data

    assert [item["id"] for item in data["images"]] == [main.id, second.id]
    assert data["images"][0]["is_main"] is True


def test_clothing_list_serializer_uses_active_variant_gallery():
    product = ClothingProduct.objects.create(
        name="Variant gallery product",
        slug="variant-gallery-product",
        price=100,
        currency="RUB",
    )
    variant = ClothingVariant.objects.create(
        product=product,
        name="Blue",
        slug="variant-gallery-product-blue",
        price=100,
        currency="RUB",
        sort_order=0,
    )
    first = ClothingVariantImage.objects.create(
        variant=variant,
        image_url="https://cdn.example.com/variant-main.jpg",
        is_main=True,
        sort_order=0,
    )
    second = ClothingVariantImage.objects.create(
        variant=variant,
        image_url="https://cdn.example.com/variant-second.jpg",
        sort_order=1,
    )

    data = ClothingProductSerializer(product).data

    assert [item["id"] for item in data["images"]] == [first.id, second.id]

    product.refresh_from_db()
    base_data = ProductSerializer(product.base_product).data
    assert [item["image_url"] for item in base_data["images"]] == [
        "https://cdn.example.com/variant-main.jpg",
        "https://cdn.example.com/variant-second.jpg",
    ]
