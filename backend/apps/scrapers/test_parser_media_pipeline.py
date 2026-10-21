"""Скачивание медиа парсеров: User-Agent, галереи цветов, повторный проход."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image

from apps.catalog.models import Category, ClothingVariant, ClothingVariantImage, Product
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.catalog.utils import parser_media_handler
from apps.catalog.utils.parser_media_handler import source_url_fingerprint
from apps.catalog.utils.storage_paths import get_parsed_media_upload_path
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService

LCW_IMAGE = "https://img-lcwaikiki.mncdn.com/mnresize/1020/1360/pim/productimages/1/a.jpg"
CDN = "https://img-lcwaikiki.mncdn.com/mnresize/1020/1360/pim/productimages"


def _session(*, user_agent="", max_images=5):
    config = SimpleNamespace(
        user_agent=user_agent,
        headers={},
        max_images_per_product=max_images,
        parser_class="lcw",
    )
    return SimpleNamespace(scraper_config=config, max_images_per_product=None)


def _jpeg_bytes():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="JPEG")
    return buffer.getvalue()


class _Response:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


def _record_user_agents(monkeypatch):
    """Сеть загрузчика без HTTP: CDN, как mncdn, отвечает 422 без User-Agent."""
    sent = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def _respond(self, method, headers):
            ua = (headers or {}).get("User-Agent", "")
            sent.append((method, ua))
            if not ua:
                return _Response(422)
            return _Response(200, _jpeg_bytes(), {"Content-Type": "image/jpeg"})

        def head(self, url, headers=None):
            return self._respond("HEAD", headers)

        def get(self, url, headers=None):
            return self._respond("GET", headers)

    monkeypatch.setattr(parser_media_handler.httpx, "Client", Client)
    monkeypatch.setattr(parser_media_handler.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(parser_media_handler.default_storage, "save", lambda path, file_obj: path)
    monkeypatch.setattr(parser_media_handler.default_storage, "exists", lambda path: False)
    monkeypatch.setattr(parser_media_handler.default_storage, "url", lambda path: f"https://cdn.example/{path}")
    return sent


def test_media_download_without_configured_user_agent_uses_browser_one(monkeypatch):
    sent = _record_user_agents(monkeypatch)

    images, _ = ScraperIntegrationService()._download_parsed_media_urls(
        _session(user_agent=""),
        source_urls=[LCW_IMAGE],
        parser_name="lcw",
        product_id="lcw-1",
        sub_folder=None,
    )

    assert len(images) == 1 and "/products/parsed/lcw/" in images[0]
    assert [method for method, _ in sent] == ["HEAD", "GET"]
    assert all(ua.startswith("Mozilla/5.0 (Windows") and "Chrome/" in ua for _, ua in sent)


def test_media_download_keeps_configured_user_agent(monkeypatch):
    sent = _record_user_agents(monkeypatch)

    images, _ = ScraperIntegrationService()._download_parsed_media_urls(
        _session(user_agent="Configured/2.0"),
        source_urls=[LCW_IMAGE],
        parser_name="lcw",
        product_id="lcw-1",
        sub_folder=None,
    )

    assert len(images) == 1
    assert sent == [("HEAD", "Configured/2.0"), ("GET", "Configured/2.0")]


def _image_for(url):
    """Свои байты на каждый URL: одинаковые копии не скрывают пересоздание галереи."""
    buffer = BytesIO()
    Image.frombytes("RGB", (4, 1), source_url_fingerprint(url).encode()).save(buffer, format="PNG")
    return buffer.getvalue()


def _fake_downloads(monkeypatch):
    """download_and_optimize_parsed_media без сети: файл в products/parsed/, как у оригинала."""
    calls = []

    def download(url, parser_name, product_id, index, headers=None, timeout=15, sub_folder=None):
        calls.append(url)
        name = f"{parser_name}-{product_id}-{index}-{source_url_fingerprint(url)}.jpg"
        path = get_parsed_media_upload_path(parser_name, "image", name, sub_folder)
        if not default_storage.exists(path):
            default_storage.save(path, ContentFile(_image_for(url)))
        return default_storage.url(path)

    monkeypatch.setattr("apps.scrapers.services.download_and_optimize_parsed_media", download)
    return calls


def _signal_downloads(monkeypatch):
    """Синхронные скачивания внешних URL pre_save-сигналом."""
    calls = []
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: calls.append(url))
    return calls


def _colour(external_id, images, sort_order=0):
    return {
        "external_id": external_id,
        "color": f"Renk {sort_order}",
        "price": 100,
        "currency": "TRY",
        "external_url": f"https://www.lcw.com/tisort-o-{external_id}",
        "sort_order": sort_order,
        "is_available": True,
        "stock_quantity": 3,
        "images": list(images),
    }


def _lcw_group(external_id, colours):
    """Группа цветов LCW: корневая галерея — фото первого цвета (как у парсера)."""
    return ScrapedProduct(
        name="Tişört",
        price=100,
        currency="TRY",
        source="lcw",
        external_id=external_id,
        url=f"https://www.lcw.com/tisort-o-{external_id}",
        images=list(colours[0]["images"]),
        attributes={"variant_group_id": external_id, "fashion_variants": colours},
    )


def _lcw_session(name):
    category, _ = Category.objects.get_or_create(
        slug="media-pipeline-clothing", defaults={"name": "Одежда media"}
    )
    config = ScraperConfig.objects.create(
        name=name, parser_class="lcw", base_url="https://www.lcw.com", default_category=category,
    )
    session = ScrapingSession.objects.create(
        scraper_config=config, start_url="https://www.lcw.com", max_pages=1, max_products=10, status="running",
    )
    return session, category


def _clothing(category, external_id):
    return Product.objects.create(
        name="Tişört",
        slug=f"tisort-{external_id}",
        category=category,
        product_type="clothing",
        price=100,
        currency="TRY",
        external_id=external_id,
        external_url=f"https://www.lcw.com/tisort-o-{external_id}",
        external_data={"source": "lcw"},
    )


def _variant_rows(product):
    return list(
        ClothingVariantImage.objects.filter(variant__product__base_product=product)
        .order_by("variant__external_id", "sort_order")
        .values_list("pk", "image_url", "image_file")
    )


@pytest.mark.django_db
def test_fashion_variant_galleries_go_through_parsed_pipeline(monkeypatch):
    downloads = _fake_downloads(monkeypatch)
    red = [f"{CDN}/pipe-red-{i}.jpg" for i in range(3)]
    blue = [f"{CDN}/pipe-blue-{i}.jpg" for i in range(3)]
    scraped = _lcw_group("lcw-pipe-1", [_colour("lcw-pipe-1-red", red), _colour("lcw-pipe-1-blue", blue, 1)])

    ScraperIntegrationService()._normalize_scraped_media(_session(max_images=2), scraped)

    # Лимит как у корневой галереи; URL, общий с корнем, качается один раз.
    assert downloads == red[:2] + blue[:2]
    red_spec, blue_spec = scraped.attributes["fashion_variants"]
    assert red_spec["images"] == scraped.images
    assert len(blue_spec["images"]) == 2
    assert all("/products/parsed/lcw/" in url for url in red_spec["images"] + blue_spec["images"])


@pytest.mark.django_db
def test_clothing_colour_galleries_are_stored_without_signal_downloads(monkeypatch):
    downloads = _fake_downloads(monkeypatch)
    signal_downloads = _signal_downloads(monkeypatch)
    session, category = _lcw_session("media-pipeline-first-pass")
    product = _clothing(category, "lcw-pipe-2")
    red = [f"{CDN}/first-red-{i}.jpg" for i in range(2)]
    blue = [f"{CDN}/first-blue-{i}.jpg" for i in range(2)]
    scraped = _lcw_group("lcw-pipe-2", [_colour("lcw-pipe-2-red", red), _colour("lcw-pipe-2-blue", blue, 1)])

    ScraperIntegrationService()._process_scraped_products(session, [scraped])

    # Раньше фото цветов качал pre_save-сигнал — по 10 с таймаута на фото, без оптимизации.
    assert signal_downloads == []
    assert sorted(downloads) == sorted(red + blue)
    rows = _variant_rows(product)
    assert len(rows) == 4
    for _, image_url, image_file in rows:
        assert image_file and "/products/parsed/" not in "/" + image_file
        assert "/products/parsed/" not in image_url
        assert default_storage.exists(image_file)


@pytest.mark.django_db
def test_colour_rows_saved_from_source_urls_match_their_parsed_copies(monkeypatch):
    _signal_downloads(monkeypatch)
    _, category = _lcw_session("media-pipeline-legacy")
    product = _clothing(category, "lcw-pipe-3")
    variant = ClothingVariant.objects.create(
        product=product.domain_item, name="Tişört - Renk 0", color="Renk 0", external_id="lcw-pipe-3-red",
        price=100, currency="TRY", is_active=True, is_available=True,
    )
    red = [f"{CDN}/legacy-red-{i}.jpg" for i in range(2)]
    for index, url in enumerate(red):
        # Так строки цветов сохранял сигнал: image_url — исходный URL, файл рядом.
        key = default_storage.save(f"products/clothing/legacy/{source_url_fingerprint(url)}.jpg", ContentFile(_image_for(url)))
        ClothingVariantImage.objects.create(
            variant=variant, image_url=url, image_file=key, sort_order=index, is_main=index == 0,
        )
    before = _variant_rows(product)
    parsed = [
        default_storage.url(
            get_parsed_media_upload_path("lcw", "image", f"lcw-lcw-pipe-3-red-{i}-{source_url_fingerprint(url)}.jpg")
        )
        for i, url in enumerate(red)
    ]

    ScraperIntegrationService()._sync_fashion_variants(product, variants=[_colour("lcw-pipe-3-red", parsed)])

    assert _variant_rows(product) == before


def _clothing_pass(session, external_id, red, blue):
    """Один проход задачи (новый сервис, как у новой задачи) по группе из двух цветов."""
    group = _lcw_group(
        external_id, [_colour(f"{external_id}-red", red), _colour(f"{external_id}-blue", blue, 1)]
    )
    return ScraperIntegrationService()._process_scraped_products(session, [group])


@pytest.mark.django_db
def test_second_identical_pass_reuses_stored_colour_galleries(monkeypatch):
    downloads = _fake_downloads(monkeypatch)
    signal_downloads = _signal_downloads(monkeypatch)
    session, category = _lcw_session("media-pipeline-rescrape")
    product = _clothing(category, "lcw-pipe-4")
    red = [f"{CDN}/again-red-{i}.jpg" for i in range(2)]
    blue = [f"{CDN}/again-blue-{i}.jpg" for i in range(2)]
    _clothing_pass(session, "lcw-pipe-4", red, blue)
    stored = _variant_rows(product)
    assert len(stored) == 4 and sorted(downloads) == sorted(red + blue)
    downloads.clear()

    result = _clothing_pass(session, "lcw-pipe-4", red, blue)

    # Раньше каждый проход заново качал все фото: HEAD + GET + Pillow + PUT в R2.
    assert downloads == []
    assert signal_downloads == []
    assert _variant_rows(product) == stored
    assert result["skipped"] == 1


@pytest.mark.django_db(transaction=True)
def test_missing_stored_copy_is_downloaded_again_without_losing_the_others(monkeypatch):
    # transaction=True: удаление файлов после delete() идёт сразу, как на проде без atomic.
    downloads = _fake_downloads(monkeypatch)
    _signal_downloads(monkeypatch)
    session, category = _lcw_session("media-pipeline-missing")
    product = _clothing(category, "lcw-pipe-5")
    red = [f"{CDN}/lost-red-{i}.jpg" for i in range(2)]
    blue = [f"{CDN}/lost-blue-{i}.jpg" for i in range(2)]
    _clothing_pass(session, "lcw-pipe-5", red, blue)
    lost = ClothingVariantImage.objects.get(
        variant__product__base_product=product, variant__external_id="lcw-pipe-5-red", sort_order=0,
    )
    default_storage.delete(lost.image_file.name)
    downloads.clear()

    _clothing_pass(session, "lcw-pipe-5", red, blue)

    assert downloads == [red[0]]
    rows = _variant_rows(product)
    assert len(rows) == 4
    assert all(default_storage.exists(image_file) for _, _, image_file in rows)


@pytest.mark.django_db
def test_colour_rows_saved_from_source_urls_are_reused_without_download(monkeypatch):
    downloads = _fake_downloads(monkeypatch)
    signal_downloads = _signal_downloads(monkeypatch)
    session, category = _lcw_session("media-pipeline-legacy-pass")
    product = _clothing(category, "lcw-pipe-6")
    red = [f"{CDN}/kept-red-{i}.jpg" for i in range(2)]
    blue = [f"{CDN}/kept-blue-{i}.jpg" for i in range(2)]
    for sort_order, (colour, urls) in enumerate((("red", red), ("blue", blue))):
        variant = ClothingVariant.objects.create(
            product=product.domain_item, name=f"Tişört - Renk {sort_order}", color=f"Renk {sort_order}",
            external_id=f"lcw-pipe-6-{colour}", price=100, currency="TRY", sort_order=sort_order,
            is_active=True, is_available=True,
        )
        for index, url in enumerate(urls):
            # Так строки цветов сохранял сигнал: image_url — исходный URL, файл рядом.
            key = default_storage.save(
                f"products/clothing/legacy-pass/{source_url_fingerprint(url)}.jpg", ContentFile(_image_for(url))
            )
            ClothingVariantImage.objects.create(
                variant=variant, image_url=url, image_file=key, sort_order=index, is_main=index == 0,
            )
    # Главные фото цвета и карточки — на файле галереи, как их оставил прошлый проход.
    ScraperIntegrationService()._dedupe_main_into_gallery(product)
    stored = _variant_rows(product)

    _clothing_pass(session, "lcw-pipe-6", red, blue)

    assert downloads == []
    assert signal_downloads == []
    assert _variant_rows(product) == stored


def _accessory(external_id):
    category, product_type = resolve_category_and_product_type("Kemer")
    return Product.objects.create(
        name="Kemer",
        slug=f"kemer-{external_id}",
        category=category,
        product_type=product_type,
        price=10,
        currency="TRY",
        external_id=external_id,
        external_url=f"https://www.lcw.com/kemer-o-{external_id}",
        external_data={"source": "lcw"},
    )


def _accessory_pass(session, external_id, images):
    scraped = ScrapedProduct(
        name="Kemer",
        price=10,
        currency="TRY",
        source="lcw",
        external_id=external_id,
        url=f"https://www.lcw.com/kemer-o-{external_id}",
        images=list(images),
    )
    return ScraperIntegrationService()._process_scraped_products(session, [scraped])


def _gallery_rows(product):
    return list(
        product.domain_item.gallery_images.order_by("sort_order", "id").values_list("pk", "image_url", "image_file")
    )


@pytest.mark.django_db
def test_second_identical_pass_reuses_stored_product_gallery(monkeypatch):
    downloads = _fake_downloads(monkeypatch)
    session, _ = _lcw_session("media-pipeline-gallery")
    product = _accessory("lcw-pipe-7")
    images = [f"{CDN}/belt-{i}.jpg" for i in range(3)]
    _accessory_pass(session, "lcw-pipe-7", images)
    stored = _gallery_rows(product)
    assert len(stored) == 3 and all("/products/parsed/" not in "/" + row[2] for row in stored)
    downloads.clear()

    result = _accessory_pass(session, "lcw-pipe-7", images)

    assert downloads == []
    assert _gallery_rows(product) == stored
    assert result["skipped"] == 1
