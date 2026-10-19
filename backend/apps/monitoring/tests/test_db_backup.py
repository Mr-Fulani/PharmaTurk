import hashlib
import io
import os
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.test import override_settings

from apps.monitoring import db_backup
from apps.monitoring.checks import db_backup_configuration_check
from apps.monitoring.db_backup import (
    Backup,
    BackupError,
    backup_key,
    checksum_key,
    create_backup,
    list_backups,
    select_retained,
    verify_latest_backup,
)
from apps.monitoring.tasks import check_database_backup, run_database_backup

NOW = datetime(2026, 10, 19, 2, 15, tzinfo=timezone.utc)  # понедельник
BACKUP_SETTINGS = {
    "DB_BACKUP_ENABLED": True,
    "DB_BACKUP_S3_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
    "DB_BACKUP_S3_BUCKET": "mudaroba-db-backups",
    "DB_BACKUP_S3_ACCESS_KEY_ID": "backup-key",
    "DB_BACKUP_S3_SECRET_ACCESS_KEY": "backup-secret",
    "DB_BACKUP_TEST_RESTORE_ENABLED": False,
    "DB_BACKUP_HEARTBEAT_URL": "",
    "TELEGRAM_BOT_TOKEN": "token",
    "TELEGRAM_CHAT_ID": "chat",
    "R2_BUCKET_NAME": "mudaroba-media",
    "R2_ACCESS_KEY_ID": "media-key",
}


