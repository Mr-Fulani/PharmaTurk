from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.ai.models import AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.llm_client import LLMClient
from apps.ai.services.medicine_fact_check import doses_match, extract_doses
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.tasks import process_product_ai_task
from apps.catalog.models import AccessoryProduct, Category, MedicineProduct


def _llm_result(content, **extra):
    return {
        "content": content,
        "tokens": {"prompt": 10, "completion": 20, "total": 30},
        "cost_usd": 0.0123,
        "processing_time_ms": 5,
        **extra,
    }


def test_llm_client_reports_truncated_json_instead_of_silent_empty_dict():
    client = LLMClient.__new__(LLMClient)
    client.model = client.openai_model = "gpt-4o-mini"
    client.claude = None
    client.pricing = {"gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60}}
    response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content='{"ru": {"generated_'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5000, total_tokens=5010),
        model_dump=lambda: {},
    )
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=response)))
    )

    result = client.generate_content(system_prompt="s", user_prompt="u", max_tokens=5000)

    assert result["truncated"] is True
    assert result["json_error"] is True
    assert result["content"] == {}


@pytest.mark.django_db
def test_truncated_generation_fails_log_records_cost_and_skips_paid_followups():
    medicine = MedicineProduct.objects.create(name="LASIRIN 20 MG TABLET", slug="robust-truncated")
    medicine.refresh_from_db()
    product = medicine.base_product
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    generator.llm = SimpleNamespace(
        model="test-model",
        generate_content=Mock(return_value=_llm_result({}, truncated=True, json_error=True)),
    )
    generator._translate_medicine_source_sections = Mock()

    with pytest.raises(ValueError, match="обрезан"):
        generator.process_product(product.id, options={"analyze_images": False, "force": True})

    log = AIProcessingLog.objects.get(product=product)
    assert log.status == AIProcessingStatus.FAILED
    assert float(log.cost_usd) == pytest.approx(0.0123)
    assert generator.llm.generate_content.call_count == 1
    generator._translate_medicine_source_sections.assert_not_called()


@pytest.mark.django_db
def test_input_data_is_collected_once_per_processing():
    accessory = AccessoryProduct.objects.create(name="Ремень", slug="robust-collect-once")
    accessory.refresh_from_db()
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.llm = SimpleNamespace(model="test-model")
    generator._collect_input_data = Mock(return_value={"name": "Ремень", "description": ""})
    generator._should_use_images_for_product = lambda _product: False

    generator.process_product(
        accessory.base_product.id, processing_type="image_analysis", options=None
    )

    assert generator._collect_input_data.call_count == 1


def test_dose_extraction_matches_across_languages():
    source = "Günde 2 kez 500 mg, %5 krem, 1.000 mg, 0,125 mg, 2 gün boyunca, 10 mg/kg."
    ru = "Дважды в день по 500 мг, крем 5%, 1 000 мг, 0,125 мг, в течение 2 дней, 10 мг/кг."
    en = "Twice daily 500 mg, 5% cream, 1,000 mg, 0.125 mg, for 2 days, 10 mg/kg."

    assert extract_doses(source) == {
        ("500", "mg"), ("5", "%"), ("1000", "mg"), ("0.125", "mg"), ("10", "mg"),
    }
    assert doses_match(source, ru)
    assert doses_match(source, en)
    assert not doses_match(source, ru.replace("500 мг", "50 мг"))
    assert not doses_match(source, en.replace("0.125 mg", "0.125 g"))


@pytest.mark.django_db
def test_medicine_section_with_changed_dose_is_blocked_for_moderation():
    content = {
        "ru": {"usage_instructions": "Принимать по 50 мг два раза в день, длинный перевод раздела."},
        "en": {"usage_instructions": "Take 500 mg twice daily, a long translation of the section."},
        "attributes": {"medicine_translation_quality": {"usage_instructions": {"complete": True}}},
    }

    ContentGenerator._apply_medicine_fact_checks(
        content, {}, {"usage_instructions": "Günde iki kez 500 mg alınız."}
    )

    details = content["attributes"]["medicine_translation_quality"]["usage_instructions"]
    assert details["complete"] is False
    assert details["fact_mismatch"] == ["ru"]

    root = Category.objects.create(name="Медицина", slug="robust-medicines-root")
    category = Category.objects.create(name="Обезболивающие", slug="robust-painkillers", parent=root)
    medicine = MedicineProduct.objects.create(name="MAJEZIK 100 MG", slug="robust-dose", category=category)
    medicine.refresh_from_db()
    log = AIProcessingLog.objects.create(
        product=medicine.base_product,
        processing_type="full",
        input_data={},
        extracted_attributes=content["attributes"],
    )
    report = SemanticValidator().validate_log(log)
    assert "medicine_translation:usage_instructions" in report.rejected_fields
    assert "medicine_fact_mismatch" in report.reasons


@pytest.mark.django_db
def test_en_translation_is_not_filled_with_russian_text():
    accessory = AccessoryProduct.objects.create(name="Ремень", slug="robust-en-not-russian")
    accessory.refresh_from_db()
    accessory.translations.create(locale="en", name="Leather belt", description="English description")
    product = accessory.base_product
    log = AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="Кожаный ремень",
        generated_description="Русское описание ремня для каталога.",
        generated_seo_title="Русский SEO",
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": "Кожаный ремень", "generated_description": "Русское описание"},
                # Модель вернула в EN-блок русский текст.
                "en": {"generated_description": "Русское описание вместо английского"},
            }
        },
    )
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()

    generator._apply_changes_to_product(product, log)

    en = accessory.translations.get(locale="en")
    assert en.name == "Leather belt"
    assert en.description == "English description"
    assert accessory.translations.get(locale="ru").description == "Русское описание"


@pytest.mark.django_db
def test_vector_indexing_can_be_disabled_for_bulk_runs(monkeypatch):
    accessory = AccessoryProduct.objects.create(name="Ремень", slug="robust-no-vectors")
    accessory.refresh_from_db()
    product = accessory.base_product
    log = AIProcessingLog.objects.create(
        product=product, processing_type="full", status=AIProcessingStatus.PENDING, input_data={}
    )

    class FakeGenerator:
        def process_product(self, **kwargs):
            return SimpleNamespace(id=log.id, status=AIProcessingStatus.COMPLETED)

        def sync_variant_titles_from_parent(self, *args, **kwargs):
            return 0

    indexed = Mock()
    monkeypatch.setattr("apps.ai.tasks.ContentGenerator", FakeGenerator)
    monkeypatch.setattr("apps.ai.tasks.prepare_variant_ai_candidates_task.delay", Mock())
    monkeypatch.setattr("apps.recommendations.tasks.index_product_vectors.apply_async", indexed)

    process_product_ai_task.run(product_id=product.id, log_entry_id=log.id, index_vectors=False)
    indexed.assert_not_called()

    AIProcessingLog.objects.filter(pk=log.pk).update(status=AIProcessingStatus.PENDING)
    process_product_ai_task.run(product_id=product.id, log_entry_id=log.id)
    indexed.assert_called_once()
