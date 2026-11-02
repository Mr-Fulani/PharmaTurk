"""Перенос исправленных абзацев памяти на страницы опубликованных лекарств (TD-025, TD-031).

Сопоставлять строку можно только по турецкому исходнику: разделы берутся из входа последнего
применённого лога, абзацы выравниваются по строкам, как в ``section_paragraph_problems``. Строка
меняется, только если её турецкий абзац — исправленная запись памяти и на сайте стоит одна из старых
версий перевода этой записи (из бэкапов). Совпадение одного лишь русского текста не считается:
«содержащихся в ADELEKS» у таблеток и «в ампуле ADELEKS» у ампул — разные исходники. Замена по
русскому тексту испортила бы ≈ 2 700 верных строк (проверка 24.10.2026).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from django.db import transaction

from apps.ai.models import AITranslationMemory
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_memory import (
    BRAND_TOKEN,
    PARAGRAPH_NAMESPACE,
    normalize_paragraph,
    split_paragraphs,
)
from apps.ai.services.medicine_refresh import latest_applied_log
from apps.ai.services.medicine_title import paragraph_brand
from apps.ai.services.translation_files import read_json
from apps.ai.services.translation_memory import source_hash

SECTION_FIELDS = ("indications", "usage_instructions", "side_effects", "contraindications", "storage_conditions")


def load_old_versions(paths) -> dict:
    """Бэкапы памяти → {хэш: {"ru": старые версии, "en": старые версии}}."""
    versions = defaultdict(lambda: {"ru": set(), "en": set()})
    for path in paths:
        for row in read_json(path):
            fields = row["fields"]
            if fields["namespace"] == PARAGRAPH_NAMESPACE:
                versions[fields["source_hash"]]["ru"].add((fields["ru_text"] or "").strip())
                versions[fields["source_hash"]]["en"].add((fields["en_text"] or "").strip())
    return versions


def _source_of(generator, base_id: int) -> tuple[dict, str]:
    log = latest_applied_log(base_id)
    input_data = (log.input_data if log else None) or {}
    brand = paragraph_brand(input_data.get("name"), input_data.get("active_ingredient"))
    return generator._build_medicine_source_sections(input_data), brand


def _source_parts(source: str, line_count: int):
    """Абзацы исходника по числу строк раздела: сначала как при обработке, затем по строкам."""
    for parts in (split_paragraphs(source), re.split(r"(\n+)", source.strip())):
        found = [part.strip() for part in parts[::2] if part.strip()]
        if len(found) == line_count:
            return found
    return None


def plan_site_lines(old_versions: dict) -> tuple[list[dict], Counter, set]:
    """Только чтение → (план замен, статистика, лекарства с заменами)."""
    from apps.catalog.models import MedicineProductTranslation

    current = {
        record.source_hash: {"ru": (record.ru_text or "").strip(), "en": (record.en_text or "").strip()}
        for record in AITranslationMemory.objects.filter(namespace=PARAGRAPH_NAMESPACE, source_hash__in=list(old_versions))
    }
    generator = ContentGenerator.__new__(ContentGenerator)
    plan, stats, products = [], Counter(), set()
    rows = (
        MedicineProductTranslation.objects.filter(locale__in=("ru", "en"))
        .select_related("product")
        .defer("product__external_data")
        .order_by("product_id", "id")
    )
    cached_base, sections, brand = None, {}, ""
    for row in rows.iterator(chunk_size=300):
        base = row.product.base_product_id or row.product_id
        for field in SECTION_FIELDS:
            text = getattr(row, field) or ""
            if not text.strip():
                continue
            if base != cached_base:
                cached_base = base
                sections, brand = _source_of(generator, base)
            lines = [(index, line.strip()) for index, line in enumerate(text.split("\n")) if line.strip()]
            parts = _source_parts(sections.get(field) or "", len(lines))
            if parts is None:
                stats["раздел не сопоставлен"] += 1
                continue
            for part, (index, line) in zip(parts, lines):
                key = source_hash(normalize_paragraph(part, brand))
                if key not in current:
                    continue
                shown = line.replace(brand, BRAND_TOKEN) if brand else line
                fixed = current[key][row.locale]
                if shown == fixed:
                    stats["уже исправлено"] += 1
                elif shown in old_versions[key][row.locale]:
                    plan.append({"base": base, "tr_id": row.pk, "locale": row.locale, "field": field, "line": index,
                                 "old": line, "new": fixed.replace(BRAND_TOKEN, brand), "source": part})
                    stats["замена"] += 1
                    products.add(base)
                else:
                    stats["на сайте другой текст — не трогаем"] += 1
    return plan, stats, products


def match_plan(plan) -> tuple[dict, dict, Counter]:
    """План → (строки перевода, новые значения полей, статистика). Заменяется только прежний текст."""
    from apps.catalog.models import MedicineProductTranslation

    by_row = defaultdict(list)
    for item in plan:
        by_row[item["tr_id"]].append(item)
    rows = MedicineProductTranslation.objects.in_bulk(list(by_row))
    changes, stats = {}, Counter()
    for pk, items in by_row.items():
        row = rows.get(pk)
        if row is None:
            stats["строки нет"] += len(items)
            continue
        by_field = defaultdict(list)
        for item in items:
            by_field[item["field"]].append(item)
        for field, field_items in by_field.items():
            lines = (getattr(row, field) or "").split("\n")
            matched = 0
            for item in field_items:
                index = item["line"]
                if index < len(lines) and lines[index].strip() == item["old"]:
                    lines[index] = lines[index].replace(item["old"], item["new"])
                    matched += 1
                else:
                    stats["текст изменился"] += 1
            if matched:
                changes.setdefault(pk, {})[field] = "\n".join(lines)
                stats["к замене"] += matched
    stats["строк перевода"] = len(changes)
    return rows, changes, stats


def apply_site_lines(rows: dict, changes: dict) -> None:
    with transaction.atomic():
        for pk, fields in changes.items():
            row = rows[pk]
            for field, value in fields.items():
                setattr(row, field, value)
            row.save(update_fields=sorted(fields))
