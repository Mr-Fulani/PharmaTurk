import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai.admin import (
    MEDICINE_EDITOR_FORM_FIELDS,
    AIProcessingLogAdmin,
    AIProcessingLogForm,
    _get_product_admin_url,
)
from apps.ai.models import (
    AIApplicationStatus,
    AIModerationQueue,
    AIProcessingLog,
    AIProcessingStatus,
)
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.moderation import (
    build_change_preview,
    get_incomplete_medicine_field_messages,
    get_workflow_title,
    reject_log,
)
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidationReport, SemanticValidator
from apps.ai.views import AIProcessingLogViewSet
from apps.catalog.models import (
    AccessoryProduct,
    AutoPartProduct,
    Category,
    ElectronicsProduct,
    HeadwearProduct,
    IslamicClothingProduct,
    JewelryProduct,
    MedicineProduct,
    MedicineProductTranslation,
    SportsProduct,
    UnderwearProduct,
)


pytestmark = pytest.mark.django_db


def _generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    return generator


def _reviewable_log(product, **overrides):
    data = {
        "product": product,
        "processing_type": "full",
        "status": AIProcessingStatus.COMPLETED,
        "input_data": {},
        "generated_title": "Новое проверенное название MODEL-101",
        "generated_description": " ".join(["Подробное описание товара"] * 10),
        "generated_seo_title": "SEO заголовок товара",
        "generated_seo_description": "Подробное SEO описание товара для каталога.",
        "generated_keywords": ["товар", "каталог"],
        "extracted_attributes": {
            "seo_translations": {
                "ru": {
                    "generated_title": "Новое проверенное название MODEL-101",
                    "generated_description": " ".join(["Подробное описание товара"] * 10),
                    "meta_title": "SEO заголовок товара",
                    "meta_description": "Подробное SEO описание товара для каталога.",
                },
                "en": {
                    "generated_title": "Verified product MODEL-101",
                    "generated_description": "Detailed English product description.",
                    "meta_title": "Product SEO title",
                    "meta_description": "Detailed product SEO description.",
                },
            }
        },
    }
    data.update(overrides)
    return AIProcessingLog.objects.create(**data)


def _bound_admin_form_data(log):
    """Build the technical ModelAdmin payload around user-facing editor fields."""
    return {
        "product": log.product_id,
        "processing_type": log.processing_type,
        "status": log.status,
        "application_status": log.application_status,
        # Django's required JSONField treats an empty object as an empty form
        # value.  The real admin excludes these read-only fields from POST, but
        # this direct ModelForm test must still provide non-empty technical data.
        "input_data": json.dumps(log.input_data or {"test_payload": True}, ensure_ascii=False),
        "input_images_urls": json.dumps(log.input_images_urls or [], ensure_ascii=False),
        "generated_title": log.generated_title,
        "generated_description": log.generated_description,
        "generated_seo_title": log.generated_seo_title,
        "generated_seo_description": log.generated_seo_description,
        "generated_keywords": json.dumps(log.generated_keywords or [], ensure_ascii=False),
        "category_alternatives": json.dumps(log.category_alternatives or [], ensure_ascii=False),
        "extracted_attributes": json.dumps(log.extracted_attributes or {}, ensure_ascii=False),
        "image_analysis": json.dumps(log.image_analysis or {}, ensure_ascii=False),
        "llm_model": log.llm_model,
        "tokens_used": json.dumps(log.tokens_used or {"total": 0}, ensure_ascii=False),
        "application_report": json.dumps(log.application_report or {}, ensure_ascii=False),
        "generated_en_title": (
            ((log.extracted_attributes or {}).get("seo_translations") or {})
            .get("en", {})
            .get("generated_title", "")
        ),
        "generated_en_description": (
            ((log.extracted_attributes or {}).get("seo_translations") or {})
            .get("en", {})
            .get("generated_description", "")
        ),
        "og_title": "",
        "og_description": "",
    }


def test_full_apply_tracks_application_and_resolves_existing_queue():
    accessory = AccessoryProduct.objects.create(
        name="MODEL-101 ремень",
        slug="moderation-full-apply-accessory",
        description="Старое описание",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)
    queue = AIModerationQueue.objects.create(
        log_entry=log,
        reason="short_description",
        priority=3,
    )

    _generator().apply_log_to_product(log)

    log.refresh_from_db()
    queue.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED
    assert log.application_status == AIApplicationStatus.APPLIED
    assert log.applied_at is not None
    assert log.application_report["result"] == AIApplicationStatus.APPLIED
    assert queue.resolved_at is not None


