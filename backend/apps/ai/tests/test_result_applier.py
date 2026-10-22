import pytest
from django.db import IntegrityError, transaction

from apps.ai.models import AIApplicationStatus, AIProcessingLog
from apps.ai.models import AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.medicine_memory import paragraph_problems
from apps.ai.services.result_applier import AIResultApplier
from apps.catalog.models import (
    AccessoryProduct,
    Category,
    GlobalAttributeKey,
    MedicineProduct,
    ProductAttributeValue,
)


pytestmark = pytest.mark.django_db


def test_dynamic_attribute_apply_is_idempotent_for_repeated_slug():
    key, _ = GlobalAttributeKey.objects.get_or_create(
        slug="material",
        defaults={"sort_order": 17},
    )
    accessory = AccessoryProduct.objects.create(
        name="Тестовый ремень",
        slug="test-repeated-dynamic-attribute",
    )
    accessory.refresh_from_db()
    product = accessory.base_product
    applier = AIResultApplier()

    applier.apply_to_product(
        product,
        {
            "extracted_attributes": {
                "dynamic_attributes": [
                    {
                        "slug": "material",
                        "value": "кожа",
                        "value_ru": "кожа",
                        "value_en": "leather",
                    },
                    {
                        "slug": "material",
                        "value": "Искусственная кожа",
                        "value_ru": "Искусственная кожа",
                        "value_en": "Faux Leather",
                    },
                ]
            }
        },
    )

    values = accessory.dynamic_attributes.filter(attribute_key=key)
    assert values.count() == 1
    value = values.get()
    assert value.value_ru == "Искусственная кожа"
    assert value.value_en == "Faux Leather"
    assert value.sort_order == key.sort_order

    applier.apply_to_product(
        product,
        {
            "extracted_attributes": {
                "dynamic_attributes": [
                    {
                        "slug": "material",
                        "value": "Натуральная кожа",
                        "value_ru": "Натуральная кожа",
                        "value_en": "Genuine Leather",
                    }
                ]
            }
        },
    )

    assert values.count() == 1
    value.refresh_from_db()
    assert value.value_ru == "Натуральная кожа"

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductAttributeValue.objects.create(
            content_object=accessory,
            attribute_key=key,
            value="Повтор",
        )


def test_medicine_applier_saves_localized_translation_seo_fields():
    medicine = MedicineProduct.objects.create(
        name="Тестовый препарат",
        slug="test-medicine",
        description="Старое описание",
    )
    medicine.refresh_from_db()
    product = medicine.base_product

    AIResultApplier().apply_to_product(
        product,
        {
            "generated_title": "Тестовый препарат",
            "generated_description": "Описание по умолчанию",
            "generated_seo_title": "Русский SEO fallback",
            "generated_seo_description": "Русское SEO описание fallback",
            "generated_keywords": ["лекарство", "тест"],
            "translations": {
                "ru": {
                    "name": "Тестовый препарат",
                    "description": "Русское описание",
                    "meta_title": "Русский SEO title",
                    "meta_description": "Русское SEO описание",
                    "meta_keywords": ["лекарство", "тест"],
                    "og_title": "Русский OG title",
                    "og_description": "Русское OG описание",
                    "indications": "Показания на русском",
                },
                "en": {
                    "name": "Test medicine",
                    "description": "English description",
                    "meta_title": "English SEO title",
                    "meta_description": "English SEO description",
                    "meta_keywords": ["medicine", "test"],
                    "og_title": "English OG title",
                    "og_description": "English OG description",
                    "indications": "English indications",
                },
            },
        },
    )

    ru = medicine.translations.get(locale="ru")
    en = medicine.translations.get(locale="en")

    assert ru.meta_title == "Русский SEO title"
    assert ru.meta_description == "Русское SEO описание"
    assert ru.meta_keywords == "лекарство, тест"
    assert ru.og_title == "Русский OG title"
    assert ru.og_description == "Русское OG описание"
    assert ru.indications == "Показания на русском"

    assert en.meta_title == "English SEO title"
    assert en.meta_description == "English SEO description"
    assert en.meta_keywords == "medicine, test"
    assert en.og_title == "English OG title"
    assert en.og_description == "English OG description"
    assert en.indications == "English indications"


