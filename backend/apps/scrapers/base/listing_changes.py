"""Режим «Только изменения»: строка листинга и решение «открывать карточку или нет».

Здесь нет обращений к БД и сети — только данные строки и то, что о товаре уже
известно. Хранение и запросы — ``apps.scrapers.listing_changes``.
"""

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

OPEN = "open"  # открыть карточку и сохранить обычным путём парсера
SKIP = "skip"  # строка не изменилась (или пассивный товар, которого у нас нет)
GONE = "gone"  # источник пометил товар пассивным — снять с продажи у нас

ACTIVE_STATUS = "AKTIF"


@dataclass(frozen=True)
class ListingRow:
    url: str
    name: str
    barcode: str
    price: Optional[Decimal]  # None — цены нет; 0 — «не опубликована»
    price_text: str
    status: str  # нормализованный: AKTIF / PASIF
    prescription: str

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE_STATUS

    @property
    def fingerprint(self) -> str:
        payload = "\x1f".join(
            (self.name, self.barcode, self.price_text, self.status, self.prescription)
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KnownProduct:
    """Что о товаре уже есть в БД (для первого прохода без отпечатка)."""

    name: str  # название источника (external_data.source_name) или name
    price: Optional[Decimal]
    is_available: bool
    is_stub: bool

    def matches(self, row: ListingRow) -> bool:
        row_price = row.price if row.price else None  # 0 = цены нет, как и в БД
        return (
            self.name.strip().casefold() == row.name.strip().casefold()
            and self.price == row_price
        )


def listing_decision(
    row: ListingRow, *, known_fingerprint: str, product: Optional[KnownProduct]
) -> str:
    """OPEN / SKIP / GONE для одной строки листинга."""
    if not row.is_active:
        if product is not None and product.is_available and not product.is_stub:
            return GONE
        return SKIP  # пассивных товаров, которых у нас нет, не заводим
    if product is None or product.is_stub or not product.is_available:
        return OPEN  # новый товар, заглушка аналога или вернулся в продажу
    if known_fingerprint:
        return SKIP if known_fingerprint == row.fingerprint else OPEN
    # Первый проход: отпечатка ещё нет — сверяем с тем, что сохранено.
    return SKIP if product.matches(row) else OPEN
