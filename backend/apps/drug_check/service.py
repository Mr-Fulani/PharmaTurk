"""Проверка лекарства по всем источникам (TD-044, docs/DRUG_CHECK.md).

Только показывает: цены, наличие и видимость товара не меняются (решение владельца 12.11.2026 —
«пассивные» по одному-двум источникам остаются в продаже, менеджер решает по заявке).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from apps.catalog.models import MedicineProduct

from .sources import SOURCES, file_sources
from .sources.base import ALERT, ERROR, LEVEL_ORDER, WARN, CheckContext, SourceResult, fmt_price

logger = logging.getLogger(__name__)

ORDER_CHECK_SECONDS = 15  # на все лекарства заявки; дальше «не успели проверить»
ORDER_MAX_MEDICINES = 10
REGISTRY = "skrs"  # государственный реестр: его фраза в сообщении о заявке идёт первой


@dataclass
class DrugCheckReport:
    barcode: str
    medicine: MedicineProduct | None = None
    results: list[SourceResult] = field(default_factory=list)
    checked_at: object = None

    @property
    def name(self) -> str:
        return self.medicine.name if self.medicine else self.barcode

    @property
    def level(self) -> str:
        levels = [r.level for r in self.results] or [ERROR]
        return max(levels, key=LEVEL_ORDER.__getitem__)

    def _price_phrase(self) -> str:
        """Одна фраза про цену: из сравнимых цен источников — та, что дальше от нашей."""
        compared = [r for r in self.results if r.price_diff is not None]
        if not compared:
            return ""
        result = max(compared, key=lambda r: abs(r.price_diff))
        if not result.price_diff:
            return f"Цена продавца {fmt_price(result.price)} — у нас в базе та же"
        verb = "выросла" if result.price_diff > 0 else "снизилась"
        ours = fmt_price(result.price - result.price_diff)
        return f"Цена продавца {verb}: {fmt_price(result.price)}, у нас в базе {ours}"

    def telegram_status(self) -> str:
        """Итог для менеджера простыми словами, без названий источников.

        «✅ В реестре Турции: действует · Цена продавца 204,49 TL — у нас в базе та же».
        Порядок: реестр, цена, замечания источников цены. Подробности — в окне проверки.
        """
        price = self._price_phrase()
        registry, sellers, no_data = [], [], False
        for result in self.results:
            phrases = [result.plain]
            if result.missing and (result.key == REGISTRY or not price):
                phrases.append(result.missing)
                no_data = True
            (registry if result.key == REGISTRY else sellers).extend(p for p in phrases if p)
        level = self.level
        if level in (ALERT, WARN):
            icon = "⚠️"
        elif all(r.level == ERROR for r in self.results):
            icon = "❔"
        elif no_data:
            icon = "ℹ️"
        else:
            icon = "✅"
        return f"{icon} " + " · ".join([*registry, *([price] if price else []), *sellers])


def lookup_query(medicine: MedicineProduct) -> str:
    """Что подставить в окно поиска: настоящий штрихкод, иначе турецкое название источника."""
    barcode = CheckContext(barcode=medicine.barcode or "").real_barcode
    return barcode or str((medicine.external_data or {}).get("source_name") or medicine.name or "").strip()


def _context(medicine: MedicineProduct | None, barcode: str, deadline: float | None) -> CheckContext:
    if medicine is None:
        return CheckContext(barcode=barcode, deadline=deadline)
    price = Decimal(str(medicine.price)) if medicine.price is not None else None
    return CheckContext(
        barcode=(medicine.barcode or barcode or "").strip(),
        medicine=medicine,
        our_price=price,
        our_currency=(medicine.currency or "").upper(),
        our_available=bool(medicine.is_active and medicine.is_available),
        deadline=deadline,
    )


def _run(ctx: CheckContext, sources=None) -> list[SourceResult]:
    results = []
    for source in SOURCES if sources is None else sources:
        try:
            results.append(source.check(ctx))
        except Exception:  # один сломанный источник не прячет остальные
            logger.exception("drug_check_source_failed", extra={"source": source.key})
            results.append(
                SourceResult(
                    key=source.key,
                    title=source.title,
                    level=ERROR,
                    status="Не проверено",
                    note="Ошибка проверки источника (подробности в журнале).",
                    short=f"{source.title}: не удалось проверить",
                    missing=f"{source.plain_title}: проверить не удалось",
                )
            )
    return results


def check_medicine(medicine: MedicineProduct, *, deadline: float | None = None) -> DrugCheckReport:
    ctx = _context(medicine, "", deadline)
    return DrugCheckReport(barcode=ctx.barcode, medicine=medicine, results=_run(ctx), checked_at=timezone.now())


def quick_check(medicine: MedicineProduct) -> DrugCheckReport:
    """Только свои списки (SKRS, склад) — без запросов наружу; для панели в карточке лекарства."""
    ctx = _context(medicine, "", None)
    return DrugCheckReport(
        barcode=ctx.barcode, medicine=medicine, results=_run(ctx, file_sources()), checked_at=timezone.now()
    )


def check_barcode(barcode: str, *, deadline: float | None = None) -> DrugCheckReport:
    """Проверка по штрихкоду: если у нас есть карточка с этим штрихкодом — по ней."""
    barcode = (barcode or "").strip()
    medicine = (
        MedicineProduct.objects.filter(barcode=barcode, is_active=True).select_related("base_product").first()
        or MedicineProduct.objects.filter(barcode=barcode).select_related("base_product").first()
    )
    if medicine is not None:
        return check_medicine(medicine, deadline=deadline)
    ctx = _context(None, barcode, deadline)
    return DrugCheckReport(barcode=barcode, results=_run(ctx), checked_at=timezone.now())


def _order_medicines(order) -> list[MedicineProduct]:
    medicines, seen = [], set()
    for item in order.items.select_related("product__medicine_item__base_product").order_by("pk"):
        product = item.product
        if product is None or product.product_type != "medicines":
            continue
        medicine = getattr(product, "medicine_item", None)
        if medicine is not None and medicine.pk not in seen:
            seen.add(medicine.pk)
            medicines.append(medicine)
    return medicines


def order_checks(order, *, seconds: float = ORDER_CHECK_SECONDS) -> dict[str, str]:
    """Итоги проверки лекарств заявки для сообщения менеджеру: {id лекарства: итог одной строкой}.

    Ключи — строки: словарь передаётся в повтор задачи Celery (JSON). Пусто, если лекарств нет.
    Время ограничено: что не успели — «не успели проверить», заявку и сообщение это не держит
    дольше ``seconds`` (плюс один запрос, начатый до срока). Проверяются первые
    ``ORDER_MAX_MEDICINES`` препаратов, у остальных в сообщении только ссылка на проверку.
    """
    try:
        medicines = _order_medicines(order)
    except Exception:
        logger.warning("drug_check_order_items_failed", extra={"order": getattr(order, "pk", None)}, exc_info=True)
        return {}
    deadline = time.monotonic() + seconds
    checks = {}
    for medicine in medicines[:ORDER_MAX_MEDICINES]:
        try:
            checks[str(medicine.pk)] = check_medicine(medicine, deadline=deadline).telegram_status()
        except Exception:
            logger.exception("drug_check_order_medicine_failed", extra={"medicine": medicine.pk})
            checks[str(medicine.pk)] = "❔ Проверить не удалось"
    return checks
