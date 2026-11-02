"""Точечная замена исправленных абзацев на страницах лекарств, только по турецкому исходнику (TD-031).

    manage.py medicine_site_lines plan --backups before1.json before2.json.gz --out plan.json
    manage.py medicine_site_lines apply --plan plan.json                         # только показать
    manage.py medicine_site_lines apply --plan plan.json --apply --backup rows-before.json.gz

--backups — бэкапы памяти до исправления (medicine_memory_review apply). Модель не вызывается.
"""

import json

from django.core.management.base import BaseCommand

from apps.ai.services.medicine_site_lines import apply_site_lines, load_old_versions, match_plan, plan_site_lines
from apps.ai.services.translation_files import read_json, require_backup, write_json, write_rows_backup


class Command(BaseCommand):
    help = "Замена исправленных абзацев на страницах лекарств по турецкому исходнику, с бэкапом строк."

    def add_arguments(self, parser):
        steps = parser.add_subparsers(dest="step", required=True)

        step = steps.add_parser("plan", help="План замен (только чтение)")
        step.add_argument("--backups", required=True, nargs="+", help="Бэкапы памяти со старыми версиями перевода")
        step.add_argument("--out", required=True)

        step = steps.add_parser("apply", help="Запись плана (без --apply — только показать)")
        step.add_argument("--plan", required=True)
        step.add_argument("--apply", action="store_true", help="Записать")
        step.add_argument("--backup", help="Новый файл бэкапа строк (обязателен с --apply)")

    def handle(self, *args, **options):
        if options["step"] == "plan":
            self._plan(options)
        else:
            self._apply(options)

    def _report(self, data):
        self.stdout.write(json.dumps(data, ensure_ascii=False))

    def _plan(self, options):
        plan, stats, products = plan_site_lines(load_old_versions(options["backups"]))
        write_json(options["out"], plan)
        self._report({**stats, "лекарств": len(products)})

    def _apply(self, options):
        require_backup(options)
        plan = read_json(options["plan"])
        rows, changes, stats = match_plan(plan)
        self._report({**stats, "лекарств": len({item["base"] for item in plan})})
        for item in plan[:5]:
            self.stdout.write(f"  {item['base']} {item['field']}[{item['locale']}]: {item['old'][:80]!r} → {item['new'][:80]!r}")
        if not options["apply"]:
            self.stdout.write("Только показ: для записи — --apply --backup <файл>.")
            return
        write_rows_backup(options["backup"], [rows[pk] for pk in changes])
        apply_site_lines(rows, changes)
        self.stdout.write(f"Записано строк перевода: {len(changes)}, бэкап: {options['backup']}.")
