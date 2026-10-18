"""Названия БАДов: правило промпта, словарь валидатора и короткий повтор названия."""

import os
import re
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.management import call_command

from apps.ai.models import AIModerationQueue, AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import SUPPLEMENT_TITLE_RULES, ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import AccessoryProduct, Category, Product, SupplementProduct

pytestmark = pytest.mark.django_db

DESCRIPTION = " ".join(["Пищевая добавка с витаминами и минералами для ежедневного приёма."] * 4)
EN_DESCRIPTION = " ".join(["Food supplement with vitamins and minerals for daily use."] * 4)


@pytest.fixture
def category():
    return Category.objects.create(name="БАДы", slug="supplements")


def _title_reasons(category, source_name, ru_title, en_title="Translated title", product_type="supplements"):
    product = Product.objects.create(
        name=source_name,
        slug=f"st-{abs(hash((source_name, ru_title, en_title)))}",
        product_type=product_type,
        category=category,
    )
    report = SemanticValidator().validate(
        product,
        generated_titles={"ru": ru_title, "en": en_title},
        dynamic_attributes=[],
    )
    return [reason for reason in report.reasons if reason.startswith("title_")]


# Примеры промпта — реальные кейсы контрольной партии.
PROMPT_EXAMPLES = re.findall(r"«([^»]+)» → «([^»]+)» / «([^»]+)»; ошибка: «([^»]+)»", SUPPLEMENT_TITLE_RULES)


def test_prompt_has_five_examples():
    assert len(PROMPT_EXAMPLES) == 5


@pytest.mark.parametrize("source_name, ru_title, en_title, _bad", PROMPT_EXAMPLES)
def test_prompt_example_titles_pass_validator(category, source_name, ru_title, en_title, _bad):
    assert _title_reasons(category, source_name, ru_title, en_title) == []


@pytest.mark.parametrize(
    "source_name, ru_title, reason",
    [
        (
            "AVICENNA CALCIUM MAGNESIUM ZINC VITAMIN D3 100 tablet",
            "Кальций, магний, цинк с витамином D3 таблетки 100 шт.",
            "title_identity_lost",
        ),
        ("MAGNIMORE PLUS TAKVIYE EDICI GIDA 30 tablet", "MAGNIMORE PLUS", "title_identity_lost"),
        ("SISTIONE SASE 14 saşe", "SISTIONE SASE 14 saşe", "title_untranslated"),
        ("SAMBUVIT PLUS SPREY 25 ml", "SAMBUVIT PLUS SPREY 25 ml", "title_untranslated"),
        ("ZINCO PLUS KIDS BALIK YAĞI 150 ml", "ZINCO PLUS KIDS БАЛИК ЯГИ", "title_untranslated"),
    ],
)
def test_background_bad_titles_are_rejected(category, source_name, ru_title, reason):
    assert _title_reasons(category, source_name, ru_title) == [reason]


@pytest.mark.parametrize(
    "ru_title",
    ["SAMBUVIT PLUS, спрей 25 ml", "SAMBUVIT PLUS, спрей 25ml", "SAMBUVIT PLUS Spreyi, 25 мл"],
)
def test_sprey_and_latin_ml_in_ru_title_are_untranslated(category, ru_title):
    assert _title_reasons(category, "SAMBUVIT PLUS SPREY 25 ml", ru_title) == ["title_untranslated"]


def test_ml_is_allowed_in_en_title_but_sprey_is_not(category):
    source = "SAMBUVIT PLUS SPREY 25 ml"
    assert _title_reasons(category, source, "SAMBUVIT PLUS, спрей 25 мл", "SAMBUVIT PLUS Spray, 25 ml") == []
    assert _title_reasons(category, source, "SAMBUVIT PLUS, спрей 25 мл", "SAMBUVIT PLUS Sprey, 25 ml") == [
        "title_untranslated"
    ]


def test_latin_ml_rule_is_limited_to_supplements():
    perfume = Category.objects.create(name="Парфюмерия", slug="perfumery")
    assert _title_reasons(perfume, "CHANEL N5 100 ml", "Духи CHANEL N5 100 ml", product_type="perfumery") == []


def _prompt_generator(input_by_name):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator._get_prompt_template = lambda *_args, **_kwargs: ""
    generator._collect_input_data = lambda product: input_by_name[product.name]
    return generator


