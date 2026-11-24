"""Учёт поисковых запросов страницы /search (docs/PRODUCT_SEARCH.md, «Учёт запросов»)."""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models_search import SearchQueryStat
from .product_search import SearchPlan, normalize_search_text

logger = logging.getLogger(__name__)

_MAX_QUERY = SearchQueryStat._meta.get_field("query").max_length


def record_search(search: str, plan: SearchPlan | None, results: int, locale: str) -> None:
    """Записывает один поиск: +1 к счётчику запроса, число найденного и то, как запрос понят.

    Ошибка записи не должна ломать поиск: она уходит в лог.
    """
    query = normalize_search_text(search)[:_MAX_QUERY]
    if not query:
        return
    values = {
        "results": results,
        "mode": plan.mode if plan else "",
        "corrected_query": plan.query[:_MAX_QUERY] if plan and plan.corrected else "",
    }
    try:
        rows = SearchQueryStat.objects.filter(query=query, locale=locale)
        if rows.update(searches=F("searches") + 1, last_at=timezone.now(), **values):
            return
        try:
            with transaction.atomic():
                SearchQueryStat.objects.create(query=query, locale=locale, searches=1, **values)
        except IntegrityError:  # тот же запрос записан параллельно
            rows.update(searches=F("searches") + 1, last_at=timezone.now(), **values)
    except Exception:
        logger.exception("search query stat was not recorded")
