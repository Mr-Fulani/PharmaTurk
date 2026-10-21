"""Предзаполнение памяти абзацев инструкций через OpenAI Batch API (−50% цены) — частями.

Опционально, для массового прогона лекарств. То же самое кнопками — в админке:
AI → AI-прогоны → «Перевести абзацы инструкций (Batch API)»; общий код —
services/medicine_paragraph_batch.py, части из админки команда тоже видит.
Пакет отправляется частями по ``--part-size`` абзацев (по умолчанию 5000):
при ошибке теряются деньги одной части, а не всего пакета.

- ``submit`` — следующая часть: абзацы клинических разделов, которых ещё нет
  в памяти, по лекарствам в порядке pk — с лекарства после последней части
  (оно записано в метаданных пакета), ``--from-start`` — с начала каталога.
  Часть не отправляется, пока предыдущая в работе или у последней части нет в
  памяти больше ``--max-defect`` абзацев: она не забрана или брак выше порога.
- ``submit --retry <batch_id>`` — повтор только отклонённых абзацев этой части.
- ``collect <batch_id>`` — забирает готовую часть (ответ — до 24 ч), проверяет
  каждый абзац теми же правилами, что обычный перевод (дозировки, язык, длина,
  сдвиг ответа — тогда отклоняется весь запрос), пишет принятые в память и
  печатает отчёт: принято, отклонено по причинам, цена, можно ли дальше.
- ``status`` — все части: состояние, сколько абзацев, до какого лекарства.

Обычная обработка лекарств потом берёт абзацы из памяти; отклонённые
переведутся в ней же синхронно или повтором части.

    manage.py medicine_paragraph_batch submit --dry-run
    manage.py medicine_paragraph_batch submit
    manage.py medicine_paragraph_batch collect <batch_id>
    manage.py medicine_paragraph_batch submit --retry <batch_id>
    manage.py medicine_paragraph_batch status

``collect`` работает потоково (пиковая память — десятки МБ) и пишет в память
порциями по 500 строк, каждая в своей транзакции; прерванный (Ctrl+C) или
упавший collect повторяется той же командой — записанное не дублируется.
Входной файл части (несколько МБ; ~200–300 МБ на весь каталог одним пакетом)
временно кладётся в ``--work-dir`` (по умолчанию системный tmp), нужно ещё
1 ГБ свободного места.
"""

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.ai.services.llm_client import LLMClient
from apps.ai.services.medicine_memory import PARAGRAPH_NAMESPACE
from apps.ai.services.medicine_paragraph_batch import (
    MAX_DEFECT,
    PART_SIZE,
    RUNNING_STATUSES,
    PartError,
    check_previous_part,
    collect_part,
    describe,
    estimate,
    iter_parts,
    list_parts,
    part_summary,
    rejected_paragraphs,
    submit_part,
)


