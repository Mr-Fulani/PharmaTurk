import pytest

from apps.ai.models import (
    AIApplicationStatus,
    AIModerationQueue,
    AIProcessingLog,
    AIProcessingStatus,
)
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.category_policy import build_category_policy
from apps.catalog.models import (
    Category,
    CategoryTranslation,
    FurnitureProduct,
    FurnitureProductTranslation,
    IslamicClothingProduct,
    MedicineProduct,
)
from apps.catalog.product_semantics import looks_untranslated_turkish


pytestmark = pytest.mark.django_db


def test_category_policy_uses_catalog_data_for_arbitrary_category():
    category = Category.objects.create(
        name="Тормозные колодки",
        slug="brake-pads",
        external_data={
            "semantic_policy": {
                "canonical_product_kind": "vehicle-brake-pad",
                "aliases": {"ru": ["колодки тормозные"], "en": ["brake pad"]},
            }
        },
    )

    policy = build_category_policy(category, "auto-parts")

    assert policy.canonical_product_kind == "vehicle-brake-pad"
    assert "колодки тормозные" in policy.aliases["ru"]
    assert "brake pad" in policy.aliases["en"]
    assert "category" in policy.immutable_fields


def test_validator_uses_longest_category_kind_and_preserves_model_identity():
    category = Category.objects.create(name="Основания кроватей", slug="bed-bases")
    furniture = FurnitureProduct.objects.create(
        name="Основание для кровати TONSTAD/LINDBÅDEN",
        slug="tonstad-lindbaden-base",
        category=category,
    )
    furniture.refresh_from_db()
    validator = SemanticValidator()

    valid = validator.validate(
        furniture.base_product,
        generated_titles={"ru": "Основание кровати TONSTAD/LINDBÅDEN"},
        dynamic_attributes=[],
    )
    wrong_kind = validator.validate(
        furniture.base_product,
        generated_titles={"ru": "Кровать TONSTAD/LINDBÅDEN"},
        dynamic_attributes=[],
    )
    lost_identity = validator.validate(
        furniture.base_product,
        generated_titles={"ru": "Основание кровати серии Норд"},
        dynamic_attributes=[],
    )

    assert "title" not in valid.rejected_fields
    assert "title_category_mismatch" in wrong_kind.reasons
    assert "title_identity_lost" in lost_identity.reasons


def test_validator_is_policy_driven_for_non_furniture_categories():
    perfume = Category.objects.create(
        name="Парфюмерия",
        slug="perfumery-test",
        external_data={"semantic_policy": {"aliases": {"ru": ["парфюм", "духи"]}}},
    )
    Category.objects.create(
        name="Дезодоранты",
        slug="deodorants-test",
        external_data={"semantic_policy": {"aliases": {"ru": ["дезодорант"]}}},
    )
    # A generic Product is sufficient here: the policy comes from its category.
    from apps.catalog.models import Product

    product = Product.objects.create(
        name="PARFUM MODEL-X",
        slug="parfum-model-x",
        product_type="perfumery",
        category=perfume,
    )

    report = SemanticValidator().validate(
        product,
        generated_titles={"ru": "Дезодорант PARFUM MODEL-X"},
        dynamic_attributes=[],
    )

    assert report.canonical_product_kind == "perfumery-test"
    assert report.rejected_fields == {"title"}


def test_burkini_title_is_not_confused_with_swimming_context():
    burkini = Category.objects.create(name="Буркини", slug="burkini")
    CategoryTranslation.objects.create(
        category=burkini,
        locale="en",
        name="Burkinis",
    )
    swimming = Category.objects.create(name="Плавание", slug="swimming")
    CategoryTranslation.objects.create(
        category=swimming,
        locale="en",
        name="Swimming",
    )
    domain = IslamicClothingProduct.objects.create(
        name="Последние буркини из лайкры ниже колена для бассейна",
        slug="burkini-semantic-context",
        category=burkini,
    )
    domain.refresh_from_db()

    report = SemanticValidator().validate(
        domain.base_product,
        generated_titles={
            "ru": "Буркини из лайкры ниже колена для бассейна",
            "en": "Lycra Burkini for Swimming",
        },
        dynamic_attributes=[],
    )

    assert report.rejected_fields == set()
    assert report.reasons == []


