from types import SimpleNamespace

import pytest

from apps.ai.admin import AIProcessingLogForm
from apps.ai.models import AIApplicationStatus, AIProcessingLog, AIProcessingStatus
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.moderation import build_change_preview
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.semantic_validator import SemanticValidator, _identity_tokens
from apps.ai.services.size_inventory import extract_sizes_from_input, merge_confirmed_sizes
from apps.catalog.models import (
    AccessoryProduct,
    Category,
    ClothingProduct,
    HeadwearProduct,
    IslamicClothingProduct,
    IslamicClothingProductSize,
    IslamicClothingVariant,
    ShoeProduct,
    UnderwearProduct,
)


pytestmark = pytest.mark.django_db


RAW_BURKINI = (
    "Удобные, практичные буркини для бассейна от Adasea в наличии. "
    "Остались последние размеры m, xl, 2xl. Стоимость 3950"
)


def _generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.result_applier = AIResultApplier()
    return generator


def _size_log(product, **overrides):
    data = {
        "product": product,
        "processing_type": "full",
        "status": AIProcessingStatus.COMPLETED,
        "input_data": {
            "product_type": "islamic_clothing",
            "raw_description": RAW_BURKINI,
        },
        "generated_title": "Буркини Adasea",
        "generated_description": (
            "Практичный буркини Adasea подходит для плавания в бассейне. "
            "В наличии размеры M, XL и 2XL. Модель обеспечивает комфорт и свободу движений."
        ),
        "generated_seo_title": "Буркини Adasea для бассейна",
        "generated_seo_description": (
            "Буркини Adasea для бассейна. Доступны размеры M, XL и 2XL."
        ),
        "generated_keywords": ["буркини", "Adasea"],
        "extracted_attributes": {
            "seo_translations": {
                "ru": {
                    "generated_title": "Буркини Adasea",
                    "generated_description": (
                        "Практичный буркини Adasea для бассейна. "
                        "В наличии размеры M, XL и 2XL."
                    ),
                    "meta_title": "Буркини Adasea",
                    "meta_description": "Доступны размеры M, XL и 2XL. Буркини для бассейна.",
                },
                "en": {
                    "generated_title": "Adasea burkini",
                    "generated_description": (
                        "A practical Adasea burkini for swimming. "
                        "Available in sizes M, XL and 2XL."
                    ),
                    "meta_title": "Adasea burkini",
                    "meta_description": "Available in sizes M, XL and 2XL. Pool burkini.",
                },
            }
        },
    }
    data.update(overrides)
    return AIProcessingLog.objects.create(**data)


def test_extracts_burkini_sizes_but_not_price():
    rows = extract_sizes_from_input(
        {"raw_description": RAW_BURKINI},
        "islamic_clothing",
    )

    assert [row["size"] for row in rows] == ["M", "XL", "2XL"]
    assert all(row["availability_explicit"] for row in rows)
    assert "3950" not in {row["size"] for row in rows}


def test_source_price_is_not_misreported_as_lost_model_identity():
    tokens = _identity_tokens(
        "Удобные буркини Adasea. Остались размеры M, XL, 2XL. Стоимость 3950"
    )

    assert "3950" not in tokens
    assert "2XL" not in tokens


def test_full_content_sanitizer_moves_sizes_to_attributes_and_removes_prose():
    content = {
        "ru": {
            "generated_title": "Буркини Adasea",
            "generated_description": "Удобный буркини. В наличии размеры M, XL и 2XL.",
            "seo_description": "Доступны размеры M, XL и 2XL. Для бассейна.",
            "og_description": "Остались размеры M, XL, 2XL. Буркини Adasea.",
        },
        "en": {
            "generated_title": "Adasea burkini",
            "generated_description": "Comfortable burkini. Available in sizes M, XL and 2XL.",
            "seo_description": "Available in sizes M and XL. Made for swimming.",
        },
        "attributes": {
            "sizes": [{"size": "4XL"}],  # Not present in source: must be rejected.
        },
    }

    sanitized = _generator()._sanitize_ai_content(
        content,
        {
            "product_type": "islamic_clothing",
            "raw_description": RAW_BURKINI,
        },
    )

    assert [row["size"] for row in sanitized["attributes"]["sizes"]] == ["M", "XL", "2XL"]
    assert "размер" not in sanitized["ru"]["generated_description"].lower()
    assert "sizes" not in sanitized["en"]["generated_description"].lower()
    assert sanitized["ru"]["seo_description"] == "Для бассейна."
    assert sanitized["ru"]["og_description"] == "Буркини Adasea."


