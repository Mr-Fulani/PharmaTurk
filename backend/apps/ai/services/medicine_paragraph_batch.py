"""Перевод абзацев инструкций лекарств через OpenAI Batch API (−50% цены) частями.

Общий код команды ``medicine_paragraph_batch`` и AI-прогона «Перевод абзацев
инструкций» в админке (services/ai_runs.py): выбор следующей части, отправка,
сбор с проверкой и итог части.

Часть — абзацы клинических разделов, которых ещё нет в памяти переводов, по
лекарствам в порядке pk; заканчивается на границе лекарства, чтобы следующая
часть началась с лекарства после неё. Номер части, число абзацев и последнее
лекарство пишутся в метаданные пакета OpenAI — по ним команда видит и части,
отправленные из админки (у них ещё ``run`` — номер прогона).
"""

import json
import re
import shutil
import tempfile
from collections import Counter

from apps.ai.models import AITranslationMemory
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

PART_SIZE = 5000
# Доля абзацев части, не попавших в память, при которой дальше не идём.
MAX_DEFECT = 0.15
# Запас свободного места сверх размера входного файла пакета (диск прода маленький).
MIN_FREE_DISK_BYTES = 1024 * 2**20
# Пакет ещё не готов — следующую часть не отправлять (иначе те же абзацы оплатятся дважды).
RUNNING_STATUSES = ("validating", "in_progress", "finalizing", "cancelling")
# Сколько новых абзацев проверять в памяти переводов одним запросом при чтении каталога.
LOOKUP_CHUNK = 2000


class PartError(Exception):
    """Понятная причина, по которой часть не отправлена или не забрана."""


def cached_hashes(hashes: list[str]) -> set[str]:
    cached = set()
    for start in range(0, len(hashes), 5000):
        cached.update(AITranslationMemory.objects.filter(
            namespace=PARAGRAPH_NAMESPACE, source_hash__in=hashes[start:start + 5000]
        ).values_list("source_hash", flat=True))
    return cached


def iter_missing_paragraphs(after_product: int = 0, limit_products: int = 0):
    """(абзац, pk первого лекарства с ним) — абзацы, которых нет в памяти, по порядку pk.

    Каталог читается потоком: в памяти Python — хэши уже встреченных абзацев и
    порция до LOOKUP_CHUNK новых, которые сверяются с памятью переводов одним запросом.
    """
    qs = MedicineProduct.objects.filter(is_active=True, pk__gt=after_product).order_by("pk").values_list(
        "pk", "name", "active_ingredient", "external_data"
    )
    if limit_products:
        qs = qs[:limit_products]
    seen: set[str] = set()
    pending: list[tuple[str, str, int]] = []
    for pk, name, active_ingredient, external_data in qs.iterator(chunk_size=200):
        # Ключи абзацев — как при обработке: бренд из турецкого оригинала.
        brand = paragraph_brand(medicine_source_name(name, external_data)[0], active_ingredient)
        for text in source_tab_texts(external_data):
            for part in split_paragraphs(text)[::2]:
                if not needs_translation(part):
                    continue
                paragraph = normalize_paragraph(part, brand)
                key = source_hash(paragraph)
                if key not in seen:
                    seen.add(key)
                    pending.append((key, paragraph, pk))
        if len(pending) >= LOOKUP_CHUNK:
            yield from _not_cached(pending)
            pending = []
    yield from _not_cached(pending)


def _not_cached(rows):
    cached = cached_hashes([key for key, _, _ in rows])
    for key, paragraph, pk in rows:
        if key not in cached:
            yield paragraph, pk


def iter_parts(after_product: int = 0, part_size: int = PART_SIZE, limit_products: int = 0):
    """Части каталога после лекарства ``after_product``: (абзацы, pk последнего лекарства)."""
    paragraphs, last_product = [], 0
    for paragraph, pk in iter_missing_paragraphs(after_product, limit_products):
        # Часть заканчивается на границе лекарства: следующая начнётся с лекарства после него.
        if len(paragraphs) >= part_size and pk != last_product:
            yield paragraphs, last_product
            paragraphs = []
        paragraphs.append(paragraph)
        last_product = pk
    if paragraphs:
        yield paragraphs, last_product


def estimate(paragraphs: list[str]) -> dict:
    """Оценка части: запросов, символов и цена — в Batch API (половина обычной) и обычным путём."""
    regular = estimate_translation_cost(paragraphs)["cost_usd"]
    return {
        "paragraphs": len(paragraphs),
        "chars": sum(len(p) for p in paragraphs),
        "requests": len(paragraph_batches(paragraphs)),
        "cost_usd": regular / 2,
        "regular_cost_usd": regular,
    }


def list_parts(client) -> list:
    """Части (пакеты с номером части в метаданных) — из консоли и из админки, новые первыми."""
    return [
        batch for batch in client.client.batches.list(limit=100)
        if (batch.metadata or {}).get("kind") == PARAGRAPH_NAMESPACE and (batch.metadata or {}).get("part")
    ]


def running_parts(client) -> list:
    return [part for part in list_parts(client) if part.status in RUNNING_STATUSES]


def describe(part) -> str:
    return f"№{part.metadata['part']} {part.id} ({part.status})"


def submit_part(client, paragraphs: list[str], metadata: dict):
    """Отправить часть в Batch API (готова до 24 ч) → пакет OpenAI."""
    lines = []
    for index, batch in enumerate(paragraph_batches(paragraphs)):
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
    return client.client.batches.create(
        input_file_id=upload.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata=metadata,
    )


