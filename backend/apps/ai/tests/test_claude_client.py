"""Claude — основной провайдер текста, OpenAI — запасной (LLMClient.generate_content)."""
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import httpx2
import pytest

from apps.ai.services import claude_client
from apps.ai.services.llm_client import LLMClient

PRICING = {
    "claude-haiku-5-5": {"input": 0.10, "cached_input": 0.01, "output": 0.50},
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
}


def _claude_response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=200_000, output_tokens=100_000,
            cache_read_input_tokens=800_000, cache_creation_input_tokens=0,
        ),
        to_dict=lambda: {"stop_reason": stop_reason},
    )


def _openai_response(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model_dump=lambda: {},
    )


@pytest.fixture
def llm(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    settings.OPENAI_API_KEY = "test-openai"
    settings.AI_CONFIG = {**settings.AI_CONFIG, "PRICING": PRICING, "MODEL": "gpt-4o-mini",
                          "ANTHROPIC_MODEL": "claude-haiku-5-5"}
    client = LLMClient()
    client.claude.client = SimpleNamespace(messages=SimpleNamespace(create=Mock()))
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=Mock(return_value=_openai_response('{"from": "openai"}'))
    )))
    return client


def test_claude_answers_first_with_cached_system_prompt_and_cost(llm):
    llm.claude.client.messages.create.return_value = _claude_response('```json\n{"from": "claude"}\n```')

    result = llm.generate_content(system_prompt="Ты редактор.", user_prompt="Товар", max_tokens=1000)

    assert llm.model == "claude-haiku-5-5"
    assert result["content"] == {"from": "claude"}
    assert result["model"] == "claude-haiku-5-5"
    llm.client.chat.completions.create.assert_not_called()
    kwargs = llm.claude.client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-5-5"
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "JSON" in kwargs["system"][0]["text"]
    assert "temperature" not in kwargs
    # 200k + 800k из кэша на входе, 100k на выходе.
    assert result["tokens"] == {"prompt": 1_000_000, "completion": 100_000, "total": 1_100_000, "cached": 800_000}
    assert result["cost_usd"] == pytest.approx(0.2 * 0.10 + 0.8 * 0.01 + 0.1 * 0.50)


@pytest.mark.parametrize(
    "failure",
    [
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")),
        _claude_response("", stop_reason="refusal"),
        _claude_response("это не JSON"),
    ],
    ids=["api-error", "refusal", "not-json"],
)
def test_claude_failure_falls_back_to_openai(llm, failure):
    create = llm.claude.client.messages.create
    if isinstance(failure, Exception):
        create.side_effect = failure
    else:
        create.return_value = failure

    result = llm.generate_content(system_prompt="s", user_prompt="u")

    assert result["content"] == {"from": "openai"}
    assert result["model"] == "gpt-4o-mini"
    assert llm.client.chat.completions.create.call_args.kwargs["model"] == "gpt-4o-mini"


def test_truncated_claude_answer_is_reported_like_openai(llm):
    llm.claude.client.messages.create.return_value = _claude_response('{"ru": {"a": 1}}', stop_reason="max_tokens")

    result = llm.generate_content(system_prompt="s", user_prompt="u")

    assert result["truncated"] is True
    assert result["finish_reason"] == "length"
    assert result["model"] == "claude-haiku-5-5"


def test_without_anthropic_key_only_openai_is_used(settings):
    settings.ANTHROPIC_API_KEY = ""
    settings.OPENAI_API_KEY = "test-openai"
    client = LLMClient()

    assert client.claude is None
    assert client.model == client.openai_model


def test_claude_client_reads_model_from_settings(settings):
    settings.ANTHROPIC_API_KEY = "k"
    settings.AI_CONFIG = {**settings.AI_CONFIG, "ANTHROPIC_MODEL": "claude-sonnet-5-5"}

    assert claude_client.ClaudeClient().model == "claude-sonnet-5-5"
