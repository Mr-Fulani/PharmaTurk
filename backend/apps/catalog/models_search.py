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
