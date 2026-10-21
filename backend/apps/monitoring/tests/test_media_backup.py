"""Копия медиа маркетинга, страниц и услуг: только новое и изменённое, удалённое живёт 30 дней."""

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from django.core.management import call_command
from django.test import override_settings

from apps.monitoring import media_backup
from apps.monitoring.checks import media_backup_configuration_check
from apps.monitoring.db_backup import BackupError
from apps.monitoring.media_backup import MANIFEST_KEY, backup_media, restore, restore_plan, verify_media_backup
from apps.monitoring.tasks import run_media_backup

NOW = datetime(2026, 10, 23, 23, 0, tzinfo=timezone.utc)  # 02:00 МСК
SETTINGS = {
    "R2_BUCKET_NAME": "mudaroba-media",
    "R2_CONFIG": {"prefix": ""},
    "DB_BACKUP_S3_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
    "DB_BACKUP_S3_BUCKET": "mudaroba-db-backups",
    "DB_BACKUP_S3_ACCESS_KEY_ID": "backup-key",
    "DB_BACKUP_S3_SECRET_ACCESS_KEY": "backup-secret",
    "MEDIA_BACKUP_ENABLED": True,
    "MEDIA_BACKUP_PREFIXES": ["marketing/", "pages/", "services/"],
    "MEDIA_BACKUP_KEEP_DELETED_DAYS": 30,
}


class FakeBucket:
    """Нужная модулю часть S3 API; файл читается и пишется частями, как в boto3."""

    def __init__(self, page_size=2):
        self.objects = {}  # key → (bytes, content type)
        self.page_size = page_size
        self.uploads = []
        self.largest_read = 0

    def put(self, key, data, content_type="image/webp"):
        self.objects[key] = (data, content_type)

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + self.page_size]
        response = {
            "Contents": [
                {"Key": key, "Size": len(self.objects[key][0]), "ETag": f'"{hashlib.md5(self.objects[key][0]).hexdigest()}"'}
                for key in page
            ],
            "IsTruncated": start + self.page_size < len(keys),
        }
        if response["IsTruncated"]:
            response["NextContinuationToken"] = str(start + self.page_size)
        return response

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        data, content_type = self.objects[Key]
        return {"Body": io.BytesIO(data), "ContentType": content_type}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key][0])}

    def upload_fileobj(self, Fileobj, Bucket, Key, ExtraArgs, Config):
        chunks = []
        while chunk := Fileobj.read(Config.multipart_chunksize):
            self.largest_read = max(self.largest_read, len(chunk))
            chunks.append(chunk)
        self.objects[Key] = (b"".join(chunks), ExtraArgs["ContentType"])
        self.uploads.append(Key)

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = (Body, ContentType)

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def buckets():
    media, backup = FakeBucket(), FakeBucket()
    media.put("marketing/banners/main.webp", b"banner-v1")
    media.put("marketing/cards/brands/bayer.webp", b"bayer")
    media.put("pages/og-home.webp", b"og")
    media.put("services/video.mp4", b"v" * (20 * 1024 * 1024), "video/mp4")
    media.put("products/parsed/lcw/x.jpg", b"product")  # товарные фото не копируются
    media.put("dev/marketing/banners/main.webp", b"dev")  # чужое окружение
    with override_settings(**SETTINGS):
        yield media, backup


def _manifest(backup):
    return json.loads(backup.objects[MANIFEST_KEY][0])


def test_copies_only_marketing_pages_services_in_parts(buckets):
    media, backup = buckets

    result = backup_media(media, backup, now=NOW)

    assert result["copied"] == 4
    assert set(backup.objects) == {
        "media/marketing/banners/main.webp",
        "media/marketing/cards/brands/bayer.webp",
        "media/pages/og-home.webp",
        "media/services/video.mp4",
        MANIFEST_KEY,
    }
    assert backup.objects["media/services/video.mp4"][1] == "video/mp4"
    assert backup.largest_read == 8 * 1024 * 1024  # 20 МиБ видео — частями, не целиком
    assert _manifest(backup)["last_success_at"] == NOW.isoformat()


def test_second_run_copies_only_new_and_changed_files(buckets):
    media, backup = buckets
    backup_media(media, backup, now=NOW)
    backup.uploads.clear()
    media.put("marketing/banners/main.webp", b"banner-v2")
    media.put("pages/og-delivery.webp", b"og2")

    result = backup_media(media, backup, now=NOW + timedelta(days=1))

    assert sorted(backup.uploads) == ["media/marketing/banners/main.webp", "media/pages/og-delivery.webp"]
    assert result["copied"] == 2
    assert backup.objects["media/marketing/banners/main.webp"][0] == b"banner-v2"


