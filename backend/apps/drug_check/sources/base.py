"""Общее для источников проверки лекарства.

Источник — класс с ``key``, ``title`` и ``check(ctx) -> SourceResult``. Файловые источники
(список скачивается раз в неделю, проверка идёт по своей таблице) наследуют ``FileSource``
и реализуют ``find_file_url`` и ``parse``. Регистрация — строка в ``sources/__init__.py``.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from django.db import transaction

from apps.drug_check.models import DrugReferenceEntry, DrugReferenceLoad

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MAX_FILE_BYTES = 25 * 1024 * 1024
SERVICE_BARCODE_RE = re.compile(r"^1{7}")

OK = "ok"  # источник согласен с нами
INFO = "info"  # сведения без вывода
WARN = "warn"  # подсказка: стоит проверить
ALERT = "alert"  # расхождение
ERROR = "error"  # проверить не удалось
LEVEL_ORDER = {OK: 0, INFO: 0, ERROR: 1, WARN: 2, ALERT: 3}


@dataclass
class CheckContext:
    barcode: str = ""
    medicine: object | None = None  # MedicineProduct или None (проверка по штрихкоду)
    our_price: Decimal | None = None
    our_currency: str = ""
    our_available: bool | None = None
    deadline: float | None = None  # time.monotonic(), после которого внешних запросов нет

    def seconds_left(self) -> float | None:
        return None if self.deadline is None else self.deadline - time.monotonic()

    @property
    def real_barcode(self) -> str:
        """Штрихкод, по которому есть смысл сверять: 8–14 цифр, не служебный «1111111…»."""
        value = (self.barcode or "").strip()
        if not re.fullmatch(r"\d{8,14}", value) or SERVICE_BARCODE_RE.match(value):
            return ""
        return value


@dataclass
class SourceResult:
    key: str
    title: str
    level: str = INFO
    status: str = ""  # «Активен с 29.01.2013», «Есть в прайсе», «Нет в списке»
    price: Decimal | None = None
    price_date: date | None = None
    note: str = ""  # пояснение для менеджера
    short: str = ""  # одна фраза для Telegram
    url: str = ""
    file_date: date | None = None


def fmt_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def fmt_price(value: Decimal | None) -> str:
    if value is None:
        return ""
    whole, frac = f"{value:.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{' '.join(groups)},{frac} TL"


def compare_price(ours: Decimal | None, currency: str, theirs: Decimal | None) -> str | None:
    """None — сравнить нельзя, "" — цены совпали, иначе текст расхождения.

    Разница до 5 курушей — округление источника, не расхождение.
    """
    if ours is None or theirs is None or (currency or "").upper() != "TRY":
        return None
    diff = theirs - ours
    if abs(diff) <= Decimal("0.05"):
        return ""
    percent = (diff / ours * 100) if ours else Decimal("0")
    return f"у нас {fmt_price(ours)}, разница {percent:+.1f} %"


def price_short(label: str, theirs: Decimal | None, comparison: str | None) -> str:
    """«IlacFiyati 202,15 TL (= наша)» / «… ≠ наша» / без сравнения."""
    text = f"{label} {fmt_price(theirs)}"
    if comparison == "":
        return text + " (= наша)"
    if comparison:
        return text + " ≠ наша"
    return text


def http_client(timeout: float) -> httpx.Client:
    # trust_env=False: без прокси из окружения — проверка ходит только напрямую.
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"},
    )


class FileSource:
    """Источник-файл: раз в неделю скачать список, проверять по таблице DrugReferenceEntry."""

    key = ""
    title = ""
    page_url = ""
    allowed_hosts: frozenset[str] = frozenset()

    # ── загрузка ───────────────────────────────────────────────
    def find_file_url(self, page_html: str) -> tuple[str, str, date | None]:
        """(адрес файла, имя файла, дата файла) по странице источника."""
        raise NotImplementedError

    def parse(self, content: bytes, file_date: date | None) -> list[DrugReferenceEntry]:
        raise NotImplementedError

    def _checked_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in self.allowed_hosts:
            raise ValueError(f"адрес вне источника: {url[:200]}")
        return url

    def _get(self, client: httpx.Client, url: str) -> bytes:
        self._checked_url(url)
        with client.stream("GET", url) as response:
            response.raise_for_status()
            self._checked_url(str(response.url))
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise ValueError(f"файл больше {MAX_FILE_BYTES // 1024 // 1024} МБ")
                chunks.append(chunk)
        return b"".join(chunks)

    def last_loaded(self) -> DrugReferenceLoad | None:
        return (
            DrugReferenceLoad.objects.filter(source=self.key, result=DrugReferenceLoad.Result.LOADED)
            .order_by("-created_at", "-pk")
            .first()
        )

    def download_and_load(self, *, force: bool = False, timeout: float = 120) -> DrugReferenceLoad:
        """Скачивает страницу и файл (2 запроса; файл — только если он новый) и загружает строки.

        Файл держится в памяти и на диск не пишется. Ошибка записывается в журнал загрузок.
        """
        file_url = file_name = ""
        file_date = None
        try:
            with http_client(timeout) as client:
                page = self._get(client, self.page_url).decode("utf-8", errors="replace")
                file_url, file_name, file_date = self.find_file_url(page)
                file_url = self._checked_url(urljoin(self.page_url, file_url))
                last = self.last_loaded()
                if last and last.file_name == file_name and not force:
                    return DrugReferenceLoad.objects.create(
                        source=self.key,
                        file_name=file_name,
                        file_url=file_url,
                        file_date=file_date,
                        result=DrugReferenceLoad.Result.UNCHANGED,
                        rows=last.rows,
                        message="Файл не менялся с прошлой загрузки.",
                    )
                content = self._get(client, file_url)
            return self.load_content(content, file_name=file_name, file_url=file_url, file_date=file_date)
        except Exception as exc:  # журнал загрузок — единственное место, где видна ошибка
            logger.warning("drug_reference_load_failed", extra={"source": self.key}, exc_info=True)
            return DrugReferenceLoad.objects.create(
                source=self.key,
                file_name=file_name,
                file_url=file_url,
                file_date=file_date,
                result=DrugReferenceLoad.Result.FAILED,
                message=f"{type(exc).__name__}: {exc}"[:2000],
            )

    def load_content(
        self, content: bytes, *, file_name: str = "", file_url: str = "", file_date: date | None = None
    ) -> DrugReferenceLoad:
        entries = self.parse(content, file_date)
        if not entries:
            raise ValueError("в файле не найдено ни одной строки со штрихкодом")
        self._carry_over(entries)
        with transaction.atomic():
            DrugReferenceEntry.objects.filter(source=self.key).delete()
            DrugReferenceEntry.objects.bulk_create(entries, batch_size=2000)
            load = DrugReferenceLoad.objects.create(
                source=self.key,
                file_name=file_name,
                file_url=file_url,
                file_date=file_date,
                result=DrugReferenceLoad.Result.LOADED,
                rows=len(entries),
                message=f"Загружено строк: {len(entries)}.",
            )
        return load

    def _carry_over(self, entries: Iterable[DrugReferenceEntry]) -> None:
        """Сохраняет пояснения прошлых загрузок: причина есть только в файле той недели."""
        old = {
            row["barcode"]: row
            for row in DrugReferenceEntry.objects.filter(source=self.key).exclude(reason="").values(
                "barcode", "status", "status_date", "reason"
            )
        }
        for entry in entries:
            previous = old.get(entry.barcode)
            if (
                not entry.reason
                and previous
                and previous["status"] == entry.status
                and previous["status_date"] == entry.status_date
            ):
                entry.reason = previous["reason"]

    # ── проверка ───────────────────────────────────────────────
    def check(self, ctx: CheckContext) -> SourceResult:
        result = SourceResult(key=self.key, title=self.title)
        last = self.last_loaded()
        result.file_date = last.file_date if last else None
        if last is None:
            result.level = ERROR
            result.status = "Файл не загружен"
            result.note = "Список ещё не загружали: load_drug_reference_files."
            result.short = f"{self.title}: файл не загружен"
            return result
        barcode = ctx.real_barcode
        if not barcode:
            result.status = "Сверить нельзя"
            result.note = "Нет настоящего штрихкода (пусто или служебный «1111111…»)."
            result.short = f"{self.title}: нет штрихкода"
            return result
        entry = DrugReferenceEntry.objects.filter(source=self.key, barcode=barcode).first()
        return self.describe(entry, ctx, result)

    def describe(self, entry: DrugReferenceEntry | None, ctx: CheckContext, result: SourceResult) -> SourceResult:
        raise NotImplementedError
