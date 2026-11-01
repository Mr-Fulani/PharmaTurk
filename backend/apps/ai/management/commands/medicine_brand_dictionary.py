"""Словарь брендов лекарств кириллицей для SEO: Claude пишет, скептик перепроверяет (TD-031).

    manage.py medicine_brand_dictionary export --out brands.json         # бренды не из словаря
    manage.py medicine_brand_dictionary chunks --export brands.json --out chunks.jsonl
    (medicine_claude_batch: --kind brand)
    manage.py medicine_brand_dictionary decisions --chunks chunks.jsonl --results r.jsonl --out verify.jsonl
    (medicine_claude_batch: --kind brand_verify)
    manage.py medicine_brand_dictionary collect --chunks chunks.jsonl --results v.jsonl --out brands_dict.json
    manage.py medicine_brand_dictionary apply --brands brands_dict.json               # только показать
    manage.py medicine_brand_dictionary apply --brands brands_dict.json --apply --backup created.json

БД пишет только apply с --apply и только новые ключи. Бэкап — список хэшей созданных записей для отката.
SEO опубликованных лекарств после записи обновляет medicine_refresh_code_fields.
"""

import json

from django.core.management.base import BaseCommand

from apps.ai.services import medicine_dictionaries as dictionaries
from apps.ai.services.translation_files import (
    read_json,
    read_jsonl,
    require_backup,
    write_json,
    write_jsonl,
)
from apps.ai.services.translation_memory import source_hash


class Command(BaseCommand):
    help = "Словарь брендов лекарств кириллицей: выгрузка, части, сбор ответов, запись новых ключей."
    requires_system_checks = []

    def add_arguments(self, parser):
        steps = parser.add_subparsers(dest="step", required=True)

        step = steps.add_parser("export", help="Бренды каталога с примерами названий")
        step.add_argument("--out", required=True)
        step.add_argument("--all", action="store_true", help="И те, что уже есть в словаре")

        step = steps.add_parser("chunks", help="Части для модели, сначала частые бренды")
        step.add_argument("--export", required=True)
        step.add_argument("--chunk-size", type=int, default=dictionaries.BRAND_CHUNK_SIZE)
        step.add_argument("--out", required=True)

        step = steps.add_parser("decisions", help="Ответы первого прохода → части для скептика")
        step.add_argument("--chunks", required=True)
        step.add_argument("--results", required=True, nargs="+")
        step.add_argument("--out", required=True)

        step = steps.add_parser("collect", help="Ответы скептика → словарь {бренд: кириллица}")
        step.add_argument("--chunks", required=True)
        step.add_argument("--results", required=True, nargs="+")
        step.add_argument("--out", required=True)
        step.add_argument("--show", type=int, default=20, help="Сколько отсеянных показать")

        step = steps.add_parser("apply", help="Запись новых ключей (без --apply — только показать)")
        step.add_argument("--brands", required=True)
        step.add_argument("--apply", action="store_true", help="Записать")
        step.add_argument("--backup", help="Новый файл со списком хэшей для отката (обязателен с --apply)")

    def handle(self, *args, **options):
        getattr(self, "_" + options["step"])(options)

    def _report(self, data):
        self.stdout.write(json.dumps(data, ensure_ascii=False))

    def _export(self, options):
        rows = dictionaries.export_brands(include_known=options["all"])
        write_json(options["out"], rows)
        self._report({"брендов": len(rows)})

    def _chunks(self, options):
        chunks = dictionaries.brand_chunks(read_json(options["export"]), options["chunk_size"])
        write_jsonl(options["out"], chunks)
        self._report({"частей": len(chunks)})

    def _decisions(self, options):
        rows, stats = dictionaries.with_decisions(list(read_jsonl(options["chunks"])), options["results"])
        write_jsonl(options["out"], rows)
        self._report(stats)

    def _collect(self, options):
        brands, stats, dropped = dictionaries.collect_brands(list(read_jsonl(options["chunks"])), options["results"])
        write_json(options["out"], brands)
        self._report(stats)
        for item in dropped[: options["show"]]:
            self.stdout.write(f"  отсев: {item}")

    def _apply(self, options):
        require_backup(options)
        brands = read_json(options["brands"])
        new = dictionaries.new_brands(brands)
        self._report({"в файле": len(brands), "уже в словаре": len(brands) - len(new), "к записи": len(new)})
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        write_json(options["backup"], [source_hash(brand) for brand in new], mode="xt")
        created = dictionaries.apply_brands(new)
        self.stdout.write(f"Создано: {created}, список для отката: {options['backup']}.")
