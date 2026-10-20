"""Предзаполнение памяти абзацев инструкций через OpenAI Batch API (−50% цены) — частями.

Опционально, для массового прогона лекарств. Пакет отправляется частями по
``--part-size`` абзацев (по умолчанию 5000): при ошибке теряются деньги одной
части, а не всего пакета.

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

import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.ai.models import AITranslationMemory
from apps.ai.services.llm_client import LLMClient
from apps.ai.services.medicine_memory import (
    PARAGRAPH_MAX_TOKENS,
    PARAGRAPH_NAMESPACE,
    PARAGRAPH_SYSTEM_PROMPT,
    check_paragraph_payload,
    estimate_translation_cost,
    items_from_user_prompt,
    needs_translation,
    normalize_paragraph,
    paragraph_batches,
    paragraph_items,
    paragraph_user_prompt,
    source_tab_texts,
    split_paragraphs,
)
from apps.ai.services.medicine_title import medicine_source_name, paragraph_brand
from apps.ai.services.translation_memory import REMEMBER_BATCH_SIZE, remember, source_hash
from apps.catalog.models import MedicineProduct


# Запас свободного места сверх размера входного файла пакета (диск прода маленький).
MIN_FREE_DISK_BYTES = 1024 * 2**20
# Пакет ещё не готов — следующую часть не отправлять (иначе те же абзацы оплатятся дважды).
RUNNING_STATUSES = ("validating", "in_progress", "finalizing", "cancelling")


class Command(BaseCommand):
    help = "Перевод новых абзацев инструкций лекарств пакетом OpenAI Batch API частями (submit / collect / status)"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["submit", "collect", "status"])
        parser.add_argument("batch_id", nargs="?", help="ID пакета (части) для collect")
        parser.add_argument("--limit-products", type=int, default=0, help="Сколько лекарств взять (0 — все)")
        parser.add_argument("--part-size", type=int, default=5000, help="submit: абзацев в части")
        parser.add_argument("--retry", default="", help="submit: только отклонённые абзацы этой части (batch_id)")
        parser.add_argument("--from-start", action="store_true", help="submit: часть с начала каталога")
        parser.add_argument(
            "--max-defect", type=float, default=0.15,
            help="Порог брака: доля абзацев части, не попавших в память, при которой дальше не идём",
        )
        parser.add_argument("--dry-run", action="store_true", help="submit: только оценка, без отправки")
        parser.add_argument("--work-dir", default="", help="collect: папка для временного входного файла")
        parser.add_argument("--progress-every", type=int, default=50, help="collect: прогресс каждые N запросов")

    def handle(self, *args, **options):
        if options["action"] == "submit":
            self._submit(options)
        elif options["action"] == "status":
            self._status()
        else:
            if not options["batch_id"]:
                raise CommandError("collect требует batch_id")
            self._collect(options["batch_id"], options)

    @staticmethod
    def _cached_hashes(hashes: list[str]) -> set[str]:
        cached = set()
        for start in range(0, len(hashes), 5000):
            cached.update(AITranslationMemory.objects.filter(
                namespace=PARAGRAPH_NAMESPACE, source_hash__in=hashes[start:start + 5000]
            ).values_list("source_hash", flat=True))
        return cached

    def _missing_paragraphs(self, options, after_product: int = 0) -> dict[str, int]:
        """Абзацы, которых нет в памяти, → pk первого лекарства с ними (по порядку pk)."""
        qs = MedicineProduct.objects.filter(is_active=True, pk__gt=after_product).order_by("pk").values_list(
            "pk", "name", "active_ingredient", "external_data"
        )
        if options["limit_products"]:
            qs = qs[: options["limit_products"]]
        paragraphs: dict[str, tuple[str, int]] = {}
        for pk, name, active_ingredient, external_data in qs.iterator(chunk_size=200):
            # Ключи абзацев — как при обработке: бренд из турецкого оригинала.
            brand = paragraph_brand(medicine_source_name(name, external_data)[0], active_ingredient)
            for text in source_tab_texts(external_data):
                for part in split_paragraphs(text)[::2]:
                    if needs_translation(part):
                        paragraph = normalize_paragraph(part, brand)
                        paragraphs.setdefault(source_hash(paragraph), (paragraph, pk))
        for key in self._cached_hashes(list(paragraphs)):
            paragraphs.pop(key, None)
        return dict(paragraphs.values())

    @staticmethod
    def _parts(client) -> list:
        """Части, отправленные этой командой (с номером в метаданных), новые первыми."""
        return [
            batch for batch in client.client.batches.list(limit=100)
            if (batch.metadata or {}).get("kind") == PARAGRAPH_NAMESPACE and (batch.metadata or {}).get("part")
        ]

    def _part_paragraphs(self, client, batch, work_dir) -> list[str]:
        """Все абзацы части — из её входного файла."""
        with tempfile.NamedTemporaryFile(dir=work_dir, suffix=".jsonl") as input_file:
            self._download_input(client, batch.input_file_id, input_file, work_dir)
            input_file.seek(0)
            return [
                text
                for line in input_file if line.strip()
                for text in items_from_user_prompt(json.loads(line)["body"]["messages"][1]["content"]).values()
            ]

    def _rejected_paragraphs(self, client, batch, work_dir) -> tuple[list[str], int]:
        """Абзацы части, которых нет в памяти (отклонены проверкой или часть не забрана), и размер части."""
        paragraphs = self._part_paragraphs(client, batch, work_dir)
        cached = self._cached_hashes([source_hash(p) for p in paragraphs])
        return [p for p in paragraphs if source_hash(p) not in cached], len(paragraphs)

    def _check_previous_part(self, client, part, options) -> None:
        """Следующая часть — только если у последней брак не выше порога."""
        rejected, total = self._rejected_paragraphs(client, part, options["work_dir"] or tempfile.gettempdir())
        share = len(rejected) / total if total else 0
        if share > options["max_defect"]:
            raise CommandError(
                f"Часть №{part.metadata['part']} ({part.id}, {part.status}): нет в памяти {len(rejected)} из "
                f"{total} абзацев ({share:.1%}) — больше порога {options['max_defect']:.0%}. Либо она не "
                f"забрана (collect {part.id}), либо брак высокий — смотрите отчёт collect. Повторить "
                f"отклонённые: submit --retry {part.id}; идти дальше всё равно: --max-defect 1"
            )

    def _submit(self, options):
        client = LLMClient()
        parts = self._parts(client)
        running = [
            f"№{part.metadata['part']} {part.id} ({part.status})" for part in parts if part.status in RUNNING_STATUSES
        ]
        if running:
            raise CommandError(
                f"Часть ещё в работе: {', '.join(running)}. Дождитесь её и заберите: collect <batch_id> "
                "(состояние — status)"
            )
        last_product = ""
        if options["retry"]:
            retried = client.client.batches.retrieve(options["retry"])
            paragraphs, total = self._rejected_paragraphs(
                client, retried, options["work_dir"] or tempfile.gettempdir()
            )
            self.stdout.write(f"Повтор части {options['retry']}: нет в памяти {len(paragraphs)} из {total} абзацев")
        else:
            previous = next((part for part in parts if not part.metadata.get("retry_of")), None)
            if previous is not None:
                self._check_previous_part(client, previous, options)
            after = 0 if options["from_start"] or previous is None else int(previous.metadata["last_product"])
            missing = self._missing_paragraphs(options, after)
            paragraphs = []
            for paragraph, pk in missing.items():
                # Часть заканчивается на границе лекарства: следующая начнётся с лекарства после него.
                if len(paragraphs) >= options["part_size"] and pk != last_product:
                    break
                paragraphs.append(paragraph)
                last_product = pk
            if not paragraphs:
                self.stdout.write(
                    f"После лекарства {after} абзацев не в памяти нет — проход по каталогу закончен. "
                    "Новый проход с начала: submit --from-start"
                )
                return
            self.stdout.write(
                f"Часть №{len(parts) + 1}: лекарства с pk {after + 1}–{last_product}; "
                f"не в памяти после лекарства {after} ещё {len(missing)} абзацев"
            )
        batches = paragraph_batches(paragraphs)
        chars = sum(len(p) for p in paragraphs)
        estimate = estimate_translation_cost(paragraphs)
        self.stdout.write(
            f"Абзацев к переводу: {len(paragraphs)}, {chars:,} симв., запросов {len(batches)}; "
            f"оценка ≈${estimate['cost_usd'] / 2:.2f} в Batch API (≈${estimate['cost_usd']:.2f} обычным путём)"
        )
        if options["dry_run"] or not batches:
            return
        lines = []
        for index, batch in enumerate(batches):
            body = {
                "model": client.model,
                "messages": [
                    {"role": "system", "content": PARAGRAPH_SYSTEM_PROMPT},
                    {"role": "user", "content": paragraph_user_prompt(paragraph_items(batch))},
                ],
                "temperature": 0,
                "max_tokens": PARAGRAPH_MAX_TOKENS,
                "response_format": {"type": "json_object"},
            }
            lines.append(json.dumps(
                {"custom_id": f"mp-{index}", "method": "POST", "url": "/v1/chat/completions", "body": body},
                ensure_ascii=False,
            ))
        upload = client.client.files.create(
            file=("medicine_paragraphs.jsonl", "\n".join(lines).encode("utf-8")), purpose="batch"
        )
        batch = client.client.batches.create(
            input_file_id=upload.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata={
                "kind": PARAGRAPH_NAMESPACE,
                "part": str(len(parts) + 1),
                "paragraphs": str(len(paragraphs)),
                "last_product": str(last_product),
                "retry_of": options["retry"],
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"Часть №{len(parts) + 1} отправлена: {batch.id}. Готова до 24 ч (status); забрать: "
            f"manage.py medicine_paragraph_batch collect {batch.id}"
        ))

    def _status(self):
        parts = self._parts(LLMClient())
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
            self.stdout.write(
                f"№{meta['part']} {part.id} — {part.status}, {created}: абзацев {meta.get('paragraphs')}, "
                f"запросов {getattr(counts, 'completed', 0)}/{getattr(counts, 'total', 0)}, "
                f"с ошибкой {getattr(counts, 'failed', 0)}; {scope}"
            )

    def _collect(self, batch_id: str, options):
        """Потоковая загрузка готового пакета в память переводов.

        Ответ читается построчно прямо из OpenAI; входной файл (исходные абзацы)
        скачивается во временный файл и читается по смещениям — в памяти Python
        только текущая строка и порция до REMEMBER_BATCH_SIZE абзацев. Запись
        идемпотентна: прерванный collect можно просто повторить.
        """
        client = LLMClient()
        batch = client.client.batches.retrieve(batch_id)
        counts = getattr(batch, "request_counts", None)
        if batch.status != "completed":
            self.stdout.write(f"Статус пакета: {batch.status}; {counts}")
            return
        if not batch.output_file_id:
            self.stdout.write(f"У пакета нет файла ответов; {counts}")
            return
        total = getattr(counts, "completed", None) or getattr(counts, "total", None) or 0
        price = client.pricing.get(client.model) or {}
        stats = {"requests": 0, "accepted": 0, "rejected": 0, "created": 0, "cost": 0.0,
                 "reasons": Counter(), "shifted_requests": 0}
        pending: dict = {}

        def flush():
            stats["created"] += remember(PARAGRAPH_NAMESPACE, pending)
            pending.clear()

        work_dir = options["work_dir"] or tempfile.gettempdir()
        with tempfile.NamedTemporaryFile(dir=work_dir, suffix=".jsonl") as input_file:
            self._download_input(client, batch.input_file_id, input_file, work_dir)
            offsets = self._index_requests(input_file)
            try:
                with client.client.files.with_streaming_response.content(batch.output_file_id) as response:
                    for line in response.iter_lines():
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        body = (row.get("response") or {}).get("body") or {}
                        items = self._request_items(input_file, offsets.get(row.get("custom_id")))
                        choice = (body.get("choices") or [{}])[0]
                        payload = {}
                        if choice.get("finish_reason") != "length":
                            payload = client._parse_json_response(
                                (choice.get("message") or {}).get("content") or ""
                            )
                        usage = body.get("usage") or {}
                        stats["cost"] += (
                            usage.get("prompt_tokens", 0) * price.get("input", 0)
                            + usage.get("completion_tokens", 0) * price.get("output", 0)
                        ) / 1_000_000 / 2  # Batch API — половина цены
                        accepted, rejected = check_paragraph_payload(items, payload)
                        pending.update(accepted)
                        stats["accepted"] += len(accepted)
                        stats["rejected"] += len(rejected)
                        for problems in rejected.values():
                            stats["reasons"].update(set(problems))
                        if any("shifted" in problems for problems in rejected.values()):
                            stats["shifted_requests"] += 1
                        stats["requests"] += 1
                        if len(pending) >= REMEMBER_BATCH_SIZE:
                            flush()
                        if stats["requests"] % options["progress_every"] == 0:
                            self._progress(stats, total)
                    flush()
            except KeyboardInterrupt:
                flush()
                self._progress(stats, total)
                self.stdout.write(self.style.WARNING(
                    f"Остановлено. Записанное сохранено; повтор: manage.py medicine_paragraph_batch collect {batch_id}"
                ))
                return
        self._progress(stats, total)
        self.stdout.write(self.style.SUCCESS(
            f"В память записано новых абзацев: {stats['created']} (принято {stats['accepted']}, "
            f"отклонено проверкой {stats['rejected']} — переведутся при обычной обработке или повтором части); "
            f"стоимость ≈${stats['cost']:.2f}; {counts}"
        ))
        self._report(batch_id, stats, options)

    def _report(self, batch_id, stats, options):
        """Итог части: брак по причинам, цена абзаца и можно ли отправлять следующую часть."""
        paragraphs = stats["accepted"] + stats["rejected"]
        if not paragraphs:
            return
        defect = stats["rejected"] / paragraphs
        shifted_share = stats["shifted_requests"] / max(stats["requests"], 1)
        reasons = ", ".join(f"{name} {count}" for name, count in stats["reasons"].most_common())
        self.stdout.write(
            f"Отчёт части {batch_id}: абзацев {paragraphs}, запросов {stats['requests']}; "
            f"принято {stats['accepted']}, брак {stats['rejected']} ({defect:.1%}); "
            f"сдвиг в {stats['shifted_requests']} запросах ({shifted_share:.1%})"
            + (f"; причины (у абзаца бывает несколько): {reasons}" if reasons else "")
        )
        self.stdout.write(
            f"Цена: ${stats['cost']:.4f} — ${stats['cost'] / paragraphs * 1000:.4f} за 1000 абзацев, "
            f"${stats['cost'] / max(stats['accepted'], 1) * 1000:.4f} за 1000 принятых"
        )
        if defect > options["max_defect"]:
            self.stdout.write(self.style.ERROR(
                f"Брак {defect:.1%} выше порога {options['max_defect']:.0%} — СТОП: следующую часть не "
                f"отправлять, сначала разобрать причины. Повторить отклонённые: submit --retry {batch_id}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Брак {defect:.1%} не выше порога {options['max_defect']:.0%} — можно следующую часть: "
                f"manage.py medicine_paragraph_batch submit (отклонённые: submit --retry {batch_id})"
            ))

    def _progress(self, stats, total):
        self.stdout.write(
            f"запросов {stats['requests']}/{total or '?'}: принято {stats['accepted']}, "
            f"отклонено {stats['rejected']}, записано новых {stats['created']}"
        )
        self.stdout.flush()

    def _download_input(self, client, file_id, target, work_dir):
        size = getattr(client.client.files.retrieve(file_id), "bytes", 0) or 0
        free = shutil.disk_usage(work_dir).free
        if size and free < size + MIN_FREE_DISK_BYTES:
            raise CommandError(
                f"Мало места в {work_dir}: свободно {free // 2**20} МБ, нужно "
                f"{(size + MIN_FREE_DISK_BYTES) // 2**20} МБ (--work-dir)"
            )
        with client.client.files.with_streaming_response.content(file_id) as response:
            for chunk in response.iter_bytes():
                target.write(chunk)
        target.flush()

    @staticmethod
    def _index_requests(input_file) -> dict[str, int]:
        """custom_id → смещение строки во входном файле."""
        offsets = {}
        input_file.seek(0)
        while True:
            offset = input_file.tell()
            line = input_file.readline()
            if not line:
                break
            match = re.search(rb'"custom_id"\s*:\s*"([^"]+)"', line)
            if match:
                offsets[match.group(1).decode()] = offset
        return offsets

    @staticmethod
    def _request_items(input_file, offset) -> dict[str, str]:
        if offset is None:
            return {}
        input_file.seek(offset)
        row = json.loads(input_file.readline())
        return items_from_user_prompt(row["body"]["messages"][1]["content"])
