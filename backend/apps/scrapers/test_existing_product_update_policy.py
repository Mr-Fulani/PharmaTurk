import pytest
from django.conf import settings

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
def test_repeat_scrape_preserves_ai_seo_meta_and_external_data():
    """Повторный парс не перезатирает AI-обработку: SEO/мета, RU-перевод, external_data.
    Даже если парсер приносит meta_* в attrs, заполняются только пустые поля."""
    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="AI Card",
        slug="ai-card-seo",
        description="AI description",
        product_type="",
        price=100,
        currency="TRY",
        external_id="ai-seo-1",
        seo_title="AI SEO title",
        seo_description="AI SEO description",
        keywords=["ai", "kw"],
        og_image_url="https://cdn.mudaroba.com/ai-og.jpg",
        external_data={"ai_enriched": True, "seo_translations": {"en": {"meta_title": "AI EN"}}},
    )
    product.translations.create(locale="ru", meta_title="AI RU title", meta_description="AI RU descr")

    changed = service._update_product_attributes(
        product,
        {
            "meta_title": "Parser title",
            "meta_description": "Parser descr",
            "meta_keywords": "parser, kw",
            "og_image_url": "https://parser.example/og.jpg",
            "og_title": "Parser OG",
        },
    )
    product.save()
    product.refresh_from_db()
    ru = product.translations.get(locale="ru")

    # AI/ручные витринные поля парсер не трогает
    assert product.seo_title == "AI SEO title"
    assert product.seo_description == "AI SEO description"
    assert product.keywords == ["ai", "kw"]
    assert product.og_image_url == "https://cdn.mudaroba.com/ai-og.jpg"
    assert ru.meta_title == "AI RU title"
    assert ru.meta_description == "AI RU descr"
    # external_data AI-ключи сохранены; source-OG складывается отдельно для справки AI
    assert product.external_data.get("ai_enriched") is True
    assert product.external_data.get("seo_translations") == {"en": {"meta_title": "AI EN"}}
    assert product.external_data.get("seo_data", {}).get("source_og_title") == "Parser OG"
    assert product.external_data.get("seo_data", {}).get("source_meta_title") == "Parser title"
    assert changed is True


@pytest.mark.django_db
def test_source_seo_is_not_mislabeled_as_russian_or_english_storefront_seo():
    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="Turkish source card",
        slug="turkish-source-card",
        product_type="",
        price=100,
        currency="TRY",
        external_id="source-seo-1",
        external_data={},
    )

    changed = service._update_product_attributes(
        product,
        {
            "meta_title": "Türkçe kaynak başlığı",
            "meta_description": "Türkçe kaynak açıklaması",
            "meta_keywords": "türkçe, kaynak",
            "og_image_url": "https://source.example/image.jpg",
        },
    )
    product.save()
    product.refresh_from_db()

    assert changed is True
    assert not product.seo_title
    assert not product.seo_description
    assert not product.keywords
    assert not product.og_image_url
    assert not product.translations.filter(locale="ru").exists()
    assert product.external_data["seo_data"]["source_meta_title"] == "Türkçe kaynak başlığı"
    assert product.external_data["seo_data"]["source_og_image_url"] == "https://source.example/image.jpg"


@pytest.mark.django_db
def test_repeat_scrape_preserves_existing_main_image(monkeypatch):
    """Повторный парс не подменяет уже заданное главное фото, если файл существует."""
    monkeypatch.setattr("django.core.files.storage.default_storage.exists", lambda key: True)
    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="With Main Image",
        slug="with-main-image",
        description="desc",
        product_type="",
        price=100,
        currency="TRY",
        external_id="main-img-1",
        main_image="https://cdn.mudaroba.com/products/manual/main.jpg",
        external_data={},
    )

    scraped = ScrapedProduct(
        name="Parser",
        description="",
        price=120,
        currency="TRY",
        url="https://example.com/p",
        external_id=product.external_id,
        is_available=True,
        source="lcw",
        images=["https://img-lcwaikiki.mncdn.com/parser-main.jpg"],
        attributes={},
    )

    service._update_existing_product(None, scraped, product)
    product.refresh_from_db()

    assert product.main_image == "https://cdn.mudaroba.com/products/manual/main.jpg"
    assert float(product.price) == 120  # цена обновилась


@pytest.mark.django_db
def test_repeat_scrape_counts_broken_main_image_repair_as_update(monkeypatch):
    r2_config = dict(getattr(settings, "R2_CONFIG", {}) or {})
    r2_config["public_url"] = "https://cdn.mudaroba.com"
    monkeypatch.setattr(settings, "R2_CONFIG", r2_config, raising=False)
    monkeypatch.setattr("django.core.files.storage.default_storage.exists", lambda key: False)

    service = ScraperIntegrationService()
    product = Product.objects.create(
        name="Broken Main Medicine",
        slug="broken-main-medicine",
        product_type="medicines",
        price=100,
        currency="TRY",
        external_id="broken-main-1",
        external_url="https://ilacfiyati.com/ilaclar/broken-main-1",
        main_image="https://cdn.mudaroba.com/products/medicines/main/images/broken-main.jpg",
        external_data={"source": "ilacfiyati"},
    )
    gallery_url = "https://cdn.mudaroba.com/products/medicines/broken-main-1/gallery.jpg"

    scraped = ScrapedProduct(
        name=product.name,
        description="",
        price=product.price,
        currency=product.currency,
        url=product.external_url,
        external_id=product.external_id,
        is_available=product.is_available,
        stock_quantity=product.stock_quantity,
        source="ilacfiyati",
        images=[gallery_url],
        attributes={},
    )

    status, updated_product = service._update_existing_product(None, scraped, product)
    updated_product.refresh_from_db()

    assert status == "updated"
    assert updated_product.main_image == gallery_url


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
