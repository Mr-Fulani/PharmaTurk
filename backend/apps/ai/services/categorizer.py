"""Сервис категоризации: RAG-контекст категорий и парсинг suggested_category из ответа LLM."""

import logging
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
        if attrs.get("raw_caption"):
            query_parts.append(attrs["raw_caption"])
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
            parent = c.get("parent") or c.get("payload", {}).get("parent", "")
            examples = c.get("examples") or c.get("payload", {}).get("examples", "") or ""
            sim = c.get("score", 0)
            lines.append(
                f"- {name} (родитель: {parent}, схожесть: {sim:.2f}). Примеры: {str(examples)[:200]}"
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
    cat_name = content.get("suggested_category_name")
    confidence = float(content.get("category_confidence", 0.5))

    if not cat_name or not str(cat_name).strip():
        return None, confidence

    category = Category.objects.filter(name__icontains=cat_name).first()
    return category, confidence
