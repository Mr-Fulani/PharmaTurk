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


def test_translate_turkish_color_keeps_detail_after_separator():
    """Различитель одинаковых цветов одной модели (SuperStep) переживает перевод."""
    assert translate_turkish_color("Beyaz · PUMA White-PUMA Black", "ru") == "Белый · PUMA White-PUMA Black"
    assert translate_turkish_color("Siyah · CHE", "en") == "Black · CHE"
    assert translate_turkish_color("Zümrüt · 01", "ru") == ""  # цвета нет в словаре
    # Скобки других источников ведут себя как раньше.
    assert translate_turkish_color("Siyah (Baskılı)", "ru") == "Черный"


def test_translate_turkish_color_superstep_tones():
    """Тоны SuperStep, которые оставались по-турецки на сайте и пропадали в фиде ВК."""
    assert translate_turkish_color("RENKLİ", "ru") == "Разноцветный"
    assert translate_turkish_color("Renkli · WZS", "ru") == "Разноцветный · WZS"
    assert translate_turkish_color("GÜMÜŞ", "en") == "Silver"
    assert translate_turkish_color("ALTIN", "ru") == "Золотой"


def test_new_superstep_tones_do_not_override_the_main_color_of_a_compound():
    """Составные цвета FLO и LCW переводятся по-прежнему — по основному цвету."""
    assert translate_turkish_color("Siyah-Renkli", "ru") == "Черный"
    assert translate_turkish_color("Mavi-Gümüş", "ru") == "Синий"
    assert translate_turkish_color("Mor/Altın", "ru") == "Фиолетовый"
    assert translate_turkish_color("Beyaz-Lacivert", "ru") == "Темно-синий"  # как раньше
