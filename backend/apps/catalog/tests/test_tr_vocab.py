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