def test_medicine_content_apply_uses_english_seo_for_fallback_fields():
    medicine = MedicineProduct.objects.create(
        name="ZOVIRAX %5 KREM (2 GR)",
        slug="zovirax-5-krem-2-gr",
        description="Raw description",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    log = AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        input_data={},
        generated_title="ZOVIRAX 5% крем (2 г)",
        generated_description="Русское описание",
        generated_seo_title="Русский SEO title",
        generated_seo_description="Русское SEO описание",
        generated_keywords=["зовиракс", "крем"],
        extracted_attributes={
            "seo_translations": {
                "ru": {
                    "generated_title": "ZOVIRAX 5% крем (2 г)",
                    "generated_description": "Русское описание",
                    "meta_title": "Русский SEO title",
                    "meta_description": "Русское SEO описание",
                    "meta_keywords": ["зовиракс", "крем"],
                },
                "en": {
                    "generated_title": "ZOVIRAX 5% cream (2 g)",
                    "generated_description": "English description",
                    "meta_title": "English SEO title",
                    "meta_description": "English SEO description",
                    "meta_keywords": ["zovirax", "cream"],
                },
            }
        },
    )

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    generator._apply_changes_to_product(product, log)
    medicine.refresh_from_db()

    assert medicine.meta_title == "English SEO title"
    assert medicine.meta_description == "English SEO description"
    assert medicine.meta_keywords == "zovirax, cream"
    assert medicine.translations.get(locale="ru").meta_title == "Русский SEO title"
    assert medicine.translations.get(locale="en").meta_title == "English SEO title"


def test_medicine_prompt_uses_structured_sections_without_duplicate_raw_description():
    product = MedicineProduct.objects.create(
        name="LASIRIN 20 MG TABLET (20 TABLET)",
        slug="lasirin-20-mg-tablet-20-tablet",
        description="Base description",
    ).base_product
    generator = ContentGenerator.__new__(ContentGenerator)
    generator._collect_input_data = lambda _product: {
        "name": "LASIRIN 20 MG TABLET (20 TABLET)",
        "description": "DUPLICATED DESCRIPTION SHOULD NOT BE SENT",
        "raw_description": "DUPLICATED RAW SHOULD NOT BE SENT",
        "active_ingredient": "Bilastin",
        "attributes": {
            "source_tabs": {
                "indications": {"text": "LASİRİN nedir ve ne için kullanılır? Uzun kaynak metin."},
                "usage_instructions": {"text": "Doktorunuzun söylediği şekilde kullanınız."},
            }
        },
    }
    generator._get_prompt_template = lambda *_args, **_kwargs: ""

    prompt = generator._construct_medicine_user_prompt(product, {}, "full")

    assert "source_sections" in prompt
    assert '"indications": {"available": true, "length": 55}' in prompt
    assert "LASİRİN nedir ve ne için kullanılır" not in prompt
    assert "DUPLICATED DESCRIPTION SHOULD NOT BE SENT" not in prompt
    assert "DUPLICATED RAW SHOULD NOT BE SENT" not in prompt
    assert "отдельный этап переведёт полный исходный текст" in prompt


def test_medicine_applier_fills_source_backed_structured_fields_only_when_empty():
    medicine = MedicineProduct.objects.create(
        name="RINVOQ 15 MG",
        slug="rinvoq-source-backed-fields",
        dosage_form="tablet",
        volume="28",
        active_ingredient="",
    )
    medicine.refresh_from_db()

    AIResultApplier().apply_to_product(
        medicine.base_product,
        {
            "extracted_attributes": {
                "dosage_form": "capsule",
                "volume": "98",
                "active_ingredient": "upadacitinib",
                "sgk_status": "Bedeli Ödenir",
            }
        },
    )

    medicine.refresh_from_db()
    assert medicine.dosage_form == "tablet"
    assert medicine.volume == "28"
    assert medicine.active_ingredient == "upadacitinib"
    assert medicine.sgk_status == "Bedeli Ödenir"


