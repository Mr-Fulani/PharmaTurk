import pytest

from apps.ai.models import AIModerationQueue, AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.category_policy import build_category_policy
from apps.catalog.models import Category, FurnitureProduct, FurnitureProductTranslation


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
    assert AIModerationQueue.objects.filter(log_entry=log).exists()
