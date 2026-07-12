import pytest
from django.conf import settings

from apps.catalog.models import Product, ProductImage
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


@pytest.mark.django_db
def test_normalizer_sets_alt_text_for_scraped_product_images_without_overwriting_manual_values(monkeypatch):
    product = Product.objects.create(
        name="LC Waikiki Basic T-Shirt",
        slug="lcw-basic-tshirt",
        product_type="accessories",
        price=100,
        currency="TRY",
        external_id="alt-test-1",
        external_data={
            "source": "lcw",
            "attributes": {
                "color": "Siyah",
            },
        },
    )

    # Нормализатор пишет в галерею доменной модели (AccessoryProduct.gallery_images),
    # а не в базовую ProductImage — domain_sync создаёт доменную строку автоматически
    domain = product.domain_item
    gallery = domain.gallery_images

    gallery.create(
        image_url="https://example.com/existing.jpg",
        alt_text="Ручной alt",
        sort_order=0,
    )

    # Нормализатор проверяет ручные ссылки HEAD-запросом и удаляет битые —
    # в тесте сеть мокаем, иначе example.com отдаёт 404 и картинка удаляется
    class _FakeResponse:
        status_code = 200

    monkeypatch.setattr("httpx.Client.head", lambda self, url: _FakeResponse())

    normalizer = CatalogNormalizer()
    normalizer._normalize_product_images(
        product,
        [
            "https://example.com/existing.jpg",
            "https://example.com/new.jpg",
        ],
    )

    existing = gallery.get(image_url="https://example.com/existing.jpg")
    created = gallery.get(image_url="https://example.com/new.jpg")

    assert existing.alt_text == "Ручной alt"
    assert created.alt_text == "LC Waikiki Basic T-Shirt - Siyah - фото 2"


@pytest.mark.django_db
def test_normalizer_repairs_missing_internal_main_image_from_gallery(monkeypatch):
    broken_main = (
        "https://cdn.mudaroba.com/products/medicines/main/images/"
        "medicines-bilaxten-20-mg-20-tabletok-bilaxten-20-mg-20-875f5b846a.png"
    )
    gallery_url = (
        "https://cdn.mudaroba.com/products/medicines/"
        "bilaxten-20-mg-20-tabletok/bilaxten-gallery-a5d741819e.png"
    )
    r2_config = dict(getattr(settings, "R2_CONFIG", {}) or {})
    r2_config["public_url"] = "https://cdn.mudaroba.com"
    monkeypatch.setattr(settings, "R2_CONFIG", r2_config, raising=False)
    monkeypatch.setattr("django.core.files.storage.default_storage.exists", lambda key: False)

    product = Product.objects.create(
        name="BILAXTEN 20 MG 20 ТАБЛЕТОК",
        slug="bilaxten-20-mg-20-tabletok",
        product_type="medicines",
        price=100,
        currency="TRY",
        main_image=broken_main,
        external_data={"source": "ilacfiyati"},
    )
    domain = product.domain_item
    domain.gallery_images.create(
        image_url=gallery_url,
        image_file="products/medicines/bilaxten-20-mg-20-tabletok/bilaxten-gallery-a5d741819e.png",
        sort_order=0,
    )

    CatalogNormalizer()._normalize_product_images(product, [gallery_url])

    product.refresh_from_db()
    domain.refresh_from_db()
    assert product.main_image == gallery_url
    assert domain.main_image == gallery_url