def test_auto_apply_existing_completed_log_applies_saved_medicine_seo():
    medicine = MedicineProduct.objects.create(
        name="BILAXTEN 20 MG 20 TABLET",
        slug="bilaxten-20-mg-20-tablet",
        description="Raw description",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="BILAXTEN 20 мг 20 таблеток",
        generated_description="Русское описание",
        generated_seo_title="Русский SEO",
        generated_seo_description="Русское SEO описание",
        generated_keywords=["биластин"],
        extracted_attributes={
            "seo_translations": {
                "ru": {
                    "generated_title": "BILAXTEN 20 мг 20 таблеток",
                    "generated_description": "Русское описание",
                    "meta_title": "Русский SEO",
                    "meta_description": "Русское SEO описание",
                    "meta_keywords": ["биластин"],
                },
                "en": {
                    "generated_title": "BILAXTEN 20 mg 20 tablets",
                    "generated_description": "English description",
                    "meta_title": "English SEO",
                    "meta_description": "English SEO description",
                    "meta_keywords": ["bilastine"],
                },
            }
        },
    )

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    log = generator.process_product(product.id, auto_apply=True)

    medicine.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED
    assert log.application_status == AIApplicationStatus.APPLIED
    assert medicine.meta_title == "English SEO"
    assert medicine.meta_description == "English SEO description"
    assert medicine.translations.get(locale="ru").meta_title == "Русский SEO"


def test_auto_apply_existing_approved_log_reapplies_saved_medicine_seo():
    medicine = MedicineProduct.objects.create(
        name="ALEREX 20 MG 20 TABLET",
        slug="alerex-20-mg-20-tablet",
        description="Raw description",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.APPROVED,
        input_data={},
        generated_title="ALEREX 20 мг 20 таблеток",
        generated_description="Русское описание",
        generated_seo_title="Русский SEO",
        generated_seo_description="Русское SEO описание",
        generated_keywords=["биластин"],
        extracted_attributes={
            "seo_translations": {
                "ru": {
                    "generated_title": "ALEREX 20 мг 20 таблеток",
                    "generated_description": "Русское описание",
                    "meta_title": "Русский SEO",
                    "meta_description": "Русское SEO описание",
                    "meta_keywords": ["биластин"],
                },
                "en": {
                    "generated_title": "ALEREX 20 mg 20 tablets",
                    "generated_description": "English description",
                    "meta_title": "English SEO",
                    "meta_description": "English SEO description",
                    "meta_keywords": ["bilastine"],
                },
            }
        },
    )

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    log = generator.process_product(product.id, auto_apply=True)

    medicine.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED
    assert medicine.meta_title == "English SEO"
    assert medicine.meta_description == "English SEO description"
    assert medicine.translations.get(locale="ru").meta_title == "Русский SEO"


def test_apply_existing_empty_log_is_rejected_instead_of_marking_applied():
    medicine = MedicineProduct.objects.create(
        name="EMPTY MEDICINE",
        slug="empty-medicine",
        description="",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="",
        generated_description="",
        generated_seo_title="",
        generated_seo_description="",
        generated_keywords=[],
        extracted_attributes={},
    )

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    log = AIProcessingLog.objects.get(product=product)

    with pytest.raises(ValueError, match="не содержит достаточного результата"):
        generator.apply_log_to_product(
            log,
            allow_approved=True,
            require_content=True,
        )

    medicine.refresh_from_db()
    log.refresh_from_db()
    assert log.status == AIProcessingStatus.COMPLETED
    assert medicine.description == ""
    assert medicine.meta_title == ""