def test_apply_calculates_semantic_validation_only_once():
    accessory = AccessoryProduct.objects.create(
        name="MODEL-101 semantic cache",
        slug="moderation-apply-semantic-cache",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)

    with patch(
        "apps.ai.services.content_generator.SemanticValidator.validate_log",
        return_value=SemanticValidationReport(),
    ) as validate_log:
        _generator().apply_log_to_product(log)

    validate_log.assert_called_once_with(log)


def test_reject_closes_queue_without_claiming_product_was_applied():
    accessory = AccessoryProduct.objects.create(
        name="Rejected accessory",
        slug="moderation-rejected-accessory",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)
    queue = AIModerationQueue.objects.create(
        log_entry=log,
        reason="manual_review",
    )

    reject_log(log, notes="Описание не соответствует товару")

    log.refresh_from_db()
    queue.refresh_from_db()
    assert log.status == AIProcessingStatus.REJECTED
    assert log.application_status == AIApplicationStatus.NOT_APPLIED
    assert log.moderation_notes == "Описание не соответствует товару"
    assert queue.resolved_at is not None


def test_approve_api_returns_the_actual_application_result(django_user_model):
    accessory = AccessoryProduct.objects.create(
        name="MODEL-101 API accessory",
        slug="moderation-api-accessory",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)
    user = django_user_model.objects.create_user(
        username="ai-moderator",
        password="test-password",
        is_staff=True,
    )
    request = APIRequestFactory().post(f"/api/ai/logs/{log.pk}/approve/", {}, format="json")
    force_authenticate(request, user=user)

    with patch("apps.ai.services.content_generator.ContentGenerator") as generator_class:
        generator_class.return_value.apply_log_to_product.side_effect = (
            lambda target_log, user: _generator().apply_log_to_product(target_log, user=user)
        )
        response = AIProcessingLogViewSet.as_view({"post": "approve"})(request, pk=log.pk)

    assert response.status_code == 200
    assert response.data == {
        "status": AIProcessingStatus.APPROVED,
        "application_status": AIApplicationStatus.APPLIED,
        "partial": False,
    }


def test_preview_is_read_only_and_uses_actual_domain_product():
    accessory = AccessoryProduct.objects.create(
        name="Current MODEL-101",
        slug="moderation-preview-accessory",
        description="Current description",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)

    rows = build_change_preview(log)

    accessory.refresh_from_db()
    assert accessory.name == "Current MODEL-101"
    assert any(row.label == "Название" and row.decision == "apply" for row in rows)
    assert any(row.section == "Контент EN" for row in rows)


def test_preview_marks_the_same_category_as_unchanged():
    category = Category.objects.create(name="Буркини", slug="burkini-preview-same")
    domain = IslamicClothingProduct.objects.create(
        name="Буркини",
        slug="moderation-preview-same-category",
        category=category,
    )
    domain.refresh_from_db()
    log = _reviewable_log(
        domain.base_product,
        suggested_category=category,
        category_confidence=0.95,
    )

    rows = build_change_preview(log)

    category_row = next(row for row in rows if row.label == "Категория")
    assert category_row.current == "Буркини"
    assert category_row.proposed == "Буркини (95%)"
    assert category_row.decision == "unchanged"


def test_admin_reuses_semantic_validation_between_summary_and_preview():
    accessory = AccessoryProduct.objects.create(
        name="MODEL-101 admin semantic cache",
        slug="moderation-admin-semantic-cache",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)
    model_admin = AIProcessingLogAdmin(AIProcessingLog, AdminSite())

    with patch(
        "apps.ai.services.semantic_validator.SemanticValidator.validate_log",
        return_value=SemanticValidationReport(),
    ) as validate_log:
        model_admin.workflow_overview(log)
        model_admin.change_preview(log)

    validate_log.assert_called_once_with(log)


def test_non_jewelry_form_hides_and_does_not_process_jewelry_fields():
    accessory = AccessoryProduct.objects.create(
        name="Accessory form",
        slug="moderation-accessory-form",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)

    form = AIProcessingLogForm(instance=log)

    assert not set(form.fields).intersection(
        {"jewelry_type", "material", "metal_purity", "stone_type", "carat_weight", "gender"}
    )
    assert not set(form.fields).intersection(MEDICINE_EDITOR_FORM_FIELDS)