def test_moderator_can_replace_or_clear_source_sizes_but_llm_cannot_forge_override():
    source = {"product_type": "islamic_clothing", "raw_description": RAW_BURKINI}
    attributes = {
        "sizes": [{"size": "4XL", "source": "moderator", "confidence": "invalid"}],
        "moderator_sizes": [{"size": "3XL", "source": "moderator"}],
    }

    llm_result = merge_confirmed_sizes(attributes, source, "islamic_clothing")
    moderator_result = merge_confirmed_sizes(
        attributes,
        source,
        "islamic_clothing",
        allow_moderator_override=True,
    )
    cleared_result = merge_confirmed_sizes(
        {"moderator_sizes": []},
        source,
        "islamic_clothing",
        allow_moderator_override=True,
    )

    assert [row["size"] for row in llm_result["sizes"]] == ["M", "XL", "2XL"]
    assert "moderator_sizes" not in llm_result
    assert [row["size"] for row in moderator_result["sizes"]] == ["3XL"]
    assert cleared_result["sizes"] == []


@pytest.mark.parametrize(
    "model,product_type,size_values",
    (
        (ClothingProduct, "clothing", ["S", "M"]),
        (ShoeProduct, "shoes", ["38", "40"]),
        (HeadwearProduct, "headwear", ["54", "56"]),
        (UnderwearProduct, "underwear", ["M", "L"]),
        (IslamicClothingProduct, "islamic_clothing", ["M", "2XL"]),
    ),
)
def test_applier_uses_only_supported_product_size_tables(model, product_type, size_values):
    domain = model.objects.create(
        name=f"Size inventory {product_type}",
        slug=f"size-inventory-{product_type}",
    )
    domain.refresh_from_db()
    rows = [
        {
            "size": size,
            "is_available": True,
            "availability_explicit": True,
            "source": "moderator",
        }
        for size in size_values
    ]

    AIResultApplier().apply_to_product(
        domain.base_product,
        {"extracted_attributes": {"sizes": rows}},
    )

    assert list(domain.sizes.order_by("sort_order").values_list("size", flat=True)) == size_values


def test_repeated_apply_is_idempotent_preserves_stock_and_unmentioned_sizes():
    domain = IslamicClothingProduct.objects.create(
        name="Burkini inventory",
        slug="burkini-size-idempotency",
    )
    domain.refresh_from_db()
    existing_xxl = IslamicClothingProductSize.objects.create(
        product=domain,
        size="XXL",
        is_available=False,
        stock_quantity=7,
        sort_order=1,
    )
    IslamicClothingProductSize.objects.create(
        product=domain,
        size="S",
        is_available=True,
        stock_quantity=3,
        sort_order=2,
    )
    payload = {
        "extracted_attributes": {
            "sizes": [
                {
                    "size": "2XL",
                    "is_available": True,
                    "availability_explicit": True,
                    "source": "moderator",
                },
                {
                    "size": "M",
                    "is_available": True,
                    "availability_explicit": True,
                    "source": "moderator",
                },
            ]
        }
    }

    applier = AIResultApplier()
    applier.apply_to_product(domain.base_product, payload)
    applier.apply_to_product(domain.base_product, payload)

    existing_xxl.refresh_from_db()
    assert domain.sizes.count() == 3
    assert existing_xxl.stock_quantity == 7
    assert existing_xxl.is_available is True
    assert set(domain.sizes.values_list("size", flat=True)) == {"XXL", "S", "M"}


def test_legacy_burkini_log_applies_clean_title_text_and_sizes_in_one_action():
    category = Category.objects.create(
        name="Буркини",
        slug="burkini-size-inventory-test",
        external_data={
            "semantic_policy": {
                "aliases": {"ru": ["буркини"], "en": ["burkini"]},
            }
        },
    )
    domain = IslamicClothingProduct.objects.create(
        name=RAW_BURKINI,
        slug="legacy-burkini-one-action",
        description=RAW_BURKINI,
        category=category,
    )
    domain.refresh_from_db()
    log = _size_log(domain.base_product)

    _generator().apply_log_to_product(log)

    domain.refresh_from_db()
    log.refresh_from_db()
    assert log.status == AIProcessingStatus.APPROVED
    assert log.application_status == AIApplicationStatus.APPLIED
    assert domain.name == "Буркини Adasea"
    assert "размер" not in domain.description.lower()
    assert list(domain.sizes.order_by("sort_order").values_list("size", flat=True)) == [
        "M",
        "XL",
        "2XL",
    ]