def test_medicine_ru_translation_repair_replaces_untranslated_turkish_fields():
    class FakeLLM:
        def generate_content(self, **_kwargs):
            return {
                "content": {
                    "indications": "Русский перевод показаний к применению.",
                    "usage_instructions": "Русский перевод способа применения.",
                },
                "tokens": {"prompt": 10, "completion": 20, "total": 30},
                "cost_usd": 0.001,
                "processing_time_ms": 123,
            }

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = FakeLLM()
    content = {
        "ru": {
            "generated_description": "Русское описание.",
            "indications": "AUGMENTİN aşağıdaki durumlarda bakteriyel enfeksiyonların tedavisinde kullanılır.",
            "usage_instructions": "Doktorunuzun söylediği şekilde kullanınız ve tabletleri yutunuz.",
        },
        "en": {
            "generated_description": "English description.",
        },
    }

    repaired, repair_result = generator._repair_medicine_ru_translation_content(
        content,
        product_id=1,
    )

    assert repair_result["repaired_fields"] == ["indications", "usage_instructions"]
    assert repaired["ru"]["indications"] == "Русский перевод показаний к применению."
    assert repaired["ru"]["usage_instructions"] == "Русский перевод способа применения."


def test_medicine_ru_translation_allows_official_turkish_acronym():
    generator = ContentGenerator.__new__(ContentGenerator)
    translated = (
        "Если возникнут побочные эффекты, обратитесь к врачу или фармацевту. "
        "Сообщить о реакции также можно в Турецкий центр фармаконадзора TÜFAM. "
        * 8
    )
    english = (
        "If side effects occur, contact your doctor or pharmacist. "
        "You can also report the reaction to the Turkish Pharmacovigilance Center TÜFAM. "
        * 8
    )
    source = "Yan etki bildirimi hakkında resmi hasta bilgilendirme metni. " * 10

    assert generator._looks_untranslated_turkish(translated) is False
    assert paragraph_problems(source, translated, english) == []


def test_medicine_ru_translation_keeps_russian_lab_terms():
    generator = ContentGenerator.__new__(ContentGenerator)
    translated = (
        "Дозировка должна контролироваться в зависимости от клинических переменных "
        "(например, гемоглобин, ферритин и трансферрин). "
        "После нормализации уровня гемоглобина следует продолжать лечение, "
        "контролируя уровень ферритина в сыворотке. "
        "Антианемический препарат принимают натощак."
    )

    assert generator._looks_turkish_transliteration(translated) is False
    assert generator._looks_untranslated_turkish(translated) is False


def test_medicine_ru_translation_repair_catches_cyrillic_turkish_transliteration():
    class FakeLLM:
        def generate_content(self, **_kwargs):
            return {
                "content": {
                    "indications": "Что такое FERRO SANOL DUODENAL и для чего он применяется? Препарат железа применяется при дефиците железа.",
                    "usage_instructions": "Всегда принимайте FERRO SANOL DUODENAL в соответствии с рекомендациями врача.",
                },
                "tokens": {"prompt": 10, "completion": 20, "total": 30},
                "cost_usd": 0.001,
                "processing_time_ms": 123,
            }

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = FakeLLM()
    content = {
        "ru": {
            "generated_description": "Русское описание.",
            "indications": "FERRO SANOL DUODENAL НЕДИР ВЕЧЕ И НЕДИР КУЛЛАНИЛЫР? FERRO SANOL DUODENAL демир йетершизлиинде кулланылан бир демир илачыдыр.",
            "usage_instructions": "FERRO SANOL DUODENAL НАСИЛ КУЛЛАНИЛЫР? Докторунуз тавсие эттиги сыклыкда алыныз.",
        },
        "en": {
            "generated_description": "English description.",
        },
    }

    repaired, repair_result = generator._repair_medicine_ru_translation_content(
        content,
        product_id=1,
    )

    assert repair_result["repaired_fields"] == ["indications", "usage_instructions"]
    assert "НЕДИР" not in repaired["ru"]["indications"]
    assert "НАСИЛ" not in repaired["ru"]["usage_instructions"]
    assert repaired["ru"]["indications"].startswith("Что такое FERRO")


