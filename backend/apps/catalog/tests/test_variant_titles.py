from types import SimpleNamespace

from apps.catalog.utils.variant_titles import (
    build_variant_display_title,
    should_replace_variant_title,
    strip_price_and_codes_from_title,
)


class _Translations:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, locale):
        matches = [row for row in self._rows if row.locale == locale]
        return SimpleNamespace(first=lambda: matches[0] if matches else None)


def test_build_variant_display_title_uses_parent_name_and_translated_color():
    product = SimpleNamespace(
        name="Кроссовки Air",
        translations=_Translations([SimpleNamespace(locale="en", name="Air Sneakers")]),
    )
    variant = SimpleNamespace(
        product=product,
        name="Кроссовки Air",
        name_en="",
        color="beyaz",
    )

    assert build_variant_display_title(variant, "ru") == "Кроссовки Air - Белый"
    assert build_variant_display_title(variant, "en") == "Air Sneakers - White"


def test_should_replace_variant_title_for_weak_titles():
    assert should_replace_variant_title("", "Кроссовки Air", "beyaz") is True
    assert should_replace_variant_title("Кроссовки Air", "Кроссовки Air", "beyaz") is True
    assert should_replace_variant_title("Beyaz", "Кроссовки Air", "beyaz") is True
    assert should_replace_variant_title("Кроссовки Air - Белый", "Кроссовки Air", "beyaz") is False


def test_strip_price_and_codes_from_variant_title():
    assert strip_price_and_codes_from_title("Кроссовки Air 1299.99 TRY AB-123") == "Кроссовки Air"
