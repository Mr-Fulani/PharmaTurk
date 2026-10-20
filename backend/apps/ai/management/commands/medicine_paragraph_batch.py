"""Предзаполнение памяти абзацев инструкций через OpenAI Batch API (−50% цены).

Опционально, для массового прогона лекарств. ``submit`` собирает уникальные
абзацы клинических разделов, которых ещё нет в памяти, и отправляет их одним
пакетом (ответ — до 24 ч). ``collect`` забирает готовый пакет, проверяет
каждый абзац теми же правилами, что обычный перевод (дозировки, язык, длина),
и пишет принятые в память. Обычная обработка лекарств потом берёт абзацы из
памяти; отклонённые переведутся в ней же синхронно.

    manage.py medicine_paragraph_batch submit --limit-products 500 --dry-run
    manage.py medicine_paragraph_batch submit --limit-products 500
    manage.py medicine_paragraph_batch collect <batch_id>

``collect`` работает потоково (пиковая память — десятки МБ) и пишет в память
порциями по 500 строк, каждая в своей транзакции; прерванный (Ctrl+C) или
упавший collect повторяется той же командой — записанное не дублируется.
Входной файл пакета (~200–300 МБ на весь каталог) временно кладётся в
``--work-dir`` (по умолчанию системный tmp), нужно ещё 1 ГБ свободного места.
"""

import json
import re
import shutil
import tempfile

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
    source_tab_texts,
    split_paragraphs,
    translation_user_prompt,
)
from apps.ai.services.medicine_title import paragraph_brand
from apps.ai.services.translation_memory import REMEMBER_BATCH_SIZE, remember, source_hash
from apps.catalog.models import MedicineProduct


# Запас свободного места сверх размера входного файла пакета (диск прода маленький).
MIN_FREE_DISK_BYTES = 1024 * 2**20


class Command(BaseCommand):
    help = "Перевод новых абзацев инструкций лекарств пакетом OpenAI Batch API (submit / collect)"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["submit", "collect"])
        parser.add_argument("batch_id", nargs="?", help="ID пакета для collect")
        parser.add_argument("--limit-products", type=int, default=0, help="Сколько лекарств взять (0 — все)")
        parser.add_argument("--max-requests", type=int, default=2000, help="Максимум запросов в пакете")
        parser.add_argument("--dry-run", action="store_true", help="submit: только оценка, без отправки")
        parser.add_argument("--work-dir", default="", help="collect: папка для временного входного файла")
        parser.add_argument("--progress-every", type=int, default=50, help="collect: прогресс каждые N запросов")

    def handle(self, *args, **options):
        if options["action"] == "submit":
            self._submit(options)
        else:
            if not options["batch_id"]:
                raise CommandError("collect требует batch_id")
            self._collect(options["batch_id"], options)

    def _missing_paragraphs(self, options) -> list[str]:
        qs = MedicineProduct.objects.filter(is_active=True).order_by("pk").values_list(
            "name", "active_ingredient", "external_data"
        )
        if options["limit_products"]:
            qs = qs[: options["limit_products"]]
        paragraphs: dict[str, str] = {}
        for name, active_ingredient, external_data in qs.iterator(chunk_size=200):
            brand = paragraph_brand(name, active_ingredient)
            for text in source_tab_texts(external_data):
                for part in split_paragraphs(text)[::2]:
                    if needs_translation(part):
                        paragraph = normalize_paragraph(part, brand)
                        paragraphs.setdefault(source_hash(paragraph), paragraph)
        hashes = list(paragraphs)
        for start in range(0, len(hashes), 5000):
            cached = AITranslationMemory.objects.filter(
                namespace=PARAGRAPH_NAMESPACE, source_hash__in=hashes[start:start + 5000]
            ).values_list("source_hash", flat=True)
            for key in cached:
                paragraphs.pop(key, None)
        return list(paragraphs.values())

    def _submit(self, options):
        batches = paragraph_batches(self._missing_paragraphs(options))[: options["max_requests"]]
        chars = sum(len(p) for batch in batches for p in batch)
        estimate = estimate_translation_cost(chars=chars)
        self.stdout.write(
            f"Абзацев к переводу: {sum(map(len, batches))}, {chars:,} симв., запросов {len(batches)}; "
            f"оценка ≈${estimate['cost_usd'] / 2:.2f} в Batch API (≈${estimate['cost_usd']:.2f} обычным путём)"
        )
        if options["dry_run"] or not batches:
            return
        client = LLMClient()
        lines = []
        for index, batch in enumerate(batches):
            body = {
                "model": client.model,
                "messages": [
                    {"role": "system", "content": PARAGRAPH_SYSTEM_PROMPT},
                    {"role": "user", "content": translation_user_prompt(paragraph_items(batch))},
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
            metadata={"kind": PARAGRAPH_NAMESPACE},
        )
        self.stdout.write(self.style.SUCCESS(
            f"Пакет отправлен: {batch.id}. Забрать: manage.py medicine_paragraph_batch collect {batch.id}"
        ))

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
        stats = {"requests": 0, "accepted": 0, "rejected": 0, "created": 0, "cost": 0.0}
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
            f"отклонено проверкой {stats['rejected']} — переведутся при обычной обработке); "
            f"стоимость ≈${stats['cost']:.2f}; {counts}"
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
