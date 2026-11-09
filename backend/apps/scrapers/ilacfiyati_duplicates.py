"""Дубли лекарств и БАДов ilacfiyati по списку пар «оставить / скрыть».

Один препарат у источника бывает на двух страницах с разными адресами и штрихкодами
(страница со старым штрихкодом «…-2» со статусом «Pasif», вторая карточка БАДа), и у нас
он становился двумя товарами. Пары собирает человек (отчёт reports/medicine-duplicates-…),
код только перепроверяет каждую пару по текущим данным и скрывает лишь полное
совпадение: турецкое название (препарат, дозировка, форма, количество), состав,
штрихкод (у лекарств), производитель, цена и наличие. Любое расхождение —
«сомнительно», ничего не скрывается. Описание — docs/ILACFIYATI_DUPLICATES.md.

Скрыть = то же, что у близнецов (``ilacfiyati_twins.hide_twin``): ``is_active=False``
у Product и доменной карточки, адрес — 301 на оставленный товар; ничего не удаляется.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.core.cache import cache
from django.db import transaction

from apps.scrapers import ilacfiyati_twins

HIDE = "hide"
REVIEW = "review"
# Пометка в external_data скрытого дубля: pk оставленного товара.
DUPLICATE_OF_KEY = "ilacfiyati_duplicate_of"
PRODUCT_TYPES = ("medicines", "supplements")
# Служебный номер источника у импортных препаратов: один на разные препараты.
PLACEHOLDER_BARCODE_PREFIX = "1111111"
_BARCODE_IN_TEXT_RE = re.compile(r"Barkod\W{0,5}(\d{8,14})", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _external(product) -> dict:
    return product.external_data if isinstance(product.external_data, dict) else {}


def _attrs(product) -> dict:
    attrs = _external(product).get("attributes")
    return attrs if isinstance(attrs, dict) else {}


def _domain(product):
    try:
        return ilacfiyati_twins.domain_model(product.product_type).objects.filter(base_product_id=product.pk).first()
    except KeyError:
        return None


def source_barcode(product) -> str:
    """Штрихкод источника: поле лекарства, атрибут парсера или «Barkod: N» в тексте источника."""
    domain = _domain(product)
    for value in (getattr(domain, "barcode", ""), _attrs(product).get("barcode")):
        value = str(value or "").strip()
        if value:
            return value
    for text in (_external(product).get("source_description"), product.description):
        match = _BARCODE_IN_TEXT_RE.search(str(text or ""))
        if match:
            return match.group(1)
    return ""


def is_real_barcode(barcode: str) -> bool:
    return bool(barcode) and not barcode.startswith(PLACEHOLDER_BARCODE_PREFIX)


def _manufacturer(product) -> str:
    value = _attrs(product).get("manufacturer") or getattr(_domain(product), "manufacturer", "") or ""
    return " ".join(_WORD_RE.findall(ilacfiyati_twins._fold(value)))


def _is_shown(product) -> bool:
    domain = _domain(product)
    return bool(product.is_active and domain is not None and domain.is_active)


def _is_stub(product) -> bool:
    return _external(product).get("is_stub") is True


def _price(page) -> tuple:
    return (page.price, getattr(page.product, "currency", "") or "")


def pair_problem(keep, hide) -> str:
    """Почему пару нельзя скрыть автоматически; пусто — полный дубль, ``hide`` скрывается."""
    if keep.pk == hide.pk:
        return "один и тот же товар"
    if keep.product_type != hide.product_type or keep.product_type not in PRODUCT_TYPES:
        return f"типы товаров: {keep.product_type} / {hide.product_type}"
    if not all("ilacfiyati.com" in str(p.external_url or "") for p in (keep, hide)):
        return "товар не из ilacfiyati"
    if not _is_shown(hide):
        return "скрываемая уже не на сайте"
    if not _is_shown(keep):
        return "оставляемая скрыта"
    if _is_stub(keep):
        return "оставляемая — заглушка аналога, на сайте не видна"
    if _is_stub(hide):
        return "скрываемая — заглушка аналога, на сайте не видна"
    keep_page = ilacfiyati_twins.page_from_product(keep)
    hide_page = ilacfiyati_twins.page_from_product(hide)
    if not _external(keep).get("source_name") or not _external(hide).get("source_name"):
        return "нет турецкого названия источника"
    reason = ilacfiyati_twins.mismatch_reason(keep_page, hide_page)
    if reason:
        return reason
    keep_barcode, hide_barcode = source_barcode(keep), source_barcode(hide)
    if (keep.product_type == "medicines" and is_real_barcode(keep_barcode) and is_real_barcode(hide_barcode)
            and keep_barcode != hide_barcode):
        # Разные штрихкоды лекарства — бывает и другая упаковка: решает человек.
        return f"разные штрихкоды: {keep_barcode} / {hide_barcode}"
    keep_maker, hide_maker = _manufacturer(keep), _manufacturer(hide)
    if keep_maker and hide_maker and keep_maker != hide_maker:
        return "разные производители"
    if hide_page.has_price and not keep_page.has_price:
        return "у скрываемой есть цена, у оставляемой нет"
    if hide_page.is_available and not keep_page.is_available:
        return "оставляемая не в наличии, скрываемая в наличии"
    if (keep.product_type == "medicines" and keep_page.has_price and hide_page.has_price
            and _price(keep_page) != _price(hide_page)):
        # Цены лекарств регулируются: другая цена — скорее другая упаковка.
        return "разные цены"
    return ""


@dataclass
class PairDecision:
    keep: object
    hide: object
    action: str  # HIDE | REVIEW
    reason: str


def decide_pairs(pairs: list[tuple[int, int]]) -> tuple[list[PairDecision], list[tuple[int, int, str]]]:
    """Решения по парам (keep_id, hide_id) и пары, товаров которых нет в базе."""
    from apps.catalog.models import Product

    ids = {pk for pair in pairs for pk in pair}
    products = Product.objects.in_bulk(ids)
    keep_ids = {keep_id for keep_id, _hide_id in pairs}
    hide_counts: dict[int, int] = {}
    for _keep_id, hide_id in pairs:
        hide_counts[hide_id] = hide_counts.get(hide_id, 0) + 1
    decisions, missing = [], []
    for keep_id, hide_id in pairs:
        keep, hide = products.get(keep_id), products.get(hide_id)
        if keep is None or hide is None:
            missing.append((keep_id, hide_id, "товара нет в базе"))
            continue
        if hide_id in keep_ids:
            reason = "скрываемая оставляется в другой паре"
        elif hide_counts[hide_id] > 1:
            reason = "скрываемая встречается в нескольких парах"
        else:
            reason = pair_problem(keep, hide)
        decisions.append(PairDecision(keep, hide, REVIEW if reason else HIDE, reason or "полный дубль"))
    return decisions, missing


def backup_row(hide, keep) -> dict:
    """Состояние скрываемого товара «до» — для --restore."""
    from apps.catalog.models import ProductSlugHistory

    domain = ilacfiyati_twins.domain_model(hide.product_type)
    domain_rows = list(domain.objects.filter(base_product_id=hide.pk).values("pk", "is_active", "slug"))
    slugs = sorted({hide.slug, *(row["slug"] for row in domain_rows)} - {"", None})
    return {
        "product_id": hide.pk,
        "product_type": hide.product_type,
        "keep_id": keep.pk,
        "is_active": hide.is_active,
        "external_data": hide.external_data,
        "domain_is_active": [{"pk": row["pk"], "is_active": row["is_active"]} for row in domain_rows],
        "slug_history_before": list(
            ProductSlugHistory.objects.filter(old_slug__in=slugs).values("old_slug", "product_id", "product_type")
        ),
        "slugs": slugs,
    }


def restore_row(row: dict) -> bool:
    """Вернуть товар из строки бэкапа: показ, прежний external_data и старые адреса.

    Возвращает False, если товара уже нет. QuerySet.update — как при скрытии.
    """
    from apps.catalog.models import Product, ProductSlugHistory
    from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX

    if not Product.objects.filter(pk=row["product_id"]).exists():
        return False
    domain = ilacfiyati_twins.domain_model(row["product_type"])
    with transaction.atomic():
        Product.objects.filter(pk=row["product_id"]).update(
            is_active=row["is_active"], external_data=row["external_data"],
        )
        for item in row["domain_is_active"]:
            domain.objects.filter(pk=item["pk"]).update(is_active=item["is_active"])
        ProductSlugHistory.objects.filter(old_slug__in=row["slugs"]).delete()
        for item in row["slug_history_before"]:
            if Product.objects.filter(pk=item["product_id"]).exists():
                ProductSlugHistory.objects.create(**item)
        for slug in row["slugs"]:
            cache.delete(RESOLVE_CACHE_PREFIX + slug)
    return True


def hide_duplicate(hide, keep) -> list[str]:
    return ilacfiyati_twins.hide_twin(hide, keep, marker_key=DUPLICATE_OF_KEY)
