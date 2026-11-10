"""Судья описания БАДа: второй запрос к Claude сверяет готовое RU описание с турецким источником.

Волна 1 на проде (10.11.2026): у 192 из 455 описаний, прошедших автоматические проверки, сверка человеком нашла
ошибки, ≈ 70 из них — во вводном абзаце модели (выдуманное, неверно переведённое растение, грамматика, повтор),
правилами их не поймать. Судья только отправляет описание на модерацию (``supplement_judge`` в ``log_problems``),
текст не правит. Только Claude: при ошибке запроса описание тоже уходит на модерацию, OpenAI не вызывается.
Числа и единицы по-прежнему сверяют правила (``dose_suspicious``, ``unsourced_numbers``), судья — в дополнение.
"""

from __future__ import annotations

import hashlib
import os
import html
import json
import re
from typing import Any, Optional

import anthropic
from django.conf import settings

from apps.ai.services.claude_client import ClaudeClient, ClaudeUnavailable, claude_usage

KINDS = ("перевод", "транслит", "выдумано", "число", "состав", "форма", "грамматика", "повтор", "чужая_страница")
SOURCE_LIMIT = 6000
MAX_TOKENS = 8000
EFFORT = "medium"

SYSTEM_PROMPT = """Ты редактор интернет-аптеки. Тебе дают турецкий текст страницы пищевой добавки (источник) и \
русское описание, написанное по нему. Найди в описании ОШИБКИ — места, где русский текст говорит не то, что \
источник, или сломан. Места, где описание верно передаёт источник, — не ошибки, их не перечисляй.

Что считается ошибкой:
- перевод: смысл передан неверно — другое вещество, растение, вкус, мера, время приёма или возраст \
(«Ayva suyu» → «яблочный сок» вместо айвового; «yemek zamanı» → «после еды» вместо «во время еды»; \
«tatlı kaşığı» → «чайная ложка» вместо десертной; запрет стал разрешением);
- транслит: турецкое слово русскими буквами или по-турецки в русском тексте («кедиотуа», «портакала», «Феррик»), \
турецкие буквы ğ ş ı вне названия бренда;
- выдумано: в описании есть вещество, вкус, страна, свойство или число, которых в источнике нет совсем;
- число: число или единица в описании не совпадает с источником (процент нормы выдан за мкг, доза на 2 капсулы — \
за дозу на 1, строки таблицы перепутаны, другое число штук в упаковке);
- состав: в абзаце «Состав» вместо компонентов заголовки таблиц, фразы, обрывки или голые числа;
- форма: описание называет другую форму выпуска, чем источник;
- грамматика: фраза грамматически сломана или бессмысленна по-русски;
- повтор: одна и та же мысль почти дословно в двух абзацах;
- чужая_страница: источник о другом товаре.

Не ошибки: верный перевод другими словами («yemekle birlikte» → «вместе с едой» — верно; «aç tok farketmeksizin» → \
«натощак или после еды» — верно); опущенные детали источника; бренд и латинские названия как есть; «взрослым и \
детям от 11 лет»; короткие общеизвестные пояснения о веществе («ресвератрол содержится в кожуре винограда»); \
стиль и порядок слов.

Для каждой ошибки укажи: kind, quote (цитата из описания), source (что в источнике), error (в чём именно \
расхождение, одним предложением), confidence от 1 до 5 (5 — точно ошибка). Если ошибок нет, problems — пустой \
список. Лучше пропустить сомнительное, чем отметить верное."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "problems": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "quote": {"type": "string"},
                    "source": {"type": "string"},
                    "error": {"type": "string"},
                    "confidence": {"type": "integer"},
                },
                "required": ["kind", "quote", "source", "error", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["problems"],
    "additionalProperties": False,
}
# Ниже порога — сомнение модели. Калибровка на волне 1 (455 размеченных): от 2 — поймано 96 из 193 плохих,
# зря отмечено 7 из 262 хороших; от 4 — 23 из 60 и 0 из 60 на выборке.
MIN_CONFIDENCE = 2


def flagged(result: Any) -> bool:
    """На модерацию: ошибка запроса или находка с уверенностью от ``MIN_CONFIDENCE``."""
    if not isinstance(result, dict):
        return False
    return "error" in result or any(
        (problem.get("confidence") or 0) >= MIN_CONFIDENCE for problem in result.get("problems") or []
    )


def enabled() -> bool:
    return bool(getattr(settings, "ANTHROPIC_API_KEY", "")) and bool(settings.AI_CONFIG.get("SUPPLEMENT_JUDGE", True))


def description_hash(description: Any) -> str:
    """Отпечаток описания, которое видел судья (для разбора: перед сохранением текст ещё очищается)."""
    return hashlib.sha256(str(description or "").encode("utf-8")).hexdigest()[:16]


def _plain(description: Any, skip: tuple[str, ...]) -> str:
    paragraphs = [
        html.unescape(re.sub(r"<[^>]+>", "", paragraph)).strip()
        for paragraph in re.findall(r"<p>(.*?)</p>", str(description or ""), re.S)
    ]
    return "\n".join(paragraph for paragraph in paragraphs if paragraph and paragraph not in skip)


def user_prompt(source_name: str, sections: dict[str, str], description_ru: Any, skip: tuple[str, ...] = ()) -> str:
    source = "\n\n".join(f"[{key}]\n{text}" for key, text in sections.items())[:SOURCE_LIMIT]
    return (
        f"Название товара в источнике: {source_name}\n\nИсточник (турецкий):\n{source}\n\n"
        f"Описание на сайт (русский):\n{_plain(description_ru, skip)}"
    )


def _ask(client: ClaudeClient, prompt: str):
    """Запрос с размышлениями: без них Haiku отмечал верные места как ошибки (волна 1, 10.11.2026)."""
    # Haiku 5.5 принимает только адаптивные размышления; глубину задаёт effort.
    effort = os.environ.get("AI_SUPPLEMENT_JUDGE_EFFORT", EFFORT)
    try:
        response = client.client.messages.create(
            model=client.model,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"} if effort else {"type": "disabled"},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}, **({"effort": effort} if effort else {}),
            },
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise ClaudeUnavailable(type(exc).__name__) from exc
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ClaudeUnavailable(response.stop_reason)
    return "".join(block.text for block in response.content if block.type == "text"), response


def judge(
    source_name: str, sections: dict[str, str], description_ru: Any, *, skip: tuple[str, ...] = (),
    client: Optional[ClaudeClient] = None,
) -> dict[str, Any]:
    """→ {"hash", "problems": [{kind, quote, source}], "cost_usd", "tokens"} или {"hash", "error"}."""
    result: dict[str, Any] = {"hash": description_hash(description_ru)}
    if not str(description_ru or "").strip():
        return {**result, "problems": [], "cost_usd": 0.0, "tokens": {}}
    try:
        client = client or ClaudeClient()
        text, response = _ask(client, user_prompt(source_name, sections, description_ru, skip))
        answer = json.loads(text)
    except (ClaudeUnavailable, ValueError) as exc:
        return {**result, "error": str(exc)[:200] or type(exc).__name__}
    problems = [
        {**{key: str(item.get(key) or "")[:300] for key in ("kind", "quote", "source", "error")},
         "confidence": item.get("confidence")}
        for item in answer.get("problems") or []
        if isinstance(item, dict) and item.get("kind") in KINDS and isinstance(item.get("confidence"), int)
    ]
    prompt_tokens, cached, completion_tokens = claude_usage(response.usage)
    price = (settings.AI_CONFIG.get("PRICING") or {}).get(client.model) or {}
    cost = (
        (prompt_tokens - cached) * price.get("input", 0) + cached * price.get("cached_input", price.get("input", 0))
        + completion_tokens * price.get("output", 0)
    ) / 1_000_000
    tokens = {"prompt": prompt_tokens, "completion": completion_tokens, "total": prompt_tokens + completion_tokens,
              "cached": cached}
    return {**result, "problems": problems, "cost_usd": round(cost, 6), "tokens": tokens}
