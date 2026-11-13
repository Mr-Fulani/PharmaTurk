"""Прайс склада Selçuk Ecza — контроль цены и второе мнение о наличии.

Открытый файл «WEBLISTE-ДД-ММ-ГГГГ.xlsx» со страницы поиска цен склада (обновляется при
смене цен). Колонки: штрихкод, название, розничная цена с НДС, фирма, дата изменения цены,
НДС, … Позиции «не производится» склад держит под фирмой «ZZZ URETILMEYEN».
«Нет у склада» — подсказка, не приговор: склад возит ~6 тыс. позиций из ~12 тыс. наших.
Только для внутренней проверки: склад на витрине не называется (docs/DRUG_CHECK.md).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from apps.drug_check.models import DrugReferenceEntry
from apps.drug_check.xlsx import Workbook, XlsxError, barcode_from, cell, excel_date

from .base import ALERT, OK, WARN, CheckContext, FileSource, SourceResult, compare_price, price_short

SHEET = "WEBLISTE"
BARCODE, NAME, PRICE, FIRM, PRICE_DATE = 0, 1, 2, 3, 4
NOT_PRODUCED_FIRM = "ZZZ URETILMEYEN"


def _price(value: str) -> Decimal | None:
    try:
        price = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


class SelcukSource(FileSource):
    key = "selcuk"
    title = "Склад (Selçuk)"
    page_url = "https://selcukecza.com.tr/sayfa/ilac-fiyat-ve-barkod-arama/ilac-ve-barkod-arama"
    allowed_hosts = frozenset({"selcukecza.com.tr", "www.selcukecza.com.tr"})

    def find_file_url(self, page_html: str) -> tuple[str, str, date | None]:
        match = re.search(r'href="([^"]*?(WEBLISTE-(\d{2})-(\d{2})-(\d{4})\.xlsx))"', page_html, flags=re.I)
        if not match:
            raise ValueError("на странице склада не найден файл прайса WEBLISTE-….xlsx")
        day, month, year = (int(match.group(i)) for i in (3, 4, 5))
        try:
            file_date = date(year, month, day)
        except ValueError:
            file_date = None
        return match.group(1), match.group(2), file_date

    def parse(self, content: bytes, file_date: date | None) -> list[DrugReferenceEntry]:
        book = Workbook(content)
        if SHEET not in book.sheets:
            sheets = list(book.sheets)
            if len(sheets) != 1:
                raise XlsxError(f"в файле склада нет листа «{SHEET}»")
            sheet = sheets[0]
        else:
            sheet = SHEET
        entries: dict[str, DrugReferenceEntry] = {}
        for row in book.rows(sheet):
            barcode = barcode_from(cell(row, BARCODE))
            if len(barcode) < 8:
                continue  # заголовок и тестовые строки склада («123123123x»)
            firm = cell(row, FIRM)
            entries[barcode] = DrugReferenceEntry(
                source=self.key,
                barcode=barcode,
                name=cell(row, NAME)[:300],
                firm=firm[:200],
                status=(
                    DrugReferenceEntry.Status.NOT_PRODUCED
                    if firm.upper() == NOT_PRODUCED_FIRM
                    else DrugReferenceEntry.Status.LISTED
                ),
                price=_price(cell(row, PRICE)),
                price_date=excel_date(cell(row, PRICE_DATE)),
                file_date=file_date,
            )
        return list(entries.values())

    def describe(self, entry, ctx: CheckContext, result: SourceResult) -> SourceResult:
        if entry is None:
            result.level = WARN if ctx.our_available else OK
            result.status = "Нет в прайсе"
            result.note = "Подсказка, не приговор: склад возит не все препараты."
            result.short = "у склада нет"
            return result
        result.price = entry.price
        result.price_date = entry.price_date
        if entry.status == DrugReferenceEntry.Status.NOT_PRODUCED:
            result.level = WARN if ctx.our_available else OK
            result.status = "Не производится"
            result.note = "Склад держит позицию в группе «не производится»."
            result.short = "склад: не производится"
            return result
        comparison = compare_price(ctx.our_price, ctx.our_currency, entry.price)
        result.status = "Есть в прайсе"
        result.level = ALERT if comparison else OK
        if comparison:
            result.note = f"Цена склада другая: {comparison}."
        result.short = price_short("склад", entry.price, comparison)
        return result
