"""Источники проверки лекарства. Новый источник — модуль рядом и строка в SOURCES.

Порядок списка — порядок строк в окне проверки и в сообщении о заявке.
"""

from .ilacfiyati import IlacFiyatiSource
from .selcuk import SelcukSource
from .skrs import SkrsSource

SOURCES = [
    SkrsSource(),
    IlacFiyatiSource(),
    SelcukSource(),
]


def file_sources():
    """Источники, у которых раз в неделю скачивается файл (load_drug_reference_files)."""
    from .base import FileSource

    return [source for source in SOURCES if isinstance(source, FileSource)]


def get_source(key: str):
    return next((source for source in SOURCES if source.key == key), None)