@pytest.mark.django_db
def test_normalizer_uses_readable_gallery_url_for_repaired_main_image(monkeypatch):
    parsed_url = (
        "https://cdn.mudaroba.com/products/parsed/ilacfiyati/medicines/images/"
        "ilacfiyati-lasirin-20-mg-tablet-20-tablet-0-53959973d994.jpg"
    )
    readable_url = (
        "https://cdn.mudaroba.com/products/medicines/"
        "lasirin-20-mg-tablet-20-tablet/lasirin-gallery-5129a9d701.jpg"
    )
    broken_main = (
        "https://cdn.mudaroba.com/products/medicines/main/images/"
        "medicines-lasirin-20-mg-tablet-20-tablet-broken.jpg"
    )
    r2_config = dict(getattr(settings, "R2_CONFIG", {}) or {})
    r2_config["public_url"] = "https://cdn.mudaroba.com"
    monkeypatch.setattr(settings, "R2_CONFIG", r2_config, raising=False)
    monkeypatch.setattr("django.core.files.storage.default_storage.exists", lambda key: False)

    def fake_auto_download(instance, field_name="image_file", url_field="image_url"):
        url = getattr(instance, url_field, "") or ""
        if not url.startswith("https://cdn.mudaroba.com/products/"):
            return
        if "/products/parsed/" in url:
            setattr(instance, url_field, readable_url)
        setattr(instance, field_name, "products/medicines/lasirin-20-mg-tablet-20-tablet/lasirin-gallery-5129a9d701.jpg")

    monkeypatch.setattr("apps.catalog.signals._auto_download_impl", fake_auto_download)

    product = Product.objects.create(
        name="LASIRIN 20 MG TABLET 20 TABLET",
        slug="lasirin-20-mg-tablet-20-tablet",
        product_type="medicines",
        price=100,
        currency="TRY",
        main_image=broken_main,
        external_data={"source": "ilacfiyati"},
    )

    CatalogNormalizer()._normalize_product_images(product, [parsed_url])

    product.refresh_from_db()
    domain = product.domain_item
    domain.refresh_from_db()
    gallery = domain.gallery_images.get()
    assert gallery.image_url == readable_url
    assert product.main_image == readable_url
    assert domain.main_image == readable_url
    assert domain.main_image_file.name == "products/medicines/lasirin-20-mg-tablet-20-tablet/lasirin-gallery-5129a9d701.jpg"


@pytest.mark.django_db
def test_normalizer_keeps_external_manual_main_image(monkeypatch):
    manual_main = "https://manual-cdn.example.com/products/custom-main.jpg"
    parser_url = "https://cdn.mudaroba.com/products/medicines/example/gallery.jpg"
    r2_config = dict(getattr(settings, "R2_CONFIG", {}) or {})
    r2_config["public_url"] = "https://cdn.mudaroba.com"
    monkeypatch.setattr(settings, "R2_CONFIG", r2_config, raising=False)
    monkeypatch.setattr("django.core.files.storage.default_storage.exists", lambda key: False)

    product = Product.objects.create(
        name="Manual main",
        slug="manual-main",
        product_type="medicines",
        price=100,
        currency="TRY",
        main_image=manual_main,
        external_data={"source": "ilacfiyati"},
    )

    CatalogNormalizer()._normalize_product_images(product, [parser_url])

    product.refresh_from_db()
    assert product.main_image == manual_main


@pytest.mark.django_db
def test_internal_readable_media_is_not_checked_over_http(monkeypatch):
    internal_url = "https://cdn.mudaroba.com/products/furniture/chair/ikea-gallery-a1.jpg"
    r2_config = dict(getattr(settings, "R2_CONFIG", {}) or {})
    r2_config["public_url"] = "https://cdn.mudaroba.com"
    monkeypatch.setattr(settings, "R2_CONFIG", r2_config, raising=False)
    monkeypatch.setattr("django.core.files.storage.default_storage.exists", lambda key: True)

    def forbidden_head(*args, **kwargs):
        raise AssertionError("Внутренний R2 URL не должен проверяться HTTP HEAD")

    monkeypatch.setattr("httpx.Client.head", forbidden_head)

    product = Product.objects.create(
        name="Internal media",
        slug="internal-media",
        product_type="accessories",
        price=100,
        currency="TRY",
        external_data={"source": "ikea"},
    )
    domain = product.domain_item
    domain.gallery_images.create(
        image_url=internal_url,
        image_file="products/furniture/chair/ikea-gallery-a1.jpg",
        sort_order=0,
    )

    CatalogNormalizer()._normalize_product_images(product, [internal_url])
    assert domain.gallery_images.filter(image_url=internal_url).exists()