def test_medicine_form_exposes_translation_editor_without_changing_other_categories():
    medicine = MedicineProduct.objects.create(
        name="TESTMED 10 MG TABLET",
        slug="moderation-medicine-editor-fields",
    )
    medicine.refresh_from_db()
    log = _reviewable_log(
        medicine.base_product,
        extracted_attributes={
            "translations_data": {
                "ru": {"storage_conditions": "Хранить в сухом месте."},
                "en": {},
            },
            "medicine_translation_quality": {
                "storage_conditions": {
                    "source_length": 100,
                    "ru_length": 21,
                    "en_length": 0,
                    "complete": False,
                }
            },
        },
    )

    form = AIProcessingLogForm(instance=log)
    model_admin = AIProcessingLogAdmin(AIProcessingLog, AdminSite())
    fieldset_titles = [title for title, _options in model_admin.get_fieldsets(None, log)]

    assert set(MEDICINE_EDITOR_FORM_FIELDS).issubset(form.fields)
    assert form.fields["medicine_storage_conditions_ru"].initial == "Хранить в сухом месте."
    assert form.fields["medicine_storage_conditions_en"].initial == ""
    assert "Сейчас заблокировано" in form.fields["medicine_storage_conditions_ru"].help_text
    assert "Исправление медицинских разделов RU/EN" in fieldset_titles


def test_moderator_can_fix_blocked_medicine_translation_then_apply_it():
    medicine = MedicineProduct.objects.create(
        name="TESTMED 10 MG TABLET",
        slug="moderation-fix-medicine-translation",
    )
    medicine.refresh_from_db()
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="ru",
        storage_conditions="Старые условия хранения RU",
    )
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="en",
        storage_conditions="Old storage conditions EN",
    )
    log = _reviewable_log(
        medicine.base_product,
        generated_title="TESTMED 10 мг, таблетки",
        generated_description=(
            "Краткое точное описание препарата содержит действующее вещество форму выпуска "
            "дозировку количество таблеток способ приема и сведения изготовителя"
        ),
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": "TESTMED 10 мг, таблетки"},
                "en": {"generated_title": "TESTMED 10 mg tablets"},
            },
            "translations_data": {
                "ru": {"storage_conditions": "Хранить ниже 25 °C в сухом месте."},
                "en": {},
            },
            "medicine_translation_quality": {
                "storage_conditions": {
                    "source_length": 120,
                    "source_sha256": "source-hash",
                    "ru_length": 34,
                    "en_length": 0,
                    "ru_complete": True,
                    "en_complete": False,
                    "complete": False,
                }
            },
        },
    )
    initial_form = AIProcessingLogForm(instance=log)
    data = _bound_admin_form_data(log)
    for field_name in MEDICINE_EDITOR_FORM_FIELDS:
        data[field_name] = initial_form.fields[field_name].initial or ""
    data["medicine_storage_conditions_en"] = "Store below 25 °C in a dry place."

    form = AIProcessingLogForm(data=data, instance=log)

    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    saved.save()
    report = SemanticValidator().validate_log(saved)
    assert "medicine_translation:storage_conditions" not in report.rejected_fields
    quality = saved.extracted_attributes["medicine_translation_quality"]["storage_conditions"]
    assert quality["complete"] is True
    assert quality["moderator_reviewed"] is True

    _generator().apply_log_to_product(saved)

    medicine.refresh_from_db()
    saved.refresh_from_db()
    assert (
        medicine.translations.get(locale="ru").storage_conditions
        == "Хранить ниже 25 °C в сухом месте."
    )
    assert (
        medicine.translations.get(locale="en").storage_conditions
        == "Store below 25 °C in a dry place."
    )
    assert saved.status == AIProcessingStatus.APPROVED
    assert saved.application_status == AIApplicationStatus.APPLIED


