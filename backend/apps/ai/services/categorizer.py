"""Сервис категоризации: RAG-контекст категорий и парсинг suggested_category из ответа LLM."""

import logging
import math
from typing import Optional, Tuple, Any

from apps.catalog.models import Category

logger = logging.getLogger(__name__)


def get_category_context_for_prompt(product: Any, vector_store: Any) -> str:
    """
    Формирует блок «Доступные категории из каталога» для промпта.
    Использует vector_store.search_similar_categories_by_text по имени/описанию товара.
    """
    if not vector_store:
        return ""

    query_parts = [product.name or "", product.description or ""]
    if getattr(product, "external_data", None):
        attrs = product.external_data.get("attributes") or {}
        raw_caption = attrs.get("raw_caption") or product.external_data.get("raw_caption")
        if raw_caption:
            query_parts.append(str(raw_caption))
    query_text = " ".join(query_parts).strip() or "товар"

    try:
        similar_cats = vector_store.search_similar_categories_by_text(
            query_text, top_k=5
        )
        if not similar_cats:
            return ""

        lines = []
        for c in similar_cats[:3]:
            name = c.get("category_name") or c.get("payload", {}).get("category_name", "")
            slug = c.get("category_slug") or c.get("payload", {}).get("category_slug", "")
            parent = c.get("parent") or c.get("payload", {}).get("parent", "")
            examples = c.get("examples") or c.get("payload", {}).get("examples", "") or ""
            sim = c.get("score", 0)
            lines.append(
                f"- {name} (slug: {slug}, родитель: {parent}, схожесть: {sim:.2f}). "
                f"Примеры: {str(examples)[:200]}"
            )
        return (
            "Доступные категории из каталога (используй при выборе suggested_category_name):\n"
            + "\n".join(lines)
            + "\n\n"
        )
    except Exception as e:
        logger.debug("RAG categories skipped: %s", e)
        return ""


def parse_suggested_category_from_content(content: dict):
    """
    Из JSON ответа LLM достаёт suggested_category_name и category_confidence,
    ищет Category по имени, возвращает (category, confidence).
    """
    cat_name = str(content.get("suggested_category_name") or "").strip()
    category_slug = str(content.get("suggested_category_slug") or "").strip()
    try:
        confidence = float(content.get("category_confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence)) if math.isfinite(confidence) else 0.0
    except (TypeError, ValueError):
        confidence = 0.0

    if not cat_name and not category_slug:
        return None, confidence

    category = None
    if category_slug:
        category = Category.objects.filter(slug=category_slug, is_active=True).first()
    if category is None and cat_name:
        category = Category.objects.filter(name__iexact=cat_name, is_active=True).first()
    return category, confidence if category else 0.0
