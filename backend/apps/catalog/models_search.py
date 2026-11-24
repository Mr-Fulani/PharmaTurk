"""Подготовленный текст товара для поиска на сайте. Устройство — docs/PRODUCT_SEARCH.md.

Хранится отдельно от основного models.py, как models_stock. Строки собирает
``apps.catalog.product_search``: при сохранении товара и командой
``rebuild_product_search_index``. Отдельная таблица, а не колонка ``Product``:
пересчёт не переписывает строку товара с тяжёлым ``external_data``.
"""
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils.translation import gettext_lazy as _


class ProductSearchIndex(models.Model):
    """Нормализованный текст одного товара (нижний регистр, ё→е, турецкие буквы → латиница)."""

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="search_index",
        verbose_name=_("Товар"),
    )
    # Названия товара (основное, переводы, доменная запись) — по одному в строке.
    name = models.TextField(_("Названия"), blank=True, default="")
    # Бренд и его переводы — по одному в строке.
    brand = models.TextField(_("Бренд"), blank=True, default="")
    # Всё, по чему ищется товар: названия, бренд, производитель, вещество, коды.
    text = models.TextField(_("Текст для поиска"), blank=True, default="")
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Поисковый текст товара")
        verbose_name_plural = _("Поисковые тексты товаров")
        indexes = [
            # Расширение pg_trgm создано миграцией 0207.
            GinIndex(fields=["text"], name="catalog_psi_text_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self):
        return f"{self.product_id}: {self.text[:80]}"


class SearchQueryStat(models.Model):
    """Что искали на странице /search и сколько нашлось: одна строка на запрос и язык.

    Без пользователя и адреса — только текст запроса. Пишет ``search_stats.record_search``;
    подсказки в шапке (запрос на каждую букву) сюда не попадают.
    """

    MODE_TITLES = {
        "words": "как написано",
        "layout": "другая раскладка",
        "translit": "латиница ↔ кириллица",
        "typo": "исправлена опечатка",
        "partial": "без лишнего слова",
    }

    query = models.CharField(_("Запрос"), max_length=120)
    locale = models.CharField(_("Язык"), max_length=5, default="ru")
    searches = models.PositiveIntegerField(_("Сколько раз искали"), default=0)
    results = models.PositiveIntegerField(_("Найдено товаров"), default=0, help_text=_("При последнем поиске."))
    mode = models.CharField(_("Как понят запрос"), max_length=10, blank=True, default="")
    corrected_query = models.CharField(_("Искали по запросу"), max_length=120, blank=True, default="")
    first_at = models.DateTimeField(_("Первый раз"), auto_now_add=True)
    last_at = models.DateTimeField(_("Последний раз"), auto_now=True)

    class Meta:
        verbose_name = _("Поисковый запрос")
        verbose_name_plural = _("Поисковые запросы")
        constraints = [models.UniqueConstraint(fields=["query", "locale"], name="catalog_searchquerystat_query_locale")]

    def __str__(self):
        return self.query