def test_missing_medicine_en_defaults_to_current_product_value_and_closes_review():
    medicine = MedicineProduct.objects.create(
        name="MERGEMED 15 MG TABLET",
        slug="moderation-merge-current-medicine-translation",
    )
    medicine.refresh_from_db()
    current_ru = "Проверенные прежние условия хранения препарата на русском языке."
    current_en = "Verified current medicine storage conditions in English."
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="ru",
        storage_conditions=current_ru,
    )
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="en",
        storage_conditions=current_en,
    )
    new_ru = "Новые проверенные условия хранения препарата на русском языке."
    log = _reviewable_log(
        medicine.base_product,
        generated_title="MERGEMED 15 мг, таблетки",
        generated_description=(
            "Краткое точное описание препарата содержит действующее вещество форму выпуска "
            "дозировку количество таблеток способ приема и сведения изготовителя"
        ),
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": "MERGEMED 15 мг, таблетки"},
                "en": {"generated_title": "MERGEMED 15 mg tablets"},
            },
            "translations_data": {
                "ru": {"storage_conditions": new_ru},
                "en": {},
            },
            "medicine_translation_quality": {
                "storage_conditions": {
                    "source_length": 100,
                    "ru_length": len(new_ru),
                    "en_length": 0,
                    "ru_complete": True,
                    "en_complete": False,
                    "complete": False,
                }
            },
            # Simulates an old partial attempt made before merge_current existed.
            "medicine_moderator_decisions": {"storage_conditions": "apply"},
        },
    )
    queue = AIModerationQueue.objects.create(
        log_entry=log,
        reason="incomplete_medicine_translation",
    )

    initial_form = AIProcessingLogForm(instance=log)

    assert initial_form.fields["medicine_storage_conditions_en"].initial == current_en
    assert (
        initial_form.fields["medicine_storage_conditions_decision"].initial
        == "merge_current"
    )
    assert "AI не создал EN" in initial_form.fields["medicine_storage_conditions_en"].help_text

    data = _bound_admin_form_data(log)
    for field_name in MEDICINE_EDITOR_FORM_FIELDS:
        data[field_name] = initial_form.fields[field_name].initial or ""
    form = AIProcessingLogForm(data=data, instance=log)

    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    saved.save()
    assert SemanticValidator().validate_log(saved).rejected_fields == set()

    _generator().apply_log_to_product(saved)

    medicine.refresh_from_db()
    saved.refresh_from_db()
    queue.refresh_from_db()
    assert medicine.translations.get(locale="ru").storage_conditions == new_ru
    assert medicine.translations.get(locale="en").storage_conditions == current_en
    assert saved.status == AIProcessingStatus.APPROVED
    assert saved.application_status == AIApplicationStatus.APPLIED
    assert saved.application_report["moderator_preserved_locales"] == {
        "storage_conditions": ["en"]
    }
    assert queue.resolved_at is not None


def test_bulk_apply_preserves_current_medicine_en_and_closes_review():
    medicine = MedicineProduct.objects.create(
        name="BULKMERGE 15 MG TABLET",
        slug="moderation-bulk-merge-current-medicine-translation",
    )
    medicine.refresh_from_db()
    current_en = "Verified current medicine storage conditions in English."
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="ru",
        storage_conditions="Проверенные прежние условия хранения препарата.",
    )
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="en",
        storage_conditions=current_en,
    )
    new_ru = "Новые проверенные условия хранения препарата на русском языке."
    log = _reviewable_log(
        medicine.base_product,
        generated_title="BULKMERGE 15 мг, таблетки",
        generated_description=(
            "Краткое точное описание препарата содержит действующее вещество форму выпуска "
            "дозировку количество таблеток способ приема и сведения изготовителя"
        ),
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": "BULKMERGE 15 мг, таблетки"},
                "en": {"generated_title": "BULKMERGE 15 mg tablets"},
            },
            "translations_data": {
                "ru": {"storage_conditions": new_ru},
                "en": {},
            },
            "medicine_translation_quality": {
                "storage_conditions": {
                    "source_length": 100,
                    "ru_length": len(new_ru),
                    "en_length": 0,
                    "ru_complete": True,
                    "en_complete": False,
                    "complete": False,
                }
            },
            "medicine_moderator_decisions": {"storage_conditions": "apply"},
        },
    )
    queue = AIModerationQueue.objects.create(
        log_entry=log,
        reason="incomplete_medicine_translation",
    )
    model_admin = AIProcessingLogAdmin(AIProcessingLog, AdminSite())
    request = SimpleNamespace(user=None)
    generator = _generator()

    with (
        patch(
            "apps.ai.services.content_generator.ContentGenerator",
            return_value=generator,
        ),
        patch("apps.ai.admin.messages.success") as success_message,
    ):
        model_admin.apply_to_product(
            request,
            AIProcessingLog.objects.filter(pk=log.pk),
        )

    medicine.refresh_from_db()
    log.refresh_from_db()
    queue.refresh_from_db()
    assert medicine.translations.get(locale="ru").storage_conditions == new_ru
    assert medicine.translations.get(locale="en").storage_conditions == current_en
    assert log.status == AIProcessingStatus.APPROVED
    assert log.application_status == AIApplicationStatus.APPLIED
    assert log.extracted_attributes["medicine_moderator_decisions"] == {
        "storage_conditions": "merge_current"
    }
    assert log.application_report["moderator_preserved_locales"] == {
        "storage_conditions": ["en"]
    }
    assert queue.resolved_at is not None
    assert "текущий EN" in success_message.call_args.args[1]


