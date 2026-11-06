from types import SimpleNamespace

import pytest

from apps.ai.services.rules.facts import ProductFacts, clean_source_text, parse_name, product_source
from apps.ai.services.rules.pipeline import _dynamic_attributes, drop_filler_sentences

SS = "superstep"
SUPERSTEP_SOURCE = (
    "Lacoste L003 Erkek Gri Spor Ayakkabı, modern bir sneaker modelidir. "
    "Sayfada doğrulanabilen kesim ayrıntıları özellikler bölümünde yer alır; varyant kodu modeli kontrol etmene yardımcı olur. "
    "Ürün Özellikleri Üst yüzey: süet sığır derisi. Dış taban: %100 kauçuk. Option / ürün kodu: 752SMA0083.2B6. "
    "Kombin Önerileri Siyah bir chino pantolon ve beyaz basic bir tişört ile tamamlayabilirsin. "
    "Bakım Önerileri Nemli bezle silin."
)


def test_product_source_from_external_id():
    assert product_source(SimpleNamespace(external_id="superstep-B75806")) == SS
    assert product_source(SimpleNamespace(external_id="")) == ""


def test_superstep_outfit_tips_disclaimers_and_option_codes_are_cut():
    text = clean_source_text(SUPERSTEP_SOURCE, SS)
    assert "süet sığır derisi" in text and "%100 kauçuk" in text and "Nemli bezle silin" in text
    for filler in ("chino", "Kombin", "doğrulan", "varyant kodu", "752SMA0083"):
        assert filler not in text


def test_superstep_text_limited_to_name_and_category_is_empty():
    text = (
        "Lacoste Cochet Erkek Siyah Loafer, bir loafer modelidir. Doğrulanamayan materyal, teknoloji veya işlev "
        "iddiaları eklenmemiş; açıklama ürün sayfasında yer alan ad ve kategori bilgisiyle sınırlı tutulmuştur."
    )
    assert clean_source_text(text, SS) == ""


def test_superstep_disclaimer_about_one_field_cuts_only_that_sentence():
    text = (
        "Teknik Özellikler Marka: Lacoste. Teknoloji ve donanım: Liste verisinde doğrulanmış teknik teknoloji "
        "bilgisi yer almamaktadır. Dış taban: %100 kauçuk."
    )
    assert clean_source_text(text, SS) == "Teknik Özellikler Marka: Lacoste. Dış taban: %100 kauçuk."


def test_superstep_html_list_without_dots_keeps_other_items():
    text = "<ul><li>Dış taban: kauçuk</li><li>Sayfada doğrulanabilen kesim ayrıntıları yer alır</li><li>Üst: süet</li></ul>"
    assert clean_source_text(text, SS) == "Dış taban: kauçuk Üst: süet"


def test_superstep_outfit_section_before_features_keeps_features():
    text = "Giriş metni. Kombin Önerileri Jean ile tamamla. Ürün Özellikleri Üst: süet. Taban: kauçuk."
    assert clean_source_text(text, SS) == "Giriş metni. Ürün Özellikleri Üst: süet. Taban: kauçuk."


def test_superstep_real_technology_claim_stays():
    text = "Klinik olarak doğrulanmış Air Max yastıklama sunar."
    assert clean_source_text(text, SS) == text


@pytest.mark.parametrize(
    "source, text",
    [
        ("flo", "Teknoloji: doğrulanmış teknik bilgi yer almamaktadır. Kombin Önerileri Jean ile tamamla. Option / ürün kodu: X1."),
        ("lcw", "Dermatolojik olarak doğrulanmış formülünde paraben bulunmamaktadır. Ferah çiçeksi koku."),
        ("lcw", "Paraben eklenmemiş formül; açıklama ürün adı ile sınırlı tutulmuştur."),
        ("", "Klinik olarak doğrulanmış Air Max yastıklama. Varyant kodu: 12."),
    ],
)
def test_other_sources_text_is_not_touched(source, text):
    assert clean_source_text(text, source) == text