def test_medicine_section_translation_overrides_bad_ru_long_section():
    class FakeLLM:
        def generate_content(self, **_kwargs):
            return {
                "content": {
                    "ru": {"1": "Всегда принимайте препарат так, как рекомендовал врач. " * 20},
                    "en": {"1": "Always take the medicine as instructed by your doctor. " * 20},
                },
                "tokens": {"prompt": 100, "completion": 50, "total": 150},
                "cost_usd": 0.001,
                "processing_time_ms": 123,
            }

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = FakeLLM()
    source_text = "Doktorunuzun söylediği şekilde kullanınız. " * 20
    content = {
        "ru": {
            "usage_instructions": "3. FERRO SANOL DUODENAL НАСИЛ КУЛЛАНИЛИР? Докторунуз тавсие эттиги шеклде алыныз.",
        },
        "en": {
            "usage_instructions": "3. How to use FERRO SANOL DUODENAL?",
        },
    }

    result = generator._translate_medicine_source_sections(
        content,
        {
            "summary": "Этот раздел не должен переводиться отдельным полным переводом." * 100,
            "usage_instructions": source_text,
        },
        product_id=1,
    )

    assert result["translated_fields"] == ["usage_instructions"]
    assert "НАСИЛ" not in content["ru"]["usage_instructions"]
    assert content["ru"]["usage_instructions"].startswith("Всегда принимайте препарат")
    assert content["attributes"]["medicine_translation_quality"]["usage_instructions"]["complete"]
    assert "summary" not in content["attributes"]["medicine_translation_quality"]


def test_medicine_full_translation_discards_short_preview_and_marks_failed_coverage():
    class ShortLLM:
        def generate_content(self, **_kwargs):
            return {
                "content": {
                    "ru": {"indications": "Короткий перевод."},
                    "en": {"indications": "Short translation."},
                },
                "tokens": {"prompt": 10, "completion": 10, "total": 20},
                "cost_usd": 0.001,
                "processing_time_ms": 10,
            }

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = ShortLLM()
    content = {
        "ru": {"indications": "Старый перевод первых 700 символов."},
        "en": {"indications": "Old translation of the first 700 characters."},
    }

    result = generator._translate_medicine_source_sections(
        content,
        {"indications": "Kaynak metin. " * 500},
        product_id=1,
    )

    assert result["failed_fields"] == ["indications"]
    assert "indications" not in content["ru"]
    assert "indications" not in content["en"]
    assert not content["attributes"]["medicine_translation_quality"]["indications"]["complete"]


def test_medicine_translation_retries_only_rejected_paragraph_once():
    source_text = "RINVOQ nemden korunarak 25 derece altında saklanmalıdır. " * 12
    ru_text = "Храните RINVOQ в сухом месте при температуре ниже 25 градусов. " * 12
    en_text = "Store RINVOQ in a dry place below 25 degrees. " * 12

    class MissingEnglishThenRecoveredLLM:
        def __init__(self):
            self.calls = []

        def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            content = (
                {"ru": {"1": ru_text}, "en": {}}
                if len(self.calls) == 1
                else {"ru": {"1": ru_text}, "en": {"1": en_text}}
            )
            return {
                "content": content,
                "tokens": {"prompt": 10, "completion": 10, "total": 20},
                "cost_usd": 0.001,
                "processing_time_ms": 10,
            }

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = MissingEnglishThenRecoveredLLM()
    content = {"ru": {}, "en": {}}

    result = generator._translate_medicine_source_sections(
        content,
        {"storage_conditions": source_text},
        product_id=8299,
    )

    assert len(generator.llm.calls) == 2
    assert result["failed_fields"] == []
    assert result["retried_paragraphs"] == 1
    assert result["translated_fields"] == ["storage_conditions"]
    assert result["tokens"]["total"] == 40
    assert content["ru"]["storage_conditions"] == ru_text.strip()
    assert content["en"]["storage_conditions"] == en_text.strip()
    assert content["attributes"]["medicine_translation_quality"]["storage_conditions"]["complete"] is True


