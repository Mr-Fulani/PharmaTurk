"""Запросы проверки переводов в Message Batches API Claude (TD-025, TD-031). БД не пишет.

    manage.py medicine_claude_batch submit --kind review --effort high --input chunks.jsonl.gz  # только показать
    manage.py medicine_claude_batch submit --kind review --effort high --input chunks.jsonl.gz --send
    manage.py medicine_claude_batch status --batch-id msgbatch_1 msgbatch_2
    manage.py medicine_claude_batch results --batch-id msgbatch_1 --out results.jsonl

Без --send запрос никуда не уходит: показывается число запросов и оценка входа.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai.services import claude_batches
from apps.ai.services.translation_files import read_jsonl, write_jsonl


class Command(BaseCommand):
    help = "Проверка переводов через Message Batches API Claude: отправка, состояние, ответы."
    requires_system_checks = []

    def add_arguments(self, parser):
        steps = parser.add_subparsers(dest="step", required=True)

        step = steps.add_parser("submit", help="Отправить части (без --send — только показать)")
        step.add_argument("--kind", required=True, choices=sorted(claude_batches.KINDS))
        step.add_argument("--effort", required=True, choices=claude_batches.EFFORTS)
        step.add_argument("--input", required=True, help="JSON lines с частями")
        step.add_argument("--model", default=claude_batches.MODEL)
        step.add_argument("--max-tokens", type=int, help="Лимит ответа для части, которая в него не уложилась")
        step.add_argument("--send", action="store_true", help="Отправить (платно)")

        step = steps.add_parser("status", help="Состояние пакетов")
        step.add_argument("--batch-id", required=True, nargs="+")

        step = steps.add_parser("results", help="Скачать ответы пакета")
        step.add_argument("--batch-id", required=True)
        step.add_argument("--out", required=True)

    def handle(self, *args, **options):
        if options["step"] == "submit":
            self._submit(options)
            return
        if not settings.ANTHROPIC_API_KEY:
            raise CommandError("Нет ANTHROPIC_API_KEY")
        if options["step"] == "status":
            for batch_id in options["batch_id"]:
                self.stdout.write(json.dumps(claude_batches.status(batch_id)))
        else:
            written = write_jsonl(options["out"], claude_batches.results(options["batch_id"]))
            self.stdout.write(json.dumps({"ответов": written}, ensure_ascii=False))

    def _submit(self, options):
        rows = list(read_jsonl(options["input"]))
        if not options["send"]:
            self.stdout.write(json.dumps(claude_batches.estimate(options["kind"], rows), ensure_ascii=False))
            self.stdout.write("Только показ: для отправки — --send. Цена выхода зависит от числа замечаний.")
            return
        if not settings.ANTHROPIC_API_KEY:
            raise CommandError("Нет ANTHROPIC_API_KEY")
        result = claude_batches.submit(
            options["kind"], options["effort"], rows, model=options["model"], max_tokens=options["max_tokens"],
        )
        self.stdout.write(json.dumps(result))
