"""Покрытие лекарств кодом: справочники, шаблон названия, МНН и абзацы в памяти.

Только чтение, OpenAI не вызывается. Показывает значения справочных полей,
которых нет в словаре (на сайте остаются исходником), долю названий по
шаблону и оценку стоимости перевода того, чего ещё нет в памяти переводов.

    manage.py medicine_reference_coverage
    manage.py medicine_reference_coverage --paragraphs   # + абзацы инструкций (дольше)
"""

from collections import Counter

from django.core.management.base import BaseCommand

from apps.ai.services.medicine_memory import (
    INN_NAMESPACE,
    estimate_translation_cost,
    PARAGRAPH_NAMESPACE,
    needs_translation,
    normalize_paragraph,
    source_tab_texts,
    split_inn,
    split_paragraphs,
)
from apps.ai.services.medicine_reference import CODE_FIELDS, translate_reference_field
from apps.ai.services.medicine_title import build_medicine_title
from apps.ai.services.translation_memory import lookup, source_hash
from apps.ai.models import AITranslationMemory
from apps.catalog.models import MedicineProduct


class Command(BaseCommand):
    help = "Отчёт: какие поля лекарств закрывает код и сколько будет стоить перевод недостающего"

    def add_arguments(self, parser):
        parser.add_argument("--paragraphs", action="store_true", help="Посчитать абзацы инструкций")
        parser.add_argument("--top", type=int, default=15, help="Сколько неизвестных значений показать")

    def handle(self, *args, **options):
        qs = MedicineProduct.objects.filter(is_active=True)
        fields = [f for f in CODE_FIELDS if f != "volume"]
        rows = qs.values_list("name", "active_ingredient", "volume", *fields)
        total = 0
        unknown = {field: Counter() for field in (*fields, "volume")}
        covered = Counter()
        titles = 0
        inn_parts = Counter()
        for name, inn, volume, *values in rows.iterator(chunk_size=2000):
            total += 1
            data = dict(zip(fields, values), name=name, volume=volume)
            for field in (*fields, "volume"):
                value = data.get(field)
                if not value or str(value).strip() in ("", "-") or (field == "dosage_form" and value == "other"):
                    continue
                if translate_reference_field(field, value, data):
                    covered[field] += 1
                else:
                    unknown[field][str(value)] += 1
            titles += bool(build_medicine_title(name))
            inn_parts.update(split_inn(inn))

        self.stdout.write(f"Активных лекарств: {total}")
        for field, counter in unknown.items():
            missing = sum(counter.values())
            self.stdout.write(
                f"\n{field}: переведено кодом {covered[field]}, без перевода {missing} "
                f"({len(counter)} уникальных)"
            )
            for value, count in counter.most_common(options["top"]):
                self.stdout.write(f"    {count:>6}  {value!r}")
        self.stdout.write(f"\nНазвание по шаблону: {titles} из {total} ({titles / max(total, 1):.0%}); остальные — моделью")

        in_memory = lookup(INN_NAMESPACE, list(inn_parts), count_hits=False)
        missing_inn = [part for part in inn_parts if part not in in_memory]
        estimate = estimate_translation_cost(missing_inn, items_per_request=100)
        self.stdout.write(
            f"\nМНН: уникальных веществ {len(inn_parts)}, в памяти {len(in_memory)}, "
            f"без перевода {len(missing_inn)} → ≈${estimate['cost_usd']:.3f} "
            f"({estimate['requests']} запросов; translate_medicine_inn)"
        )
        if options["paragraphs"]:
            self._paragraphs(qs)

    def _paragraphs(self, qs):
        lengths: dict[str, int] = {}
        total_chars = 0
        for external_data in qs.values_list("external_data", flat=True).iterator(chunk_size=500):
            for text in source_tab_texts(external_data):
                for part in split_paragraphs(text)[::2]:
                    if needs_translation(part):
                        paragraph = normalize_paragraph(part)
                        total_chars += len(paragraph)
                        lengths.setdefault(source_hash(paragraph), len(paragraph))
        cached = set()
        hashes = list(lengths)
        for start in range(0, len(hashes), 5000):
            cached.update(
                AITranslationMemory.objects.filter(
                    namespace=PARAGRAPH_NAMESPACE, source_hash__in=hashes[start:start + 5000]
                ).values_list("source_hash", flat=True)
            )
        missing_chars = sum(length for h, length in lengths.items() if h not in cached)
        estimate = estimate_translation_cost(chars=missing_chars, request_chars=20000)
        unique_chars = sum(lengths.values())
        self.stdout.write(
            f"\nАбзацы инструкций: всего {total_chars:,} симв., уникальных {unique_chars:,} "
            f"({len(lengths):,} абзацев), в памяти {len(cached):,}; перевести {missing_chars:,} симв. "
            f"→ ≈${estimate['cost_usd']:.2f} (Batch API ≈${estimate['cost_usd'] / 2:.2f})"
        )