def test_moderator_can_keep_current_blocked_medicine_section_and_close_review():
    medicine = MedicineProduct.objects.create(
        name="KEEPMED 20 MG TABLET",
        slug="moderation-keep-current-medicine-translation",
    )
    medicine.refresh_from_db()
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="ru",
        storage_conditions="Проверенное текущее хранение RU",
    )
    MedicineProductTranslation.objects.create(
        product=medicine,
        locale="en",
        storage_conditions="Verified current storage EN",
    )
    log = _reviewable_log(
        medicine.base_product,
        generated_title="KEEPMED 20 мг, таблетки",
        generated_description=(
            "Краткое точное описание препарата содержит действующее вещество форму выпуска "
            "дозировку количество таблеток способ приема и сведения изготовителя"
        ),
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": "KEEPMED 20 мг, таблетки"},
                "en": {"generated_title": "KEEPMED 20 mg tablets"},
            },
            "translations_data": {
                "ru": {"storage_conditions": "Неполное предложение RU"},
                "en": {},
            },
            "medicine_translation_quality": {
                "storage_conditions": {
                    "source_length": 500,
                    "ru_length": 22,
                    "en_length": 0,
                    "complete": False,
                }
            },
        },
    )
    initial_form = AIProcessingLogForm(instance=log)
    data = _bound_admin_form_data(log)
    for field_name in MEDICINE_EDITOR_FORM_FIELDS:
        data[field_name] = initial_form.fields[field_name].initial or ""
    data["medicine_storage_conditions_decision"] = "keep_current"

    form = AIProcessingLogForm(data=data, instance=log)

    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    saved.save()
    report = SemanticValidator().validate_log(saved)
    assert report.rejected_fields == set()

    _generator().apply_log_to_product(saved)

    medicine.refresh_from_db()
    saved.refresh_from_db()
    assert (
        medicine.translations.get(locale="ru").storage_conditions
        == "Проверенное текущее хранение RU"
    )
    assert (
        medicine.translations.get(locale="en").storage_conditions
        == "Verified current storage EN"
    )
    assert saved.application_report["moderator_kept_fields"] == ["storage_conditions"]
    assert saved.status == AIProcessingStatus.APPROVED


# Раздел хранения VISCOTEARS: исходник и верный перевод по абзацам.
STORAGE_ROWS = (
    ("5. VISCOTEARS'IN SAKLANMASI", "5. ХРАНЕНИЕ VISCOTEARS", "5. STORAGE OF VISCOTEARS"),
    (
        "VISCOTEARS'ı çocukların göremeyeceği, erişemeyeceği yerlerde ve ambalajında saklayınız.",
        "Храните VISCOTEARS в недоступном для детей месте и в упаковке.",
        "Store VISCOTEARS in a place out of the reach of children and in its packaging.",
    ),
    (
        "25°C'nin altındaki oda sıcaklığında saklayınız.",
        "Храните при комнатной температуре ниже 25°C.",
        "Store at room temperature below 25°C.",
    ),
    (
        "Kullandıktan sonra kapağını hemen kapatınız.",
        "После использования сразу закройте крышку.",
        "Immediately close the cap after use.",
    ),
    (
        "Tüp açıldıktan sonra 6 hafta içerisinde kullanılmalıdır. Kullanılmayan kısmı saklamayınız.",
        "После открытия тюбик следует использовать в течение 6 недель. Не храните неиспользованную часть.",
        "The tube should be used within 6 weeks after opening. Do not store any unused portion.",
    ),
)


