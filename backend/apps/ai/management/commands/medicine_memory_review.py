"""Проверка памяти абзацев лекарств моделью: шаги без запросов к API (TD-025, TD-031).

    manage.py medicine_memory_review export --out memory.jsonl.gz
    manage.py medicine_memory_review alignment --memory memory.jsonl.gz --out alignment.json
    manage.py medicine_memory_review chunks --memory … --alignment … --out-dir run [--seen ids.json] [--limit 50]
    manage.py medicine_memory_review flagged --chunks run/chunks.jsonl.gz --results a.jsonl b.jsonl --out flagged.jsonl
    manage.py medicine_memory_review fragments --fixes run/fixes.jsonl --out fragments.jsonl
    manage.py medicine_memory_review fixes --chunks … --groups … --alignment … --memory … --out-dir run \
        --review a.jsonl b.jsonl --verify v.jsonl [--fragment f.jsonl]
    manage.py medicine_memory_review updates --memory … --fixes run/fixes.jsonl --out updates.json
    manage.py medicine_memory_review apply --updates updates.json               # только показать
    manage.py medicine_memory_review apply --updates updates.json --apply --backup before.json
    manage.py medicine_memory_review apply --updates updates.json --verify      # сверка записанного
    manage.py medicine_memory_review score --dir run --labels p4_real.json

БД пишет только apply с --apply. Запросы к Claude — medicine_claude_batch. Порядок — AI_GUIDE.md.
"""

import json
import os

from django.core.management.base import BaseCommand

from apps.ai.services import memory_review as review
from apps.ai.services.translation_files import (
    read_json,
    read_jsonl,
    require_backup,
    write_json,
    write_jsonl,
    write_rows_backup,
)


