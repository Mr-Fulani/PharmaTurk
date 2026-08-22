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
