"""Очередь модерации 01.11.2026, круг 4: не медицинские причины.

Примеры — логи прода (номер в комментарии). Рядом — настоящие ошибки из той же
очереди: проверки должны их ловить и дальше.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.ai.models import AITranslationMemory
from apps.ai.services import supplement_content
from apps.ai.services.content_generator import ContentGenerator
from apps.ai.services.quality_checker import get_moderation_reasons
from apps.ai.services.result_applier import AIResultApplier
from apps.ai.services.rules import vocab
from apps.ai.services.rules.facts import clean_source_text, drop_codes, is_supplier_code
from apps.ai.services.semantic_validator import SemanticValidator
from apps.ai.services.size_inventory import (
    extract_sizes_from_input,
    merge_confirmed_sizes,
    strip_size_inventory_sentences,
)
from apps.catalog.models import Brand, Category, ClothingProduct, Product
from apps.catalog.utils.variant_titles import strip_price_and_codes_from_title


def _sizes(input_data, product_type="shoes"):
    return [row["size"] for row in extract_sizes_from_input(input_data, product_type)]


# --- размеры ---


@pytest.mark.parametrize(
    "product_type, description, parser_sizes",
    [
        # 29605: турецкое «size» — это «вам», «m» из «mükemmel» принималось за размер.
        ("shoes", "Rahat bir görünüm arıyorsanız, GRAFF 5FX tam size göre.", ["40", "41", "42"]),
        ("shoes", "günlük yaşamda size mükemmel bir uyum sunar.", ["36", "37,5", "38,5"]),
        # 30600: размер модели — не размер в продаже.
        ("clothing", "Boy: 190 cm Göğüs: 100 cm Modelin giydiği beden: M", ["L", "XL"]),
        # 30648: вес футболки и размер, на котором он измерен.
        ("clothing", "Ağırlık: 130 gr (M beden) Modelimiz 185 cm boyunda ve M beden giymektedir.", ["S"]),
    ],
)
def test_parser_size_list_beats_free_text(product_type, description, parser_sizes):
    data = {"description": description, "attributes": {"sizes": parser_sizes}}
    assert _sizes(data, product_type) == parser_sizes


def test_model_cannot_add_size_outside_parser_list():
    data = {"description": "tam size göre", "attributes": {"sizes": ["40", "41"]}}
    merged = merge_confirmed_sizes({"sizes": [{"size": "M"}, {"size": "40"}]}, data, "shoes")
    assert [row["size"] for row in merged["sizes"]] == ["40", "41"]


def test_turkish_word_is_not_a_size_without_parser_list():
    assert _sizes({"description": "günlük yaşamda size mükemmel bir uyum sunar."}) == []


def test_sizes_in_text_still_work_without_parser_list():
    assert _sizes({"description": "Bedenler: M, L, XL"}, "clothing") == ["M", "L", "XL"]


# --- чистка размеров в описании ---


def test_size_sentence_does_not_take_previous_paragraph_with_it():
    # Лог 29728 (FORELLI): без пробела между </p><p> терялись материалы и закрывающий тег.
    text = (
        "<p>Подошва выполнена из полиуретана. Внутренний и внешний материал — кожа и текстиль.</p>"
        "<p>Колодка полная, размер большой: рекомендуется брать на 1 номер меньше обычного.</p>"
    )
    assert strip_size_inventory_sentences(text) == (
        "<p>Подошва выполнена из полиуретана. Внутренний и внешний материал — кожа и текстиль.</p>"
    )


def test_paragraphs_without_sizes_stay_byte_for_byte():
    text = "<p>Первый абзац о кроссовках.</p><p>Второй абзац о подошве.</p>"
    assert strip_size_inventory_sentences(text) == text


def test_size_sentence_at_paragraph_end_keeps_closing_tag():
    # Лог 30648 (Jack Wolfskin).
    text = "<p>Футболка из хлопка. Мягкая и удобная. Вес 130 г (размер M). Длина в размере L — 74 см.</p>"
    assert strip_size_inventory_sentences(text) == "<p>Футболка из хлопка. Мягкая и удобная.</p>"


# --- короткие описания: источник бедный, а модель вызвана ради названия ---


def _llm_result(content):
    return {
        "content": content,
        "tokens": {"prompt": 400, "completion": 300, "total": 700, "cached": 0},
        "cost_usd": 0.0003,
        "processing_time_ms": 5,
    }


def _generator(llm):
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.vector_store = None
    generator.result_applier = AIResultApplier()
    generator.llm = llm
    return generator


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name, source, title_ru, title_en",
    [
        # Логи 29872, 30716: источник повторяет название или это два слова, названия правилами нет.
        ("RUNNING GRAPHIC SS TEE M", "RUNNING GRAPHIC SS TEE M", "Мужская футболка RUNNING", "Men's RUNNING T-Shirt"),
        ("Ekru Erkek Basic Rayon Karışımlı T-Shirt F5SM-TST 2778", "Parlak ve dayanıklı.", "Мужская футболка", "Men's T-Shirt"),
    ],
)
def test_thin_source_with_llm_title_gets_fact_description(name, source, title_ru, title_en):
    category, _ = Category.objects.update_or_create(slug="t-shirts", defaults={"name": "Футболки", "is_active": True})
    slug = f"c4-thin-{abs(hash(name))}"
    product = Product.objects.create(name=name, slug=slug, product_type="clothing", category=category, description=source)
    ClothingProduct.objects.update_or_create(base_product=product, defaults={"name": name, "slug": slug})
    content = {
        "ru": {"generated_title": title_ru, "generated_description": "<p>Блестящая и прочная.</p>"},
        "en": {"generated_title": title_en, "generated_description": "<p>Shiny and durable.</p>"},
    }
    llm = SimpleNamespace(model="test-model", generate_content=Mock(return_value=_llm_result(content)))
    generator = _generator(llm)

    # Названия правилами нет — модель вызывается ради него, как у логов очереди.
    with patch("apps.ai.services.rules.pipeline.build_titles", return_value={"ru": "", "en": ""}):
        log = generator.process_product(product.id, options={"analyze_images": False, "force": True})

    assert llm.generate_content.call_count == 1
    assert log.raw_llm_response["rule_content"]["description_source"] == "template"
    assert "Блестящая" not in log.generated_description
    assert title_ru in log.generated_description
    assert "short_description" not in get_moderation_reasons(log)
    assert not AITranslationMemory.objects.filter(source_text=clean_source_text(source)).exists()


def test_broken_answer_on_rich_source_stays_short():
    # Порог не ослаблен: описание из трёх слов при обычном источнике остаётся на модерации.
    log = SimpleNamespace(
        category_confidence=None,
        input_data={},
        generated_title="Мужские сандалии",
        generated_description="<p>Блестящая и прочная.</p>",
        extracted_attributes={},
        raw_llm_response={"rule_content": {"description_source": "llm"}},
        product=None,
    )
    assert "short_description" in get_moderation_reasons(log)


# --- артикулы в названии ---


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Erkek Basic Tişört BASIC-T-SHIRT1", "Erkek Basic Tişört"),
        ("Polo Yaka Tişört POLOYAKA-T-SHIRT1", "Polo Yaka Tişört"),
        ("Tişört J5SM-TST7325", "Tişört"),
        # Слова через дефис без цифры — не артикул.
        ("SPIDER-MAN T-Shirt Slip-Ons", "SPIDER-MAN T-Shirt Slip-Ons"),
    ],
)
def test_code_with_several_hyphens_is_removed_whole(title, expected):
    assert strip_price_and_codes_from_title(title) == expected


def test_long_mixed_code_is_supplier_code():
    assert is_supplier_code("Tb0a6vdpenx1")  # лог 30726, Timberland
    assert drop_codes("Polo Erkek Mor Tshirt Tb0a6vdpenx1".split())[-1] == "Tshirt"
    # Обычные модели остаются: цифр мало или слово короткое.
    assert not is_supplier_code("GRAFF5FX")
    assert not is_supplier_code("AirMax270")


def test_apple_green_is_a_colour_not_a_model():
    # Лог 30708 (Buratti): «ELMA YEŞİLİ» требовалось в названии как модель.
    assert "elma" in vocab.generic_title_words()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name, ru, en, expected",
    [
        ("Erkek T Shirt 5904030 ELMA YEŞİLİ", "Мужская футболка Buratti в полоску", "Buratti Men's T-Shirt", []),
        (
            "Mıllers Rıver Pique Short Sleeve Polo Erkek Mor Tshirt Tb0a6vdpenx1",
            "Мужское поло Timberland Pique", "Timberland Men's Pique Polo Shirt", [],
        ),
        # Обрывок артикула в уже готовом названии (логи 30711, 30719) показывать нельзя.
        (
            "Erkek T-shirt Bisiklet Yaka Basic Tişört BASIC-T-SHIRT1",
            "Мужская футболка -SHIRT1 из хлопка", "SHIRT1 Men's Cotton T-Shirt", ["title_code_scrap"],
        ),
        # Настоящая потеря модели остаётся.
        ("Boxing Club PRO500X Erkek Tişört", "Мужская футболка", "Men's T-Shirt", ["title_identity_lost"]),
    ],
)
def test_clothing_titles_from_the_queue(name, ru, en, expected):
    category, _ = Category.objects.update_or_create(slug="clothing", defaults={"name": "Одежда", "is_active": True})
    brand, _ = Brand.objects.get_or_create(name="Timberland", defaults={"slug": "c4-timberland"})
    product = Product.objects.create(
        name=name, slug=f"c4-{abs(hash(name))}", product_type="clothing", category=category, brand=brand
    )
    report = SemanticValidator().validate(product, generated_titles={"ru": ru, "en": en}, dynamic_attributes=[])
    assert report.reasons == expected


# --- категории ---


@pytest.fixture
def shoe_catalog():
    def make(name, slug, parent=None, en=None):
        category, _ = Category.objects.update_or_create(
            slug=slug, defaults={"name": name, "parent": parent, "is_active": True}
        )
        if en:
            category.translations.update_or_create(locale="en", defaults={"name": en})
        return category

    shoes = make("Обувь", "shoes", en="Shoes")
    sandals = make("Сандалии", "sandals", shoes, "Sandals")
    make("Шлёпанцы", "flip-flops", sandals, "Flip-Flops")
    home = make("Домашняя обувь", "home-shoes", shoes, "Home Shoes")
    slippers = make("Тапочки", "slippers", home, "Slippers")
    sneakers = make("Кроссовки", "sneakers", shoes, "Sneakers")
    casual = make("Повседневная обувь", "casual-shoes", shoes, "Casual Shoes")
    make("Слипоны", "slip-ons", casual, "Slip-ons")
    incense = make("Благовония", "incense", en="Incense")
    make("Угли", "charcoal-resin-burners", incense, "Charcoal")
    make("Эвкалиптовое", "eucalyptus-oil", incense, "Eucalyptus")
    supplements = make("БАДы", "supplements", en="Supplements")
    gastro = make("ЖКТ", "gastro", en="Gastro")
    return {
        "sandals": sandals, "slippers": slippers, "sneakers": sneakers, "supplements": supplements, "gastro": gastro,
    }


def _category_reasons(category, product_type, name, ru, en):
    product = Product.objects.create(
        name=name, slug=f"c4-{abs(hash((name, ru)))}", product_type=product_type, category=category
    )
    return SemanticValidator().validate(product, generated_titles={"ru": ru, "en": en}, dynamic_attributes=[]).reasons


@pytest.mark.django_db
def test_terlik_in_sandals_is_not_home_slippers(shoe_catalog):
    # Логи 30709, 30712, 30714: «шлепанцы» — подраздел «Сандалий», EN «Slippers» совпадал с «Тапочками».
    reasons = _category_reasons(
        shoe_catalog["sandals"], "shoes", "09878 Rahat Erkek Terlik Sandalet",
        "Мужские шлепанцы Gezer", "Gezer Men's Slippers",
    )
    assert "title_category_mismatch" not in reasons


@pytest.mark.django_db
def test_slippers_in_sneakers_are_still_a_mismatch(shoe_catalog):
    reasons = _category_reasons(
        shoe_catalog["sneakers"], "shoes", "Erkek Terlik", "Мужские кроссовки Gezer", "Gezer Men's Slippers",
    )
    assert "title_category_mismatch" in reasons


@pytest.mark.django_db
def test_slip_ons_in_sneakers_stay_in_the_queue(shoe_catalog):
    # Лог 30715 (YVON): товар лежит не в своём разделе — переносит человек.
    reasons = _category_reasons(
        shoe_catalog["sneakers"], "shoes", "YVON Lacivert Erkek Slip On",
        "Мужские слипоны Torex YVON тёмно-синие", "Torex YVON Men's Navy Slip-On Shoes",
    )
    assert "title_category_mismatch" in reasons


@pytest.mark.django_db
def test_activated_charcoal_medicine_is_not_incense(shoe_catalog):
    # Лог 28755 (AQUA-CARBO): сорбент — не угли для благовоний.
    reasons = _category_reasons(
        shoe_catalog["gastro"], "medicines", "AQUA-CARBO 50 G/240 ML SULU AKTIF KARBON ICEREN SUSPANSIYON",
        "AQUA-CARBO 50 г/240 мл готовая суспензия с активированным углём",
        "AQUA-CARBO 50 g/240 ml ready-to-use suspension with activated charcoal",
    )
    assert "title_category_mismatch" not in reasons


@pytest.mark.django_db
def test_essential_oil_in_supplements_stays_in_the_queue(shoe_catalog):
    # Логи 28777, 29023 (PHYTOIL): эфирное масло лежит в БАДах с дисклеймером БАДа — раздел выбирает человек.
    reasons = _category_reasons(
        shoe_catalog["supplements"], "supplements", "PHYTOIL EUCALYPTUS 50 ML",
        "PHYTOIL Эвкалиптовое масло, 50 мл", "PHYTOIL Eucalyptus Oil, 50 ml",
    )
    assert "title_category_mismatch" in reasons


# --- БАДы ---


def test_form_from_source_name_is_not_foreign():
    # Лог 29024 (TERAPAS): название источника само говорит «PASTIL».
    source = "TERAPAS NANE LIMON PASTIL 24 tablet"
    pack = supplement_content.parse_pack(source)
    assert pack.piece == "tablet"
    assert not supplement_content.form_mismatch("<p>Терапас — пастилки со вкусом мяты.</p>", pack, source)


def test_foreign_form_is_still_caught():
    # Лог 29017 (BRUGGE): в источнике таблетки, в описании — капсулы. Настоящая ошибка.
    source = "BRUGGE BROMELAIN TAKVIYE EDICI GIDA 30 tablet"
    pack = supplement_content.parse_pack(source)
    description = "<p>BRUGGE Бромелаин — пищевая добавка, которая выпускается в форме капсул.</p>"
    assert supplement_content.form_mismatch(description, pack, source)


@pytest.mark.parametrize(
    "source, ru, piece",
    [
        # Логи 29021, 28993: фасовка не разбиралась, число пропадало из названия.
        ("MAGGUMMY Magnezyum,B12,D3 ve K2 içeren 60 Böğürtlen Aromalı Çiğnenebilir Jel Form", "60", "gummy"),
        ("NEMIX PASCAL BURUN YIKAMA KITI 20 poşet+1 araç", "20", "bag"),
    ],
)
def test_pack_with_flavour_or_device_is_parsed(source, ru, piece):
    pack = supplement_content.parse_pack(source)
    assert pack is not None and pack.piece == piece and pack.ru.startswith(ru)


@pytest.mark.parametrize(
    "title, source",
    [
        # Лог 29039: потеряна линейка «ADVANCED 40+».
        ("SOLGAR Ацидофилус, 60 капсул", "SOLGAR ADVANCED 40+/ACIDOPHILUS KAPSUL 60 kapsül"),
        # Лог 28772: «100 şişe» — ни объём, ни число флаконов не подтверждены.
        ("VITAPURE HERBION, пищевая добавка", "VITAPURE HERBION TAKVIYE EDICI GIDA 100 şişe"),
    ],
)
def test_lost_number_stays_in_the_queue(title, source):
    assert supplement_content.title_problems(title, source) == ["supplement_title_number_lost"]
