"""БАДы не уходят в модерацию из-за «лекарственных» атрибутов."""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.ai.models import AIModerationQueue, AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.result_applier import AIResultApplier
from apps.catalog.models import Category, GlobalAttributeKey, ProductAttributeValue, SupplementProduct

pytestmark = pytest.mark.django_db

MEDICINE_ATTRS = {
    "administration_route": "Oral",
    "sgk_status": "Bedeli Ödenmez",
    "prescription_type": "Reçetesiz",
    "shelf_life": "24 Ay",
}
DESCRIPTION = " ".join(["Пищевая добавка Solgar с витамином D3 для ежедневного приёма."] * 4)


def _supplement(slug="solgar-d3"):
    category = Category.objects.create(name="БАДы", slug=f"noise-{slug}")
    supplement = SupplementProduct.objects.create(
        name="SOLGAR VITAMIN D3 1000 IU 100 kapsül",
        slug=slug,
        category=category,
        external_data={"source": "ilacfiyati", "attributes": dict(MEDICINE_ATTRS)},
    )
    supplement.refresh_from_db()
    return supplement


def _log(product, dynamic, status=AIProcessingStatus.COMPLETED):
    return AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=status,
        input_data={},
        generated_title="Витамин D3 Solgar 1000 МЕ, 100 капсул",
        generated_description=DESCRIPTION,
        generated_seo_title="Витамин D3 Solgar",
        generated_seo_description="Пищевая добавка Solgar с витамином D3.",
        category_confidence=0.9,
        extracted_attributes={
            "dynamic_attributes": dynamic,
            "seo_translations": {
                "en": {
                    "generated_title": "Solgar Vitamin D3 1000 IU, 100 capsules",
                    "generated_description": "Solgar dietary supplement with vitamin D3.",
                }
            },
        },
    )


FORBIDDEN = [{"slug": "administration_route", "value": "перорально", "value_ru": "перорально", "value_en": "oral"}]


def test_medicine_keys_are_not_offered_to_supplement_prompt():
    supplement = _supplement()
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None

    data = generator._collect_input_data(supplement.base_product)

    assert "administration_route" not in data and "sgk_status" not in data
    prompt = generator._construct_user_prompt(supplement.base_product, {}, "full", input_data=data)
    assert '"known_attributes": {"isbn": null, "publisher": null, "pages": null}' in prompt


def test_supplement_with_forbidden_attribute_is_approved_without_moderation():
    GlobalAttributeKey.objects.get_or_create(slug="administration-route", defaults={"sort_order": 1})
    supplement = _supplement()
    log = _log(supplement.base_product, FORBIDDEN)
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()

    generator.apply_log_to_product(log)

    log.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED
    assert "dynamic_attributes:administration_route" in log.application_report["rejected_fields"]
    assert not AIModerationQueue.objects.filter(log_entry=log).exists()
    assert not ProductAttributeValue.objects.filter(object_id=supplement.pk).exists()


def _light_generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    return generator


def test_close_command_resolves_entries_without_remaining_reasons(monkeypatch):
    monkeypatch.setattr(
        "apps.ai.management.commands.close_resolved_ai_moderation.ContentGenerator", _light_generator
    )
    noisy = _log(_supplement("noise-1").base_product, FORBIDDEN, status=AIProcessingStatus.MODERATION)
    real = _log(
        _supplement("noise-2").base_product,
        [{"slug": "material", "value": "kapsül", "value_ru": "Yumuşak jelatin kapsül", "value_en": "softgel"}],
        status=AIProcessingStatus.MODERATION,
    )
    for log in (noisy, real):
        AIModerationQueue.objects.create(log_entry=log, reason="forbidden_attribute", priority=3)

    out = StringIO()
    call_command("close_resolved_ai_moderation", "--dry-run", stdout=out)
    assert f"лог {noisy.id}" in out.getvalue() and f"лог {real.id}" not in out.getvalue()
    assert AIModerationQueue.objects.filter(resolved_at__isnull=True).count() == 2

    call_command("close_resolved_ai_moderation", stdout=StringIO())

    noisy.refresh_from_db()
    real.refresh_from_db()
    assert noisy.status == AIProcessingStatus.APPROVED
    assert AIModerationQueue.objects.get(log_entry=noisy).resolved_at is not None
    assert real.status == AIProcessingStatus.MODERATION  # untranslated_attribute остаётся причиной
    assert AIModerationQueue.objects.get(log_entry=real).resolved_at is None