def test_partial_apply_blocks_incomplete_medicine_section_in_both_locales():
    category = Category.objects.create(
        name="Медицина для проверки блокировки",
        slug="medicines-block-incomplete-section",
    )
    medicine = MedicineProduct.objects.create(
        name="TESTMED 10 MG TABLET (20 ADET)",
        slug="testmed-block-incomplete-section",
        description="Старое описание",
        category=category,
    )
    medicine.refresh_from_db()
    medicine.translations.create(
        locale="ru",
        side_effects="Проверенные старые побочные эффекты RU",
    )
    medicine.translations.create(
        locale="en",
        side_effects="Verified old side effects EN",
    )
    log = AIProcessingLog.objects.create(
        product=medicine.base_product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="TESTMED 10 мг, таблетки, 20 шт.",
        generated_description=(
            "Подробное описание препарата содержит форму выпуска действующее вещество "
            "количество единиц способ приема и сведения об упаковке для карточки товара."
        ),
        extracted_attributes={
            "medicine_translation_quality": {
                "side_effects": {
                    "source_length": 1000,
                    "ru_length": 900,
                    "en_length": 920,
                    "complete": False,
                }
            },
            "translations_data": {
                "ru": {"side_effects": "Новый неполный текст RU"},
                "en": {"side_effects": "New incomplete text EN"},
            },
        },
    )
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()

    generator.apply_log_to_product(log)

    log.refresh_from_db()
    assert log.application_status == AIApplicationStatus.PARTIAL
    assert log.application_report["rejected_fields"] == [
        "medicine_translation:side_effects"
    ]
    assert (
        medicine.translations.get(locale="ru").side_effects
        == "Проверенные старые побочные эффекты RU"
    )
    assert (
        medicine.translations.get(locale="en").side_effects
        == "Verified old side effects EN"
    )


def test_apply_log_without_category_sends_turkish_ru_section_to_moderation():
    # До 20.10.2026 лекарство без категории валидатор не проверял, и лог с
    # турецким RU-разделом применялся как APPROVED. Теперь — как у лекарства с
    # категорией: раздел не применяется ни в одном языке, лог остаётся на модерации.
    medicine = MedicineProduct.objects.create(
        name="AUGMENTIN 875 MG/125 MG",
        slug="augmentin-875-mg125-mg",
        description="",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="AUGMENTIN 875 MG/125 MG",
        generated_description="Русское описание",
        generated_seo_title="Русский SEO",
        generated_seo_description="Русское SEO описание",
        generated_keywords=["augmentin"],
        extracted_attributes={
            "seo_translations": {
                "ru": {
                    "generated_title": "AUGMENTIN 875 MG/125 MG",
                    "generated_description": "Русское описание",
                    "meta_title": "Русский SEO",
                    "meta_description": "Русское SEO описание",
                },
                "en": {
                    "generated_title": "AUGMENTIN 875 MG/125 MG",
                    "generated_description": "English description",
                    "meta_title": "English SEO",
                    "meta_description": "English SEO description",
                },
            },
            "translations_data": {
                "ru": {
                    "indications": "AUGMENTİN aşağıdaki durumlarda bakteriyel enfeksiyonların tedavisinde kullanılır.",
                },
                "en": {
                    "indications": "English indications.",
                },
            },
        },
    )

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    log = AIProcessingLog.objects.get(product=product)

    generator.apply_log_to_product(
        log,
        allow_approved=True,
        require_content=True,
    )

    log.refresh_from_db()
    medicine.refresh_from_db()
    assert log.status == AIProcessingStatus.MODERATION
    assert log.application_status == AIApplicationStatus.PARTIAL
    assert "medicine_translation:indications" in log.application_report["rejected_fields"]
    for locale in ("ru", "en"):
        translation = medicine.translations.filter(locale=locale).first()
        assert translation is None or not translation.indications


