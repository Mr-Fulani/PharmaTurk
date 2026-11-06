import pytest

from apps.ai.services.rules.facts import clean_source_text


SUPERSTEP_SOURCE = (
    "Lacoste L003 Erkek Gri Spor Ayakkabı, modern bir sneaker modelidir. "
    "Sayfada doğrulanabilen kesim ayrıntıları özellikler bölümünde yer alır; varyant kodu modeli kontrol etmene yardımcı olur. "
    "Ürün Özellikleri Üst yüzey: süet sığır derisi. Dış taban: %100 kauçuk. Option / ürün kodu: 752SMA0083.2B6. "
    "Kombin Önerileri Siyah bir chino pantolon ve beyaz basic bir tişört ile tamamlayabilirsin. "
    "Bakım Önerileri Nemli bezle silin."
)


def test_superstep_outfit_tips_disclaimers_and_option_codes_are_cut():
    text = clean_source_text(SUPERSTEP_SOURCE)
    assert "süet sığır derisi" in text and "%100 kauçuk" in text and "Nemli bezle silin" in text
    for filler in ("chino", "Kombin", "doğrulan", "varyant kodu", "752SMA0083"):
        assert filler not in text


@pytest.mark.parametrize(
    "disclaimer",
    [
        "Doğrulanamayan materyal, teknoloji veya işlev iddiaları eklenmemiş; açıklama ad ve kategoriyle sınırlı tutulmuştur.",
        "Materyal: Mevcut liste verisinde doğrulanmış materyal bilgisi bulunmamaktadır.",
    ],
)
def test_superstep_text_that_admits_no_facts_is_empty(disclaimer):
    assert clean_source_text(f"Lacoste Cochet Erkek Siyah Loafer, bir loafer modelidir. {disclaimer}") == ""


def test_ordinary_eklenmemis_is_not_a_superstep_disclaimer():
    assert "Paraben eklenmemiş" in clean_source_text("Paraben eklenmemiş formül, ferah çiçeksi koku.")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("DIS YUZEY:%62 PAMUK %27 SIGIR DERISI %11 SUET SIGIR DERISI TABAN:%100 KAUCUK", "Хлопок"),
        ("DIS YUZEY:%100 SIGIR DERISI TABAN:%100 KAUCUK", None),  # верх не распознан — лучше пусто, чем подошва
        ("Upper:Recycled polyester, TPUOutsole: Rubber", None),
        ("Kauçuk", "Каучук"),  # одна подошва без разметки (шлёпанцы) — как раньше
    ],
)
def test_shoe_material_is_not_taken_from_sole(raw, expected):
    from types import SimpleNamespace

    from apps.ai.services.rules.facts import ProductFacts
    from apps.ai.services.rules.pipeline import _dynamic_attributes

    rows = _dynamic_attributes(SimpleNamespace(product_type="shoes"), {"attributes": {"material": raw}}, ProductFacts(product_type="shoes"))
    assert next((row["value_ru"] for row in rows if row["slug"] == "material"), None) == expected


def test_filler_sentences_are_dropped_whole_and_empty_paragraphs_go():
    from apps.ai.services.rules.pipeline import drop_filler_sentences

    text = (
        "<p>Футболка Lacoste из 100% хлопка. Модель подходит для повседневной носки. Вырез круглый.</p>"
        "<p>Чёрный цвет сочетается с джинсами и брюками.</p>"
    )
    assert drop_filler_sentences(text, "ru") == "<p>Футболка Lacoste из 100% хлопка. Вырез круглый.</p>"
    assert drop_filler_sentences("<p>Подошва 3.5 см. Подходит для повседневной носки.</p>", "ru") == "<p>Подошва 3.5 см.</p>"
    assert drop_filler_sentences("<p>Модель подходит для повседневной носки.</p>", "ru") == ""
    assert drop_filler_sentences("<p>Made of cotton. It pairs well with jeans.</p>", "en") == "<p>Made of cotton.</p>"


@pytest.mark.parametrize(
    "name, brand, model",
    [
        ("Lacoste AG-LT23 Ultra Kadın Mavi Sneaker", "Lacoste", "AG-LT23 Ultra"),
        ("McKinley MG30-1 Çocuk Beyaz Kayak Botu", "Mc Kinley", "MG30-1"),
        ("Pierre Cardin PC-7315 Erkek Sandalet", "Pierre Cardin", ""),  # 4 цифры — артикул
        ("Kinetix J5SM-TST7325 Erkek Sneaker", "Kinetix", ""),
    ],
)
def test_short_hyphen_code_right_after_brand_is_model(name, brand, model):
    from apps.ai.services.rules.facts import ProductFacts, parse_name

    facts = ProductFacts(product_type="shoes", brand=brand)
    parse_name(name, facts)
    assert facts.model == model


def test_title_cleanup_keeps_short_model_code_and_drops_supplier_codes():
    from apps.catalog.utils.variant_titles import strip_price_and_codes_from_title

    assert strip_price_and_codes_from_title("Женские кроссовки Lacoste AG-LT23 Ultra") == "Женские кроссовки Lacoste AG-LT23 Ultra"
    assert strip_price_and_codes_from_title("Bisiklet Yaka T-Shirt J5SM-TST7325") == "Bisiklet Yaka T-Shirt"
    assert strip_price_and_codes_from_title("Sandalet PC-7315 Taba") == "Sandalet Taba"
