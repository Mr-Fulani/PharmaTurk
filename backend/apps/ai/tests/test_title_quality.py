"""Регрессии из тестовой партии на проде 2026-10-18."""

from types import SimpleNamespace

import pytest

from apps.ai.models import AIProcessingLog
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import AccessoryProduct, Category, FurnitureProduct, ShoeProduct
from apps.catalog.utils.variant_titles import strip_price_and_codes_from_title


def test_title_keeps_decimal_dosage_but_drops_price():
    generator = ContentGenerator.__new__(ContentGenerator)

    title = generator._normalize_product_name(
        "SALRES 2,5 мг / 2,5 мл раствор для ингаляций, 20 флаконов", "medicines"
    )

    assert title == "SALRES 2,5 мг / 2,5 мл раствор для ингаляций, 20 флаконов"
    assert strip_price_and_codes_from_title("Ремень - 799,00 TL") == "Ремень"
    assert strip_price_and_codes_from_title("Дезодорант 349,00") == "Дезодорант"
    assert strip_price_and_codes_from_title("Крем 0,5 г") == "Крем 0,5 г"


def test_only_book_titles_are_cut_at_subtitle_comma():
    generator = ContentGenerator.__new__(ContentGenerator)

    assert generator._normalize_product_name("ИСЛАМСКИЕ ФИНАНСЫ, концепция", "books") == "ИСЛАМСКИЕ ФИНАНСЫ"
    assert generator._normalize_product_name("Маджезик 100 мг, 15 таблеток", "medicines") == (
        "Маджезик 100 мг, 15 таблеток"
    )


def _log_for(domain_model, category, title, **extra):
    domain = domain_model.objects.create(name="Source", slug=f"title-quality-{category.slug}", category=category)
    domain.refresh_from_db()
    return AIProcessingLog.objects.create(
        product=domain.base_product,
        processing_type="full",
        input_data={},
        generated_title=title,
        **extra,
    )


@pytest.mark.django_db
def test_turkish_words_in_ru_title_block_the_title():
    category = Category.objects.create(name="Сандалии", slug="title-quality-sandals")
    log = _log_for(ShoeProduct, category, "Эркек Ортофедические Сандалии из Натуральной Кожи")

    report = SemanticValidator().validate_log(log)

    assert "title" in report.rejected_fields
    assert "title_untranslated" in report.reasons


@pytest.mark.django_db
def test_dresser_called_wardrobe_is_a_category_mismatch():
    Category.objects.create(name="Шкафы", slug="wardrobes")
    dressers = Category.objects.create(name="Комоды", slug="dressers")
    log = _log_for(FurnitureProduct, dressers, "Шифоньер HAUGA")

    report = SemanticValidator().validate_log(log)

    assert "title_category_mismatch" in report.reasons


@pytest.mark.django_db
def test_suggesting_parent_category_is_not_sent_to_moderation():
    root = Category.objects.create(name="Аксессуары", slug="title-quality-accessories")
    belts = Category.objects.create(name="Ремни", slug="title-quality-belts", parent=root)
    other = Category.objects.create(name="Сумки", slug="title-quality-bags", parent=root)
    log = _log_for(AccessoryProduct, belts, "Кожаный ремень", suggested_category=root, category_confidence=1.0)

    assert "category_change_suggested" not in SemanticValidator().validate_log(log).reasons

    log.suggested_category = other
    assert "category_change_suggested" in SemanticValidator().validate_log(log).reasons


def test_brand_with_turkish_letters_alone_is_not_flagged():
    from apps.ai.services.semantic_validator import _title_has_turkish_words

    assert not _title_has_turkish_words("Футболка LC Waikiki")
    assert not _title_has_turkish_words(SimpleNamespace() and "Кольцо из серебра с ониксом")


@pytest.mark.django_db
def test_supplement_title_keeps_brand_and_pack_but_may_translate_turkish_words():
    from apps.catalog.models import Product

    category = Category.objects.create(name="БАДы", slug="title-quality-supplements")
    product = Product.objects.create(
        name="SOLGAR VITAMIN D3 YUMUSAK JELATIN KAPSUL 1000 IU 100 kapsül",
        slug="title-quality-solgar",
        product_type="supplements",
        category=category,
    )

    def reasons(title):
        log = AIProcessingLog.objects.create(product=product, processing_type="full", input_data={}, generated_title=title)
        return SemanticValidator().validate_log(log).reasons

    assert "title_identity_lost" not in reasons("Витамин D3 Solgar 1000 МЕ, 100 мягких желатиновых капсул")
    assert "title_identity_lost" in reasons("Витамин D3 1000 МЕ, 100 капсул")  # пропал бренд
    assert "title_identity_lost" in reasons("Витамин D3 Solgar, 60 капсул")  # другая фасовка


def test_attributes_without_spec_for_product_type_are_dropped_before_moderation():
    generator = ContentGenerator.__new__(ContentGenerator)
    rows = [
        {"slug": "administration_route", "value": "перорально", "value_ru": "перорально", "value_en": "oral"},
        {"slug": "sgk_status", "value": "не оплачивается", "value_ru": "не оплачивается", "value_en": "not covered"},
    ]

    kept = generator._apply_confidence_gate_to_dynamic_attributes(
        rows,
        {"product_type": "supplements", "description": "перорально, не оплачивается", "available_dynamic_attributes": []},
    )

    assert kept == []