def test_apply_log_with_cyrillic_turkish_transliteration_blanks_ru_field():
    medicine = MedicineProduct.objects.create(
        name="FERRO SANOL DUODENAL",
        slug="ferro-sanol-duodenal",
        description="",
    )
    medicine.refresh_from_db()
    product = medicine.base_product
    AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="FERRO SANOL DUODENAL",
        generated_description="Русское описание",
        generated_seo_title="Русский SEO",
        generated_seo_description="Русское SEO описание",
        generated_keywords=["ferro"],
        extracted_attributes={
            "seo_translations": {
                "ru": {
                    "generated_title": "FERRO SANOL DUODENAL",
                    "generated_description": "Русское описание",
                    "meta_title": "Русский SEO",
                    "meta_description": "Русское SEO описание",
                }
            },
            "translations_data": {
                "ru": {
                    "indications": "FERRO SANOL DUODENAL НЕДИР ВЕЧЕ И НЕДИР КУЛЛАНИЛЫР? FERRO SANOL DUODENAL демир йетершизлиинде кулланылан бир демир илачыдыр.",
                }
            },
        },
    )

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    log = AIProcessingLog.objects.get(product=product)

    # Контракт с c439591: лог применяется, кириллизированная турецкая
    # транслитерация в RU-полях заменяется пустой строкой
    generator.apply_log_to_product(
        log,
        allow_approved=True,
        require_content=True,
    )

    log.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED
    ru = medicine.translations.get(locale="ru")
    assert ru.indications == ""


def _accessory_log(product, **overrides):
    data = {
        "product": product,
        "processing_type": "full",
        "status": AIProcessingStatus.COMPLETED,
        "input_data": {},
        "generated_title": "Новый ремень MODEL-202",
        "generated_description": " ".join(["Подробное описание товара"] * 10),
        "generated_seo_title": "SEO заголовок ремня",
        "generated_seo_description": "Подробное SEO описание ремня для каталога.",
        "generated_keywords": ["ремень"],
        "extracted_attributes": {
            "seo_translations": {
                "ru": {
                    "generated_title": "Новый ремень MODEL-202",
                    "generated_description": "AI описание RU",
                    "meta_title": "AI SEO RU",
                },
                "en": {
                    "generated_title": "New belt MODEL-202",
                    "generated_description": "AI description EN",
                    "meta_title": "AI SEO EN",
                },
            }
        },
    }
    data.update(overrides)
    return AIProcessingLog.objects.create(**data)


def _generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    return generator


def test_ai_does_not_move_product_out_of_assigned_category_and_sends_log_to_moderation():
    from apps.ai.models import AIModerationQueue

    root = Category.objects.create(name="Медицина", slug="ai-guard-medicines-root")
    child = Category.objects.create(name="Анальгетики", slug="ai-guard-analgesics", parent=root)
    accessory = AccessoryProduct.objects.create(
        name="Ремень MODEL-202", slug="ai-guard-category-kept", category=child
    )
    accessory.refresh_from_db()
    product = accessory.base_product
    other = Category.objects.create(name="Витамины", slug="ai-guard-vitamins", parent=root)
    log = _accessory_log(product, suggested_category=other, category_confidence=0.95)

    _generator().apply_log_to_product(log)

    accessory.refresh_from_db()
    product.refresh_from_db()
    log.refresh_from_db()
    assert accessory.category_id == child.id
    assert product.category_id == child.id
    assert log.status == AIProcessingStatus.MODERATION
    assert "category_change_suggested" in log.application_report["semantic_reasons"]
    assert AIModerationQueue.objects.get(log_entry=log).resolved_at is None


def test_ai_fills_category_only_when_product_has_none():
    category = Category.objects.create(name="Ремни", slug="ai-guard-belts")
    accessory = AccessoryProduct.objects.create(name="Ремень MODEL-202", slug="ai-guard-category-empty")
    accessory.refresh_from_db()
    product = accessory.base_product
    assert product.category_id is None

    AIResultApplier().apply_to_product(
        product, {"suggested_category": category, "category_confidence": 0.9}
    )

    accessory.refresh_from_db()
    product.refresh_from_db()
    assert accessory.category_id == category.id
    assert product.category_id == category.id


def test_medicine_prompt_and_fallback_do_not_suggest_root_medicines_category():
    name = "MAJEZIK 100 MG 15 FILM TABLET"
    product = MedicineProduct.objects.create(name=name, slug="majezik-prompt-no-root-category").base_product
    generator = ContentGenerator.__new__(ContentGenerator)
    generator._collect_input_data = lambda _product: {"name": name}
    generator._get_prompt_template = lambda *_args, **_kwargs: ""

    prompt = generator._construct_medicine_user_prompt(product, {}, "full")
    fallback = generator._build_medicine_fallback_content({"name": name})

    assert '"medicines"' not in prompt
    assert "0.95" not in prompt
    assert "suggested_category_slug" not in fallback
    assert "category_confidence" not in fallback


