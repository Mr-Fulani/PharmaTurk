"""Оригинал products/parsed/ удаляется в конце прогона парсера, только когда копия
сохранена и на оригинал больше никто не ссылается (utils/parsed_originals.py).

Резервной копии медиа товаров нет (инцидент 14.06.2026): любое сомнение — файл остаётся.
"""

from unittest.mock import patch

import pytest
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductImage, SupplementProductImage
from apps.catalog.utils.media_references import MediaReferenceCheckError
from apps.catalog.utils.parsed_originals import collect_parsed_originals, delete_resaved_originals
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService

pytestmark = pytest.mark.django_db

CDN = "https://cdn.mudaroba.com"
JPEG = b"\xff\xd8\xff\xe0fakejpegdata"


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    """Своё хранилище во временной папке: тест не тронет R2, даже если ключи R2 заданы."""
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path), "base_url": "/media/"},
        },
    }
    settings.R2_CONFIG = {"public_url": CDN}
    settings.DEBUG = False
    with patch("apps.catalog.utils.parsed_originals._MIN_PRODUCTS", 1):
        yield


@pytest.fixture
def supplement():
    category = Category.objects.create(name="БАДы оригиналы", slug="supplements-originals-test")
    product = Product.objects.create(
        name="BAD originals",
        slug="bad-originals-test",
        category=category,
        product_type="supplements",
        price=10,
        currency="TRY",
        external_id="superstep-originals-1",
        external_data={},
    )
    supplement = product.domain_item
    assert supplement is not product, "доменный SupplementProduct должен создаться"
    return supplement


@pytest.fixture
def parsed_key():
    key = "products/parsed/superstep/sneakers/images/superstep-orig-0-0123456789ab.jpg"
    default_storage.delete(key)
    default_storage.save(key, ContentFile(JPEG))
    yield key
    default_storage.delete(key)


def _save_gallery_image(supplement, key, capture):
    img = SupplementProductImage(product=supplement, image_url=f"{CDN}/{key}", image_file="")
    with capture(execute=True):
        img.save()  # pre_save копирует parsed → читаемый путь
    img.refresh_from_db()
    return img


def test_original_deleted_after_copy_saved(supplement, parsed_key, django_capture_on_commit_callbacks):
    with collect_parsed_originals():
        img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    copy = img.image_file.name
    try:
        assert copy and "products/parsed/" not in copy
        assert "products/parsed/" not in img.image_url
        assert default_storage.exists(copy)
        assert not default_storage.exists(parsed_key)
    finally:
        default_storage.delete(copy)


def test_original_kept_without_collector(supplement, parsed_key, django_capture_on_commit_callbacks):
    """Сохранение вне прогона парсера (админка, скрипты) оригинал не трогает."""
    img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert "products/parsed/" not in img.image_file.name
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_original_kept_when_copy_not_saved(supplement, parsed_key, django_capture_on_commit_callbacks):
    with patch.object(FieldFile, "save", side_effect=OSError("R2 недоступен")):
        with collect_parsed_originals():
            img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    assert not img.image_file
    assert default_storage.exists(parsed_key)


def test_original_kept_when_copy_missing_at_cleanup(supplement, parsed_key):
    deleted = delete_resaved_originals({parsed_key: "products/supplements/x/missing-copy.jpg"})
    assert deleted == 0
    assert default_storage.exists(parsed_key)


def test_original_kept_when_other_record_references_it(
    supplement, parsed_key, django_capture_on_commit_callbacks
):
    # bulk_create — без сигналов: строка так и ссылается на оригинал.
    ProductImage.objects.bulk_create([ProductImage(product=supplement.base_product, image_url=f"{CDN}/{parsed_key}")])
    with collect_parsed_originals():
        img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert "products/parsed/" not in img.image_file.name
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_original_kept_when_transaction_rolled_back(supplement, parsed_key, django_capture_on_commit_callbacks):
    copies = []
    with collect_parsed_originals():
        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(RuntimeError):
                with transaction.atomic():
                    img = SupplementProductImage(product=supplement, image_url=f"{CDN}/{parsed_key}", image_file="")
                    img.save()
                    copies.append(img.image_file.name)
                    raise RuntimeError("сбой товара")
    try:
        assert default_storage.exists(parsed_key)
    finally:
        for name in copies:
            default_storage.delete(name)