def test_filler_sentences_are_dropped_whole_and_empty_paragraphs_go():
    text = (
        "<p>Футболка Lacoste из 100% хлопка. Модель подходит для повседневной носки. Вырез круглый.</p>"
        "<p>Чёрный цвет сочетается с джинсами и брюками.</p>"
    )
    assert drop_filler_sentences(text, "ru") == "<p>Футболка Lacoste из 100% хлопка. Вырез круглый.</p>"
    assert drop_filler_sentences("<p>Подошва 3.5 см. Подходит для повседневной носки.</p>", "ru") == "<p>Подошва 3.5 см.</p>"
    assert drop_filler_sentences("<p>Модель подходит для повседневной носки.</p>", "ru") == ""
    assert drop_filler_sentences("<p>Верх из сетки. Подходит для повседневной городской носки.</p>", "ru") == "<p>Верх из сетки.</p>"
    assert drop_filler_sentences("<p>Низкий профиль. Для повседневного и городского использования.</p>", "ru") == "<p>Низкий профиль.</p>"
    assert "сочетается с современными линиями" in drop_filler_sentences("<p>Силуэт сочетается с современными линиями.</p>", "ru")
    assert drop_filler_sentences("<p>Made of cotton. It pairs well with jeans.</p>", "en") == "<p>Made of cotton.</p>"


@pytest.mark.parametrize(
    "raw, material, sole",
    [
        ("DIS YUZEY:%62 PAMUK %27 SIGIR DERISI %11 SUET SIGIR DERISI TABAN:%100 KAUCUK", "Хлопок", "Каучук"),
        ("DIS YUZEY:%100 SIGIR DERISI TABAN:%100 KAUCUK", "Натуральная кожа", "Каучук"),
        ("DIS YUZEY:%76 POLYESTER %12 SUET SIGIR DERISI TABAN:%100 KAUCUK", None, "Каучук"),  # основной — полиэстер
        ("Üst: Sığır Derisi, İç taban: Deri, Ara taban: EVA, Taban: Kauçuk", "Натуральная кожа", "Каучук"),
        ("Üst: Süet, Astar: Tekstil, Taban: Kauçuk", "Замша", "Каучук"),
        ("Üst: Deri, Taban: Kauçuk", None, "Каучук"),  # одно «deri» не распознаём — лучше пусто
        ("Tekstil/Deri, Taban: Kauçuk", "Текстиль", "Каучук"),  # верх без метки
        ("Upper:Recycled polyester, TPUOutsole: Rubber", None, "Резина"),
        ("Kauçuk", "Каучук", None),  # одна подошва без меток (шлёпанцы) — как раньше
    ],
)
def test_shoe_material_upper_and_sole_by_labels(raw, material, sole):
    rows = _dynamic_attributes(SimpleNamespace(product_type="shoes"), {"attributes": {"material": raw}}, ProductFacts(product_type="shoes"))
    values = {row["slug"]: row["value_ru"] for row in rows}
    assert values.get("material") == material
    assert values.get("sole-material") == sole


@pytest.mark.parametrize(
    "name, brand, model",
    [
        ("Lacoste AG-LT23 Ultra Kadın Mavi Sneaker", "Lacoste", "AG-LT23 Ultra"),
        ("McKinley MG30-1 Çocuk Beyaz Kayak Botu", "Mc Kinley", "MG30-1"),
        ("Pierre Cardin PC-7315 Erkek Sandalet", "Pierre Cardin", ""),  # 4 цифры — артикул
        ("Kinetix J5SM-TST7325 Erkek Sneaker", "Kinetix", ""),
    ],
)
def test_labelled_materials_only_for_shoes():
    rows = _dynamic_attributes(
        SimpleNamespace(product_type="accessories"), {"attributes": {"material": "Üst: Hakiki deri, Taban: Kauçuk"}},
        ProductFacts(product_type="accessories"),
    )
    assert {row["slug"]: row["value_ru"] for row in rows}.get("material") == "Натуральная кожа"


def test_short_hyphen_code_right_after_brand_is_model(name, brand, model):
    facts = ProductFacts(product_type="shoes", brand=brand)
    parse_name(name, facts)
    assert facts.model == model


def test_title_cleanup_keeps_short_model_code_and_drops_supplier_codes():
    from apps.catalog.utils.variant_titles import strip_price_and_codes_from_title

    assert strip_price_and_codes_from_title("Женские кроссовки Lacoste AG-LT23 Ultra") == "Женские кроссовки Lacoste AG-LT23 Ultra"
    assert strip_price_and_codes_from_title("Bisiklet Yaka T-Shirt J5SM-TST7325") == "Bisiklet Yaka T-Shirt"
    assert strip_price_and_codes_from_title("Sandalet PC-7315 Taba") == "Sandalet Taba"
