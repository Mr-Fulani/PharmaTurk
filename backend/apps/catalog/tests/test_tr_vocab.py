from apps.catalog.utils.tr_vocab import (
    translate_turkish_color,
    translate_turkish_product_term,
)


def test_translate_turkish_color_supports_common_shades():
    assert translate_turkish_color("beyaz", "ru") == "Белый"
    assert translate_turkish_color("lacivert", "en") == "Navy"
    assert translate_turkish_color("kirik beyaz", "en") == "Off-white"


def test_translate_turkish_product_term_supports_common_catalog_terms():
    assert translate_turkish_product_term("spor ayakkabi", "ru") == "Кроссовки"
    assert translate_turkish_product_term("çanta", "en") == "Bag"
    assert translate_turkish_product_term("gömlek", "ru") == "Рубашка"


def test_translate_turkish_color_handles_dotted_capital_i_and_feed_shades():
    # «İ» с точкой: Python lower() давал «i» + комбинируемую точку, и цвет не находился.
    assert translate_turkish_color("SİYAH", "ru") == "Черный"
    assert translate_turkish_color("LACİVERT", "ru") == "Темно-синий"
    assert translate_turkish_color("çeşitli", "ru") == "Ассорти"
    assert translate_turkish_color("Çok renkli", "ru") == "Разноцветный"
    assert translate_turkish_color("Kum rengi", "ru") == "Песочный"
    assert translate_turkish_color("Koyu Indıgo", "ru") == "Темный индиго"
    assert translate_turkish_color("Açık Mavi", "ru") == "Голубой"
