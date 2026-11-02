"""Диагностика шаблона названий лекарств (только чтение, TD-031).

    manage.py medicine_title_diagnostics                         # покрытие и слова, на которых шаблон не собрался
    manage.py medicine_title_diagnostics --save titles.json      # снимок перед правкой шаблона
    manage.py medicine_title_diagnostics --compare titles.json   # что изменилось после правки
    manage.py medicine_title_diagnostics --moderation            # брак шаблона или проверки в очереди модерации
"""

import json
import re
from collections import Counter

from django.core.management.base import BaseCommand

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.services.medicine_title import (
    CYRILLIC_RE,
    TRUNCATED_TITLE_RE,
    build_medicine_title,
    medicine_source_name,
)
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.translation_files import read_json, write_json
from apps.catalog.models import Product

_FORM_WORD = re.compile(r"[A-ZÇĞİÖŞÜ.]{3,}")


def _tail_words(source: str):
    """Слова после бренда: среди них то, чего не знает шаблон."""
    return _FORM_WORD.findall(re.sub(r"^\S+\s+", "", source.upper()))


class Command(BaseCommand):
    help = "Покрытие шаблона названий лекарств, сравнение со снимком, причины в очереди модерации."

    def add_arguments(self, parser):
        parser.add_argument("--save", help="Записать снимок названий в файл")
        parser.add_argument("--compare", help="Сравнить со снимком из файла")
        parser.add_argument("--moderation", action="store_true", help="Разобрать очередь модерации лекарств")
        parser.add_argument("--top", type=int, default=40, help="Сколько слов и примеров показать")

    def handle(self, *args, **options):
        if options["moderation"]:
            self._moderation(options)
            return
        titles, stats, words, examples = {}, Counter(), Counter(), []
        products = Product.objects.filter(product_type="medicines", is_active=True).only("id", "name", "external_data")
        for product in products.iterator(chunk_size=500):
            source, origin = medicine_source_name(product.name, product.external_data)
            title = build_medicine_title(source)
            titles[str(product.id)] = {"source": source, "title": title}
            stats["всего"] += 1
            stats[f"источник: {origin}"] += 1
            stats["кириллица в исходнике"] += bool(CYRILLIC_RE.search(source))
            stats["обрезанный исходник"] += bool(TRUNCATED_TITLE_RE.search(source))
            if title:
                stats["шаблон собрал"] += 1
            else:
                words.update(_tail_words(source))
                examples.append((product.id, source))
        self.stdout.write(json.dumps(stats, ensure_ascii=False))
        self.stdout.write(f"Шаблон не собрал {len(examples)}, частые слова: {words.most_common(options['top'])}")
        for product_id, source in examples[: options["top"]]:
            self.stdout.write(f"  {product_id} | {source}")
        if options["save"]:
            write_json(options["save"], titles)
        if options["compare"]:
            self._compare(read_json(options["compare"]), titles, options["top"])

    def _compare(self, before, after, top):
        stats, shown = Counter(), []
        for key, new in after.items():
            old = before.get(key)
            if old is None:
                stats["нет в снимке"] += 1
            elif old["title"] == new["title"]:
                stats["без изменений"] += 1
            else:
                kind = "появилось" if old["title"] is None else "пропало" if new["title"] is None else "изменилось"
                stats[kind] += 1
                shown.append((kind, key, new["source"], (old["title"] or {}).get("ru"), (new["title"] or {}).get("ru")))
        self.stdout.write(json.dumps(stats, ensure_ascii=False))
        for row in shown[:top]:
            self.stdout.write(f"  {row}")

    def _moderation(self, options):
        validator = SemanticValidator()
        stats, shown, seen = Counter(), [], set()
        logs = (
            AIProcessingLog.objects.filter(status=AIProcessingStatus.MODERATION, product__product_type="medicines")
            .select_related("product__category")
            .order_by("-id")
        )
        for log in logs.iterator(chunk_size=200):
            if log.product_id in seen:
                continue
            seen.add(log.product_id)
            reasons = [reason for reason in validator.validate_log(log).reasons if reason.startswith("title")]
            if not reasons:
                continue
            source = medicine_source_name(log.product.name, log.product.external_data)[0]
            built = bool(build_medicine_title(source))
            for reason in reasons:
                stats[f"{reason}: {'шаблон собрал, брак проверки' if built else 'шаблон не собрал'}"] += 1
            shown.append((log.product_id, source, log.generated_title, reasons))
        self.stdout.write(json.dumps(stats, ensure_ascii=False))
        for row in shown[: options["top"]]:
            self.stdout.write(f"  {row}")
