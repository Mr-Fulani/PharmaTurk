"""Ночная копия медиа в бакет бэкапов (docs/DB_BACKUP.md).

Копируются баннеры, карточки брендов и категорий (``marketing/``), og-картинки
страниц (``pages/``), медиа услуг (``services/``) и с 24.10.2026 — фото товаров
(``products/``, ≈ 20 ГБ, ≈ 98 тыс. файлов; решение владельца, TD-013). Временные
файлы парсеров (``products/parsed/``) не копируются: их чистит сам парсер.

- Ночь ограничена ``MEDIA_BACKUP_TIME_BUDGET_SECONDS``: первая копия фото товаров идёт
  несколько ночей (или вручную без предела, docs/DB_BACKUP.md). Манифест сохраняется по
  ходу, прерванная копия продолжается со следующего файла; ``last_success_at`` — только
  у копии, дошедшей до конца.

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
import time
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
# Первая копия фото товаров идёт по ночам: полной копии нет — тревога, только если так неделю.
MAX_INCOMPLETE_AGE = timedelta(days=8)
MAX_MISSING_SHARE = 0.5
# Манифест пишется каждые N скопированных файлов: обрыв задачи не теряет прогресс.
MANIFEST_FLUSH_EVERY = 500
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


def is_quiet_missing(key: str) -> bool:
    """Фото товаров пропадают штатно (перескрейп, cleanup_orphaned_media): копия хранится, без тревоги."""
    location = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
    return key.startswith(f"{location}/products/" if location else "products/")


def excluded_prefixes() -> list[str]:
    location = (getattr(settings, "R2_CONFIG", {}).get("prefix", "") or "").strip("/")
    return [
        f"{location}/{prefix.strip('/')}/" if location else f"{prefix.strip('/')}/"
        for prefix in getattr(settings, "MEDIA_BACKUP_EXCLUDE_PREFIXES", [])
    ]


def _list(client, bucket: str, prefix: str, exclude: tuple[str, ...] = ()) -> dict[str, dict]:
    objects = {}
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents", []):
            if exclude and item["Key"].startswith(exclude):
                continue
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


def _save_manifest(target, manifest: dict) -> None:
    target.put_object(
        Bucket=settings.DB_BACKUP_S3_BUCKET,
        Key=MANIFEST_KEY,
        Body=json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode(),
        ContentType="application/json",
    )


def backup_media(
    source=None,
    target=None,
    *,
    now: datetime | None = None,
    allow_mass_missing: bool = False,
    time_budget: float | None = None,
    clock=time.monotonic,
) -> dict:
    """Копия новых и изменённых файлов; ``time_budget`` (с) — остановиться и продолжить в следующий раз."""
    source = source or media_client()
    target = target or db_backup.s3_client()
    now = now or datetime.now(timezone.utc)
    deadline = clock() + time_budget if time_budget else None
    media_bucket, backup_bucket = settings.R2_BUCKET_NAME, settings.DB_BACKUP_S3_BUCKET
    manifest = load_manifest(target)
    files = manifest["files"]
    current = {}
    exclude = tuple(excluded_prefixes())
    for prefix in source_prefixes():
        current.update(_list(source, media_bucket, prefix, exclude))
    stored = {key: item for key, item in _list(target, backup_bucket, KEY_PREFIX).items() if key != MANIFEST_KEY}

    known = set(files) | {key[len(KEY_PREFIX):] for key in stored}
    missing = sorted(known - set(current))
    if known and len(missing) > len(known) * MAX_MISSING_SHARE and not allow_mass_missing:
        raise BackupError(
            f"из бакета медиа пропало {len(missing)} из {len(known)} файлов — копия не тронута; "
            f"примеры: {', '.join(missing[:5])}"
        )

    copied, copied_bytes, complete = [], 0, True
    for key, item in sorted(current.items()):
        if deadline is not None and clock() >= deadline:
            complete = False
            break
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
        if len(copied) % MANIFEST_FLUSH_EVERY == 0:
            _save_manifest(target, manifest)

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

    manifest["last_run_at"] = now.isoformat()
    if complete:
        manifest["last_success_at"] = now.isoformat()
    _save_manifest(target, manifest)
    return {
        "status": "ok" if complete else "partial",
        "remaining": sum(1 for key in current if key not in files or files[key].get("etag") != current[key]["etag"]),
        "files": len(current),
        "copied": len(copied),
        "copied_bytes": copied_bytes,
        "missing": len(missing),
        "newly_missing": newly_missing,
        "deleted": deleted,
        "keep_until": (now + keep_until).date().isoformat(),
    }


def verify_media_backup(target=None, *, now: datetime | None = None) -> dict:
    """Копия свежая (последний запуск не старше 26 ч), полная — не старше 8 дней, файлы манифеста на месте."""
    target = target or db_backup.s3_client()
    now = now or datetime.now(timezone.utc)
    manifest = load_manifest(target)
    last = manifest.get("last_success_at")
    last_run = manifest.get("last_run_at") or last
    if not last_run:
        raise BackupError("копии медиа ещё нет")
    if now - datetime.fromisoformat(last_run) > MAX_AGE:
        raise BackupError(f"последняя копия медиа старше суток: {last_run}")
    if not last or now - datetime.fromisoformat(last) > MAX_INCOMPLETE_AGE:
        raise BackupError(f"копия медиа не доходит до конца больше недели (последняя полная: {last or 'нет'})")
    stored = _list(target, settings.DB_BACKUP_S3_BUCKET, KEY_PREFIX)
    broken = [
        key
        for key, entry in manifest["files"].items()
        if stored.get(KEY_PREFIX + key, {}).get("size") != entry.get("size")
    ]
    if broken:
        raise BackupError(f"в копии медиа нет или не того размера {len(broken)} файлов: {', '.join(broken[:5])}")
    return {"status": "ok", "files": len(manifest["files"]), "last_success_at": last, "last_run_at": last_run}


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
