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
