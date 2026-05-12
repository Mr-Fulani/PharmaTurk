import pytest

from apps.ai.models import AIProcessingLog
from apps.ai.models import AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.result_applier import AIResultApplier
from apps.catalog.models import MedicineProduct


pytestmark = pytest.mark.django_db


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
    assert "LASİRİN nedir ve ne için kullanılır" in prompt
    assert "DUPLICATED DESCRIPTION SHOULD NOT BE SENT" not in prompt
    assert "DUPLICATED RAW SHOULD NOT BE SENT" not in prompt
    assert "переводи полностью" in prompt
    assert "Не сокращай до 1-2 строк" in prompt


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
                    "text": "3. Как применять FERRO SANOL DUODENAL?\nВсегда принимайте препарат так, как рекомендовал врач. Дозу следует подбирать по клиническим показателям."
                },
                "tokens": {"prompt": 100, "completion": 50, "total": 150},
                "cost_usd": 0.001,
                "processing_time_ms": 123,
            }

    generator = ContentGenerator.__new__(ContentGenerator)
    generator.llm = FakeLLM()
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
            "usage_instructions": "3. FERRO SANOL DUODENAL NASIL KULLANILIR? Doktorunuz tavsiye ettiği şekilde alınız.",
        },
        product_id=1,
    )

    assert result["translated_fields"] == ["usage_instructions"]
    assert "НАСИЛ" not in content["ru"]["usage_instructions"]
    assert content["ru"]["usage_instructions"].startswith("3. Как применять")


def test_apply_log_with_turkish_ru_sections_is_rejected():
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

    with pytest.raises(ValueError, match="не содержит достаточного результата"):
        generator.apply_log_to_product(
            log,
            allow_approved=True,
            require_content=True,
        )

    log.refresh_from_db()
    medicine.refresh_from_db()
    assert log.status == AIProcessingStatus.COMPLETED
    assert medicine.translations.count() == 0


def test_apply_log_with_cyrillic_turkish_transliteration_is_rejected():
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

    with pytest.raises(ValueError, match="не содержит достаточного результата"):
        generator.apply_log_to_product(
            log,
            allow_approved=True,
            require_content=True,
        )

    assert medicine.translations.count() == 0
