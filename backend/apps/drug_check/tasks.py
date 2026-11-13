"""Еженедельная загрузка справочных файлов проверки лекарств (TD-044)."""

import logging

from config.celery import app

from .sources import file_sources

logger = logging.getLogger(__name__)


@app.task(name="drug_check.load_reference_files")
def load_reference_files() -> dict:
    """Скачивает файлы SKRS и склада, если они новые. Итог каждой загрузки — в админке."""
    summary = {}
    for source in file_sources():
        load = source.download_and_load()
        summary[source.key] = {"result": load.result, "rows": load.rows, "file": load.file_name}
        logger.info("drug_reference_load", extra={"source": source.key, **summary[source.key]})
    return summary
