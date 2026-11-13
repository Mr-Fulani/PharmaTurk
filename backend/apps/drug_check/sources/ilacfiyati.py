"""IlacFiyati — цена и «Aktif / Pasif» прямо сейчас, один запрос на карточку.

Адрес карточки берётся из нашей записи (как у проверки цены на витрине). Без карточки —
поиск источника по штрихкоду (``/tum-urunler?q=``) и карточка: два запроса. Вкладки
инструкции и аналогов не открываются, прокси не используется, повторов нет.
Цена здесь только показывается: каталог не меняется (решение владельца, TD-044).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from apps.catalog.services.medicine_market_check import MedicineMarketCheckService
from apps.scrapers.models import ScraperConfig

from .base import ALERT, ERROR, OK, WARN, CheckContext, SourceResult, compare_price, price_short

logger = logging.getLogger(__name__)

BASE_URL = "https://ilacfiyati.com"
REQUEST_TIMEOUT = 8.0
MIN_SECONDS = 2.0  # меньше — запрос не начинаем: «не успели проверить»


class _NotChecked(Exception):
    """Проверить не удалось; текст — для менеджера."""


class IlacFiyatiSource:
    key = "ilacfiyati"
    title = "IlacFiyati"

    @staticmethod
    def _parser():
        from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser

        parser = IlacFiyatiParser(
            BASE_URL, delay_range=(0, 0), timeout=REQUEST_TIMEOUT, max_retries=0, use_proxy=False
        )
        config = (
            ScraperConfig.objects.filter(parser_class__iexact="ilacfiyati", is_enabled=True, status="active")
            .order_by("priority", "pk")
            .first()
        )
        if config is not None:
            parser.configure_request_identity(
                user_agent=config.user_agent or None,
                headers=config.headers if isinstance(config.headers, dict) else None,
                cookies=config.cookies if isinstance(config.cookies, dict) else None,
            )
        return parser

    @staticmethod
    def card_url(medicine) -> str:
        if medicine is None:
            return ""
        for candidate in MedicineMarketCheckService._source_candidates(medicine):
            url = MedicineMarketCheckService._canonical_ilacfiyati_medicine_url(candidate)
            if url:
                return url
        return ""

    @staticmethod
    def _fetch(parser, ctx: CheckContext, url: str) -> str:
        left = ctx.seconds_left()
        if left is not None and left < MIN_SECONDS:
            raise _NotChecked("не успели проверить (время на проверку вышло)")
        parser.client.timeout = httpx.Timeout(REQUEST_TIMEOUT if left is None else min(REQUEST_TIMEOUT, left))
        html = parser._make_request(url)
        if not html:
            raise _NotChecked("страница источника не открылась (нет ответа или 404)")
        return html

    def _find_by_barcode(self, parser, ctx: CheckContext, barcode: str) -> str:
        html = self._fetch(parser, ctx, f"{BASE_URL}/tum-urunler?q={quote(barcode)}")
        urls = parser._extract_listing_product_urls(html)
        if not urls:
            raise _NotChecked("по штрихкоду карточка не найдена")
        if len(urls) > 1:
            raise _NotChecked(f"по штрихкоду найдено несколько карточек ({len(urls)}) — откройте поиск вручную")
        return urls[0]

    @staticmethod
    def price_valid_date(soup: BeautifulSoup):
        """«Fiyat Geçerlilik Tarihi» — день последнего изменения цены у источника."""
        for label in soup.select(".info-card__label"):
            if label.find_parent(class_="medicine-item"):
                continue
            text = label.get_text(" ", strip=True).casefold()
            if "fiyat" in text and "tarih" in text:
                value = label.parent.select_one(".info-card__value")
                match = re.search(r"\d{2}\.\d{2}\.\d{4}", value.get_text(" ", strip=True) if value else "")
                if match:
                    return datetime.strptime(match.group(0), "%d.%m.%Y").date()
        return None

    def check(self, ctx: CheckContext) -> SourceResult:
        result = SourceResult(key=self.key, title=self.title)
        parser = None
        try:
            url = self.card_url(ctx.medicine)
            if not url and not ctx.real_barcode:
                raise _NotChecked("нет ссылки на карточку источника и настоящего штрихкода")
            parser = self._parser()
            if not url:
                url = self._find_by_barcode(parser, ctx, ctx.real_barcode)
            result.url = url
            html = self._fetch(parser, ctx, url)
            scraped = parser.parse_product_detail(url, html=html, include_detail_tabs=False, include_analogs=False)
        except _NotChecked as exc:
            result.level = ERROR
            result.status = "Не проверено"
            result.note = str(exc)
            result.short = f"IlacFiyati: {exc}"
            return result
        except Exception as exc:
            logger.warning("drug_check_ilacfiyati_failed", extra={"url": result.url}, exc_info=True)
            result.level = ERROR
            result.status = "Не проверено"
            result.note = f"источник не ответил или страница не разобралась ({type(exc).__name__})"
            result.short = "IlacFiyati: не удалось проверить"
            return result
        finally:
            if parser is not None and parser.client:
                parser.client.close()

        result.price_date = self.price_valid_date(BeautifulSoup(html, "html.parser"))
        try:
            result.price = Decimal(str(scraped.price)).quantize(Decimal("0.01")) if scraped.price else None
        except (InvalidOperation, ValueError):
            result.price = None
        currency = (scraped.currency or "TRY").upper()
        notes = []
        inactive = bool(getattr(scraped, "source_inactive", False))
        result.status = "Pasif (снят)" if inactive else "Aktif"
        level = OK
        if inactive and ctx.our_available:
            level = ALERT
            notes.append("На странице «İlaç Durumu: Pasif», а у нас «в наличии».")
        if getattr(scraped, "price_unpublished", False):
            notes.append("Цена на странице 0,00 — не опубликована.")
            level = WARN if level == OK else level
        page_barcode = (scraped.barcode or "").strip()
        if ctx.real_barcode and page_barcode and page_barcode != ctx.real_barcode:
            notes.append(f"Штрихкод на странице другой: {page_barcode}.")
            level = ALERT
        comparison = compare_price(ctx.our_price, ctx.our_currency, result.price) if currency == "TRY" else None
        if currency != "TRY" and result.price is not None:
            notes.append(f"Цена источника в {currency}.")
        if comparison:
            notes.append(f"Цена другая: {comparison}.")
            level = ALERT
        result.level = level
        result.note = " ".join(notes)
        if result.price is not None:
            result.short = price_short("IlacFiyati", result.price, comparison)
        else:
            result.short = "IlacFiyati: цены нет"
        if inactive:
            result.short += ", Pasif"
        return result
