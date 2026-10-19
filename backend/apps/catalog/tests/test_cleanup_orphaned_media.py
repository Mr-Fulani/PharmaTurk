"""cleanup_orphaned_media: потоковый обход хранилища и предохранители от массового удаления."""
import inspect
from types import SimpleNamespace

import pytest
from django.conf import settings as django_settings

from apps.catalog import tasks
from apps.catalog.models import Brand


class FakeBucketStorage:
    """S3/R2-хранилище: ключи отдаются генератором, как постраничный листинг boto3."""

    def __init__(self, keys, location=""):
        self.location = location
        self.keys = keys
        self.listed_prefix = None
        self.deleted = []
        self.bucket = SimpleNamespace(objects=SimpleNamespace(filter=self._filter))

    def _filter(self, Prefix):
        self.listed_prefix = Prefix
        return (SimpleNamespace(key=key) for key in self.keys)

    def delete(self, path):
        self.deleted.append(path)


REFERENCED = [f"products/main/{i}.jpg" for i in range(150)]
ORPHANS = ["products/parsed/a.jpg", "products/parsed/b.jpg", "products/parsed/c.jpg"]
PROTECTED = ["products/original/keep.jpg", "dev/products/keep.jpg", "avatars/u.jpg"]


@pytest.fixture
def run_cleanup(monkeypatch, settings):
    settings.DEBUG = False
    sent = []
    monkeypatch.setattr(
        "apps.monitoring.watchdog.send_admin_telegram_notification",
        lambda text: sent.append(text) or True,
    )

    def run(storage_keys, db_paths=REFERENCED, unreadable=(), **kwargs):
        storage = FakeBucketStorage(storage_keys)
        monkeypatch.setattr("django.core.files.storage.default_storage", storage)

        def fake_db_paths(unreadable_fields):
            unreadable_fields.extend(unreadable)
            yield from db_paths

        monkeypatch.setattr(tasks, "_iter_db_media_paths", fake_db_paths)
        result = tasks.cleanup_orphaned_media(**kwargs)
        return result, storage, sent

    return run


def test_deletes_only_unreferenced_unprotected_files(run_cleanup):
    result, storage, sent = run_cleanup(REFERENCED + ORPHANS + PROTECTED)

    assert result["status"] == "success"
    assert sorted(storage.deleted) == sorted(ORPHANS)
    assert result["deleted"] == 3
    assert result["storage"] == len(REFERENCED + ORPHANS + PROTECTED)
    assert result["protected_excluded"] == len(PROTECTED)
    assert sent == []


def test_too_many_files_to_delete_only_reports(run_cleanup):
    result, storage, sent = run_cleanup(REFERENCED + ORPHANS, max_delete=2)

    assert result["status"] == "aborted"
    assert result["reason"] == "max_delete_exceeded"
    assert result["orphaned"] == 3
    assert storage.deleted == []
    assert len(sent) == 1 and "max_delete_exceeded" in sent[0]


def test_too_large_share_of_storage_only_reports(run_cleanup):
    orphans = [f"products/parsed/{i}.jpg" for i in range(20)]  # 20 из 170 ≈ 11,8 %
    result, storage, sent = run_cleanup(REFERENCED + orphans, max_delete_percent=10)

    assert result["reason"] == "max_delete_percent_exceeded"
    assert storage.deleted == []
    assert len(sent) == 1


def test_default_limits_come_from_settings(run_cleanup, settings):
    settings.ORPHANED_MEDIA_MAX_DELETE = 2
    result, storage, _ = run_cleanup(REFERENCED + ORPHANS)

    assert result["reason"] == "max_delete_exceeded"
    assert result["max_delete"] == 2
    assert storage.deleted == []


def test_empty_database_never_deletes(run_cleanup):
    """Инцидент 2026-06-14: стек с пустой БД и общим бакетом стёр весь каталог."""
    result, storage, sent = run_cleanup(REFERENCED + ORPHANS, db_paths=REFERENCED[:10])

    assert result["reason"] == "db_paths_too_low"
    assert storage.deleted == []
    assert len(sent) == 1


def test_unreadable_db_field_never_deletes(run_cleanup):
    result, storage, sent = run_cleanup(
        REFERENCED + ORPHANS, unreadable=["catalog.Brand.logo"]
    )

    assert result["reason"] == "db_fields_unreadable"
    assert storage.deleted == []
    assert "catalog.Brand.logo" in sent[0]


def test_dry_run_reports_without_deleting_or_alerting(run_cleanup):
    result, storage, sent = run_cleanup(REFERENCED + ORPHANS, dry_run=True)

    assert result["status"] == "dry_run"
    assert sorted(result["sample"]) == sorted(ORPHANS)
    assert storage.deleted == []
    assert sent == []


def test_storage_listing_failure_deletes_nothing(run_cleanup, monkeypatch):
    def broken_listing(storage):
        yield "products/parsed/a.jpg"
        raise ConnectionError("R2 unavailable")

    monkeypatch.setattr(tasks, "_iter_storage_paths", broken_listing)
    result, storage, sent = run_cleanup(REFERENCED + ORPHANS)

    assert result["status"] == "error"
    assert storage.deleted == []
    assert len(sent) == 1


def test_bucket_keys_are_streamed_relative_to_location():
    storage = FakeBucketStorage(["dev/products/a.jpg", "dev/temp/b.png"], location="dev")

    paths = tasks._iter_storage_paths(storage)

    assert inspect.isgenerator(paths)
    assert storage.listed_prefix is None  # ничего не прочитано до начала обхода
    assert list(paths) == ["products/a.jpg", "temp/b.png"]
    assert storage.listed_prefix == "dev/"


@pytest.mark.django_db
def test_db_paths_include_url_fields(settings):
    settings.R2_CONFIG = {"prefix": ""}
    Brand.objects.bulk_create(
        [
            Brand(name="A", slug="a", logo="https://cdn.mudaroba.com/brands/a.png"),
            Brand(name="B", slug="b", logo=""),
        ]
    )
    unreadable = []

    paths = set(tasks._iter_db_media_paths(unreadable))

    assert "brands/a.png" in paths
    assert unreadable == []


def test_weekly_schedule_does_not_overlap_recsys_nightly():
    schedule = django_settings.CELERY_BEAT_SCHEDULE
    cleanup = schedule["cleanup-orphaned-media"]["schedule"]
    recsys = schedule["recsys-sync-stale-nightly"]["schedule"]

    assert cleanup.day_of_week == {0}  # воскресенье
    assert cleanup.hour == {3}
    assert recsys.hour == {2}
