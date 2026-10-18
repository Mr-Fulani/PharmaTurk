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
"""

import json

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
from apps.ai.services.translation_memory import remember, source_hash
from apps.catalog.models import MedicineProduct


class Command(BaseCommand):
    help = "Перевод новых абзацев инструкций лекарств пакетом OpenAI Batch API (submit / collect)"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["submit", "collect"])
        parser.add_argument("batch_id", nargs="?", help="ID пакета для collect")
        parser.add_argument("--limit-products", type=int, default=0, help="Сколько лекарств взять (0 — все)")
        parser.add_argument("--max-requests", type=int, default=2000, help="Максимум запросов в пакете")
        parser.add_argument("--dry-run", action="store_true", help="submit: только оценка, без отправки")

    def handle(self, *args, **options):
        if options["action"] == "submit":
            self._submit(options)
        else:
            if not options["batch_id"]:
                raise CommandError("collect требует batch_id")
            self._collect(options["batch_id"])

    def _missing_paragraphs(self, options) -> list[str]:
        qs = MedicineProduct.objects.filter(is_active=True).order_by("pk").values_list("external_data", flat=True)
        if options["limit_products"]:
            qs = qs[: options["limit_products"]]
        paragraphs: dict[str, str] = {}
        for external_data in qs.iterator(chunk_size=200):
            for text in source_tab_texts(external_data):
                for part in split_paragraphs(text)[::2]:
                    if needs_translation(part):
                        paragraph = normalize_paragraph(part)
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

    def _collect(self, batch_id: str):
        client = LLMClient()
        batch = client.client.batches.retrieve(batch_id)
        counts = getattr(batch, "request_counts", None)
        if batch.status != "completed":
            self.stdout.write(f"Статус пакета: {batch.status}; {counts}")
            return
        requests = {}
        for line in client.client.files.content(batch.input_file_id).text.splitlines():
            row = json.loads(line)
            requests[row["custom_id"]] = items_from_user_prompt(row["body"]["messages"][1]["content"])
        accepted, rejected, cost = {}, 0, 0.0
        output = client.client.files.content(batch.output_file_id).text if batch.output_file_id else ""
        for line in output.splitlines():
            row = json.loads(line)
            body = (row.get("response") or {}).get("body") or {}
            items = requests.get(row.get("custom_id")) or {}
            choice = (body.get("choices") or [{}])[0]
            payload = {}
            if choice.get("finish_reason") != "length":
                payload = client._parse_json_response((choice.get("message") or {}).get("content") or "")
            usage = body.get("usage") or {}
            price = client.pricing.get(client.model) or {}
            cost += (
                usage.get("prompt_tokens", 0) * price.get("input", 0)
                + usage.get("completion_tokens", 0) * price.get("output", 0)
            ) / 1_000_000 / 2  # Batch API — половина цены
            batch_accepted, batch_rejected = check_paragraph_payload(items, payload)
            accepted.update(batch_accepted)
            rejected += len(batch_rejected)
        remember(PARAGRAPH_NAMESPACE, accepted)
        self.stdout.write(self.style.SUCCESS(
            f"В память записано абзацев: {len(accepted)}, отклонено проверкой: {rejected} "
            f"(переведутся при обычной обработке); стоимость ≈${cost:.2f}; {counts}"
        ))
