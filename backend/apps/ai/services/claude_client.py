"""Claude (Anthropic) — основной провайдер генерации текста.

Включается ключом ANTHROPIC_API_KEY; модель — AI_ANTHROPIC_MODEL (по умолчанию
Claude Haiku 5.5). Любой непригодный ответ — ошибка API после повторов SDK,
отказ модели, пустой или неразобранный JSON — поднимает ClaudeUnavailable, и
LLMClient повторяет тот же запрос в OpenAI.
"""

import logging

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

# Ответ JSON просим словами: схема у каждого промпта своя.
JSON_INSTRUCTION = (
    "\n\nОтвет — ровно один JSON-объект, без пояснений до или после него и без обёртки ```."
)


class ClaudeUnavailable(Exception):
    """Claude не дал пригодного ответа — запрос уходит в OpenAI."""


class ClaudeClient:
    def __init__(self):
        self.model = settings.AI_CONFIG.get("ANTHROPIC_MODEL") or "claude-haiku-5-5"
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=4, timeout=180.0)

    def create(self, system_prompt: str, user_prompt: str, *, json_mode: bool, max_tokens: int, output_schema=None):
        """Один запрос к Claude → (текст, ответ SDK) или ClaudeUnavailable.

        output_schema — JSON-схема ответа (structured outputs): API отдаёт только валидный JSON
        этой формы. Без неё JSON просим словами, и Haiku изредка теряет скобку в длинном ответе.
        """
        extra = {}
        if output_schema is not None:
            extra["output_config"] = {"format": {"type": "json_schema", "schema": output_schema}}
        try:
            response = self.client.messages.create(
                model=self.model,
                # Токенизатор Claude длиннее на русском тексте; оплачивается только написанное.
                max_tokens=min(max(max_tokens * 2, 2000), 16000),
                # Карточка — пересказ фактов источника: размышления не нужны, весь лимит — ответу.
                thinking={"type": "disabled"},
                # Системный промпт одинаков у всех товаров партии — кэшируется (чтение в 10 раз дешевле).
                system=[{
                    "type": "text",
                    "text": system_prompt + (JSON_INSTRUCTION if json_mode and output_schema is None else ""),
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_prompt}],
                **extra,
            )
        except anthropic.AuthenticationError as exc:
            logger.error("Claude: ключ ANTHROPIC_API_KEY не принят (%s) — запрос уходит в OpenAI", exc)
            raise ClaudeUnavailable("authentication") from exc
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            logger.warning("Claude недоступен (%s) — запрос уходит в OpenAI", exc)
            raise ClaudeUnavailable(type(exc).__name__) from exc
        if response.stop_reason == "refusal":
            logger.warning("Claude отказал (%s) — запрос уходит в OpenAI", getattr(response, "stop_details", None))
            raise ClaudeUnavailable("refusal")
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response


def claude_usage(usage) -> tuple[int, int, int]:
    """(входные с кэшем, из них прочитано из кэша, выходные) токены ответа Claude."""
    cached = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    written = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return int(usage.input_tokens) + cached + written, cached, int(usage.output_tokens)
