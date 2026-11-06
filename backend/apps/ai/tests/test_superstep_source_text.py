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
    assert "paraben" in clean_source_text("Paraben eklenmemiş formül, ferah çiçeksi koku.")
