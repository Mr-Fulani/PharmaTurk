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

from .sources import SOURCES
from .sources.base import ALERT, ERROR, LEVEL_ORDER, WARN, CheckContext, SourceResult

logger = logging.getLogger(__name__)

ORDER_CHECK_SECONDS = 15  # на все лекарства заявки; дальше «не успели проверить»
ORDER_MAX_MEDICINES = 10
NAME_LIMIT = 70


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

    def telegram_line(self) -> str:
        """Одна строка на лекарство: «• NAME: ⚠️ SKRS: пассивен с …; IlacFiyati …; у склада нет»."""
        level = self.level
        if level in (ALERT, WARN):
            icon = "⚠️"
        elif all(r.level == ERROR for r in self.results):
            icon = "❔"
        else:
            icon = "✅"
        name = self.name if len(self.name) <= NAME_LIMIT else self.name[: NAME_LIMIT - 1] + "…"
        details = "; ".join(r.short for r in self.results if r.short)
        return f"• {name}: {icon} {details}"


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


def _run(ctx: CheckContext) -> list[SourceResult]:
    results = []
    for source in SOURCES:
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
                )
            )
    return results


def check_medicine(medicine: MedicineProduct, *, deadline: float | None = None) -> DrugCheckReport:
    ctx = _context(medicine, "", deadline)
    return DrugCheckReport(barcode=ctx.barcode, medicine=medicine, results=_run(ctx), checked_at=timezone.now())


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


def order_check_text(order, *, seconds: float = ORDER_CHECK_SECONDS) -> str:
    """Итог проверки лекарств заявки для сообщения менеджеру; пусто, если лекарств нет.

    Время ограничено: что не успели — «не успели проверить», заявку и сообщение это не держит
    дольше ``seconds`` (плюс один запрос, начатый до срока).
    """
    try:
        medicines = _order_medicines(order)
    except Exception:
        logger.warning("drug_check_order_items_failed", extra={"order": getattr(order, "pk", None)}, exc_info=True)
        return ""
    if not medicines:
        return ""
    deadline = time.monotonic() + seconds
    lines = ["🔎 Проверка лекарств (на сайте ничего не меняется):"]
    for medicine in medicines[:ORDER_MAX_MEDICINES]:
        try:
            lines.append(check_medicine(medicine, deadline=deadline).telegram_line())
        except Exception:
            logger.exception("drug_check_order_medicine_failed", extra={"medicine": medicine.pk})
            lines.append(f"• {medicine.name[:NAME_LIMIT]}: ❔ не удалось проверить")
    rest = len(medicines) - ORDER_MAX_MEDICINES
    if rest > 0:
        lines.append(f"…и ещё {rest} — проверьте в админке кнопкой «Проверить сейчас».")
    return "\n".join(lines)