def _storage_log(medicine, *, shifted):
    """Лог лекарства с переводом хранения по абзацам; shifted — ответ модели со сдвигом (как до 21.10)."""
    ru = [row[1] for row in STORAGE_ROWS]
    en = [row[2] for row in STORAGE_ROWS]
    if shifted:
        ru = ru[1:] + ["Обратитесь к врачу."]
        en = en[1:] + ["Consult your doctor."]
    return _reviewable_log(
        medicine.base_product,
        generated_title="TESTMED 10 мг, таблетки",
        generated_description=(
            "Краткое точное описание препарата содержит действующее вещество форму выпуска "
            "дозировку количество таблеток способ приема и сведения изготовителя"
        ),
        input_data={
            "attributes": {
                "source_tabs": {
                    "storage_conditions": {"text": "\n".join(row[0] for row in STORAGE_ROWS)}
                }
            }
        },
        extracted_attributes={
            "seo_translations": {
                "ru": {"generated_title": "TESTMED 10 мг, таблетки"},
                "en": {"generated_title": "TESTMED 10 mg tablets"},
            },
            "translations_data": {
                "ru": {"storage_conditions": "\n".join(ru)},
                "en": {"storage_conditions": "\n".join(en)},
            },
            "medicine_translation_quality": {
                "storage_conditions": {"source_length": 300, "complete": True}
            },
        },
    )


def _medicine_with_storage(slug):
    medicine = MedicineProduct.objects.create(name="TESTMED 10 MG TABLET", slug=slug)
    medicine.refresh_from_db()
    for locale, text in (("ru", "Текущее хранение RU"), ("en", "Current storage EN")):
        MedicineProductTranslation.objects.create(
            product=medicine, locale=locale, storage_conditions=text
        )
    return medicine


def test_shifted_medicine_paragraphs_go_to_moderation_and_name_the_paragraphs():
    medicine = _medicine_with_storage("moderation-shifted-medicine-paragraphs")
    log = _storage_log(medicine, shifted=True)

    report = SemanticValidator().validate_log(log)
    assert "medicine_translation:storage_conditions" in report.rejected_fields
    assert "medicine_paragraph_mismatch" in report.reasons
    numbers = {item["number"] for item in report.paragraph_findings["storage_conditions"]}
    assert {1, 2, 3, 4} <= numbers

    preview = build_change_preview(log, semantic_report=report)
    storage_rows = [row for row in preview if row.label == "Условия хранения"]
    assert storage_rows and all(row.decision == "blocked" for row in storage_rows)
    assert storage_rows[0].reason.startswith("Абзацы 1–")
    assert "похожи на чужой перевод" in storage_rows[0].reason
    form = AIProcessingLogForm(instance=log)
    help_text = form.fields["medicine_storage_conditions_ru"].help_text
    assert "№1: исходник «5. VISCOTEARS&#x27;IN SAKLANMASI»" in help_text
    assert "перевод соседнего абзаца (сдвиг)" in help_text

    _generator().apply_log_to_product(log)

    medicine.refresh_from_db()
    log.refresh_from_db()
    assert medicine.translations.get(locale="ru").storage_conditions == "Текущее хранение RU"
    assert medicine.translations.get(locale="en").storage_conditions == "Current storage EN"
    assert log.status == AIProcessingStatus.MODERATION
    assert log.application_status == AIApplicationStatus.PARTIAL
    reported = log.application_report["paragraph_problems"]["storage_conditions"]
    assert {1, 2, 3, 4} <= {item["number"] for item in reported}
    assert AIModerationQueue.objects.filter(log_entry=log, resolved_at__isnull=True).exists()
    message = " ".join(
        get_incomplete_medicine_field_messages(log, log.application_report["rejected_fields"])
    )
    assert "условия хранения" in message and "похожи на чужой перевод" in message
    assert "перезапустите AI" in message


def test_paragraph_reason_in_preview_keeps_locale_case():
    medicine = _medicine_with_storage("moderation-paragraph-reason-case")
    log = _storage_log(medicine, shifted=False)
    report = SemanticValidationReport(
        rejected_fields={"medicine_translation:storage_conditions"},
        reasons=["medicine_paragraph_mismatch"],
        paragraph_findings={"storage_conditions": [{"number": 2, "problems": ["ru_en_mismatch"]}]},
    )

    rows = [row for row in build_change_preview(log, semantic_report=report) if row.label == "Условия хранения"]

    assert rows[0].reason == "Абзац 2 похож на чужой перевод: RU и EN расходятся — раздел не будет применён"


