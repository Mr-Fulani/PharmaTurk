"""Пересборка словаря МНН: Claude сверяет названия с Wikidata по коду АТХ, скептик перепроверяет (TD-031).

    manage.py medicine_inn_dictionary export --out inn.json
    manage.py medicine_inn_dictionary chunks --export inn.json --wikidata-dir wd --out chunks.jsonl
    (medicine_claude_batch: --kind inn)
    manage.py medicine_inn_dictionary decisions --chunks chunks.jsonl --results r.jsonl --out verify.jsonl
    (medicine_claude_batch: --kind inn_verify)
    manage.py medicine_inn_dictionary collect --chunks chunks.jsonl --results v.jsonl --out updates.json
    manage.py medicine_inn_dictionary apply --updates updates.json               # только показать
    manage.py medicine_inn_dictionary apply --updates updates.json --apply --backup before.json

БД пишет только apply с --apply: словарь, затем active_ingredient в переводах товаров.
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
    write_rows_backup,
)


class Command(BaseCommand):
    help = "Пересборка словаря МНН: выгрузка, части, сбор ответов, запись с бэкапом."
    requires_system_checks = []

    def add_arguments(self, parser):
        steps = parser.add_subparsers(dest="step", required=True)

        step = steps.add_parser("export", help="Словарь и коды АТХ лекарств")
        step.add_argument("--out", required=True)

        step = steps.add_parser("chunks", help="Части с доказательствами Wikidata")
        step.add_argument("--export", required=True)
        step.add_argument("--wikidata-dir", help="Папка с wd_atc_labels.csv, wd_atc_alias.csv, wd_who_inn.csv")
        step.add_argument("--chunk-size", type=int, default=dictionaries.INN_CHUNK_SIZE)
        step.add_argument("--out", required=True)

        step = steps.add_parser("decisions", help="Ответы первого прохода → части для скептика")
        step.add_argument("--chunks", required=True)
        step.add_argument("--results", required=True, nargs="+")
        step.add_argument("--out", required=True)

        step = steps.add_parser("collect", help="Ответы скептика → файл записи")
        step.add_argument("--chunks", required=True)
        step.add_argument("--results", required=True, nargs="+")
        step.add_argument("--out", required=True)
        step.add_argument("--show", type=int, default=30, help="Сколько замечаний показать")

        step = steps.add_parser("apply", help="Запись в словарь (без --apply — только показать)")
        step.add_argument("--updates", required=True)
        step.add_argument("--apply", action="store_true", help="Записать")
        step.add_argument("--backup", help="Новый файл бэкапа строк (обязателен с --apply)")

    def handle(self, *args, **options):
        getattr(self, "_" + options["step"])(options)

    def _report(self, data):
        self.stdout.write(json.dumps(data, ensure_ascii=False))

    def _export(self, options):
        rows = dictionaries.export_inn()
        write_json(options["out"], rows)
        self._report({"записей": len(rows), "с АТХ": sum(1 for row in rows if row["atc"])})

    def _chunks(self, options):
        evidence = dictionaries.wikidata_evidence(options["wikidata_dir"]) if options["wikidata_dir"] else None
        chunks = dictionaries.inn_chunks(read_json(options["export"]), evidence, options["chunk_size"])
        write_jsonl(options["out"], chunks)
        self._report({"частей": len(chunks)})

    def _decisions(self, options):
        rows, stats = dictionaries.with_decisions(list(read_jsonl(options["chunks"])), options["results"])
        write_jsonl(options["out"], rows)
        self._report(stats)

    def _collect(self, options):
        updates, stats, notes = dictionaries.collect_inn(list(read_jsonl(options["chunks"])), options["results"])
        write_json(options["out"], updates)
        self._report({**stats, "к записи": len(updates), "товаров": sum(row["products"] for row in updates)})
        for note in notes[: options["show"]]:
            self.stdout.write(f"  {note}")

    def _apply(self, options):
        require_backup(options)
        rows, stats = dictionaries.plan_inn_updates(read_json(options["updates"]))
        self._report(stats)
        for _, update in rows[:20]:
            self.stdout.write(f"  {update['tr']}: {update['ru_old']} → {update['ru_new']} | {update['en_new']}")
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        write_rows_backup(options["backup"], [record for record, _ in rows])
        updated = dictionaries.apply_inn_updates(rows)
        self.stdout.write(f"Записано: {len(rows)}, строк переводов товаров: {updated}, бэкап: {options['backup']}.")
