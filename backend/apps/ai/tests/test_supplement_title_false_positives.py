"""Ложные срабатывания проверки названий БАДов (контрольная партия 7072–7081)."""

import pytest

from apps.ai.models import AIProcessingLog
from apps.ai.services.semantic_validator import SemanticValidator
from apps.catalog.models import Category, Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    electronics = Category.objects.create(name="Электроника", slug="electronics")
    tablets = Category.objects.create(name="Планшеты", slug="tablets", parent=electronics)
    tablets.translations.create(locale="en", name="Tablets")
    auto = Category.objects.create(name="Автозапчасти", slug="auto-parts")
    suspension = Category.objects.create(name="Подвеска", slug="suspension", parent=auto)
    suspension.translations.create(locale="en", name="Suspension")
    services = Category.objects.create(name="Услуги", slug="uslugi")
    cooktop = Category.objects.create(name="Варочные панели", slug="svc-cooktop", parent=services)
    gas = Category.objects.create(name="Газовая", slug="svc-gas-cooktop", parent=cooktop)
    gas.translations.create(locale="en", name="Gas")
    return Category.objects.create(name="БАДы", slug="supplements")


def _reasons(category, source_name, ru_title, en_title):
    product = Product.objects.create(
        name=source_name,
        slug=f"fp-{abs(hash(source_name))}",
        product_type="supplements",
        category=category,
    )
    log = AIProcessingLog.objects.create(
        product=product,
        processing_type="full",
        input_data={},
        generated_title=ru_title,
        extracted_attributes={"seo_translations": {"en": {"generated_title": en_title}}},
    )
    return SemanticValidator().validate_log(log).reasons


@pytest.mark.parametrize(
    "source_name, ru_title, en_title",
    [
        ("HAVER MELATONIN 3 MG 60 TABLET", "Мелатонин HAVER 3 мг, 60 таблеток", "HAVER Melatonin Tablets 3 mg 60 tablets"),
        ("HAVER MULTIVITAMIN 60 CIGNEME TABLETI", "Мультивитамины HAVER, 60 жевательных таблеток", "HAVER Multivitamin 60 Chewable Tablets"),
        ("AKKORA SUSPANSIYON 300 ML", "Суспензия AKKORA 300 мл", "AKKORA SUSPENSION 300 ml"),
        ("METEOKIDS GAZ GIDERICI DAMLA 20 ML", "Капли от газов METEOKIDS 20 мл", "METEOKIDS GAS RELIEF DROPS 20 ml"),
    ],
)
def test_dosage_forms_and_service_aliases_are_not_category_conflicts(catalog, source_name, ru_title, en_title):
    assert "title_category_mismatch" not in _reasons(catalog, source_name, ru_title, en_title)


@pytest.mark.parametrize(
    "source_name, ru_title",
    [
        ("AKKORA SUSPANSIYON 300 ML", "AKKORA SUSPANSIYON 300 мл"),
        ("METEOKIDS GAZ GIDERICI DAMLA 20 ML", "METEOKIDS ГАЗ ГИДЕРИЧИ ДАМЛА 20 мл"),
    ],
)
def test_untranslated_turkish_in_ru_title_is_blocked(catalog, source_name, ru_title):
    assert "title_untranslated" in _reasons(catalog, source_name, ru_title, "Translated title")


def test_russian_words_and_brands_are_not_flagged(catalog):
    reasons = _reasons(catalog, "SOLGAR SASE 30", "Solgar, 30 саше по 5 г", "Solgar, 30 sachets")
    assert "title_untranslated" not in reasons
