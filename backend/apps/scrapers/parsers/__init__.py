"""Конкретные реализации парсеров для различных сайтов."""

from .registry import ParserRegistry, get_parser

__all__ = [
    'ParserRegistry',
    'get_parser',
]