def test_medicine_identity_allows_localized_form_but_preserves_brand_dose_and_pack():
    category = Category.objects.create(name="Медицина", slug="medicines")
    electronics = Category.objects.create(name="Электроника", slug="electronics")
    Category.objects.create(name="Планшеты", slug="tablets", parent=electronics)
    Category.objects.create(name="Ноутбуки", slug="laptop", parent=electronics)
    medicine = MedicineProduct.objects.create(
        name="RINVOQ 15 MG UZATILMIS SALIMLI TABLET (28 ADET)",
        slug="rinvoq-medicine-identity",
        category=category,
    )
    medicine.refresh_from_db()
    validator = SemanticValidator()

    valid = validator.validate(
        medicine.base_product,
        generated_titles={
            "ru": "RINVOQ 15 мг, таблетки пролонгированного высвобождения, 28 шт.",
            "en": "RINVOQ 15 MG tablets (28 pieces)",
        },
        dynamic_attributes=[],
    )
    missing_dose = validator.validate(
        medicine.base_product,
        generated_titles={"ru": "RINVOQ, таблетки пролонгированного высвобождения, 28 шт."},
        dynamic_attributes=[],
    )
    wrong_kind = validator.validate(
        medicine.base_product,
        generated_titles={
            "ru": "RINVOQ 15 мг, таблетки пролонгированного высвобождения, 28 шт.",
            "en": "RINVOQ 15 MG laptop (28 pieces)",
        },
        dynamic_attributes=[],
    )

    assert "title" not in valid.rejected_fields
    assert "title_identity_lost" not in valid.reasons
    assert "title" in missing_dose.rejected_fields
    assert "title_identity_lost" in missing_dose.reasons
    assert "title" in wrong_kind.rejected_fields
    assert "title_category_mismatch" in wrong_kind.reasons