def test_product_with_variants_requires_moderation_and_does_not_guess_variant():
    domain = IslamicClothingProduct.objects.create(
        name="Adasea MODEL-560",
        slug="burkini-variant-size-guard",
    )
    domain.refresh_from_db()
    variant = IslamicClothingVariant.objects.create(
        product=domain,
        name="Blue MODEL-560",
        slug="burkini-blue-model-560",
        color="blue",
    )
    log = _size_log(domain.base_product, generated_title="Adasea MODEL-560")

    report = SemanticValidator().validate_log(log)
    _generator().apply_log_to_product(log)

    log.refresh_from_db()
    assert report.rejected_fields == {"sizes"}
    assert report.reasons == ["ambiguous_variant_sizes"]
    assert domain.sizes.count() == 0
    assert variant.sizes.count() == 0
    assert log.status == AIProcessingStatus.MODERATION
    assert log.application_status == AIApplicationStatus.PARTIAL
    assert log.application_report["rejected_fields"] == ["sizes"]


def test_legacy_log_preview_and_form_show_clean_prose_and_structured_sizes():
    domain = IslamicClothingProduct.objects.create(
        name="Adasea MODEL-560",
        slug="burkini-legacy-log-preview",
    )
    domain.refresh_from_db()
    log = _size_log(domain.base_product, generated_title="Adasea MODEL-560")

    form = AIProcessingLogForm(instance=log)
    rows = build_change_preview(log)

    assert "inventory_sizes" in form.fields
    assert form.fields["inventory_sizes"].initial == "M, XL, 2XL"
    assert "размер" not in form.initial["generated_description"].lower()
    size_row = next(row for row in rows if row.label == "Доступные размеры")
    assert size_row.proposed == "M, XL, 2XL"
    assert size_row.decision == "apply"
    ru_description = next(
        row for row in rows if row.section == "Контент RU" and row.label == "Описание"
    )
    assert "размер" not in ru_description.proposed.lower()


def test_unrelated_category_is_unchanged_and_has_no_size_form_field():
    accessory = AccessoryProduct.objects.create(
        name="Чехол размер M",
        slug="unrelated-size-guard",
        description="Размер M указан для упаковки аксессуара.",
    )
    accessory.refresh_from_db()
    log = AIProcessingLog.objects.create(
        product=accessory.base_product,
        processing_type="full",
        status=AIProcessingStatus.COMPLETED,
        input_data={"product_type": "accessories", "raw_description": "Размер M"},
        generated_description="Размер M указан для упаковки аксессуара.",
    )
    content = {
        "ru": {"generated_description": "Размер M указан для упаковки аксессуара."},
        "attributes": {"sizes": [{"size": "M"}]},
    }

    sanitized = _generator()._sanitize_ai_content(content, log.input_data)
    form = AIProcessingLogForm(instance=log)

    assert sanitized["ru"]["generated_description"] == "Размер M указан для упаковки аксессуара."
    assert "sizes" not in sanitized["attributes"]
    assert "inventory_sizes" not in form.fields


def test_prompt_declares_structured_size_contract(monkeypatch):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    monkeypatch.setattr(
        generator,
        "_collect_input_data",
        lambda _product: {
            "name": "Adasea burkini",
            "product_type": "islamic_clothing",
            "description": RAW_BURKINI,
            "brand": "Adasea",
            "category_context": {},
            "detected_sizes": extract_sizes_from_input(
                {"raw_description": RAW_BURKINI}, "islamic_clothing"
            ),
        },
    )

    prompt = generator._construct_user_prompt(SimpleNamespace(category=None), {}, "full")

    assert '"product_type": "islamic_clothing"' in prompt
    assert '"detected_sizes"' in prompt
    assert '"sizes": [' in prompt
    assert "ТОЛЬКО в attributes.sizes" in prompt
    assert "не повторяй их в title, generated_description, SEO или OG" in prompt
