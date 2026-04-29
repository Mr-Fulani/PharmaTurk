import pytest

from apps.catalog.models import Product
from apps.catalog.services import CatalogNormalizer
from apps.vapi.client import ProductData


@pytest.mark.django_db
def test_normalizer_keeps_shared_gallery_for_accessories_with_fashion_variants():
    normalizer = CatalogNormalizer()
    image_urls = [
        "https://example.com/accessory-1.jpg",
        "https://example.com/accessory-2.jpg",
        "https://example.com/accessory-3.jpg",
    ]
    payload = ProductData(
        id="gallery-accessory-1",
        name="Kemer - LC WAIKIKI - 249,99 TL",
        description="Accessory gallery sync",
        price=249.99,
        currency="TRY",
        category="Kemer",
        brand="LC Waikiki",
        images=image_urls,
        url="https://example.com/accessory-product",
        availability=True,
        metadata={
            "source": "lcw",
            "attributes": {
                "fashion_variants": [
                    {
                        "external_id": "acc-var-1",
                        "images": image_urls,
                    }
                ]
            },
        },
    )

    product = normalizer.normalize_product(payload)
    domain = product.accessory_item

    assert domain.gallery_images.count() == len(image_urls)
    assert list(domain.gallery_images.order_by("sort_order").values_list("image_url", flat=True)) == image_urls


@pytest.mark.django_db
def test_normalizer_still_skips_shared_gallery_for_clothing_variant_payloads():
    product = Product.objects.create(
        name="Variant clothing",
        slug="variant-clothing",
        product_type="clothing",
        price=100,
        currency="TRY",
        external_id="variant-clothing-1",
        external_data={
            "source": "lcw",
            "attributes": {
                "fashion_variants": [
                    {
                        "external_id": "cloth-var-1",
                        "images": [
                            "https://example.com/clothing-1.jpg",
                            "https://example.com/clothing-2.jpg",
                        ],
                    }
                ]
            },
        },
    )

    normalizer = CatalogNormalizer()
    normalizer._normalize_product_images(
        product,
        [
            "https://example.com/clothing-1.jpg",
            "https://example.com/clothing-2.jpg",
        ],
    )

    assert product.images.count() == 0
