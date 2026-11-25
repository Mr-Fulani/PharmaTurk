"""Запись артикула, OEM-номеров и применимости автозапчасти из парсера.

Парсер кладёт их в ``ScrapedProduct.auto_part`` (а не в ``attributes``): строк
применимости бывает до ~900 на деталь, в ``external_data`` и журнале товаров им не место.
Строки, добавленные вручную в админке (поле «Откуда» пустое) или другим парсером, не
трогаются: заменяются только строки того же источника.
"""

from typing import Any, Dict

from django.db import transaction

from apps.catalog.models import AutoPartFitment, AutoPartNumber, AutoPartProduct
from apps.catalog.utils.part_numbers import normalize_part_number, vehicle_slug

FITMENT_FIELDS = (
    "make", "model", "generation", "year_from", "month_from", "year_to", "month_to",
    "engine", "power_kw", "power_hp", "note",
)


def _years(fitment: Dict[str, Any]) -> str:
    start, end = fitment.get("year_from"), fitment.get("year_to")
    if start and end:
        return f"{start}–{end}"
    return f"{start}–" if start else ""


def sync_auto_part_data(product, scraped_product) -> bool:
    """Обновляет запись автозапчасти и её таблицы; True — что-то изменилось."""
    payload = getattr(scraped_product, "auto_part", None)
    if not isinstance(payload, dict) or product.product_type != "auto_parts":
        return False
    part = AutoPartProduct.objects.filter(base_product_id=product.pk).first()
    if part is None:
        return False
    source = str(scraped_product.source or "")[:32]
    numbers = payload.get("numbers") or []
    fitments = payload.get("fitments") or []
    changed = False

    fields: Dict[str, Any] = {}
    part_number = str(payload.get("part_number") or "").strip()[:100]
    if part_number and part.part_number != part_number:
        fields["part_number"] = part_number
    normalized = normalize_part_number(part_number or part.part_number)[:100]
    if part.part_number_normalized != normalized:
        fields["part_number_normalized"] = normalized
    if fitments:
        # Прежние поля «одна марка, одна модель» — из первой строки применимости.
        first = fitments[0]
        legacy = {
            "car_brand": str(first.get("make") or "")[:100],
            "car_model": str(first.get("model") or "")[:100],
            "compatibility_years": _years(first)[:50],
        }
        fields.update({name: value for name, value in legacy.items() if getattr(part, name) != value})
    if fields:
        # update(): save() доменной записи пишет её общие поля обратно в Product.
        AutoPartProduct.objects.filter(pk=part.pk).update(**fields)
        changed = True

    with transaction.atomic():
        existing = {(row.kind, row.number_normalized): row for row in part.numbers.all()}
        incoming = {}
        for row in numbers:
            key = (row.get("kind") or AutoPartNumber.Kind.OEM, normalize_part_number(row.get("number"))[:100])
            if key[1]:
                incoming.setdefault(key, row)
        stale = [row.pk for key, row in existing.items() if row.source == source and key not in incoming]
        if stale:
            AutoPartNumber.objects.filter(pk__in=stale).delete()
            changed = True
        new_rows = []
        for key, row in incoming.items():
            maker = str(row.get("maker") or "")[:255]
            current = existing.get(key)
            if current is None:
                new_rows.append(AutoPartNumber(
                    product=part, number=str(row.get("number") or "")[:100], number_normalized=key[1],
                    kind=key[0], maker=maker, source=source,
                ))
            elif current.source == source and current.maker != maker:
                AutoPartNumber.objects.filter(pk=current.pk).update(maker=maker)
                changed = True
        if new_rows:
            AutoPartNumber.objects.bulk_create(new_rows)
            changed = True

        wanted = [tuple(row.get(name) for name in FITMENT_FIELDS) for row in fitments]
        current_rows = list(part.fitments.filter(source=source).values_list(*FITMENT_FIELDS))
        if sorted(wanted, key=repr) != sorted(current_rows, key=repr):
            part.fitments.filter(source=source).delete()
            AutoPartFitment.objects.bulk_create(
                [
                    AutoPartFitment(
                        product=part, source=source,
                        make_slug=vehicle_slug(row.get("make")), model_slug=vehicle_slug(row.get("model")),
                        **{name: row.get(name) for name in FITMENT_FIELDS},
                    )
                    for row in fitments
                ],
                batch_size=500,
            )
            changed = True
    return changed


def enqueue_auto_part_card(product) -> None:
    """Русская и английская карточка — сразу после сбора, без кнопки в админке.

    Карточку автозапчасти собирает код (``apps/ai/services/rules/auto_parts.py``), модель не
    вызывается, поэтому ждать ручного запуска незачем. Уже обработанная карточка пропускается;
    неудачная (вида детали нет в словаре) пробуется снова при следующем сборе.
    """
    if product.product_type != "auto_parts":
        return
    from apps.ai.tasks import enqueue_or_apply_product_ai

    with transaction.atomic():
        enqueue_or_apply_product_ai(product_id=product.pk, auto_apply=True)

