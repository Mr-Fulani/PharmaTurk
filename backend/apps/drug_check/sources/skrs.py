"""SKRS E-Reçete TİTCK — государственный список «активных» и «пассивных» препаратов.

Еженедельный открытый файл (обычно по вторникам) на titck.gov.tr/dinamikmodul/43. Листы:
«AKTİF ÜRÜNLER LİSTESİ» и «PASİF ÜRÜNLER LİSTESİ» — штрихкод, фирма, ATC, дата включения
в лист; «DEĞİŞİKLİK YAPILAN ÜRÜNLER» — переведённые на этой неделе с причиной
(«по данным İTS нет на рынке»); «PASİFE ALINACAK ÜRÜNLER» — предупреждение заранее.
Пассивен = препарат не выписывается и, как правило, не продаётся в аптеках Турции.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from urllib.parse import unquote

from apps.drug_check.models import DrugReferenceEntry
from apps.drug_check.xlsx import Workbook, XlsxError, barcode_from, cell, excel_date

from .base import ALERT, OK, WARN, CheckContext, FileSource, SourceResult, fmt_date

ACTIVE_SHEET = "AKTİF ÜRÜNLER LİSTESİ"
PASSIVE_SHEET = "PASİF ÜRÜNLER LİSTESİ"
CHANGES_SHEET = "DEĞİŞİKLİK YAPILAN ÜRÜNLER"
TO_PASSIVE_SHEET = "PASİFE ALINACAK ÜRÜNLER"
HEADER = "Barkod"

# Колонки (от 0): название, штрихкод, ATC, имя ATC, фирма, вид рецепта, статус, пояснение, …
NAME, BARCODE, ATC, FIRM, NOTE = 0, 1, 2, 4, 7
ACTIVE_DATE, PASSIVE_DATE = 11, 8

# Пояснения файла по-русски; ключ — кусок турецкого текста без регистра и точек над i.
REASONS_RU = (
    ("its'ye gore piyasada bulunmad", "по данным İTS нет на рынке"),
    ("fiyat liste", "нет в действующем прайс-листе лекарств"),
    ("ruhsat", "регистрация отменена или приостановлена"),
)


def _fold(text: str) -> str:
    """«İTS'ye Göre» → «its'ye gore»: без турецких букв и регистра."""
    return unicodedata.normalize("NFKD", text.replace("ı", "i")).encode("ascii", "ignore").decode().lower()


def reason_ru(text: str) -> str:
    folded = _fold(text)
    for key, label in REASONS_RU:
        if key in folded:
            return label
    return text


class SkrsSource(FileSource):
    key = "skrs"
    title = "SKRS (TİTCK)"
    page_url = "https://www.titck.gov.tr/dinamikmodul/43"
    allowed_hosts = frozenset({"titck.gov.tr", "www.titck.gov.tr"})

    def find_file_url(self, page_html: str) -> tuple[str, str, date | None]:
        best = None
        for href in re.findall(r'href="([^"]+\.xlsx)"', page_html, flags=re.I):
            name = unquote(href.rsplit("/", 1)[-1])
            if "skrs" not in name.lower():
                continue
            match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", name)
            if not match:
                continue
            try:
                file_date = datetime.strptime(match.group(0), "%d.%m.%Y").date()
            except ValueError:
                continue
            if best is None or file_date > best[2]:
                best = (href, name, file_date)
        if best is None:
            raise ValueError("на странице TİTCK не найден файл SKRS E-Reçete (.xlsx)")
        return best

    @staticmethod
    def _data_rows(book: Workbook, sheet: str):
        started = False
        for row in book.rows(sheet):
            if not started:
                started = cell(row, BARCODE) == HEADER
                continue
            barcode = barcode_from(cell(row, BARCODE))
            if barcode:
                yield barcode, row

    def parse(self, content: bytes, file_date: date | None) -> list[DrugReferenceEntry]:
        book = Workbook(content)
        for sheet in (ACTIVE_SHEET, PASSIVE_SHEET):
            if sheet not in book.sheets:
                raise XlsxError(f"в файле SKRS нет листа «{sheet}»")
        reasons = {}
        if CHANGES_SHEET in book.sheets:
            reasons = {barcode: cell(row, NOTE) for barcode, row in self._data_rows(book, CHANGES_SHEET)}
        to_passive = set()
        if TO_PASSIVE_SHEET in book.sheets:
            to_passive = {barcode for barcode, _row in self._data_rows(book, TO_PASSIVE_SHEET)}

        entries: dict[str, DrugReferenceEntry] = {}
        for sheet, status, date_col in (
            (ACTIVE_SHEET, DrugReferenceEntry.Status.ACTIVE, ACTIVE_DATE),
            (PASSIVE_SHEET, DrugReferenceEntry.Status.PASSIVE, PASSIVE_DATE),
        ):
            for barcode, row in self._data_rows(book, sheet):
                reason = reasons.get(barcode, "")
                if status == DrugReferenceEntry.Status.ACTIVE:
                    reason = "в списке на перевод в пассивные" if barcode in to_passive else ""
                entry = DrugReferenceEntry(
                    source=self.key,
                    barcode=barcode,
                    name=cell(row, NAME)[:300],
                    firm=cell(row, FIRM)[:200],
                    atc_code=cell(row, ATC)[:20],
                    status=status,
                    status_date=excel_date(cell(row, date_col)),
                    reason=reason[:500],
                    file_date=file_date,
                )
                previous = entries.get(barcode)
                # Штрихкод в обоих листах: верит более поздней дате, при равенстве — «активен».
                if previous is None or (entry.status_date or date.min) > (previous.status_date or date.min):
                    entries[barcode] = entry
        return list(entries.values())

    def describe(self, entry, ctx: CheckContext, result: SourceResult) -> SourceResult:
        Status = DrugReferenceEntry.Status
        if entry is None:
            result.level = WARN if ctx.our_available else OK
            result.status = "Нет в списке"
            result.note = "Штрихкода нет ни среди активных, ни среди пассивных (импорт, новинка или старый)."
            result.short = "SKRS: нет в списке"
            return result
        since = fmt_date(entry.status_date)
        reason = reason_ru(entry.reason) if entry.reason else ""
        if entry.status == Status.PASSIVE:
            result.level = ALERT if ctx.our_available else OK
            result.status = f"Пассивен с {since}" if since else "Пассивен"
            result.note = reason or "Препарат выключен из списка для рецептов: скорее всего, не продаётся."
            result.short = f"SKRS: пассивен с {since}" + (f" ({reason})" if reason else "")
        else:
            result.level = WARN if (ctx.our_available is False or reason) else OK
            result.status = f"Активен с {since}" if since else "Активен"
            result.note = reason or (
                "У нас «нет в наличии», а в SKRS активен — возможно, зря скрыт." if ctx.our_available is False else ""
            )
            result.short = "SKRS: активен" + (f" ({reason})" if reason else "")
        if entry.firm:
            result.note = (result.note + f" Фирма: {entry.firm.rstrip('.')}.").strip()
        return result