def part_paragraphs(client, batch, work_dir=None) -> list[str]:
    """Все абзацы части — из её входного файла."""
    work_dir = work_dir or tempfile.gettempdir()
    with tempfile.NamedTemporaryFile(dir=work_dir, suffix=".jsonl") as input_file:
        _download_input(client, batch.input_file_id, input_file, work_dir)
        input_file.seek(0)
        return [
            text
            for line in input_file if line.strip()
            for text in items_from_user_prompt(json.loads(line)["body"]["messages"][1]["content"]).values()
        ]


def rejected_paragraphs(client, batch, work_dir=None) -> tuple[list[str], int]:
    """Абзацы части, которых нет в памяти (отклонены проверкой или часть не забрана), и размер части."""
    paragraphs = part_paragraphs(client, batch, work_dir)
    cached = cached_hashes([source_hash(p) for p in paragraphs])
    return [p for p in paragraphs if source_hash(p) not in cached], len(paragraphs)


def check_previous_part(client, part, max_defect: float, work_dir=None) -> None:
    """Следующая часть — только если у последней брак не выше порога."""
    rejected, total = rejected_paragraphs(client, part, work_dir)
    share = len(rejected) / total if total else 0
    if share > max_defect:
        raise PartError(
            f"Часть №{part.metadata['part']} ({part.id}, {part.status}): нет в памяти {len(rejected)} из "
            f"{total} абзацев ({share:.1%}) — больше порога {max_defect:.0%}. Либо она не "
            f"забрана (collect {part.id}), либо брак высокий — смотрите отчёт collect. Повторить "
            f"отклонённые: submit --retry {part.id}; идти дальше всё равно: --max-defect 1"
        )


def collect_part(client, batch, work_dir=None, progress=None, progress_every: int = 50) -> dict:
    """Потоковая загрузка готовой части в память переводов → статистика.

    Ответ читается построчно прямо из OpenAI; входной файл (исходные абзацы)
    скачивается во временный файл и читается по смещениям — в памяти Python
    только текущая строка и порция до REMEMBER_BATCH_SIZE абзацев. Каждый
    абзац проверяется теми же правилами, что обычный перевод (дозировки, язык,
    длина, сдвиг ответа — тогда отклоняется весь запрос). Запись идемпотентна:
    прерванный сбор можно просто повторить. ``progress(stats, total)``
    вызывается каждые ``progress_every`` запросов; прерывание (Ctrl+C)
    записывает проверенное и возвращает статистику с ``interrupted``.
    """
    counts = getattr(batch, "request_counts", None)
    total = getattr(counts, "completed", None) or getattr(counts, "total", None) or 0
    price = client.pricing.get(client.model) or {}
    stats = {"requests": 0, "accepted": 0, "rejected": 0, "created": 0, "cost": 0.0,
             "reasons": Counter(), "shifted_requests": 0, "total": total, "interrupted": False}
    pending: dict = {}

    def flush():
        stats["created"] += remember(PARAGRAPH_NAMESPACE, pending)
        pending.clear()

    work_dir = work_dir or tempfile.gettempdir()
    with tempfile.NamedTemporaryFile(dir=work_dir, suffix=".jsonl") as input_file:
        _download_input(client, batch.input_file_id, input_file, work_dir)
        offsets = _index_requests(input_file)
        try:
            with client.client.files.with_streaming_response.content(batch.output_file_id) as response:
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    body = (row.get("response") or {}).get("body") or {}
                    items = _request_items(input_file, offsets.get(row.get("custom_id")))
                    choice = (body.get("choices") or [{}])[0]
                    payload = {}
                    if choice.get("finish_reason") != "length":
                        payload = client._parse_json_response((choice.get("message") or {}).get("content") or "")
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
                    if progress and stats["requests"] % progress_every == 0:
                        progress(stats, total)
                flush()
        except KeyboardInterrupt:
            flush()
            stats["interrupted"] = True
    return stats


def part_summary(stats: dict, submitted: int = 0) -> dict:
    """Итог части: брак (отклонено проверкой и без ответа), сдвиг, цена за 1000 абзацев.

    ``submitted`` — сколько абзацев отправлено: абзацы запросов, на которые
    OpenAI не ответил (ошибка запроса, пакет истёк), тоже брак — их нет в памяти.
    """
    answered = stats["accepted"] + stats["rejected"]
    paragraphs = max(submitted, answered)
    defect_count = paragraphs - stats["accepted"]
    cost = stats["cost"]
    return {
        "paragraphs": paragraphs,
        "requests": stats["requests"],
        "accepted": stats["accepted"],
        "rejected": stats["rejected"],
        "no_answer": paragraphs - answered,
        "defect_count": defect_count,
        "defect": defect_count / paragraphs if paragraphs else 0.0,
        "shifted_requests": stats["shifted_requests"],
        "shifted_share": stats["shifted_requests"] / max(stats["requests"], 1),
        "reasons": dict(stats["reasons"].most_common()),
        "cost_usd": cost,
        "per_1000": cost / paragraphs * 1000 if paragraphs else 0.0,
        "per_1000_accepted": cost / max(stats["accepted"], 1) * 1000,
        "created": stats["created"],
    }


def _download_input(client, file_id, target, work_dir):
    size = getattr(client.client.files.retrieve(file_id), "bytes", 0) or 0
    free = shutil.disk_usage(work_dir).free
    if size and free < size + MIN_FREE_DISK_BYTES:
        raise PartError(
            f"Мало места в {work_dir}: свободно {free // 2**20} МБ, нужно "
            f"{(size + MIN_FREE_DISK_BYTES) // 2**20} МБ"
        )
    with client.client.files.with_streaming_response.content(file_id) as response:
        for chunk in response.iter_bytes():
            target.write(chunk)
    target.flush()


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


def _request_items(input_file, offset) -> dict[str, str]:
    if offset is None:
        return {}
    input_file.seek(offset)
    row = json.loads(input_file.readline())
    return items_from_user_prompt(row["body"]["messages"][1]["content"])
