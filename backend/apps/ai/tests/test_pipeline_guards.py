from types import SimpleNamespace

import pytest
from celery.exceptions import Retry

from apps.ai.models import AIProcessingLog
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier, BaseAIApplier, BookAIApplier
from apps.ai.tasks import process_product_ai_task
from apps.catalog.models import Category, Product


def _generator():
    return ContentGenerator.__new__(ContentGenerator)


def _valid_content():
    return {
        "ru": {
            "generated_title": "Название",
            "generated_description": "Подробное описание товара на русском языке.",
            "seo_title": "SEO заголовок",
            "seo_description": "SEO описание",
            "keywords": ["товар"],
        },
        "en": {
            "generated_title": "Title",
            "generated_description": "Detailed product description in English.",
            "seo_title": "SEO title",
            "seo_description": "SEO description",
            "keywords": ["product"],
        },
    }


def test_empty_generation_result_is_rejected():
    with pytest.raises(ValueError, match="пустой или невалидный JSON"):
        _generator()._validate_generated_content({}, "full")


def test_full_generation_requires_bilingual_seo_schema():
    content = _valid_content()
    del content["en"]["seo_description"]

    with pytest.raises(ValueError, match="en.seo_description"):
        _generator()._validate_generated_content(content, "full")


def test_dynamic_attribute_gate_uses_structured_parser_attributes():
    rows = [{"slug": "material", "value": "Pamuk", "value_ru": "хлопок", "value_en": "cotton"}]
    input_data = {
        "attributes": {"Kumaş": "Pamuk"},
        "available_dynamic_attributes": [{"slug": "material"}],
    }

    assert _generator()._apply_confidence_gate_to_dynamic_attributes(rows, input_data) == rows


def test_moderation_uses_currency_and_word_boundaries():
    log = SimpleNamespace(
        category_confidence=0.9,
        input_data={"price": "80", "currency": "TRY"},
        generated_description=(
            "Copyright information accompanies this carefully documented product description "
            "with enough neutral words to pass the minimum content length quality check safely."
        ),
    )

    assert get_moderation_reasons(log) == []


def test_book_applier_does_not_invent_stock(monkeypatch):
    monkeypatch.setattr(BaseAIApplier, "apply", lambda self, target, ai_data: False)
    target = SimpleNamespace(stock_quantity=0, save=lambda: None)

    BookAIApplier().apply(target, {"extracted_attributes": {"stock_quantity": 9}})

    assert target.stock_quantity == 0


def test_celery_task_retries_processing_errors(monkeypatch):
    class BrokenGenerator:
        def process_product(self, **kwargs):
            raise RuntimeError("temporary OpenAI failure")

    monkeypatch.setattr("apps.ai.tasks.ContentGenerator", BrokenGenerator)
    retry_calls = []

    def fake_retry(*, exc, countdown):
        retry_calls.append((exc, countdown))
        raise Retry("scheduled")

    monkeypatch.setattr(process_product_ai_task, "retry", fake_retry)

    with pytest.raises(Retry):
        process_product_ai_task.run(product_id=123)
    assert isinstance(retry_calls[0][0], RuntimeError)
    assert retry_calls[0][1] == 60


@pytest.mark.django_db
def test_category_resolution_uses_exact_active_slug():
    active = Category.objects.create(name="Кепки", slug="caps-exact", is_active=True)
    Category.objects.create(name="Кепки архив", slug="caps-archive", is_active=False)
    product = Product.objects.create(name="Кепка", slug="ai-category-cap")
    log = AIProcessingLog.objects.create(product=product, input_data={})
    content = _valid_content() | {
        "suggested_category_name": "Кепки архив",
        "suggested_category_slug": active.slug,
        "category_confidence": 1.7,
    }

    _generator()._parse_and_save_results(log, content)
    log.refresh_from_db()

    assert log.suggested_category_id == active.id
    assert log.category_confidence == 1.0


@pytest.mark.django_db
def test_unknown_category_is_not_selected_by_partial_name():
    Category.objects.create(name="Книги", slug="books-exact", is_active=True)
    product = Product.objects.create(name="Товар", slug="ai-unknown-category")
    log = AIProcessingLog.objects.create(product=product, input_data={})
    content = _valid_content() | {
        "suggested_category_name": "Кни",
        "category_confidence": 0.99,
    }

    _generator()._parse_and_save_results(log, content)
    log.refresh_from_db()

    assert log.suggested_category_id is None
    assert log.category_confidence == 0.0


@pytest.mark.django_db
def test_applier_updates_category_only_for_verified_high_confidence_category():
    category = Category.objects.create(name="Аксессуары", slug="verified-accessories", is_active=True)
    product = Product.objects.create(name="Ремень", slug="ai-category-apply")

    AIResultApplier().apply_to_product(
        product,
        {"suggested_category": category, "category_confidence": 0.9},
    )
    product.refresh_from_db()

    assert product.category_id == category.id
