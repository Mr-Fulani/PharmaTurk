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


def manufacturer_key(value: str) -> frozenset:
    """Слова фирмы без регистра и турецких букв; TEB — не производитель, а служба ввоза
    (страница TEB есть у любого импортного препарата), поэтому для неё пусто."""
    words = _WORD_RE.findall(ilacfiyati_twins._fold(value))
    return frozenset() if not words or words[0] == "teb" else frozenset(words)


@dataclass
class PairSide:
    """Что сравнивается у одной карточки пары (из базы или из публичных данных)."""

    page: ilacfiyati_twins.TwinPage  # турецкое название, цена, наличие, адрес источника
    barcode: str = ""
    manufacturer: str = ""
    currency: str = ""


def compare_sides(keep: PairSide, hide: PairSide, *, product_type: str, same_page: bool = False) -> str:
    """Почему ``hide`` может быть другим товаром, чем ``keep``; пусто — полный дубль.

    ``same_page`` — старый адрес источника скрываемой отдаёт 301 на адрес оставляемой
    (проверено человеком при сборе списка): это одна страница, а штрихкод, фирма и цена
    скрываемой устарели, их не сравниваем. Название сравнивается всегда.
    """
    reason = ilacfiyati_twins.mismatch_reason(keep.page, hide.page)
    if reason:
        return reason
    if not same_page:
        if product_type == "medicines" and keep.barcode and hide.barcode and keep.barcode != hide.barcode:
            # Другой штрихкод лекарства (и другой служебный номер 1111111…) — бывает и другая
            # упаковка или регистрация: решает человек.
            return f"разные штрихкоды: {keep.barcode} / {hide.barcode}"
        keep_maker, hide_maker = manufacturer_key(keep.manufacturer), manufacturer_key(hide.manufacturer)
        if keep_maker and hide_maker and not (keep_maker <= hide_maker or hide_maker <= keep_maker):
            return f"разные производители: {keep.manufacturer} / {hide.manufacturer}"
    if hide.page.has_price and not keep.page.has_price:
        return "у скрываемой есть цена, у оставляемой нет"
    if hide.page.is_available and not keep.page.is_available:
        return "оставляемая не в наличии, скрываемая в наличии"
    if (not same_page and product_type == "medicines" and keep.page.has_price and hide.page.has_price
            and (keep.page.price, keep.currency) != (hide.page.price, hide.currency)):
        # Цены лекарств регулируются: другая цена — скорее другая упаковка.
        return "разные цены"
    return ""


def side_from_product(product) -> PairSide:
    return PairSide(
        page=ilacfiyati_twins.page_from_product(product),
        barcode=source_barcode(product),
        manufacturer=str(_attrs(product).get("manufacturer") or getattr(_domain(product), "manufacturer", "") or ""),
        currency=product.currency or "",
    )


def _is_shown(product) -> bool:
    domain = _domain(product)
    return bool(product.is_active and domain is not None and domain.is_active)


def _is_stub(product) -> bool:
    return _external(product).get("is_stub") is True


def pair_problem(keep, hide, *, same_page: bool = False) -> str:
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
    if not _external(keep).get("source_name") or not _external(hide).get("source_name"):
        return "нет турецкого названия источника"
    return compare_sides(
        side_from_product(keep), side_from_product(hide), product_type=keep.product_type, same_page=same_page,
    )


@dataclass
class PairDecision:
    keep: object
    hide: object
    action: str  # HIDE | REVIEW
    reason: str
    same_page: bool = False


def decide_pairs(pairs: list[tuple]) -> tuple[list[PairDecision], list[tuple[int, int, str]]]:
    """Решения по парам (keep_id, hide_id[, same_page]) и пары, товаров которых нет в базе."""
    from apps.catalog.models import Product

    pairs = [(pair[0], pair[1], bool(pair[2]) if len(pair) > 2 else False) for pair in pairs]
    products = Product.objects.in_bulk({pk for keep_id, hide_id, _same in pairs for pk in (keep_id, hide_id)})
    keep_ids = {keep_id for keep_id, _hide_id, _same in pairs}
    hide_counts: dict[int, int] = {}
    for _keep_id, hide_id, _same in pairs:
        hide_counts[hide_id] = hide_counts.get(hide_id, 0) + 1
    decisions, missing = [], []
    for keep_id, hide_id, same_page in pairs:
        keep, hide = products.get(keep_id), products.get(hide_id)
        if keep is None or hide is None:
            missing.append((keep_id, hide_id, "товара нет в базе"))
            continue
        if hide_id in keep_ids:
            reason = "скрываемая оставляется в другой паре"
        elif hide_counts[hide_id] > 1:
            reason = "скрываемая встречается в нескольких парах"
        else:
            reason = pair_problem(keep, hide, same_page=same_page)
        decisions.append(PairDecision(keep, hide, REVIEW if reason else HIDE, reason or "полный дубль", same_page))
    return decisions, missing