def test_deleted_file_is_kept_for_thirty_days_then_removed(buckets):
    media, backup = buckets
    backup_media(media, backup, now=NOW)
    del media.objects["pages/og-home.webp"]

    first = backup_media(media, backup, now=NOW + timedelta(days=1))
    assert first["newly_missing"] == ["pages/og-home.webp"]
    assert "media/pages/og-home.webp" in backup.objects

    later = backup_media(media, backup, now=NOW + timedelta(days=30))
    assert later["newly_missing"] == [] and later["deleted"] == []

    expired = backup_media(media, backup, now=NOW + timedelta(days=31))
    assert expired["deleted"] == ["pages/og-home.webp"]
    assert "media/pages/og-home.webp" not in backup.objects
    assert "pages/og-home.webp" not in _manifest(backup)["files"]


def test_mass_disappearance_leaves_the_copy_untouched(buckets):
    media, backup = buckets
    backup_media(media, backup, now=NOW)
    manifest_before = backup.objects[MANIFEST_KEY]
    for key in [key for key in media.objects if not key.startswith("services/")]:
        del media.objects[key]

    with pytest.raises(BackupError, match="пропало 3 из 4"):
        backup_media(media, backup, now=NOW + timedelta(days=1))

    assert backup.objects[MANIFEST_KEY] == manifest_before
    assert "media/marketing/banners/main.webp" in backup.objects


def test_dev_environment_copies_its_own_prefix(buckets):
    media, backup = buckets
    with override_settings(R2_CONFIG={"prefix": "dev"}):
        result = backup_media(media, backup, now=NOW)
    assert result["copied"] == 1
    assert "media/dev/marketing/banners/main.webp" in backup.objects


def test_verify_requires_fresh_complete_copy(buckets):
    media, backup = buckets
    with pytest.raises(BackupError, match="ещё нет"):
        verify_media_backup(backup, now=NOW)
    backup_media(media, backup, now=NOW)

    assert verify_media_backup(backup, now=NOW + timedelta(hours=1))["files"] == 4
    with pytest.raises(BackupError, match="старше суток"):
        verify_media_backup(backup, now=NOW + timedelta(hours=27))
    del backup.objects["media/pages/og-home.webp"]
    with pytest.raises(BackupError, match="pages/og-home.webp"):
        verify_media_backup(backup, now=NOW + timedelta(hours=1))


def test_restore_returns_missing_files_and_overwrites_only_on_request(buckets):
    media, backup = buckets
    backup_media(media, backup, now=NOW)
    del media.objects["marketing/banners/main.webp"]
    media.put("marketing/cards/brands/bayer.webp", b"broken-file")

    plan = restore_plan("marketing/", media, backup)
    assert {item["key"]: item["state"] for item in plan} == {
        "marketing/banners/main.webp": "missing",
        "marketing/cards/brands/bayer.webp": "changed",
    }
    assert restore(plan, source=media, target=backup) == ["marketing/banners/main.webp"]
    assert media.objects["marketing/banners/main.webp"] == (b"banner-v1", "image/webp")
    assert media.objects["marketing/cards/brands/bayer.webp"][0] == b"broken-file"

    restore(restore_plan("marketing/cards/", media, backup), overwrite=True, source=media, target=backup)
    assert media.objects["marketing/cards/brands/bayer.webp"][0] == b"bayer"
    with pytest.raises(BackupError):
        restore_plan("products/", media, backup)


def test_restore_command_is_dry_run_by_default(buckets, capsys):
    media, backup = buckets
    backup_media(media, backup, now=NOW)
    del media.objects["pages/og-home.webp"]
    with patch.object(media_backup, "media_client", return_value=media), patch(
        "apps.monitoring.db_backup.s3_client", return_value=backup
    ):
        call_command("restore_media_backup", "pages/")
        assert "pages/og-home.webp" not in media.objects
        call_command("restore_media_backup", "pages/", "--apply")
    assert media.objects["pages/og-home.webp"][0] == b"og"
    assert "Возвращено файлов: 1" in capsys.readouterr().out


@patch("apps.monitoring.tasks.send_admin_telegram_notification", return_value=True)
def test_task_alerts_on_failure_and_on_missing_files(send, buckets):
    media, backup = buckets
    with patch.object(media_backup, "media_client", return_value=media), patch(
        "apps.monitoring.db_backup.s3_client", return_value=backup
    ):
        assert run_media_backup()["status"] == "ok"
        send.assert_not_called()
        del media.objects["pages/og-home.webp"]
        assert run_media_backup()["status"] == "ok"
        assert "пропало 1 файлов: pages/og-home.webp" in send.call_args.args[0]
        with patch.object(media_backup, "_list", side_effect=RuntimeError("R2 недоступен")):
            assert run_media_backup()["status"] == "failed"
    assert "Копия медиа Mudaroba: ежедневная копия — сбой" in send.call_args.args[0]


def test_configuration_check_refuses_product_photos():
    with override_settings(**{**SETTINGS, "MEDIA_BACKUP_PREFIXES": ["marketing/", "products/"]}):
        assert [error.id for error in media_backup_configuration_check(None)] == ["monitoring.E015"]
    with override_settings(**{**SETTINGS, "DB_BACKUP_S3_BUCKET": ""}):
        assert [error.id for error in media_backup_configuration_check(None)] == ["monitoring.E014"]
    with override_settings(**SETTINGS):
        assert media_backup_configuration_check(None) == []
