"""Чистка products/parsed/ после парсинга: удаляет только точно ненужное.

Резервной копии медиа товаров нет — ошибка проверки ссылок, свежие файлы,
параллельная задача того же парсера и слишком много кандидатов останавливают
удаление.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.catalog.models import Category, Product, ProductImage
from apps.catalog.utils.media_references import media_reference_fields, referenced_media_paths
from apps.scrapers.models import ScraperConfig, SiteScraperTask
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.tasks import _sweep_parsed_orphans

pytestmark = pytest.mark.django_db

OLD = datetime.now(dt_timezone.utc) - timedelta(days=2)
FRESH = datetime.now(dt_timezone.utc) - timedelta(minutes=10)
PREFIX = "products/parsed/lcw/images/"


def _listing(*objects):
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": PREFIX + name, "LastModified": modified} for name, modified in objects]}
    ]
    return client


@pytest.fixture
def storage():
    """R2 без сети: листинг задаёт тест, удаления записываются."""
    with (
        patch("apps.scrapers.tasks._SWEEP_MIN_PRODUCTS", 1),
        patch("django.core.files.storage.default_storage.delete") as delete,
    ):
        yield delete


@pytest.fixture
def product():
    return Product.objects.create(name="Sweep test", slug="sweep-test", product_type="medicines")


def _images(product, *urls):
    # bulk_create — без pre_save: сигнал автоскачивания не ходит в сеть.
    ProductImage.objects.bulk_create(ProductImage(product=product, image_url=url) for url in urls)


def _sweep(client, **kwargs):
    with patch("apps.catalog.utils.r2_utils.get_r2_client", return_value=client):
        return _sweep_parsed_orphans("lcw", **kwargs)


def test_sweep_deletes_only_old_files_without_references(storage, product):
    _images(
        product,
        "https://cdn.mudaroba.com/" + PREFIX + "in-gallery.jpg",
        "https://mudaroba.com/api/catalog/proxy-media/?path=" + PREFIX + "via-proxy.jpg&max_width=400",
    )
    client = _listing(
        ("in-gallery.jpg", OLD), ("via-proxy.jpg", OLD), ("orphan.jpg", OLD), ("just-downloaded.jpg", FRESH)
    )

    assert _sweep(client) == 1

    storage.assert_called_once_with(PREFIX + "orphan.jpg")


def test_reference_check_error_deletes_nothing(storage, product):
    broken = [(Product, "no_such_field")] + media_reference_fields()
    with patch("apps.catalog.utils.media_references.media_reference_fields", return_value=broken):
        assert _sweep(_listing(("orphan.jpg", OLD))) == 0

    storage.assert_not_called()


def test_too_many_candidates_delete_nothing_and_alert_admin(storage, product):
    client = _listing(("a.jpg", OLD), ("b.jpg", OLD), ("c.jpg", OLD))
    with patch("apps.monitoring.watchdog.send_admin_telegram_notification") as notify:
        assert _sweep(client, max_delete=2) == 0

    storage.assert_not_called()
    assert "к удалению 3 файлов" in notify.call_args.args[0]


def test_sweep_waits_for_other_task_of_the_same_parser(storage, product):
    category = Category.objects.create(name="Обувь", slug="sweep-shoes")
    config = ScraperConfig.objects.create(
        name="lcw-shoes", parser_class="lcw", base_url="https://www.lcw.com", default_category=category
    )
    SiteScraperTask.objects.create(scraper_config=config, status="running")
    client = _listing(("orphan.jpg", OLD))

    assert _sweep(client) == 0

    storage.assert_not_called()
    client.get_paginator.assert_not_called()


def test_empty_database_deletes_nothing(product):
    with (
        patch("apps.scrapers.tasks._SWEEP_MIN_PRODUCTS", 100),
        patch("django.core.files.storage.default_storage.delete") as delete,
    ):
        assert _sweep(_listing(("orphan.jpg", OLD))) == 0
    delete.assert_not_called()


def test_dry_run_counts_without_deleting(storage, product):
    assert _sweep(_listing(("orphan.jpg", OLD)), dry_run=True) == 1
    storage.assert_not_called()


def test_dev_prefix_is_listed_and_deleted_relative_to_storage(storage, product, settings):
    settings.R2_CONFIG = {**settings.R2_CONFIG, "prefix": "dev"}
    client = MagicMock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "dev/" + PREFIX + "orphan.jpg", "LastModified": OLD}]}
    ]

    assert _sweep(client) == 1

    assert client.get_paginator.return_value.paginate.call_args.kwargs["Prefix"] == "dev/products/parsed/lcw/"
    storage.assert_called_once_with(PREFIX + "orphan.jpg")


def test_reference_check_makes_one_query_per_field_for_any_number_of_files(product, django_assert_num_queries):
    _images(product, *(f"https://cdn.mudaroba.com/{PREFIX}{index}.jpg" for index in range(50)))

    with django_assert_num_queries(len(media_reference_fields())):
        found = referenced_media_paths(PREFIX)

    assert found == {f"{PREFIX}{index}.jpg" for index in range(50)}


def test_old_main_image_is_kept_when_references_cannot_be_checked():
    broken = [(Product, "no_such_field")]
    with patch("apps.catalog.utils.media_references.media_reference_fields", return_value=broken):
        assert ScraperIntegrationService()._media_key_referenced("products/shoes/main/old.jpg") is True
