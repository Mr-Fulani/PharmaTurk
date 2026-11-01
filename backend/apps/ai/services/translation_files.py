"""Файлы инструментов проверки переводов (TD-031): JSON и JSON lines, сжатые и нет, бэкапы строк."""

import gzip
import json
import os

from django.core import serializers
from django.core.management.base import CommandError


def open_text(path, mode="rt"):
    if str(path).endswith(".gz"):
        return gzip.open(path, mode, encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def read_json(path):
    with open_text(path) as handle:
        return json.load(handle)


def write_json(path, data, mode="wt"):
    with open_text(path, mode) as handle:
        json.dump(data, handle, ensure_ascii=False)


def read_jsonl(path):
    with open_text(path) as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path, rows) -> int:
    written = 0
    with open_text(path, "wt") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    return written


def require_backup(options) -> None:
    """Запись только с бэкапом, и прошлый бэкап не затирается повторным запуском."""
    if not options["apply"]:
        return
    if not options["backup"]:
        raise CommandError("--apply требует --backup <файл>")
    if os.path.exists(options["backup"]):
        raise CommandError(f"Файл бэкапа уже есть: {options['backup']}")


def write_rows_backup(path, objects) -> None:
    """Строки в формате loaddata; режим x: файл создаётся только новый."""
    with open_text(path, "xt") as handle:
        handle.write(serializers.serialize("json", objects))
