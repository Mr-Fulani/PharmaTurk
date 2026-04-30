from __future__ import annotations

import re


def normalize_ascii_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    replacements = str.maketrans({
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
    })
    return text.translate(replacements)


TR_COLOR_DICTIONARY: dict[str, dict[str, str]] = {
    "beyaz": {"ru": "Белый", "en": "White"},
    "kirik beyaz": {"ru": "Молочный", "en": "Off-white"},
    "kırık beyaz": {"ru": "Молочный", "en": "Off-white"},
    "ekru": {"ru": "Молочный", "en": "Ecru"},
    "lacivert": {"ru": "Темно-синий", "en": "Navy"},
    "siyah": {"ru": "Черный", "en": "Black"},
    "mavi": {"ru": "Синий", "en": "Blue"},
    "gri": {"ru": "Серый", "en": "Gray"},
    "antrasit": {"ru": "Антрацит", "en": "Anthracite"},
    "kahverengi": {"ru": "Коричневый", "en": "Brown"},
    "bej": {"ru": "Бежевый", "en": "Beige"},
    "krem": {"ru": "Кремовый", "en": "Cream"},
    "kirmizi": {"ru": "Красный", "en": "Red"},
    "kırmızı": {"ru": "Красный", "en": "Red"},
    "bordo": {"ru": "Бордовый", "en": "Burgundy"},
    "pembe": {"ru": "Розовый", "en": "Pink"},
    "mor": {"ru": "Фиолетовый", "en": "Purple"},
    "turuncu": {"ru": "Оранжевый", "en": "Orange"},
    "sari": {"ru": "Желтый", "en": "Yellow"},
    "sarı": {"ru": "Желтый", "en": "Yellow"},
    "yesil": {"ru": "Зеленый", "en": "Green"},
    "yeşil": {"ru": "Зеленый", "en": "Green"},
    "haki": {"ru": "Хаки", "en": "Khaki"},
}


TR_PRODUCT_TERM_DICTIONARY: dict[str, dict[str, str]] = {
    "ayakkabi": {"ru": "Обувь", "en": "Shoes"},
    "ayakkabı": {"ru": "Обувь", "en": "Shoes"},
    "spor ayakkabi": {"ru": "Кроссовки", "en": "Sneakers"},
    "spor ayakkabı": {"ru": "Кроссовки", "en": "Sneakers"},
    "sneaker": {"ru": "Кроссовки", "en": "Sneakers"},
    "bot": {"ru": "Ботинки", "en": "Boots"},
    "cizme": {"ru": "Сапоги", "en": "Boots"},
    "çizme": {"ru": "Сапоги", "en": "Boots"},
    "terlik": {"ru": "Тапочки", "en": "Slippers"},
    "sandalet": {"ru": "Сандалии", "en": "Sandals"},
    "canta": {"ru": "Сумка", "en": "Bag"},
    "çanta": {"ru": "Сумка", "en": "Bag"},
    "cuzdan": {"ru": "Кошелек", "en": "Wallet"},
    "cüzdan": {"ru": "Кошелек", "en": "Wallet"},
    "kemer": {"ru": "Ремень", "en": "Belt"},
    "saat": {"ru": "Часы", "en": "Watch"},
    "gozluk": {"ru": "Очки", "en": "Glasses"},
    "gözlük": {"ru": "Очки", "en": "Glasses"},
    "sapka": {"ru": "Шапка", "en": "Hat"},
    "şapka": {"ru": "Шапка", "en": "Hat"},
    "kep sapka": {"ru": "Кепка", "en": "Cap"},
    "kep şapka": {"ru": "Кепка", "en": "Cap"},
    "bere": {"ru": "Берет", "en": "Beret"},
    "elbise": {"ru": "Платье", "en": "Dress"},
    "gomlek": {"ru": "Рубашка", "en": "Shirt"},
    "gömlek": {"ru": "Рубашка", "en": "Shirt"},
    "tisort": {"ru": "Футболка", "en": "T-shirt"},
    "tişört": {"ru": "Футболка", "en": "T-shirt"},
    "pantolon": {"ru": "Брюки", "en": "Pants"},
    "etek": {"ru": "Юбка", "en": "Skirt"},
    "ceket": {"ru": "Куртка", "en": "Jacket"},
    "hirka": {"ru": "Кардиган", "en": "Cardigan"},
    "hırka": {"ru": "Кардиган", "en": "Cardigan"},
    "kazak": {"ru": "Свитер", "en": "Sweater"},
}


def _lookup_localized(mapping: dict[str, dict[str, str]], raw_value: str, locale: str) -> str:
    normalized = normalize_ascii_text(raw_value)
    if not normalized:
        return ""
    direct = mapping.get(normalized)
    if direct:
        return direct.get(locale) or str(raw_value).strip()
    for key, values in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(^|[^a-z]){re.escape(key)}([^a-z]|$)", normalized):
            return values.get(locale) or str(raw_value).strip()
    return ""


def translate_turkish_color(raw_value: str, locale: str) -> str:
    return _lookup_localized(TR_COLOR_DICTIONARY, raw_value, locale)


def translate_turkish_product_term(raw_value: str, locale: str) -> str:
    return _lookup_localized(TR_PRODUCT_TERM_DICTIONARY, raw_value, locale)


def match_turkish_product_term(raw_value: str) -> tuple[str, dict[str, str]] | None:
    normalized = normalize_ascii_text(raw_value)
    if not normalized:
        return None
    for key, values in sorted(TR_PRODUCT_TERM_DICTIONARY.items(), key=lambda item: len(normalize_ascii_text(item[0])), reverse=True):
        normalized_key = normalize_ascii_text(key)
        if re.search(rf"(^|[^a-z]){re.escape(normalized_key)}([^a-z]|$)", normalized):
            return normalized_key, values
    return None
