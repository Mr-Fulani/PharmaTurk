import os
from types import SimpleNamespace

import pytest

from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.llm_client import LLMClient
from apps.catalog.models import AccessoryProduct, MedicineProduct

pytestmark = pytest.mark.django_db


def _generator(input_by_name):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator._get_prompt_template = lambda *_args, **_kwargs: ""
    generator._collect_input_data = lambda product: input_by_name[product.name]
    return generator


def _base(model, **fields):
    domain = model.objects.create(**fields)
    domain.refresh_from_db()
    return domain.base_product


def _common_prefix(left: str, right: str) -> str:
    return os.path.commonprefix([left, right])


def test_medicine_prompt_puts_static_instructions_before_product_data():
    first = _base(MedicineProduct, name="MAJEZIK 100 MG", slug="prompt-majezik")
    second = _base(MedicineProduct, name="SOLIAN 400 MG", slug="prompt-solian")
    generator = _generator({
        "MAJEZIK 100 MG": {"name": "MAJEZIK 100 MG", "active_ingredient": "Flurbiprofen"},
        "SOLIAN 400 MG": {"name": "SOLIAN 400 MG", "active_ingredient": "Amisülprid"},
    })

    prompt_a = generator._construct_medicine_user_prompt(first, {}, "full")
    prompt_b = generator._construct_medicine_user_prompt(second, {}, "full")

    prefix = _common_prefix(prompt_a, prompt_b)
    # Общий префикс включает все инструкции и схему ответа — его кэширует OpenAI.
    assert "Требования к качеству" in prefix
    assert '"attributes"' in prefix
    assert prompt_a.index("Данные о лекарственном препарате") > prompt_a.index("Верни строго JSON")


def test_general_prompt_is_cache_friendly_and_has_no_copyable_examples():
    first = _base(AccessoryProduct, name="Ремень", slug="prompt-belt")
    second = _base(AccessoryProduct, name="Сумка", slug="prompt-bag")
    base = {"description": "", "brand": None, "product_type": "accessories"}
    generator = _generator({
        "Ремень": {**base, "name": "Ремень"},
        "Сумка": {**base, "name": "Сумка"},
    })

    prompt_a = generator._construct_user_prompt(first, {}, "full")
    prompt_b = generator._construct_user_prompt(second, {}, "full")

    prefix = _common_prefix(prompt_a, prompt_b)
    assert "БЕЗОПАСНОСТЬ ИСТОЧНИКА" in prefix
    assert '"dynamic_attributes"' in prefix
    assert prompt_a.index("Данные о товаре:") > prompt_a.index("Верни JSON")
    assert "0.95" not in prompt_a
    assert "искусственная кожа" not in prompt_a
    assert '"size": "M"' not in prompt_a


def _usage(prompt, completion, cached):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
    )


def test_cost_uses_configured_prices_and_cached_tokens(settings):
    settings.AI_CONFIG = {
        **settings.AI_CONFIG,
        "PRICING": {"test-model": {"input": 1.0, "cached_input": 0.5, "output": 2.0}},
    }
    client = LLMClient.__new__(LLMClient)
    client.pricing = settings.AI_CONFIG["PRICING"]

    tokens, cost = client._usage_and_cost("test-model", _usage(1_000_000, 500_000, 400_000))

    assert tokens["cached"] == 400_000
    # 600k * $1 + 400k * $0.5 + 500k * $2 за 1M токенов
    assert cost == pytest.approx(0.6 + 0.2 + 1.0)


def test_unknown_model_price_is_not_silently_taken_from_another_model():
    client = LLMClient.__new__(LLMClient)
    client.pricing = {"gpt-4o-mini": {"input": 0.15, "output": 0.6}}

    _tokens, cost = client._usage_and_cost("some-new-model", _usage(1000, 1000, 0))

    assert cost == 0.0
