"""Ежедневный pg_dump прода во внешний S3-совместимый бакет (docs/DB_BACKUP.md).

Дамп идёт потоком: stdout pg_dump режется на части по 16 МиБ и уходит
multipart-загрузкой, на локальный диск ничего не пишется, в памяти одна часть.
Проверка читает копию из бакета тоже потоком.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import boto3
import psycopg2
import requests
from botocore.config import Config
from django.conf import settings
from psycopg2 import sql

logger = logging.getLogger(__name__)

KEY_PREFIX = "postgres/"
KEY_RE = re.compile(r"^postgres/mudaroba-(\d{8}T\d{6}Z)\.dump$")
PART_SIZE = 16 * 1024 * 1024
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 7, 4, 3
MIN_SIZE_BYTES = 1024 * 1024
# Дамп меньше половины предыдущего — почти наверняка пустая или урезанная база
# (как при вайпе 2026-06-14): копию сохраняем, но ротацию не запускаем, чтобы
# она не вытеснила хорошие копии.
MIN_SIZE_RATIO = 0.5
MAX_AGE = timedelta(hours=26)
# Без этих таблиц восстановленная база бесполезна.
REQUIRED_TABLES = ("catalog_product", "orders_order", "users")
RESTORE_DB_NAME = "mudaroba_restore_check"
# Пробное восстановление не должно съесть запас под образы следующего релиза.
RESTORE_DISK_RESERVE_BYTES = 4 * 1024**3


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class Backup:
    key: str
    created: datetime
    size: int


def backup_key(now: datetime) -> str:
    return f"{KEY_PREFIX}mudaroba-{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.dump"


def checksum_key(key: str) -> str:
    return f"{key}.sha256"


def select_retained(
    backups: list[Backup],
    *,
    daily: int = KEEP_DAILY,
    weekly: int = KEEP_WEEKLY,
    monthly: int = KEEP_MONTHLY,
) -> set[str]:
    """Самая свежая копия в каждом из N последних дней, ISO-недель и месяцев."""
    newest_first = sorted(backups, key=lambda item: item.created, reverse=True)
    keep = set()
    for limit, period_of in (
        (daily, lambda moment: moment.date()),
        (weekly, lambda moment: moment.isocalendar()[:2]),
        (monthly, lambda moment: (moment.year, moment.month)),
    ):
        periods = set()
        for backup in newest_first:
            period = period_of(backup.created)
            if period in periods:
                continue
            if len(periods) == limit:
                break
            periods.add(period)
            keep.add(backup.key)
    return keep


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.DB_BACKUP_S3_ENDPOINT_URL,
        aws_access_key_id=settings.DB_BACKUP_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.DB_BACKUP_S3_SECRET_ACCESS_KEY,
        region_name=settings.DB_BACKUP_S3_REGION,
        config=Config(
            connect_timeout=10,
            read_timeout=120,
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def list_backups(client) -> list[Backup]:
    bucket = settings.DB_BACKUP_S3_BUCKET
    backups = []
    kwargs = {"Bucket": bucket, "Prefix": KEY_PREFIX}
    while True:
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents", []):
            match = KEY_RE.match(item["Key"])
            if match:
                created = datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
                backups.append(Backup(item["Key"], created, item["Size"]))
        if not page.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = page["NextContinuationToken"]
    return sorted(backups, key=lambda item: item.created)


def _pg_settings(dbname: str | None = None) -> dict:
    db = settings.DATABASES["default"]
    return {
        "host": db.get("HOST") or "localhost",
        "port": str(db.get("PORT") or 5432),
        "user": db["USER"],
        "password": db["PASSWORD"],
        "dbname": dbname or db["NAME"],
    }


def _pg_env(dbname: str | None = None) -> dict:
    """Пароль — через окружение, не в аргументах (их видно в ps)."""
    params = _pg_settings(dbname)
    return {
        **os.environ,
        "PGHOST": params["host"],
        "PGPORT": params["port"],
        "PGUSER": params["user"],
        "PGPASSWORD": params["password"],
        "PGDATABASE": params["dbname"],
    }


def _tail(stream) -> str:
    stream.seek(0)
    return stream.read()[-500:].decode(errors="replace").strip()


def _read_part(stream, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def create_backup(client=None, *, now: datetime | None = None) -> dict:
    client = client or s3_client()
    bucket = settings.DB_BACKUP_S3_BUCKET
    key = backup_key(now or datetime.now(timezone.utc))
    previous = list_backups(client)

    digest = hashlib.sha256()
    size = 0
    parts = []
    with tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            ["pg_dump", "--format=custom", "--no-password"],
            stdout=subprocess.PIPE,
            stderr=stderr,
            env=_pg_env(),
        )
        upload_id = client.create_multipart_upload(
            Bucket=bucket, Key=key, ContentType="application/octet-stream"
        )["UploadId"]
        try:
            while chunk := _read_part(process.stdout, PART_SIZE):
                digest.update(chunk)
                size += len(chunk)
                number = len(parts) + 1
                response = client.upload_part(
                    Bucket=bucket, Key=key, UploadId=upload_id, PartNumber=number, Body=chunk
                )
                parts.append({"PartNumber": number, "ETag": response["ETag"]})
            returncode = process.wait()
            if returncode != 0:
                raise BackupError(f"pg_dump завершился с кодом {returncode}: {_tail(stderr)}")
            if not parts:
                raise BackupError("pg_dump вернул пустой поток")
            client.complete_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
            )
        except BaseException:
            process.kill()
            process.wait()
            try:
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
            except Exception:  # noqa: BLE001 - исходная ошибка важнее
                logger.warning("db_backup_abort_upload_failed")
            raise
        finally:
            process.stdout.close()

    stored_size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if stored_size != size:
        raise BackupError(f"в бакете {stored_size} байт вместо {size}: {key}")
    sha256 = digest.hexdigest()
    client.put_object(
        Bucket=bucket,
        Key=checksum_key(key),
        Body=f"{sha256}  {key.rsplit('/', 1)[-1]}\n".encode(),
        ContentType="text/plain",
    )

    if size < MIN_SIZE_BYTES:
        raise BackupError(f"дамп подозрительно мал ({size} байт), ротация пропущена: {key}")
    if previous and size < previous[-1].size * MIN_SIZE_RATIO:
        raise BackupError(
            f"дамп {_mib(size)} — меньше половины предыдущего ({_mib(previous[-1].size)}), "
            f"ротация пропущена: {key}"
        )

    deleted = rotate(client, list_backups(client))
    return {"status": "ok", "key": key, "size": size, "sha256": sha256, "deleted": deleted}


def rotate(client, backups: list[Backup]) -> list[str]:
    bucket = settings.DB_BACKUP_S3_BUCKET
    keep = select_retained(backups)
    expired = [backup.key for backup in backups if backup.key not in keep]
    for key in expired:
        client.delete_object(Bucket=bucket, Key=key)
        client.delete_object(Bucket=bucket, Key=checksum_key(key))
    return expired


def _mib(size: int) -> str:
    return f"{size / 1024 / 1024:.1f} МиБ"


def _expected_sha256(client, key: str) -> str:
    body = client.get_object(Bucket=settings.DB_BACKUP_S3_BUCKET, Key=checksum_key(key))["Body"]
    fields = body.read().decode(errors="replace").split()
    value = fields[0] if fields else ""
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BackupError(f"нет корректной контрольной суммы для {key}")
    return value


def _stream_to_process(client, key: str, args: list[str], *, stdout, env: dict) -> str:
    """Скачивает объект потоком в stdin процесса и возвращает sha256 всего объекта.

    pg_restore --list читает только оглавление и закрывает stdin раньше конца
    файла — остаток всё равно дочитываем ради контрольной суммы.
    """
    body = client.get_object(Bucket=settings.DB_BACKUP_S3_BUCKET, Key=key)["Body"]
    digest = hashlib.sha256()
    with tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, env=env)
        feeding = True
        try:
            while chunk := body.read(1024 * 1024):
                digest.update(chunk)
                if feeding:
                    try:
                        process.stdin.write(chunk)
                    except BrokenPipeError:
                        feeding = False
            with contextlib.suppress(BrokenPipeError):
                process.stdin.close()
        except BaseException:
            process.kill()
            raise
        finally:
            returncode = process.wait()
        if returncode != 0:
            raise BackupError(f"{args[0]} завершился с кодом {returncode}: {_tail(stderr)}")
    return digest.hexdigest()


def verify_latest_backup(client=None, *, now: datetime | None = None) -> dict:
    client = client or s3_client()
    now = now or datetime.now(timezone.utc)
    backups = list_backups(client)
    if not backups:
        raise BackupError("в бакете нет ни одной копии")
    latest = backups[-1]
    if now - latest.created > MAX_AGE:
        raise BackupError(f"последняя копия старше суток: {latest.key}")

    expected = _expected_sha256(client, latest.key)
    with tempfile.TemporaryFile() as listing:
        actual = _stream_to_process(
            client, latest.key, ["pg_restore", "--list"], stdout=listing, env=_pg_env()
        )
        listing.seek(0)
        toc = listing.read().decode(errors="replace")
    if actual != expected:
        raise BackupError(f"контрольная сумма не совпала: {latest.key}")
    missing = [
        table
        for table in REQUIRED_TABLES
        if not re.search(rf" TABLE DATA public {re.escape(table)} ", toc)
    ]
    if missing:
        raise BackupError(f"в оглавлении дампа нет таблиц {', '.join(missing)}: {latest.key}")

    result = {"status": "ok", "key": latest.key, "size": latest.size, "sha256": actual}
    if settings.DB_BACKUP_TEST_RESTORE_ENABLED:
        result["restore"] = restore_check(client, latest)
    return result


def _connect(dbname: str | None = None):
    params = _pg_settings(dbname)
    connection = psycopg2.connect(**params, connect_timeout=10)
    connection.autocommit = True
    return connection


def _drop_restore_database() -> None:
    with contextlib.closing(_connect()) as connection, connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(RESTORE_DB_NAME)
            )
        )


def restore_check(client, backup: Backup) -> dict:
    """Восстанавливает копию в одноразовую базу на том же сервере и удаляет её."""
    with contextlib.closing(_connect()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        database_size = cursor.fetchone()[0]
    # Контейнер воркера и том Postgres лежат на одном диске хоста.
    free = shutil.disk_usage("/").free
    needed = database_size * 2 + RESTORE_DISK_RESERVE_BYTES
    if free < needed:
        return {"status": "skipped", "reason": f"свободно {_mib(free)}, нужно {_mib(needed)}"}

    _drop_restore_database()
    with contextlib.closing(_connect()) as connection, connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(RESTORE_DB_NAME)))
    try:
        _stream_to_process(
            client,
            backup.key,
            [
                "pg_restore",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                f"--dbname={RESTORE_DB_NAME}",
            ],
            stdout=subprocess.DEVNULL,
            env=_pg_env(RESTORE_DB_NAME),
        )
        with contextlib.closing(_connect(RESTORE_DB_NAME)) as connection, connection.cursor() as cursor:
            rows = {}
            for table in REQUIRED_TABLES:
                cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
                rows[table] = cursor.fetchone()[0]
    finally:
        _drop_restore_database()
    if not rows["catalog_product"]:
        raise BackupError(f"в восстановленной базе нет товаров: {backup.key}")
    return {"status": "ok", "rows": rows}


def ping_heartbeat() -> None:
    """Внешний «пульс» (healthchecks.io): тревога приходит, даже если сервер
    или Celery Beat умерли и сами сообщить не могут."""
    url = settings.DB_BACKUP_HEARTBEAT_URL
    if not url:
        return
    try:
        requests.get(url, timeout=10)
    except requests.RequestException:
        logger.warning("db_backup_heartbeat_failed")
