from __future__ import annotations

from typing import Dict, Iterable
from django.conf import settings


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


def resolve_book_seo_value(product, field_name: str) -> str | None:
    if not product or getattr(product, "product_type", None) != "books":
        return getattr(product, field_name, None)
    current_value = getattr(product, field_name, None)
    if current_value:
        return current_value
    value = build_book_seo_defaults(product).get(field_name)
    return value or None
