import re
from .tr_vocab import translate_turkish_color


def strip_price_and_codes_from_title(title: str) -> str:
    if not title:
        return ""
    cleaned = str(title)
    cleaned = re.sub(r"\b[A-Z0-9]{2,}-[A-Z0-9]+\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+[.,]\d+\s*(TL|TRY|USD|EUR|RUB|KZT|USDT)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+[.,]\d+\b", "", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+-\s+$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -–—,")


def translate_common_color(raw_color: str, locale: str) -> str:
    color = (raw_color or "").strip()
    if not color:
        return ""
    return translate_turkish_color(color, locale) or color


def get_parent_localized_name(variant, locale: str) -> str:
    parent = getattr(variant, "product", None)
    if not parent:
        return ""
    if locale == "en":
        translations = getattr(parent, "translations", None)
        if hasattr(translations, "filter"):
            trans = translations.filter(locale="en").first()
            if trans and getattr(trans, "name", None):
                return str(trans.name).strip()
        direct_name = getattr(parent, "name_en", None)
        if direct_name:
            return str(direct_name).strip()
    elif locale == "ru":
        translations = getattr(parent, "translations", None)
        if hasattr(translations, "filter"):
            trans = translations.filter(locale="ru").first()
            if trans and getattr(trans, "name", None):
                return str(trans.name).strip()
    return str(getattr(parent, "name", "") or "").strip()


def build_variant_display_title(variant, locale: str) -> str:
    base_name = strip_price_and_codes_from_title(
        get_parent_localized_name(variant, locale)
        or (getattr(variant, "name_en", "") if locale == "en" else getattr(variant, "name", ""))
        or ""
    )
    translated_color = translate_common_color(getattr(variant, "color", "") or "", locale)
    if base_name and translated_color and translated_color.lower() not in base_name.lower():
        return f"{base_name} - {translated_color}"
    return base_name or translated_color


def should_replace_variant_title(current_title: str, parent_title: str, raw_color: str) -> bool:
    current = strip_price_and_codes_from_title(current_title or "")
    parent = strip_price_and_codes_from_title(parent_title or "")
    color = str(raw_color or "").strip()
    localized_colors = {translate_common_color(color, "ru").lower(), translate_common_color(color, "en").lower(), color.lower()}

    if not current:
        return True
    if parent and current.lower() == parent.lower():
        return True
    if color and current.lower() in {item for item in localized_colors if item}:
        return True
    if re.search(r"\b\d+[.,]?\d*\s*(tl|try|usd|eur|rub|kzt|usdt)\b", current, flags=re.IGNORECASE):
        return True
    if re.search(r"\b[A-Z0-9]{2,}-[A-Z0-9]+\b", current, flags=re.IGNORECASE):
        return True
    return False