def backup_row(hide, keep) -> dict:
    """Состояние скрываемого товара «до» — для --restore."""
    from apps.catalog.models import ProductSlugHistory

    domain = ilacfiyati_twins.domain_model(hide.product_type)
    domain_rows = list(domain.objects.filter(base_product_id=hide.pk).values("pk", "is_active", "slug"))
    slugs = sorted({
        hide.slug, *(row["slug"] for row in domain_rows),
        # прежние адреса скрываемого: скрытие переводит их на оставленный
        *ProductSlugHistory.objects.filter(product_id=hide.pk).values_list("old_slug", flat=True),
    } - {"", None})
    return {
        "product_id": hide.pk,
        "product_type": hide.product_type,
        "keep_id": keep.pk,
        "is_active": hide.is_active,
        "domain_is_active": [{"pk": row["pk"], "is_active": row["is_active"]} for row in domain_rows],
        "slug_history_before": list(
            ProductSlugHistory.objects.filter(old_slug__in=slugs).values("old_slug", "product_id", "product_type")
        ),
        "slugs": slugs,
    }


def restore_row(row: dict) -> str:
    """Вернуть товар из строки бэкапа: показ и прежние адреса. Пусто — возвращён, иначе — почему нет.

    Возвращается только товар, который до сих пор скрыт этой командой (пометка с тем же
    оставленным): скрытый потом по другой причине (близнец, вручную) не показывается.
    external_data не заменяется снимком — парсер мог обновить его, пока товар был скрыт:
    снимается только пометка. QuerySet.update — как при скрытии.
    """
    from apps.catalog.models import Product, ProductSlugHistory
    from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX

    domain = ilacfiyati_twins.domain_model(row["product_type"])
    with transaction.atomic():
        product = Product.objects.select_for_update().filter(pk=row["product_id"]).first()
        if product is None:
            return "товара нет в базе"
        external = dict(product.external_data) if isinstance(product.external_data, dict) else {}
        if external.get(DUPLICATE_OF_KEY) != row["keep_id"]:
            return "товар не скрыт этой командой (пометки нет) — не трогаем"
        external.pop(DUPLICATE_OF_KEY)
        Product.objects.filter(pk=product.pk).update(is_active=row["is_active"], external_data=external)
        for item in row["domain_is_active"]:
            domain.objects.filter(pk=item["pk"]).update(is_active=item["is_active"])
        ProductSlugHistory.objects.filter(old_slug__in=row["slugs"]).delete()
        for item in row["slug_history_before"]:
            if Product.objects.filter(pk=item["product_id"]).exists():
                ProductSlugHistory.objects.create(**item)
        for slug in row["slugs"]:
            cache.delete(RESOLVE_CACHE_PREFIX + slug)
    return ""


def hide_checked(keep_id: int, hide_id: int, *, same_page: bool) -> str:
    """Скрыть ``hide_id``, перепроверив пару под блокировкой строк; пусто — скрыт, иначе причина.

    Между показом и записью парсер или другая команда могли изменить товары (скрыть
    оставляемый, поменять цену) — решение принимается заново по свежим данным.
    """
    from apps.catalog.models import Product

    with transaction.atomic():
        locked = Product.objects.select_for_update().in_bulk(sorted({keep_id, hide_id}))
        keep, hide = locked.get(keep_id), locked.get(hide_id)
        if keep is None or hide is None:
            return "товара нет в базе"
        reason = pair_problem(keep, hide, same_page=same_page)
        if reason:
            return reason
        ilacfiyati_twins.hide_twin(hide, keep, marker_key=DUPLICATE_OF_KEY)
    return ""