def test_correct_medicine_paragraphs_are_applied():
    medicine = _medicine_with_storage("moderation-correct-medicine-paragraphs")
    log = _storage_log(medicine, shifted=False)

    report = SemanticValidator().validate_log(log)
    assert report.paragraph_findings == {}
    assert "medicine_translation:storage_conditions" not in report.rejected_fields

    _generator().apply_log_to_product(log)

    medicine.refresh_from_db()
    assert medicine.translations.get(locale="ru").storage_conditions.startswith("5. ХРАНЕНИЕ VISCOTEARS")


def test_moderator_fix_of_flagged_paragraphs_is_applied_without_paragraph_check():
    medicine = _medicine_with_storage("moderation-fixed-medicine-paragraphs")
    log = _storage_log(medicine, shifted=True)
    initial_form = AIProcessingLogForm(instance=log)
    data = _bound_admin_form_data(log)
    for field_name in MEDICINE_EDITOR_FORM_FIELDS:
        data[field_name] = initial_form.fields[field_name].initial or ""
    fixed_ru = "Храните VISCOTEARS при температуре ниже 25°C, в недоступном для детей месте."
    data["medicine_storage_conditions_ru"] = fixed_ru

    form = AIProcessingLogForm(data=data, instance=log)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    saved.save()

    quality = saved.extracted_attributes["medicine_translation_quality"]["storage_conditions"]
    assert quality["paragraphs_reviewed"] is True
    assert SemanticValidator().validate_log(saved).paragraph_findings == {}
    _generator().apply_log_to_product(saved)
    medicine.refresh_from_db()
    assert medicine.translations.get(locale="ru").storage_conditions == fixed_ru


def test_unchanged_form_save_keeps_paragraph_check():
    medicine = _medicine_with_storage("moderation-unchanged-medicine-paragraphs")
    log = _storage_log(medicine, shifted=True)
    initial_form = AIProcessingLogForm(instance=log)
    data = _bound_admin_form_data(log)
    for field_name in MEDICINE_EDITOR_FORM_FIELDS:
        data[field_name] = initial_form.fields[field_name].initial or ""
    data["medicine_storage_conditions_decision"] = "merge_current"

    form = AIProcessingLogForm(data=data, instance=log)
    assert form.is_valid(), form.errors
    saved = form.save(commit=False)
    saved.save()

    assert "storage_conditions" in SemanticValidator().validate_log(saved).paragraph_findings


def test_category_alternatives_accepts_an_empty_list_in_admin_form():
    accessory = AccessoryProduct.objects.create(
        name="Accessory empty alternatives",
        slug="moderation-empty-category-alternatives",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product, category_alternatives=[])

    form = AIProcessingLogForm(instance=log)

    assert form.fields["category_alternatives"].required is False
    assert form.fields["category_alternatives"].clean("[]") == []


def test_admin_rerun_endpoint_does_not_validate_current_log_form(client, django_user_model):
    admin_user = django_user_model.objects.create_superuser(
        username="ai-admin",
        email="ai-admin@example.com",
        password="test-password",
    )
    client.force_login(admin_user)
    accessory = AccessoryProduct.objects.create(
        name="Accessory rerun endpoint",
        slug="moderation-rerun-endpoint",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product, category_alternatives=[])
    url = reverse("admin:ai_aiprocessinglog_rerun", args=[log.pk])

    with patch("apps.ai.tasks.enqueue_product_ai_task") as enqueue:
        enqueue.return_value = (SimpleNamespace(id=999), "task-id", True)
        response = client.post(url, data={})

    assert response.status_code == 302
    assert response.url == reverse("admin:ai_aiprocessinglog_change", args=[999])
    enqueue.assert_called_once_with(
        product_id=log.product_id,
        processing_type=log.processing_type,
        auto_apply=False,
        force=True,
    )


def test_short_medicine_card_uses_clinical_sections_instead_of_padding_description():
    description = (
        "Краткое точное описание препарата содержит действующее вещество форму выпуска "
        "количество таблеток и способ приема"
    )
    medicine = MedicineProduct.objects.create(
        name="TESTMED 10 MG TABLET",
        slug="moderation-short-medicine-card",
    )
    medicine.refresh_from_db()
    medicine_log = _reviewable_log(
        medicine.base_product,
        generated_description=description,
    )
    accessory = AccessoryProduct.objects.create(
        name="Short accessory",
        slug="moderation-short-accessory-card",
    )
    accessory.refresh_from_db()
    accessory_log = _reviewable_log(
        accessory.base_product,
        generated_description=description,
    )

    medicine_reasons = get_moderation_reasons(
        medicine_log,
        semantic_report=SemanticValidationReport(),
    )
    accessory_reasons = get_moderation_reasons(
        accessory_log,
        semantic_report=SemanticValidationReport(),
    )

    assert "short_description" not in medicine_reasons
    assert "short_description" in accessory_reasons