class FakeS3:
    """Достаточная для модуля часть S3 API в памяти."""

    def __init__(self, page_size=1000):
        self.objects = {}
        self.uploads = {}
        self.aborted = []
        self.page_size = page_size

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + self.page_size]
        truncated = start + self.page_size < len(keys)
        response = {
            "Contents": [{"Key": key, "Size": len(self.objects[key])} for key in page],
            "IsTruncated": truncated,
        }
        if truncated:
            response["NextContinuationToken"] = str(start + self.page_size)
        return response

    def create_multipart_upload(self, Bucket, Key, ContentType):
        upload_id = f"upload-{len(self.uploads) + 1}"
        self.uploads[upload_id] = {}
        return {"UploadId": upload_id}

    def upload_part(self, Bucket, Key, UploadId, PartNumber, Body):
        self.uploads[UploadId][PartNumber] = Body
        return {"ETag": f'"etag-{PartNumber}"'}

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        parts = self.uploads.pop(UploadId)
        self.objects[Key] = b"".join(parts[p["PartNumber"]] for p in MultipartUpload["Parts"])

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.uploads.pop(UploadId)
        self.aborted.append(Key)

    def head_object(self, Bucket, Key):
        return {"ContentLength": len(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)

    def add_backup(self, created, data=b"x" * 4 * 1024 * 1024):
        key = backup_key(created)
        self.objects[key] = data
        digest = hashlib.sha256(data).hexdigest()
        self.objects[checksum_key(key)] = f"{digest}  {key.rsplit('/', 1)[-1]}\n".encode()
        return key


class FakeProcess:
    """Подмена subprocess.Popen: pg_dump отдаёт data, pg_restore пишет toc."""

    def __init__(self, data=b"", toc=b"", returncode=0, error=b""):
        self.data = data
        self.toc = toc
        self.returncode = returncode
        self.error = error
        self.calls = []

    def __call__(self, args, stdout=None, stderr=None, env=None, stdin=None):
        self.calls.append({"args": args, "env": env})
        self.stdout = io.BytesIO(self.data)
        self.stdin = io.BytesIO()
        if stdin is not None and stdout is not None and hasattr(stdout, "write"):
            stdout.write(self.toc)
        stderr.write(self.error)
        return self

    def wait(self):
        return self.returncode

    def kill(self):
        pass


def _toc(*tables):
    return "".join(
        f"{index}; 0 1638{index} TABLE DATA public {table} pharmaturk\n"
        for index, table in enumerate(tables, start=1)
    ).encode()


def _backups(*moments):
    return [Backup(backup_key(moment), moment, 1) for moment in moments]


def test_retention_keeps_seven_days_four_weeks_three_months():
    backups = _backups(*(NOW - timedelta(days=offset) for offset in range(120)))

    kept = select_retained(backups)

    expected_days = [NOW - timedelta(days=offset) for offset in range(7)]  # 13–19 октября
    expected_weeks = [
        datetime(2026, 10, 18, 2, 15, tzinfo=timezone.utc),  # воскресенье 42-й недели
        datetime(2026, 10, 11, 2, 15, tzinfo=timezone.utc),
        datetime(2026, 10, 4, 2, 15, tzinfo=timezone.utc),
    ]
    expected_months = [
        datetime(2026, 9, 30, 2, 15, tzinfo=timezone.utc),
        datetime(2026, 8, 31, 2, 15, tzinfo=timezone.utc),
    ]
    assert kept == {backup_key(m) for m in expected_days + expected_weeks + expected_months}


def test_retention_keeps_only_newest_backup_of_a_day():
    morning = NOW - timedelta(hours=2)
    backups = _backups(morning, NOW)

    assert select_retained(backups) == {backup_key(NOW)}


def test_list_backups_follows_pages_and_ignores_foreign_objects():
    client = FakeS3(page_size=2)
    keys = [client.add_backup(NOW - timedelta(days=offset)) for offset in range(3)]
    client.objects["postgres/notes.txt"] = b"x"

    with override_settings(**BACKUP_SETTINGS):
        backups = list_backups(client)

    assert [backup.key for backup in backups] == list(reversed(keys))


@override_settings(**BACKUP_SETTINGS)
def test_create_backup_streams_parts_and_rotates(monkeypatch):
    monkeypatch.setattr(db_backup, "PART_SIZE", 1024 * 1024)
    client = FakeS3()
    old_keys = [client.add_backup(NOW - timedelta(days=offset)) for offset in range(1, 10)]
    data = os.urandom(3 * 1024 * 1024 + 17)
    process = FakeProcess(data=data)
    monkeypatch.setattr(db_backup.subprocess, "Popen", process)

    result = create_backup(client, now=NOW)

    key = backup_key(NOW)
    assert result["status"] == "ok"
    assert client.objects[key] == data
    digest = hashlib.sha256(data).hexdigest()
    assert client.objects[checksum_key(key)] == f"{digest}  {key.rsplit('/', 1)[-1]}\n".encode()
    assert result["sha256"] == digest
    assert len(client.uploads) == 0
    # Остаются 13–19.10 (дни) и 11.10 (воскресенье прошлой недели);
    # 12.10 и 10.10 не самые свежие ни в своём дне-периоде, ни в неделе.
    assert sorted(result["deleted"]) == sorted([old_keys[6], old_keys[8]])
    for deleted in result["deleted"]:
        assert deleted not in client.objects
        assert checksum_key(deleted) not in client.objects
    call = process.calls[0]
    assert call["args"] == ["pg_dump", "--format=custom", "--no-password"]
    assert call["env"]["PGPASSWORD"]
    assert not any(call["env"]["PGPASSWORD"] in arg for arg in call["args"])


@override_settings(**BACKUP_SETTINGS)
def test_failed_pg_dump_aborts_upload_and_keeps_old_backups(monkeypatch):
    client = FakeS3()
    old_key = client.add_backup(NOW - timedelta(days=30))
    process = FakeProcess(data=b"partial", returncode=1, error=b"connection refused")
    monkeypatch.setattr(db_backup.subprocess, "Popen", process)

    with pytest.raises(BackupError, match="connection refused"):
        create_backup(client, now=NOW)

    assert client.aborted == [backup_key(NOW)]
    assert backup_key(NOW) not in client.objects
    assert old_key in client.objects


@override_settings(**BACKUP_SETTINGS)
def test_shrunken_dump_is_kept_but_rotation_is_skipped(monkeypatch):
    client = FakeS3()
    old_keys = [client.add_backup(NOW - timedelta(days=offset)) for offset in range(1, 10)]
    monkeypatch.setattr(db_backup.subprocess, "Popen", FakeProcess(data=b"y" * 1536 * 1024))

    with pytest.raises(BackupError, match="меньше половины"):
        create_backup(client, now=NOW)

    assert backup_key(NOW) in client.objects
    assert all(key in client.objects for key in old_keys)


@override_settings(**BACKUP_SETTINGS)
def test_verify_checks_checksum_and_table_of_contents(monkeypatch):
    client = FakeS3()
    key = client.add_backup(NOW - timedelta(hours=1))
    process = FakeProcess(toc=_toc("catalog_product", "orders_order", "users"))
    monkeypatch.setattr(db_backup.subprocess, "Popen", process)

    result = verify_latest_backup(client, now=NOW)

    assert result["status"] == "ok"
    assert result["key"] == key
    assert process.calls[0]["args"] == ["pg_restore", "--list"]


@override_settings(**BACKUP_SETTINGS)
def test_verify_rejects_corrupted_copy(monkeypatch):
    client = FakeS3()
    key = client.add_backup(NOW - timedelta(hours=1))
    client.objects[key] = client.objects[key][:-1] + b"z"
    monkeypatch.setattr(
        db_backup.subprocess, "Popen", FakeProcess(toc=_toc("catalog_product", "orders_order", "users"))
    )

    with pytest.raises(BackupError, match="контрольная сумма"):
        verify_latest_backup(client, now=NOW)


@override_settings(**BACKUP_SETTINGS)
def test_verify_rejects_dump_without_key_tables(monkeypatch):
    client = FakeS3()
    client.add_backup(NOW - timedelta(hours=1))
    monkeypatch.setattr(db_backup.subprocess, "Popen", FakeProcess(toc=_toc("catalog_product")))

    with pytest.raises(BackupError, match="orders_order, users"):
        verify_latest_backup(client, now=NOW)


@override_settings(**BACKUP_SETTINGS)
def test_verify_alerts_when_daily_backup_stopped():
    client = FakeS3()
    client.add_backup(NOW - timedelta(hours=27))

    with pytest.raises(BackupError, match="старше суток"):
        verify_latest_backup(client, now=NOW)


@override_settings(**BACKUP_SETTINGS)
def test_restore_check_is_skipped_without_disk_space(monkeypatch):
    client = FakeS3()
    client.add_backup(NOW - timedelta(hours=1))
    cursor = Mock()
    cursor.fetchone.return_value = (2 * 1024**3,)
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(db_backup, "_connect", Mock(return_value=connection))
    monkeypatch.setattr(
        db_backup.shutil, "disk_usage", Mock(return_value=Mock(free=7 * 1024**3))
    )
    drop = Mock()
    monkeypatch.setattr(db_backup, "_drop_restore_database", drop)

    result = db_backup.restore_check(client, list_backups(client)[-1])

    assert result["status"] == "skipped"
    drop.assert_not_called()


@override_settings(DB_BACKUP_ENABLED=False)
def test_tasks_do_nothing_until_enabled():
    with patch.object(db_backup, "create_backup") as create:
        assert run_database_backup() == {"status": "disabled"}
    create.assert_not_called()


@override_settings(**{**BACKUP_SETTINGS, "DB_BACKUP_HEARTBEAT_URL": "https://hc-ping.com/uuid"})
def test_successful_backup_pings_heartbeat():
    with patch.object(db_backup, "create_backup", return_value={"status": "ok"}), patch.object(
        db_backup.requests, "get"
    ) as get, patch("apps.monitoring.tasks.send_admin_telegram_notification") as notify:
        assert run_database_backup() == {"status": "ok"}

    get.assert_called_once_with("https://hc-ping.com/uuid", timeout=10)
    notify.assert_not_called()


@override_settings(**{**BACKUP_SETTINGS, "DB_BACKUP_HEARTBEAT_URL": "https://hc-ping.com/uuid"})
def test_failed_backup_alerts_telegram_and_skips_heartbeat():
    with patch.object(
        db_backup, "create_backup", side_effect=BackupError("pg_dump завершился с кодом 1")
    ), patch.object(db_backup.requests, "get") as get, patch(
        "apps.monitoring.tasks.send_admin_telegram_notification"
    ) as notify:
        result = run_database_backup()

    assert result["status"] == "failed"
    get.assert_not_called()
    text = notify.call_args.args[0]
    assert "ежедневная копия" in text
    assert "pg_dump завершился с кодом 1" in text


@override_settings(**BACKUP_SETTINGS)
def test_unexpected_check_error_is_reported_without_secrets():
    with patch.object(
        db_backup, "verify_latest_backup", side_effect=ConnectionError("endpoint unreachable")
    ), patch("apps.monitoring.tasks.send_admin_telegram_notification") as notify:
        result = check_database_backup()

    assert result == {"status": "failed", "error": "ConnectionError: endpoint unreachable"}
    text = notify.call_args.args[0]
    assert "еженедельная проверка" in text
    assert "backup-secret" not in text


@override_settings(**BACKUP_SETTINGS)
def test_skipped_restore_check_is_reported():
    skipped = {"status": "ok", "restore": {"status": "skipped", "reason": "мало места"}}
    with patch.object(db_backup, "verify_latest_backup", return_value=skipped), patch(
        "apps.monitoring.tasks.send_admin_telegram_notification"
    ) as notify:
        assert check_database_backup() == skipped

    assert "мало места" in notify.call_args.args[0]


def test_configuration_check_requires_separate_bucket_and_keys():
    with override_settings(
        **{
            **BACKUP_SETTINGS,
            "DB_BACKUP_S3_ENDPOINT_URL": "http://insecure",
            "DB_BACKUP_S3_BUCKET": "mudaroba-media",
            "DB_BACKUP_S3_ACCESS_KEY_ID": "media-key",
            "TELEGRAM_CHAT_ID": "",
        }
    ):
        ids = sorted(error.id for error in db_backup_configuration_check(None))

    assert ids == ["monitoring.E010", "monitoring.E011", "monitoring.E012", "monitoring.E013"]

    with override_settings(**BACKUP_SETTINGS):
        assert db_backup_configuration_check(None) == []


@pytest.mark.skipif(
    not (shutil.which("pg_dump") and shutil.which("pg_restore")), reason="needs PostgreSQL client"
)
@pytest.mark.django_db(transaction=True)
def test_real_dump_round_trip_and_restore_check(monkeypatch):
    from apps.catalog.models import Product

    Product.objects.create(name="Backup check", slug="backup-check", product_type="clothing")
    client = FakeS3()
    # Тестовая база меньше 1 МиБ — порог «пустого дампа» здесь не проверяем.
    monkeypatch.setattr(db_backup, "MIN_SIZE_BYTES", 0)
    monkeypatch.setattr(db_backup, "RESTORE_DISK_RESERVE_BYTES", 0)

    with override_settings(**{**BACKUP_SETTINGS, "DB_BACKUP_TEST_RESTORE_ENABLED": True}):
        created = create_backup(client)
        result = verify_latest_backup(client)

    assert result["key"] == created["key"]
    assert result["sha256"] == created["sha256"]
    assert result["restore"]["status"] == "ok"
    assert result["restore"]["rows"]["catalog_product"] == 1
