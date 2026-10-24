"""Страницы препаратов (/drugs/<slug>): формы бренда и ссылка на страницу с карточки.

Формы — по правилу MedicineGroup.medicine_filter (начало названия), без препаратов,
ввоз которых в РФ и СНГ запрещён или ограничен (отметка TD-024
``import_restricted_countries``, apps/catalog/controlled_substances.py). Сначала id
выбираются условием только по обычным полям, и лишь потом на этих строках проверяется
заглушка в external_data: условие на jsonb по всей таблице детоастило бы дампы парсеров
(DEVELOPMENT_RULES §2.9).
"""

from __future__ import annotations

from typing import Any, Optional

from django.core.cache import cache
from django.db import models

GROUPS_CACHE_KEY = "medicine_groups:v1:active"
GROUPS_CACHE_TTL = 300


def _stub_q() -> models.Q:
    return models.Q(external_data__has_key="is_stub") & models.Q(external_data__is_stub=True)


def visible_member_ids(group) -> list[int]:
    """id форм препарата на витрине: активные, не заглушки, без отметки «ввоз ограничен»."""
    from apps.catalog.models import MedicineProduct

    ids = list(
        MedicineProduct.objects.filter(is_active=True, import_restricted_countries="")
        .filter(group.medicine_filter())
        .values_list("id", flat=True)
    )
    if not ids:
        return []
    stubs = set(MedicineProduct.objects.filter(id__in=ids).filter(_stub_q()).values_list("id", flat=True))
    return [pk for pk in ids if pk not in stubs]


def _is_prescription(kind: str) -> bool:
    """«beyaz recete», «рецептурный препарат», «prescription medicine» — да; «recetesiz», «безрецептурный» — нет."""
    return any(
        word in kind and not any(negative in kind for negative in negatives)
        for word, negatives in (
            ("recete", ("recetesiz",)),
            ("рецепт", ("безрецепт",)),
            ("prescription", ("over-the-counter", "non-prescription")),
        )
    )


def member_flags(ids: list[int]) -> dict[str, bool]:
    """Пометки страницы: рецептурный ли препарат и нужна ли холодовая цепь (2–8 °C).

    Рецепт — по турецкому типу рецепта источника («Beyaz Reçete» и т. п., не «Reçetesiz»).
    Холодовая цепь — по условиям хранения источника и их переводу (needs_cold_chain).
    """
    from apps.ai.services.medicine_reference import fold_tr
    from apps.ai.services.medicine_seo import needs_cold_chain
    from apps.catalog.models import MedicineProduct, MedicineProductTranslation

    rows = MedicineProduct.objects.filter(id__in=ids).values_list("prescription_type", "storage_conditions")
    prescription = any(_is_prescription(fold_tr(kind)) for kind, _ in rows)
    storage = [text for _, text in rows] + list(
        MedicineProductTranslation.objects.filter(product_id__in=ids).values_list("storage_conditions", flat=True)
    )
    return {"prescription": prescription, "cold_chain": any(needs_cold_chain(text) for text in storage)}


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

    Карточка с отметкой «ввоз ограничен» (TD-024) на страницу не ссылается: страница
    такую форму не показывает. Отметку читаем из базы — в payload вещество уже переведено,
    а отметка считается по исходному турецкому.
    """
    from apps.catalog.models import MedicineGroup, MedicineProduct

    name = str(payload.get("name") or "")
    for group in _active_groups():
        probe = MedicineGroup(name=group["name"], name_prefixes=",".join(group["prefixes"]))
        if probe.matches_name(name):
            if MedicineProduct.objects.filter(slug=payload.get("slug")).exclude(import_restricted_countries="").exists():
                return None
            return {
                "slug": group["slug"],
                "name": group["names"].get(lang) or group["name"],
                "latin": group["name"],
            }
    return None