def test_original_kept_when_reference_check_fails(supplement, parsed_key, django_capture_on_commit_callbacks):
    with patch(
        "apps.catalog.utils.media_references.referenced_media_paths",
        side_effect=MediaReferenceCheckError("catalog.Product.main_image: timeout"),
    ):
        with collect_parsed_originals():
            img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_only_parsed_zone_is_deleted(supplement):
    readable = "products/supplements/bad-originals-test/readable-copy.jpg"
    default_storage.save(readable, ContentFile(JPEG))
    other = "products/supplements/bad-originals-test/not-parsed.jpg"
    default_storage.save(other, ContentFile(JPEG))
    try:
        assert delete_resaved_originals({other: readable}) == 0
        assert default_storage.exists(other)
    finally:
        default_storage.delete(readable)
        default_storage.delete(other)


def test_nested_collectors_delete_once_at_outer_end(supplement, parsed_key, django_capture_on_commit_callbacks):
    with collect_parsed_originals():
        with collect_parsed_originals():
            img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
        assert default_storage.exists(parsed_key)
    try:
        assert not default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def _config():
    category = Category.objects.create(name="Обувь оригиналы", slug="shoes-originals-test")
    return ScraperConfig.objects.create(
        name="SuperStep originals",
        parser_class="superstep",
        base_url="https://www.superstep.com.tr",
        default_category=category,
    )


def test_original_kept_while_other_run_of_parser_is_active(
    supplement, parsed_key, django_capture_on_commit_callbacks
):
    """Параллельный прогон мог взять тот же parsed-файл (имя постоянное) и ещё не записать строку."""
    ScrapingSession.objects.create(scraper_config=_config(), status="running", started_at=timezone.now())
    with collect_parsed_originals():
        img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_stale_running_session_does_not_block(supplement, parsed_key, django_capture_on_commit_callbacks):
    """«running» старше лимита — след убитого воркера, удаление не держит."""
    ScrapingSession.objects.create(
        scraper_config=_config(), status="running", started_at=timezone.now() - timedelta(days=2)
    )
    with collect_parsed_originals():
        img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert not default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_original_kept_in_debug(supplement, parsed_key, settings, django_capture_on_commit_callbacks):
    """Как cleanup_orphaned_media: у разработчиков общий R2-префикс, БД у каждого своя."""
    settings.DEBUG = True
    with collect_parsed_originals():
        img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_original_kept_when_db_has_few_products(supplement, parsed_key, django_capture_on_commit_callbacks):
    with patch("apps.catalog.utils.parsed_originals._MIN_PRODUCTS", 100):
        with collect_parsed_originals():
            img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_delete_error_does_not_break_saving(supplement, parsed_key, django_capture_on_commit_callbacks):
    with patch.object(type(default_storage._wrapped), "delete", side_effect=OSError("R2 503")):
        with collect_parsed_originals():
            img = _save_gallery_image(supplement, parsed_key, django_capture_on_commit_callbacks)
    try:
        assert SupplementProductImage.objects.filter(pk=img.pk).exists()
        assert "products/parsed/" not in img.image_file.name
        assert default_storage.exists(parsed_key)
    finally:
        default_storage.delete(img.image_file.name)


def test_run_scraper_deletes_originals_at_its_end():
    """run_scraper обёрнут в сбор: удаление вызывается и когда прогон упал."""
    config = _config()
    with (
        patch("apps.scrapers.services.get_parser", return_value=None),
        patch("apps.catalog.utils.parsed_originals.delete_resaved_originals") as delete,
    ):
        with pytest.raises(ValueError):
            ScraperIntegrationService().run_scraper(config)
    delete.assert_called_once_with({})
