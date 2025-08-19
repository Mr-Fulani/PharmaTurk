"""Базовые классы и утилиты для парсеров."""

from .scraper import BaseScraper, ScrapedProduct
from .selectors import DataSelector, SelectorConfig
from .utils import normalize_price, clean_text, extract_images

__all__ = [
    'BaseScraper',
    'ScrapedProduct', 
    'DataSelector',
    'SelectorConfig',
    'normalize_price',
    'clean_text',
    'extract_images',
]