def _base(model, **fields):
    domain = model.objects.create(**fields)
    domain.refresh_from_db()
    return domain.base_product


def test_supplement_prompt_has_title_rules_in_cached_prefix():
    first = _base(SupplementProduct, name="SISTIONE SASE 14 saşe", slug="prompt-sistione")
    second = _base(SupplementProduct, name="SAMBUVIT PLUS SPREY 25 ml", slug="prompt-sambuvit")
    accessory = _base(AccessoryProduct, name="Ремень", slug="prompt-belt-supp")
    base = {"description": "", "brand": None}
    generator = _prompt_generator({
        "SISTIONE SASE 14 saşe": {**base, "name": "SISTIONE SASE 14 saşe", "product_type": "supplements"},
        "SAMBUVIT PLUS SPREY 25 ml": {**base, "name": "SAMBUVIT PLUS SPREY 25 ml", "product_type": "supplements"},
        "Ремень": {**base, "name": "Ремень", "product_type": "accessories"},
    })

    prompt_a = generator._construct_user_prompt(first, {}, "full")
    prompt_b = generator._construct_user_prompt(second, {}, "full")
    prefix = os.path.commonprefix([prompt_a, prompt_b])

    assert SUPPLEMENT_TITLE_RULES in prefix
    assert prefix.index("Названия БАДов") < prefix.index("Верни JSON")
    assert "Названия БАДов" not in generator._construct_user_prompt(accessory, {}, "full")


def _llm_result(content, cost=0.001):
    return {
        "content": content,
        "tokens": {"prompt": 10, "completion": 20, "total": 30},
        "cost_usd": cost,
        "processing_time_ms": 5,
    }


def _generation(ru_title, en_title):
    return {
        "ru": {
            "generated_title": ru_title,
            "generated_description": DESCRIPTION,
            "seo_title": "SEO",
            "seo_description": "SEO описание",
            "keywords": ["бад"],
        },
        "en": {
            "generated_title": en_title,
            "generated_description": EN_DESCRIPTION,
            "seo_title": "SEO",
            "seo_description": "SEO description",
            "keywords": ["supplement"],
        },
        "attributes": {"dynamic_attributes": []},
    }


def _process(category, source_name, responses):
    supplement = SupplementProduct.objects.create(
        name=source_name, slug=f"retry-{abs(hash(source_name))}", category=category
    )
    supplement.refresh_from_db()
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    generator._get_prompt_template = lambda *_args, **_kwargs: ""
    generator.llm = SimpleNamespace(model="test-model", generate_content=Mock(side_effect=responses))
    log = generator.process_product(
        supplement.base_product.id, options={"analyze_images": False, "categorize": False, "force": True}
    )
    log.refresh_from_db()
    return log, generator.llm.generate_content


def test_rejected_title_is_retried_once_with_reason(category):
    log, llm_call = _process(
        category,
        "MAGNIMORE PLUS TAKVIYE EDICI GIDA 30 tablet",
        [
            _llm_result(_generation("MAGNIMORE PLUS", "MAGNIMORE PLUS"), cost=0.001),
            _llm_result(
                {"ru": "MAGNIMORE PLUS, пищевая добавка, 30 таблеток", "en": "MAGNIMORE PLUS Food Supplement, 30 tablets"},
                cost=0.0002,
            ),
        ],
    )

    assert llm_call.call_count == 2
    retry_prompt = llm_call.call_args_list[1].kwargs["user_prompt"]
    assert "потерян бренд, дозировка или фасовка" in retry_prompt
    assert '"rejected_titles": {"ru": "MAGNIMORE PLUS"' in retry_prompt
    assert llm_call.call_args_list[1].kwargs["max_tokens"] == 200
    assert log.generated_title == "MAGNIMORE PLUS, пищевая добавка, 30 таблеток"
    seo = log.extracted_attributes["seo_translations"]
    assert seo["en"]["generated_title"] == "MAGNIMORE PLUS Food Supplement, 30 tablets"
    assert float(log.cost_usd) == pytest.approx(0.0012)
    assert log.raw_llm_response["title_retry"]["repaired_fields"] == ["generated_title"]
    assert not [reason for reason in get_moderation_reasons(log) if reason.startswith("title_")]