class Command(BaseCommand):
    help = "Перевод новых абзацев инструкций лекарств пакетом OpenAI Batch API частями (submit / collect / status)"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["submit", "collect", "status"])
        parser.add_argument("batch_id", nargs="?", help="ID пакета (части) для collect")
        parser.add_argument("--limit-products", type=int, default=0, help="Сколько лекарств взять (0 — все)")
        parser.add_argument("--part-size", type=int, default=PART_SIZE, help="submit: абзацев в части")
        parser.add_argument("--retry", default="", help="submit: только отклонённые абзацы этой части (batch_id)")
        parser.add_argument("--from-start", action="store_true", help="submit: часть с начала каталога")
        parser.add_argument(
            "--max-defect", type=float, default=MAX_DEFECT,
            help="Порог брака: доля абзацев части, не попавших в память, при которой дальше не идём",
        )
        parser.add_argument("--dry-run", action="store_true", help="submit: только оценка, без отправки")
        parser.add_argument("--work-dir", default="", help="collect: папка для временного входного файла")
        parser.add_argument("--progress-every", type=int, default=50, help="collect: прогресс каждые N запросов")

    def handle(self, *args, **options):
        try:
            if options["action"] == "submit":
                self._submit(options)
            elif options["action"] == "status":
                self._status()
            else:
                if not options["batch_id"]:
                    raise CommandError("collect требует batch_id")
                self._collect(options["batch_id"], options)
        except PartError as exc:
            raise CommandError(str(exc))

    def _submit(self, options):
        client = LLMClient()
        parts = list_parts(client)
        running = [describe(part) for part in parts if part.status in RUNNING_STATUSES]
        if running:
            raise CommandError(
                f"Часть ещё в работе: {', '.join(running)}. Дождитесь её и заберите: collect <batch_id> "
                "(состояние — status)"
            )
        work_dir = options["work_dir"] or None
        last_product = ""
        if options["retry"]:
            retried = client.client.batches.retrieve(options["retry"])
            paragraphs, total = rejected_paragraphs(client, retried, work_dir)
            self.stdout.write(f"Повтор части {options['retry']}: нет в памяти {len(paragraphs)} из {total} абзацев")
        else:
            previous = next((part for part in parts if not part.metadata.get("retry_of")), None)
            if previous is not None:
                check_previous_part(client, previous, options["max_defect"], work_dir)
            after = 0 if options["from_start"] or previous is None else int(previous.metadata["last_product"])
            remaining = iter_parts(after, options["part_size"], options["limit_products"])
            paragraphs, last_product = next(remaining, ([], ""))
            if not paragraphs:
                self.stdout.write(
                    f"После лекарства {after} абзацев не в памяти нет — проход по каталогу закончен. "
                    "Новый проход с начала: submit --from-start"
                )
                return
            missing = len(paragraphs) + sum(len(rest) for rest, _ in remaining)
            self.stdout.write(
                f"Часть №{len(parts) + 1}: лекарства с pk {after + 1}–{last_product}; "
                f"не в памяти после лекарства {after} ещё {missing} абзацев"
            )
        cost = estimate(paragraphs)
        self.stdout.write(
            f"Абзацев к переводу: {cost['paragraphs']}, {cost['chars']:,} симв., запросов {cost['requests']}; "
            f"оценка ≈${cost['cost_usd']:.2f} в Batch API (≈${cost['regular_cost_usd']:.2f} обычным путём)"
        )
        if options["dry_run"] or not paragraphs:
            return
        batch = submit_part(client, paragraphs, metadata={
            "kind": PARAGRAPH_NAMESPACE,
            "part": str(len(parts) + 1),
            "paragraphs": str(len(paragraphs)),
            "last_product": str(last_product),
            "retry_of": options["retry"],
        })
        self.stdout.write(self.style.SUCCESS(
            f"Часть №{len(parts) + 1} отправлена: {batch.id}. Готова до 24 ч (status); забрать: "
            f"manage.py medicine_paragraph_batch collect {batch.id}"
        ))

    def _status(self):
        parts = list_parts(LLMClient())
        if not parts:
            self.stdout.write("Частей ещё нет: manage.py medicine_paragraph_batch submit --dry-run")
            return
        for part in parts:
            meta, counts = part.metadata, part.request_counts
            created = datetime.fromtimestamp(part.created_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            scope = (
                f"повтор части {meta['retry_of']}" if meta.get("retry_of")
                else f"до лекарства {meta.get('last_product')}"
            )
            if meta.get("run"):
                scope += f"; AI-прогон #{meta['run']} из админки"
            self.stdout.write(
                f"№{meta['part']} {part.id} — {part.status}, {created}: абзацев {meta.get('paragraphs')}, "
                f"запросов {getattr(counts, 'completed', 0)}/{getattr(counts, 'total', 0)}, "
                f"с ошибкой {getattr(counts, 'failed', 0)}; {scope}"
            )

    def _collect(self, batch_id: str, options):
        client = LLMClient()
        batch = client.client.batches.retrieve(batch_id)
        counts = getattr(batch, "request_counts", None)
        if batch.status != "completed":
            self.stdout.write(f"Статус пакета: {batch.status}; {counts}")
            return
        if not batch.output_file_id:
            self.stdout.write(f"У пакета нет файла ответов; {counts}")
            return
        stats = collect_part(
            client, batch, options["work_dir"] or None, progress=self._progress,
            progress_every=options["progress_every"],
        )
        self._progress(stats, stats["total"])
        if stats["interrupted"]:
            self.stdout.write(self.style.WARNING(
                f"Остановлено. Записанное сохранено; повтор: manage.py medicine_paragraph_batch collect {batch_id}"
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"В память записано новых абзацев: {stats['created']} (принято {stats['accepted']}, "
            f"отклонено проверкой {stats['rejected']} — переведутся при обычной обработке или повтором части); "
            f"стоимость ≈${stats['cost']:.2f}; {counts}"
        ))
        self._report(batch, stats, options)

    def _report(self, batch, stats, options):
        """Итог части: брак по причинам, цена абзаца и можно ли отправлять следующую часть."""
        summary = part_summary(stats, int((batch.metadata or {}).get("paragraphs") or 0))
        if not summary["paragraphs"]:
            return
        reasons = ", ".join(f"{name} {count}" for name, count in summary["reasons"].items())
        self.stdout.write(
            f"Отчёт части {batch.id}: абзацев {summary['paragraphs']}, запросов {summary['requests']}; "
            f"принято {summary['accepted']}, брак {summary['defect_count']} ({summary['defect']:.1%})"
            + (f", из них без ответа {summary['no_answer']}" if summary["no_answer"] else "")
            + f"; сдвиг в {summary['shifted_requests']} запросах ({summary['shifted_share']:.1%})"
            + (f"; причины (у абзаца бывает несколько): {reasons}" if reasons else "")
        )
        self.stdout.write(
            f"Цена: ${summary['cost_usd']:.4f} — ${summary['per_1000']:.4f} за 1000 абзацев, "
            f"${summary['per_1000_accepted']:.4f} за 1000 принятых"
        )
        if summary["defect"] > options["max_defect"]:
            self.stdout.write(self.style.ERROR(
                f"Брак {summary['defect']:.1%} выше порога {options['max_defect']:.0%} — СТОП: следующую часть не "
                f"отправлять, сначала разобрать причины. Повторить отклонённые: submit --retry {batch.id}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Брак {summary['defect']:.1%} не выше порога {options['max_defect']:.0%} — можно следующую часть: "
                f"manage.py medicine_paragraph_batch submit (отклонённые: submit --retry {batch.id})"
            ))

    def _progress(self, stats, total):
        self.stdout.write(
            f"запросов {stats['requests']}/{total or '?'}: принято {stats['accepted']}, "
            f"отклонено {stats['rejected']}, записано новых {stats['created']}"
        )
        self.stdout.flush()
