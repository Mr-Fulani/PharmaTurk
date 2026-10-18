"""Одноразовый перевод всех МНН лекарств в память переводов (namespace medicine_inn).

Берёт уникальные вещества из MedicineProduct.active_ingredient (комбинации
«A + B» делятся), пропускает уже переведённые и переводит остальные пачками
по 100 в одном запросе. В память попадает только перевод, прошедший проверки
(полностью кириллицей, то же вещество). После перевода разносит МНН по
существующим переводам товаров. Дальше подстановка идёт кодом, правка в
админке «Память переводов AI» сразу применяется ко всем товарам.

    manage.py translate_medicine_inn --dry-run   # число веществ и оценка $
    manage.py translate_medicine_inn
"""

from django.core.management.base import BaseCommand

from apps.ai.services.llm_client import LLMClient
from apps.ai.services.medicine_memory import (
    INN_NAMESPACE,
    estimate_translation_cost,
    propagate_inn_translations,
    split_inn,
    translate_inn_values,
)
from apps.ai.services.translation_memory import lookup, remember
from apps.catalog.models import MedicineProduct


class Command(BaseCommand):
    help = "Перевести все МНН лекарств в память переводов (одноразово, пачками по 100)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только оценка; OpenAI не вызывается")
        parser.add_argument("--limit", type=int, default=0, help="Максимум веществ за запуск (0 — все)")
        parser.add_argument("--batch-size", type=int, default=100, help="Веществ в одном запросе")

    def handle(self, *args, **options):
        parts = set()
        values = MedicineProduct.objects.exclude(active_ingredient="").values_list("active_ingredient", flat=True)
        for value in values.distinct().iterator(chunk_size=2000):
            parts.update(split_inn(value))
        in_memory = lookup(INN_NAMESPACE, sorted(parts), count_hits=False)
        missing = sorted(part for part in parts if part not in in_memory)
        if options["limit"]:
            missing = missing[: options["limit"]]
        estimate = estimate_translation_cost(missing, items_per_request=options["batch_size"])
        self.stdout.write(
            f"Веществ: {len(parts)}, в памяти: {len(in_memory)}, к переводу: {len(missing)}; "
            f"оценка ≈${estimate['cost_usd']:.3f}, запросов {estimate['requests']}"
        )
        if options["dry_run"] or not missing:
            return

        translated, usage = translate_inn_values(missing, LLMClient(), batch_size=options["batch_size"])
        remember(INN_NAMESPACE, translated)
        updated = propagate_inn_translations(set(translated))
        rejected = sorted(set(missing) - set(translated))
        self.stdout.write(self.style.SUCCESS(
            f"Переведено {len(translated)}, отклонено проверкой {len(rejected)}; "
            f"фактически ${usage['cost_usd']:.4f}; обновлено переводов товаров: {updated}"
        ))
        for part in rejected[:50]:
            self.stdout.write(f"    без перевода: {part}")