def test_legacy_approved_log_does_not_claim_confirmed_application():
    accessory = AccessoryProduct.objects.create(
        name="Legacy application state",
        slug="moderation-legacy-application-state",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(
        accessory.base_product,
        status=AIProcessingStatus.APPROVED,
        application_status=AIApplicationStatus.UNKNOWN,
    )

    assert get_workflow_title(log) == (
        "Одобрено — применение не подтверждено (старый лог)",
        "warning",
    )


def test_partial_attempt_without_changes_does_not_claim_partial_application():
    accessory = AccessoryProduct.objects.create(
        name="No changes application state",
        slug="moderation-no-changes-application-state",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(
        accessory.base_product,
        status=AIProcessingStatus.MODERATION,
        application_status=AIApplicationStatus.PARTIAL,
        application_report={"product_updated": False},
    )
    model_admin = AIProcessingLogAdmin(AIProcessingLog, AdminSite())

    assert get_workflow_title(log) == (
        "Товар не изменён — требуется решение по полям",
        "warning",
    )
    assert model_admin.application_state(log) == "Товар не изменён; есть нерешённые поля"


def test_jewelry_form_keeps_specialized_fields():
    jewelry = JewelryProduct.objects.create(
        name="Jewelry form",
        slug="moderation-jewelry-form",
    )
    jewelry.refresh_from_db()
    log = _reviewable_log(jewelry.base_product)

    form = AIProcessingLogForm(instance=log)

    assert {"jewelry_type", "material", "metal_purity", "stone_type"}.issubset(form.fields)


def test_form_synchronizes_visible_ru_edits_with_nested_apply_payload():
    accessory = AccessoryProduct.objects.create(
        name="RU edit accessory",
        slug="moderation-ru-edit-accessory",
    )
    accessory.refresh_from_db()
    log = _reviewable_log(accessory.base_product)
    data = {
        "product": log.product_id,
        "processing_type": log.processing_type,
        "status": log.status,
        "application_status": log.application_status,
        "input_data": '{"source": "test"}',
        "input_images_urls": "[]",
        "generated_title": "Исправленное название RU",
        "generated_description": "Исправленное описание RU",
        "generated_seo_title": "Исправленный SEO RU",
        "generated_seo_description": "Исправленное SEO описание RU",
        "generated_keywords": '["исправлено"]',
        "category_alternatives": '[{"name": "Аксессуары"}]',
        "extracted_attributes": json.dumps(log.extracted_attributes, ensure_ascii=False),
        "image_analysis": "{}",
        "llm_model": log.llm_model,
        "tokens_used": '{"total": 0}',
        "application_report": "{}",
        "generated_en_title": "Verified product MODEL-101",
        "generated_en_description": "Detailed English product description.",
        "og_title": "",
        "og_description": "",
    }
    form = AIProcessingLogForm(data=data, instance=log)

    assert form.is_valid(), form.errors
    # Django Admin calls ModelForm.save(commit=False), then save_model().
    saved = form.save(commit=False)
    saved.save()
    ru = saved.extracted_attributes["seo_translations"]["ru"]
    assert ru["generated_title"] == "Исправленное название RU"
    assert ru["generated_description"] == "Исправленное описание RU"
    assert ru["meta_title"] == "Исправленный SEO RU"
    assert ru["meta_keywords"] == ["исправлено"]


@pytest.mark.parametrize(
    "model",
    (
        ElectronicsProduct,
        SportsProduct,
        AutoPartProduct,
        HeadwearProduct,
        UnderwearProduct,
        IslamicClothingProduct,
    ),
)
def test_admin_product_link_supports_every_previously_unmapped_domain(model):
    domain = model.objects.create(
        name=f"Admin link {model.__name__}",
        slug=f"moderation-admin-{model._meta.model_name}",
    )
    domain.refresh_from_db()

    url = _get_product_admin_url(domain.base_product)

    assert url is not None
    assert model._meta.model_name in url


def test_admin_exposes_only_unambiguous_bulk_actions():
    assert AIProcessingLogAdmin.actions == (
        "apply_to_product",
        "reject_results",
        "rerun_ai_full",
        "rerun_ai_description_only",
    )