class Command(BaseCommand):
    help = "Проверка памяти абзацев лекарств: выгрузка, словарь, части, сбор правок, запись с бэкапом."
    requires_system_checks = []

    def add_arguments(self, parser):
        steps = parser.add_subparsers(dest="step", required=True)

        step = steps.add_parser("export", help="Выгрузка абзацев и МНН")
        step.add_argument("--out", required=True)

        step = steps.add_parser("alignment", help="Словарь терминов из памяти")
        step.add_argument("--memory", required=True)
        step.add_argument("--out", required=True)

        step = steps.add_parser("chunks", help="Непроверенные записи → части с подсказкой словаря")
        step.add_argument("--memory", required=True)
        step.add_argument("--alignment", required=True)
        step.add_argument("--out-dir", required=True)
        step.add_argument("--seen", help="JSON со списком id уже проверенных записей")
        step.add_argument("--skip-sources", help="JSON [{tr}] абзацев, переведённых со скептиком")
        step.add_argument("--chunk-size", type=int, default=review.CHUNK_SIZE)
        step.add_argument("--limit", type=int, default=0, help="Только N самых подозрительных (пилот)")

        step = steps.add_parser("flagged", help="Ответы проверяющего → части для скептика")
        step.add_argument("--chunks", required=True)
        step.add_argument("--results", required=True, nargs="+")
        step.add_argument("--out", required=True)

        step = steps.add_parser("fragments", help="Правки обрывков → части для арбитра")
        step.add_argument("--fixes", required=True)
        step.add_argument("--out", required=True)

        step = steps.add_parser("fixes", help="Ответы всех проходов → правки и отклонённые")
        step.add_argument("--chunks", required=True)
        step.add_argument("--groups", required=True)
        step.add_argument("--alignment", required=True)
        step.add_argument("--memory", required=True)
        step.add_argument("--out-dir", required=True)
        step.add_argument("--review", required=True, nargs="+")
        step.add_argument("--verify", required=True, nargs="+")
        step.add_argument("--fragment", nargs="*", default=[])

        step = steps.add_parser("updates", help="Правки → файл записи с вариантами абзацев")
        step.add_argument("--memory", required=True)
        step.add_argument("--fixes", required=True)
        step.add_argument("--out", required=True)

        step = steps.add_parser("apply", help="Запись в память (без --apply — только показать)")
        step.add_argument("--updates", required=True)
        step.add_argument("--apply", action="store_true", help="Записать")
        step.add_argument("--backup", help="Новый файл бэкапа строк (обязателен с --apply)")
        step.add_argument("--verify", action="store_true", help="Сверить записанное с файлом")
        step.add_argument("--show", type=int, default=20, help="Сколько пропусков показать")

        step = steps.add_parser("score", help="Замер на разметке: что нашли и исправили")
        step.add_argument("--dir", required=True, help="Папка с fixes.jsonl и rejected.jsonl")
        step.add_argument("--labels", required=True)

    def handle(self, *args, **options):
        getattr(self, "_" + options["step"])(options)

    def _report(self, data):
        self.stdout.write(json.dumps(data, ensure_ascii=False, default=dict))

    def _export(self, options):
        self._report({"выгружено": review.export_memory(options["out"])})

    def _alignment(self, options):
        data = review.build_alignment(read_jsonl(options["memory"]))
        write_json(options["out"], data)
        self._report({"записей": data["N"], "турецких основ": len(data["tr_df"])})

    def _chunks(self, options):
        seen = read_json(options["seen"]) if options["seen"] else []
        skip = [row["tr"] for row in read_json(options["skip_sources"])] if options["skip_sources"] else []
        chunks, groups, reviewed, stats = review.build_chunks(
            read_jsonl(options["memory"]), review.Alignment(read_json(options["alignment"])),
            seen=seen, skip_sources=skip, chunk_size=options["chunk_size"], limit=options["limit"],
        )
        os.makedirs(options["out_dir"], exist_ok=True)
        write_jsonl(os.path.join(options["out_dir"], "chunks.jsonl.gz"), chunks)
        write_json(os.path.join(options["out_dir"], "groups.json"), groups)
        write_json(os.path.join(options["out_dir"], "reviewed_ids.json"), reviewed)
        write_json(os.path.join(options["out_dir"], "stats.json"), stats)
        self._report(stats)

    def _flagged(self, options):
        rows, stats = review.flagged_rows(review.read_chunks(options["chunks"]), options["results"])
        write_jsonl(options["out"], rows)
        self._report(stats)

    def _fragments(self, options):
        rows = review.fragment_rows(read_jsonl(options["fixes"]))
        write_jsonl(options["out"], rows)
        self._report({"частей": len(rows), "правок": sum(len(row["items"]) for row in rows)})

    def _fixes(self, options):
        fixes, rejected, summary = review.collect_fixes(
            review.read_chunks(options["chunks"]), read_json(options["groups"]),
            review.Alignment(read_json(options["alignment"])), review.memory_vocabulary(read_jsonl(options["memory"])),
            options["review"], options["verify"], options["fragment"],
        )
        os.makedirs(options["out_dir"], exist_ok=True)
        write_jsonl(os.path.join(options["out_dir"], "fixes.jsonl"), fixes)
        write_jsonl(os.path.join(options["out_dir"], "rejected.jsonl"), rejected)
        write_json(os.path.join(options["out_dir"], "stats.json"), summary)
        self._report(summary)

    def _updates(self, options):
        fixes = list(read_jsonl(options["fixes"]))
        updates = review.build_updates(read_jsonl(options["memory"]), fixes)
        write_json(options["out"], updates)
        self._report({"записей": len(updates), "представителей": len(fixes)})

    def _apply(self, options):
        require_backup(options)
        updates = read_json(options["updates"])
        if options["verify"]:
            self._report(review.verify_memory_updates(updates))
            return
        rows, stats, skipped = review.plan_memory_updates(updates)
        self._report({**stats, "всего к записи": len(rows)})
        for item in skipped[: options["show"]]:
            self.stdout.write(f"  пропуск: {item}")
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        write_rows_backup(options["backup"], [record for record, _, _ in rows])
        self.stdout.write(f"Записано: {review.apply_memory_updates(rows)}, бэкап строк: {options['backup']}.")

    def _score(self, options):
        fixes = list(read_jsonl(os.path.join(options["dir"], "fixes.jsonl")))
        rejected = list(read_jsonl(os.path.join(options["dir"], "rejected.jsonl")))
        labels = read_json(options["labels"])
        for row in review.score_against_labels(fixes, rejected, labels):
            self._report(row)
        labelled = {row["idx"] for row in labels}
        self._report({"правок всего": len(fixes), "вне разметки": sum(1 for row in fixes if row["id"] not in labelled)})