def test_medicine_title_substance_and_turkish_percent_are_not_false_mismatches():
    """Партия 8 (25.10.2026): вещество в скобках и «с калием» — не категория БАДов;
    «137 %2.27» — процент относится к 2,27; «D-COLEFOR-1000-IU-…» — бренд без дефиса."""
    category = Category.objects.create(name="Медицина партия 8", slug="medicines-p8")
    Category.objects.create(
        name="Железо",
        slug="iron-p8",
        external_data={"semantic_policy": {"aliases": {"ru": ["железо"], "en": ["iron", "potassium"]}}},
    )
    validator = SemanticValidator()

    def reasons(name, ru, en):
        medicine = MedicineProduct.objects.create(name=name, slug=f"p8-{abs(hash(name))}", category=category)
        medicine.refresh_from_db()
        return validator.validate(
            medicine.base_product, generated_titles={"ru": ru, "en": en}, dynamic_attributes=[]
        ).reasons

    assert reasons(
        "INFERJECT 500 MG/10 ML ИНЪЕКЦИЯ/ИНФУЗИЯ",
        "INFERJECT (железо) 500 мг/10 мл, раствор для инъекций и инфузий",
        "INFERJECT (iron) 500 mg/10 ml, solution for injection/infusion",
    ) == []
    assert reasons(
        "MULTIBIC 2 MMOL/L POTASYUMLU 4500 ML HEMOFILTRASYON SOLUSYONU",
        "MULTIBIC 2 ммоль/л, раствор для гемофильтрации, с калием, 4500 мл",
        "MULTIBIC 2 mmol/l, haemofiltration solution, with potassium, 4500 ml",
    ) == []
    assert reasons(
        "DIANEFROL 137 %2.27 GLUKOZ ICEREN PERITON DIYALIZ COZELTISI 2000 ML. TEKLI TORBA",
        "DIANEFROL 137 2,27%, раствор глюкозы для перитонеального диализа, одинарный пакет, 2000 мл",
        "DIANEFROL 137 2.27%, glucose peritoneal dialysis solution, single bag, 2000 ml",
    ) == []
    assert reasons(
        "D-COLEFOR-1000-IU-YUMUSAK-KAPSUL (100)",
        "D-COLEFOR 1000 МЕ, мягкие капсулы, 100 шт.",
        "D-COLEFOR 1000 IU, soft capsules, 100 pcs",
    ) == []
    # Партия Claude 1047: «анти-Xa» и шприцы — не брак и не категория медтехники «Шприцы».
    Category.objects.create(name="Шприцы", slug="syringes-p8",
                            external_data={"semantic_policy": {"aliases": {"ru": ["шприцы"], "en": ["syringes"]}}})
    assert reasons(
        "CLEXANE 4000 ANTI-XA IU/0,4 ML 10 KULLANIMA HAZIR ENJEKTOR",
        "CLEXANE (эноксапарин) 4000 анти-Xa МЕ/0,4 мл, в предварительно заполненном шприце, 10 шт.",
        "CLEXANE (enoxaparin) 4000 anti-Xa IU/0.4 ml, pre-filled syringe, 10 pcs",
    ) == []
    assert reasons(
        "SIMLANDI 40 MG/0.4 ML ENJEKSIYONLUK COZELTI ICEREN KULLANIMA HAZIR ENJEKTOR (2 ENJEKTOR)",
        "SIMLANDI (адалимумаб) 40 мг/0,4 мл, раствор для инъекций, 2 шприца",
        "SIMLANDI (adalimumab) 40 mg/0.4 ml, solution for injection, 2 syringes",
    ) == []
    # Вещество вне скобок и потерянная дозировка по-прежнему ловятся.
    assert "title_category_mismatch" in reasons(
        "EISEFERON 40 MG/5 ML ORAL COZELTI 10 KASIK",
        "EISEFERON железо 40 мг/5 мл, раствор для приёма внутрь, 10 доз",
        "EISEFERON iron 40 mg/5 ml, oral solution, 10 doses",
    )
    assert "title_identity_lost" in reasons(
        "DIANEFROL 137 %1.36 GLUKOZ ICEREN PERITON DIYALIZ COZELTISI 2000 ML",
        "DIANEFROL 137 2,27%, раствор глюкозы для перитонеального диализа, 2000 мл",
        "DIANEFROL 137 2.27%, glucose peritoneal dialysis solution, 2000 ml",
    )


def test_medicine_translation_quality_and_turkish_ru_fields_require_moderation():
    category = Category.objects.create(name="Медицина quality", slug="medicines-quality")
    medicine = MedicineProduct.objects.create(
        name="TESTMED 10 MG TABLET (20 ADET)",
        slug="medicine-translation-quality",
        category=category,
    )
    medicine.refresh_from_db()
    log = AIProcessingLog.objects.create(
        product=medicine.base_product,
        processing_type="full",
        input_data={},
        generated_title="TESTMED 10 мг, таблетки, 20 шт.",
        extracted_attributes={
            "medicine_translation_quality": {
                "indications": {
                    "source_length": 5000,
                    "ru_length": 400,
                    "en_length": 450,
                    "complete": False,
                }
            },
            "translations_data": {
                "ru": {"special_notes": "Ek izlemeye tabi ilaç!"},
            },
        },
    )

    report = SemanticValidator().validate_log(log)

    assert "incomplete_medicine_translation" in report.reasons
    assert "untranslated_medicine_field" in report.reasons
    assert "medicine_translation:indications" in report.rejected_fields
    assert "medicine_translation:special_notes" in report.rejected_fields


def test_shared_language_validator_preserves_turkish_acronyms_in_russian_text():
    translated = (
        "Сообщите врачу о нежелательной реакции и направьте сведения в TÜFAM. "
        "Дополнительная информация опубликована на сайте TİTCK."
    )
    untranslated = "İlacı çocukların göremeyeceği yerde saklayınız."

    assert looks_untranslated_turkish(translated) is False
    assert looks_untranslated_turkish(untranslated) is True


