from __future__ import annotations

from typing import Dict, Iterable
from django.conf import settings
from django.utils.html import strip_tags


DEFAULT_BOOK_OG_IMAGE_URL = ""


def _unique_values(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = (value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _get_site_label() -> str:
    for attr in ("BOOKS_SEO_SITE_NAME", "SITE_NAME", "PROJECT_NAME"):
        value = getattr(settings, attr, "") or ""
        value = value.strip()
        if value:
            return value
    return "Online Bookstore"


def _normalize_lang(lang: str | None) -> str:
    raw = (lang or "ru").strip().lower()
    return raw.split("-")[0] if raw else "ru"


def _plain_text(value: str | None) -> str:
    return " ".join(strip_tags(str(value or "")).replace("\xa0", " ").split()).strip()


def _truncate(value: str, limit: int) -> str:
    cleaned = _plain_text(value)
    if len(cleaned) <= limit:
        return cleaned
    shortened = cleaned[: limit - 1].rsplit(" ", 1)[0].strip()
    return (shortened or cleaned[: limit - 1]).rstrip(",.;: ") + "…"


def _get_translation_value(container, field_name: str, lang: str) -> str | None:
    translations = getattr(container, "translations", None)
    if not translations:
        return None

    candidates = [lang]
    if lang != "en":
        candidates.append("en")
    if lang != "ru":
        candidates.append("ru")

    try:
        if hasattr(translations, "filter"):
            for locale in candidates:
                tr = translations.filter(locale=locale).first()
                if tr:
                    val = getattr(tr, field_name, None)
                    if val:
                        return val
            fallback = translations.first()
            if fallback:
                val = getattr(fallback, field_name, None)
                if val:
                    return val
        else:
            trans_list = list(translations)
            for locale in candidates:
                for tr in trans_list:
                    if getattr(tr, "locale", None) == locale:
                        val = getattr(tr, field_name, None)
                        if val:
                            return val
            for tr in trans_list:
                val = getattr(tr, field_name, None)
                if val:
                    return val
    except Exception:
        return None

    return None


def _iter_seo_sources(product):
    seen = set()
    queue = [product]
    while queue:
        current = queue.pop(0)
        if not current:
            continue
        marker = (current.__class__, getattr(current, "pk", None), id(current))
        if marker in seen:
            continue
        seen.add(marker)
        yield current
        try:
            base = getattr(current, "base_product", None)
        except Exception:
            base = None
        if base and base is not current:
            queue.append(base)
        try:
            domain = getattr(current, "domain_item", None)
            if callable(domain):
                domain = domain()
        except Exception:
            domain = None
        if domain and domain is not current:
            queue.append(domain)


def _collect_book_authors(product) -> list[str]:
    try:
        authors = []
        for relation in product.book_authors.all():
            author = getattr(relation, "author", None)
            full_name = getattr(author, "full_name", "") or ""
            authors.append(full_name)
        return _unique_values(authors)
    except Exception:
        return []


def build_book_seo_defaults(product) -> Dict[str, str]:
    name = (getattr(product, "name", "") or "").strip() or "Book"
    authors = _collect_book_authors(product)
    authors_label = ", ".join(authors)
    by_clause = f" by {authors_label}" if authors_label else ""
    site_label = _get_site_label()
    meta_title = f"{name}{by_clause} | {site_label}"
    description_parts = [f"Buy {name}{by_clause} at {site_label}."]
    publisher = (getattr(product, "publisher", "") or "").strip()
    if publisher:
        description_parts.append(f"Publisher: {publisher}.")
    isbn = (getattr(product, "isbn", "") or "").strip()
    if isbn:
        description_parts.append(f"ISBN: {isbn}.")
    meta_description = " ".join(description_parts)
    keyword_values = [name, *authors]
    if publisher:
        keyword_values.append(publisher)
    keyword_values.extend(["book", "books", "bookstore", "buy books"])
    if site_label and site_label.lower() not in {"online bookstore", "bookstore"}:
        keyword_values.append(site_label)
    meta_keywords = ", ".join(_unique_values(keyword_values))
    return {
        "meta_title": meta_title[:255],
        "meta_description": meta_description[:500],
        "meta_keywords": meta_keywords[:500],
        "og_title": meta_title[:255],
        "og_description": meta_description[:500],
        "og_image_url": DEFAULT_BOOK_OG_IMAGE_URL,
    }


def build_catalog_item_seo_defaults(
    *,
    name: str,
    description: str = "",
    category_name: str = "",
    brand_name: str = "",
    product_type: str = "",
    lang: str | None = None,
    is_service: bool = False,
    site_name: str | None = None,
) -> Dict[str, str]:
    lang = _normalize_lang(lang)
    site_label = (site_name or _get_site_label()).strip() or "Mudaroba"
    clean_name = _plain_text(name) or ("Service" if lang == "en" and is_service else "Product" if lang == "en" else "Услуга" if is_service else "Товар")
    clean_description = _plain_text(description)
    clean_category = _plain_text(category_name)
    clean_brand = _plain_text(brand_name)
    clean_type = _plain_text(str(product_type or "").replace("_", " ").replace("-", " "))

    context_parts = _unique_values([clean_category, clean_brand, clean_type])

    if lang == "en":
        action = "Book" if is_service else "Buy"
        title_parts = [clean_name]
        if clean_category and clean_category.lower() not in clean_name.lower():
            title_parts.append(clean_category)
        title_parts.append(site_label)
        meta_title = " | ".join(title_parts)

        if clean_description:
            meta_description = clean_description
        else:
            sentence = f"{action} {clean_name}"
            if clean_brand:
                sentence += f" by {clean_brand}"
            if clean_category:
                sentence += f" in {clean_category}"
            sentence += f" at {site_label}."
            extra = " Prices, availability and delivery details." if not is_service else " Service details, pricing and request options."
            meta_description = sentence + extra

        keyword_values = [clean_name, *context_parts, "services" if is_service else "product", site_label]
    else:
        verb = "Заказать" if is_service else "Купить"
        title_parts = [clean_name]
        if clean_category and clean_category.lower() not in clean_name.lower():
            title_parts.append(clean_category)
        title_parts.append(site_label)
        meta_title = " | ".join(title_parts)

        if clean_description:
            meta_description = clean_description
        else:
            sentence = f"{verb} {clean_name}"
            if clean_brand:
                sentence += f" бренда {clean_brand}"
            if clean_category:
                sentence += f" в категории {clean_category}"
            sentence += f" на {site_label}."
            extra = " Актуальные цены, наличие и условия доставки." if not is_service else " Описание услуги, стоимость и условия заказа."
            meta_description = sentence + extra

        keyword_values = [clean_name, *context_parts, "услуги" if is_service else "товары", site_label]

    meta_title = _truncate(meta_title, 255)
    meta_description = _truncate(meta_description, 500)
    meta_keywords = _truncate(", ".join(_unique_values(keyword_values)), 500)
    return {
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "og_title": meta_title,
        "og_description": meta_description,
        "og_image_url": "",
    }


def resolve_book_seo_value(product, field_name: str, lang: str | None = None) -> str | None:
    lang = _normalize_lang(lang)

    if field_name != "og_image_url":
        for source in _iter_seo_sources(product):
            val = _get_translation_value(source, field_name, lang)
            if val:
                return val

    for source in _iter_seo_sources(product):
        if field_name == "meta_title":
            val = getattr(source, "seo_title", None)
        elif field_name == "meta_description":
            val = getattr(source, "seo_description", None)
        elif field_name == "meta_keywords":
            kw = getattr(source, "keywords", None)
            if isinstance(kw, list):
                val = ", ".join([str(x) for x in kw if x])
            else:
                val = kw
        else:
            val = None
        if val:
            return val

    for source in _iter_seo_sources(product):
        val = getattr(source, field_name, None)
        if val:
            return val

    # Auto-generation for Books only
    if not product or getattr(product, "product_type", None) != "books":
        return None

    value = build_book_seo_defaults(product).get(field_name)
    return value or None