def test_failed_retry_keeps_original_title_for_moderation(category):
    log, llm_call = _process(
        category,
        "SAMBUVIT PLUS SPREY 25 ml",
        [
            _llm_result(_generation("SAMBUVIT PLUS SPREY 25 ml", "SAMBUVIT PLUS Spray, 25 ml")),
            _llm_result({"ru": "SAMBUVIT PLUS спрей 25 ml", "en": "SAMBUVIT PLUS Spray, 25 ml"}),
        ],
    )

    assert llm_call.call_count == 2
    assert log.generated_title == "SAMBUVIT PLUS SPREY 25 ml"
    assert log.raw_llm_response["title_retry"]["failed_fields"] == ["generated_title"]
    assert "title_untranslated" in get_moderation_reasons(log)


def test_valid_title_is_not_retried(category):
    _log, llm_call = _process(
        category,
        "SISTIONE SASE 14 saşe",
        [_llm_result(_generation("SISTIONE, 14 саше", "SISTIONE, 14 sachets"))],
    )

    assert llm_call.call_count == 1


def _moderated_log(category, source_name, ru_title, en_title, slug):
    supplement = SupplementProduct.objects.create(name=source_name, slug=slug, category=category)
    supplement.refresh_from_db()
    log = AIProcessingLog.objects.create(
        product=supplement.base_product,
        processing_type="full",
        status=AIProcessingStatus.MODERATION,
        input_data={},
        generated_title=ru_title,
        generated_description=DESCRIPTION,
        generated_seo_title="SEO",
        generated_seo_description="SEO описание",
        category_confidence=0.9,
        cost_usd=0.001,
        raw_llm_response={"content": {}},
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": ru_title, "generated_description": DESCRIPTION},
                "en": {"generated_title": en_title, "generated_description": EN_DESCRIPTION},
            }
        },
    )
    AIModerationQueue.objects.create(log_entry=log, reason="title_identity_lost", priority=3)
    return log


def test_retry_titles_command_fixes_rejected_titles_then_close_applies(category, monkeypatch):
    rejected = _moderated_log(
        category, "MAGNIMORE PLUS TAKVIYE EDICI GIDA 30 tablet", "MAGNIMORE PLUS", "MAGNIMORE PLUS", "cmd-magnimore"
    )
    fine = _moderated_log(category, "SISTIONE SASE 14 saşe", "SISTIONE, 14 саше", "SISTIONE, 14 sachets", "cmd-sistione")
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    generator.llm = SimpleNamespace(
        model="test-model",
        generate_content=Mock(return_value=_llm_result(
            {"ru": "MAGNIMORE PLUS, пищевая добавка, 30 таблеток", "en": "MAGNIMORE PLUS Food Supplement, 30 tablets"},
            cost=0.0002,
        )),
    )
    monkeypatch.setattr("apps.ai.services.bulk_ops.ContentGenerator", lambda: generator)

    out = StringIO()
    call_command("retry_ai_titles", "--limit", "10", "--dry-run", stdout=out)
    assert f"лог {rejected.id}" in out.getvalue() and f"лог {fine.id}" not in out.getvalue()
    generator.llm.generate_content.assert_not_called()

    call_command("retry_ai_titles", "--limit", "10", stdout=StringIO())

    assert generator.llm.generate_content.call_count == 1
    rejected.refresh_from_db()
    assert rejected.generated_title == "MAGNIMORE PLUS, пищевая добавка, 30 таблеток"
    assert rejected.extracted_attributes["seo_translations"]["en"]["generated_title"] == (
        "MAGNIMORE PLUS Food Supplement, 30 tablets"
    )
    assert float(rejected.cost_usd) == pytest.approx(0.0012)
    assert rejected.raw_llm_response["title_retry"]["repaired_fields"] == ["generated_title"]
    assert rejected.status == AIProcessingStatus.MODERATION

    assert get_moderation_reasons(rejected) == []
    call_command("close_resolved_ai_moderation", "--product-type", "supplements", stdout=StringIO())

    rejected.refresh_from_db()
    assert rejected.status == AIProcessingStatus.APPROVED
    assert rejected.product.name == "MAGNIMORE PLUS, пищевая добавка, 30 таблеток"