def test_medicine_semantic_validation_does_not_block_tufam_as_untranslated_text():
    medicine = MedicineProduct.objects.create(
        name="TESTMED 10 MG TABLET",
        slug="medicine-tufam-semantic-validation",
    )
    medicine.refresh_from_db()
    log = AIProcessingLog.objects.create(
        product=medicine.base_product,
        processing_type="full",
        input_data={},
        generated_title="TESTMED 10 мг, таблетки",
        extracted_attributes={
            "translations_data": {
                "ru": {
                    "side_effects": (
                        "При появлении нежелательных реакций сообщите врачу и направьте "
                        "сведения в TÜFAM."
                    )
                },
                "en": {"side_effects": "Report adverse reactions to TÜFAM."},
            }
        },
    )

    report = SemanticValidator().validate_log(log)

    assert "untranslated_medicine_field" not in report.reasons
    assert "medicine_translation:side_effects" not in report.rejected_fields


def test_partial_apply_keeps_rejected_title_but_applies_valid_content_and_moderates():
    category = Category.objects.create(name="Основания кроватей", slug="bed-bases")
    furniture = FurnitureProduct.objects.create(
        name="Основание для кровати TONSTAD/LINDBÅDEN",
        slug="tonstad-lindbaden-original",
        description="Старое описание",
        category=category,
    )
    furniture.refresh_from_db()
    FurnitureProductTranslation.objects.create(
        product=furniture,
        locale="ru",
        name="Основание для кровати TONSTAD/LINDBÅDEN",
        description="Старое описание RU",
    )
    FurnitureProductTranslation.objects.create(
        product=furniture,
        locale="en",
        name="TONSTAD/LINDBÅDEN bed base",
        description="Old EN description",
    )
    log = AIProcessingLog.objects.create(
        product=furniture.base_product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={},
        generated_title="Кровать TONSTAD/LINDBÅDEN",
        generated_description=(
            "Новое корректное описание основания кровати содержит достаточно подробностей "
            "о конструкции материалах размерах совместимости хранении сборке эксплуатации "
            "назначении и уходе за изделием для покупателя интернет магазина."
        ),
        generated_seo_title="Основание TONSTAD/LINDBÅDEN",
        generated_seo_description="Корректное SEO-описание основания кровати.",
        generated_keywords=["основание", "TONSTAD"],
        extracted_attributes={
            "seo_translations": {
                "ru": {
                    "generated_title": "Кровать TONSTAD/LINDBÅDEN",
                    "generated_description": "Новое описание RU",
                    "meta_title": "Основание TONSTAD/LINDBÅDEN",
                },
                "en": {
                    "generated_title": "TONSTAD/LINDBÅDEN bed",
                    "generated_description": "New valid English description",
                    "meta_title": "TONSTAD/LINDBÅDEN bed base",
                },
            }
        },
    )
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()

    generator.apply_log_to_product(log)

    furniture.refresh_from_db()
    furniture.base_product.refresh_from_db()
    log.refresh_from_db()
    assert furniture.name == "Основание для кровати TONSTAD/LINDBÅDEN"
    assert furniture.slug == "tonstad-lindbaden-original"
    assert furniture.base_product.name == furniture.name
    assert furniture.description.startswith("Новое корректное описание")
    assert furniture.meta_title == "TONSTAD/LINDBÅDEN bed base"
    assert furniture.translations.get(locale="ru").name == furniture.name
    assert furniture.translations.get(locale="ru").description == "Новое описание RU"
    assert furniture.translations.get(locale="en").name == "TONSTAD/LINDBÅDEN bed base"
    assert furniture.translations.get(locale="en").description == "New valid English description"
    assert log.status == AIProcessingStatus.MODERATION
    assert log.application_status == AIApplicationStatus.PARTIAL
    moderation_task = AIModerationQueue.objects.get(log_entry=log)
    assert moderation_task.resolved_at is None
