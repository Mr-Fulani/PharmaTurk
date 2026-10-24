"""Страницы препаратов (/drugs/<slug>): формы бренда и ссылка на страницу с карточки.

Формы — по правилу MedicineGroup.medicine_filter (начало названия), без препаратов,
которые нельзя продвигать (medicine_restrictions). Сначала id выбираются условием
только по названию, и лишь потом на этих строках проверяется заглушка в
external_data: условие на jsonb по всей таблице детоастило бы дампы парсеров
(DEVELOPMENT_RULES §2.9).
"""

from __future__ import annotations

from typing import Any, Optional

from django.core.cache import cache
from django.db import models

from apps.catalog.medicine_restrictions import is_restricted_medicine

GROUPS_CACHE_KEY = "medicine_groups:v1:active"
GROUPS_CACHE_TTL = 300


def _stub_q() -> models.Q:
    return models.Q(external_data__has_key="is_stub") & models.Q(external_data__is_stub=True)


def visible_member_ids(group) -> list[int]:
    """id форм препарата на витрине: активные, не заглушки, не запрещённые к продвижению."""
    from apps.catalog.models import MedicineProduct

    rows = (
        MedicineProduct.objects.filter(is_active=True)
        .filter(group.medicine_filter())
        .values_list("id", "active_ingredient", "prescription_type")
    )
    ids = [pk for pk, ingredient, prescription in rows if not is_restricted_medicine(ingredient, prescription)]
    if not ids:
        return []
    stubs = set(MedicineProduct.objects.filter(id__in=ids).filter(_stub_q()).values_list("id", flat=True))
    return [pk for pk in ids if pk not in stubs]


def _active_groups() -> list[dict[str, Any]]:
    groups = cache.get(GROUPS_CACHE_KEY)
    if groups is None:
        from apps.catalog.models import MedicineGroup

        groups = [
            {
                "slug": group.slug,
                "name": group.name,
                "prefixes": group.prefixes(),
                "names": {t.locale: t.name for t in group.translations.all() if t.name},
            }
            for group in MedicineGroup.objects.filter(is_active=True).prefetch_related("translations")
        ]
        cache.set(GROUPS_CACHE_KEY, groups, GROUPS_CACHE_TTL)
    return groups


def group_link_for_medicine(payload: dict[str, Any], lang: str) -> Optional[dict[str, str]]:
    """{"slug", "name", "latin"} страницы препарата для карточки медикамента или None.

    Карточка препарата строгого учёта или с запрещённым к ввозу веществом на страницу
    не ссылается: страница такую форму не показывает.
    """
    from apps.catalog.models import MedicineGroup

    if is_restricted_medicine(payload.get("active_ingredient"), payload.get("prescription_type")):
        return None
    name = str(payload.get("name") or "")
    for group in _active_groups():
        probe = MedicineGroup(name=group["name"], name_prefixes=",".join(group["prefixes"]))
        if probe.matches_name(name):
            return {
                "slug": group["slug"],
                "name": group["names"].get(lang) or group["name"],
                "latin": group["name"],
            }
    return None
