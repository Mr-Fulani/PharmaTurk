"""Ночная копия медиа маркетинга, страниц и услуг в бакет бэкапов (docs/DB_BACKUP.md).

Товарные фото (products/, ≈ 19 ГБ) не копируются — решение владельца 22.10.2026:
их можно снова скачать парсерами. Копируются баннеры, карточки брендов и
категорий (``marketing/``), og-картинки страниц (``pages/``) и медиа услуг
(``services/``) — их сделали вручную.

- Копия — в бакете бэкапов БД (отдельный ключ, см. ``db_backup``) под ``media/``:
  ключ ``media/<ключ в бакете медиа>``. ``cleanup_orphaned_media`` этот бакет не видит.
- Копируются только новые и изменённые файлы: ETag и размер источника хранятся в
  манифесте ``media/.manifest.json``.
- Файл пропал из бакета медиа — копия хранится ещё MEDIA_BACKUP_KEEP_DELETED_DAYS
  дней, админу приходит отчёт. Пропала больше половины файлов разом (вайп
  14.06.2026) — копия не трогается вовсе, тревога каждую ночь.
- Файл идёт потоком частями по 8 МиБ: воркеру отведено 640 МиБ.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from django.conf import settings

from apps.monitoring import db_backup
from apps.monitoring.db_backup import BackupError

logger = logging.getLogger(__name__)

KEY_PREFIX = "media/"
MANIFEST_KEY = "media/.manifest.json"
MAX_AGE = timedelta(hours=26)
MAX_MISSING_SHARE = 0.5
TRANSFER = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,
    multipart_chunksize=8 * 1024 * 1024,
    max_concurrency=1,
    use_threads=False,
)


def media_client():
    from apps.catalog.utils.r2_utils import get_r2_client

    return get_r2_client()


def source_prefixes() -> list[str]:
    """Префиксы в бакете медиа с учётом окружения: на dev — dev/marketing/…"""
    location = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
    return [
        f"{location}/{prefix.strip('/')}/" if location else f"{prefix.strip('/')}/"
        for prefix in settings.MEDIA_BACKUP_PREFIXES
    ]


def _list(client, bucket: str, prefix: str) -> dict[str, dict]:
    objects = {}
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents", []):
            objects[item["Key"]] = {"etag": str(item.get("ETag", "")).strip('"'), "size": item["Size"]}
        if not page.get("IsTruncated"):
            return objects
        kwargs["ContinuationToken"] = page["NextContinuationToken"]


def load_manifest(target) -> dict:
    try:
        body = target.get_object(Bucket=settings.DB_BACKUP_S3_BUCKET, Key=MANIFEST_KEY)["Body"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return {"files": {}}
        raise
    manifest = json.loads(body.read())
    if not isinstance(manifest.get("files"), dict):
        raise BackupError(f"манифест копии медиа повреждён: {MANIFEST_KEY}")
    return manifest


def _stream(source, source_bucket: str, key: str, target, target_bucket: str, target_key: str, metadata: dict) -> None:
    obj = source.get_object(Bucket=source_bucket, Key=key)
    try:
        target.upload_fileobj(
            obj["Body"],
            target_bucket,
            target_key,
            ExtraArgs={
                "ContentType": obj.get("ContentType") or "application/octet-stream",
                "Metadata": metadata,
            },
            Config=TRANSFER,
        )
    finally:
        obj["Body"].close()


def backup_media(source=None, target=None, *, now: datetime | None = None, allow_mass_missing: bool = False) -> dict:
    source = source or media_client()
    target = target or db_backup.s3_client()
    now = now or datetime.now(timezone.utc)
    media_bucket, backup_bucket = settings.R2_BUCKET_NAME, settings.DB_BACKUP_S3_BUCKET
    manifest = load_manifest(target)
    files = manifest["files"]
    current = {}
    for prefix in source_prefixes():
        current.update(_list(source, media_bucket, prefix))
    stored = {key: item for key, item in _list(target, backup_bucket, KEY_PREFIX).items() if key != MANIFEST_KEY}

    known = set(files) | {key[len(KEY_PREFIX):] for key in stored}
    missing = sorted(known - set(current))
    if known and len(missing) > len(known) * MAX_MISSING_SHARE and not allow_mass_missing:
        raise BackupError(
            f"из бакета медиа пропало {len(missing)} из {len(known)} файлов — копия не тронута; "
            f"примеры: {', '.join(missing[:5])}"
        )

    copied, copied_bytes = [], 0
    for key, item in sorted(current.items()):
        target_key = KEY_PREFIX + key
        entry = files.get(key) or {}
        if (
            entry.get("etag") == item["etag"]
            and entry.get("size") == item["size"]
            and stored.get(target_key, {}).get("size") == item["size"]
        ):
            entry.pop("missing_since", None)
            continue
        _stream(source, media_bucket, key, target, backup_bucket, target_key, {"source-etag": item["etag"]})
        stored_size = target.head_object(Bucket=backup_bucket, Key=target_key)["ContentLength"]
        if stored_size != item["size"]:
            raise BackupError(f"в копии {stored_size} байт вместо {item['size']}: {key}")
        files[key] = {"etag": item["etag"], "size": item["size"], "copied_at": now.isoformat()}
        copied.append(key)
        copied_bytes += item["size"]

    newly_missing, deleted = [], []
    keep_until = timedelta(days=settings.MEDIA_BACKUP_KEEP_DELETED_DAYS)
    for key in missing:
        entry = files.setdefault(key, {"size": stored.get(KEY_PREFIX + key, {}).get("size")})
        if "missing_since" not in entry:
            entry["missing_since"] = now.isoformat()
            newly_missing.append(key)
        if now - datetime.fromisoformat(entry["missing_since"]) >= keep_until:
            target.delete_object(Bucket=backup_bucket, Key=KEY_PREFIX + key)
            files.pop(key)
            deleted.append(key)

    manifest["last_success_at"] = now.isoformat()
    target.put_object(
        Bucket=backup_bucket,
        Key=MANIFEST_KEY,
        Body=json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode(),
        ContentType="application/json",
    )
    return {
        "status": "ok",
        "files": len(current),
        "copied": len(copied),
        "copied_bytes": copied_bytes,
        "missing": len(missing),
        "newly_missing": newly_missing,
        "deleted": deleted,
        "keep_until": (now + keep_until).date().isoformat(),
    }


def verify_media_backup(target=None, *, now: datetime | None = None) -> dict:
    """Копия свежая (последний успех не старше 26 ч) и каждый файл манифеста на месте."""
    target = target or db_backup.s3_client()
    now = now or datetime.now(timezone.utc)
    manifest = load_manifest(target)
    last = manifest.get("last_success_at")
    if not last:
        raise BackupError("копии медиа ещё нет")
    if now - datetime.fromisoformat(last) > MAX_AGE:
        raise BackupError(f"последняя копия медиа старше суток: {last}")
    stored = _list(target, settings.DB_BACKUP_S3_BUCKET, KEY_PREFIX)
    broken = [
        key
        for key, entry in manifest["files"].items()
        if stored.get(KEY_PREFIX + key, {}).get("size") != entry.get("size")
    ]
    if broken:
        raise BackupError(f"в копии медиа нет или не того размера {len(broken)} файлов: {', '.join(broken[:5])}")
    return {"status": "ok", "files": len(manifest["files"]), "last_success_at": last}


def restore_plan(path: str, source=None, target=None) -> list[dict]:
    """Что вернуть в бакет медиа из копии: файл или все файлы под префиксом ``path``.

    ``state``: missing — в бакете медиа нет, changed — другой размер, present — на месте.
    """
    source = source or media_client()
    target = target or db_backup.s3_client()
    path = path.lstrip("/")
    if not any(path.startswith(prefix) for prefix in source_prefixes()):
        raise BackupError(f"в копии только {', '.join(source_prefixes())}, а не {path!r}")
    stored = _list(target, settings.DB_BACKUP_S3_BUCKET, KEY_PREFIX + path)
    plan = []
    for target_key, item in sorted(stored.items()):
        key = target_key[len(KEY_PREFIX):]
        if target_key == MANIFEST_KEY or not any(key.startswith(prefix) for prefix in source_prefixes()):
            continue
        try:
            size = source.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)["ContentLength"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                raise
            size = None
        state = "missing" if size is None else ("changed" if size != item["size"] else "present")
        plan.append({"key": key, "size": item["size"], "state": state})
    return plan


def restore(plan: list[dict], *, overwrite: bool = False, source=None, target=None) -> list[str]:
    """Вернуть файлы плана в бакет медиа: пропавшие, а с overwrite — и изменённые."""
    source = source or media_client()
    target = target or db_backup.s3_client()
    restored = []
    for item in plan:
        if item["state"] == "missing" or (overwrite and item["state"] == "changed"):
            _stream(
                target, settings.DB_BACKUP_S3_BUCKET, KEY_PREFIX + item["key"],
                source, settings.R2_BUCKET_NAME, item["key"], {},
            )
            restored.append(item["key"])
    return restored