def test_ai_title_changes_name_but_keeps_existing_slug():
    medicine = MedicineProduct.objects.create(
        name="MAJEZIK 100 MG 15 FILM TABLET",
        slug="majezik-100-mg-15-film-tablet",
    )
    medicine.refresh_from_db()
    product = medicine.base_product

    AIResultApplier().apply_to_product(
        product, {"generated_title": "Маджезик 100 мг, 15 таблеток, покрытых оболочкой"}
    )

    medicine.refresh_from_db()
    product.refresh_from_db()
    assert medicine.name == "Маджезик 100 мг, 15 таблеток, покрытых оболочкой"
    assert medicine.slug == "majezik-100-mg-15-film-tablet"
    assert product.slug == "majezik-100-mg-15-film-tablet"


def test_dynamic_attribute_keeps_manual_translation_when_ai_omits_it():
    key, _ = GlobalAttributeKey.objects.get_or_create(slug="material", defaults={"sort_order": 17})
    accessory = AccessoryProduct.objects.create(name="Ремень", slug="ai-guard-keep-value-en")
    accessory.refresh_from_db()
    accessory.dynamic_attributes.create(
        attribute_key=key,
        value="Кожа с тиснением",
        value_ru="Кожа с тиснением",
        value_en="Embossed leather",
        sort_order=key.sort_order,
    )

    AIResultApplier().apply_to_product(
        accessory.base_product,
        {"extracted_attributes": {"dynamic_attributes": [{"slug": "material", "value": "Кожа с тиснением под рептилию"}]}},
    )

    value = accessory.dynamic_attributes.get(attribute_key=key)
    assert value.value_ru == "Кожа с тиснением под рептилию"
    assert value.value_en == "Embossed leather"


def test_apply_keeps_content_edited_after_generation_and_overwrites_untouched():
    from apps.ai.services.result_applier import build_content_snapshot

    accessory = AccessoryProduct.objects.create(
        name="Ремень MODEL-202",
        slug="ai-guard-manual-edits",
        description="Спарсенное описание",
        meta_title="Спарсенный SEO",
    )
    accessory.refresh_from_db()
    accessory.translations.create(locale="ru", name="Ремень", description="Спарсенное RU")
    accessory.translations.create(locale="en", name="Belt", description="Scraped EN")
    product = accessory.base_product
    # Снимок на момент генерации; потом менеджер правит описание и RU-перевод.
    log = _accessory_log(product, input_data={"content_snapshot": build_content_snapshot(accessory)})
    accessory.description = "Ручное описание"
    accessory.save()
    accessory.translations.filter(locale="ru").update(description="Ручное RU")

    _generator()._apply_changes_to_product(product, log)

    accessory.refresh_from_db()
    ru = accessory.translations.get(locale="ru")
    en = accessory.translations.get(locale="en")
    assert accessory.description == "Ручное описание"
    assert ru.description == "Ручное RU"
    # Не менявшиеся после генерации и пустые поля AI перезаписывает.
    assert accessory.meta_title == "AI SEO EN"
    assert en.description == "AI description EN"
    assert ru.meta_title == "AI SEO RU"


def test_processing_stores_content_snapshot_in_input_data():
    accessory = AccessoryProduct.objects.create(
        name="Ремень", slug="ai-guard-snapshot-stored", description="Спарсенное описание"
    )
    accessory.refresh_from_db()
    product = accessory.base_product
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = type("LLM", (), {"model": "test"})()
    generator._collect_input_data = lambda _product: {"name": _product.name}
    generator._should_use_images_for_product = lambda _product: False
    log = AIProcessingLog.objects.create(
        product=product, processing_type="image_analysis", status=AIProcessingStatus.PENDING, input_data={}
    )

    generator.process_product(
        product.id,
        processing_type="image_analysis",
        options=None,
        log_entry_id=log.id,
    )

    log.refresh_from_db()
    assert log.input_data["content_snapshot"]["fields"]["description"]
