"""Одинаковые товары FLO и SuperStep: на сайте одно предложение — более дорогое.

Решения владельца 04.11.2026 (reports/superstep-parser-plan-2026-11-04.md, раздел 7.1),
устройство — docs/CROSS_SOURCE_DUPLICATES.md:

1. Тот же товар узнаём по штрихкодам производителя (EAN/UPC) размеров одного цвета;
   запасной признак, когда у одной стороны штрихкодов нет, — бренд + артикул
   производителя (артикул у обоих продавцов уже содержит цвет). По названию не сравниваем.
2. Показываем более дорогое предложение, остальные скрываем (``is_active=False`` у цвета
   + строка ``CrossSourceDuplicate``), ничего не удаляем. Все цвета товара скрыты —
   снимается и сама карточка, её адрес временно ведёт на показанную.
3. Пересчёт после каждого обновления цены: цены поменялись местами — предложения тоже.
4. У более дорогого нет ни одного размера в наличии, а у дешёвого есть — показываем дешёвое.

Сравниваем цену продавца в лирах: наценка у обоих одна (бренд → раздел → общая).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.catalog.models import (
    ClothingProductSize,
    ClothingVariant,
    ClothingVariantSize,
    CrossSourceDuplicate,
    HeadwearProductSize,
    HeadwearVariant,
    HeadwearVariantSize,
    Product,
    ShoeProductSize,
    ShoeVariant,
    ShoeVariantSize,
    UnderwearProductSize,
    UnderwearVariant,
    UnderwearVariantSize,
)

logger = logging.getLogger(__name__)

# Префикс external_id цвета → продавец. Фильтр по префиксу не читает тяжёлый
# Product.external_data (дампы парсеров).
SOURCE_PREFIXES = {"flo-variant-": "flo", "superstep-variant-": "superstep"}
SOURCES = tuple(SOURCE_PREFIXES.values())

TYPE_MODELS = {
    "shoes": (ShoeVariant, ShoeVariantSize, ShoeProductSize),
    "clothing": (ClothingVariant, ClothingVariantSize, ClothingProductSize),
    "headwear": (HeadwearVariant, HeadwearVariantSize, HeadwearProductSize),
    "underwear": (UnderwearVariant, UnderwearVariantSize, UnderwearProductSize),
}

# Сколько общих штрихкодов размеров нужно (у цвета с одним размером — один).
MIN_COMMON_GTINS = 2
# Сколько раз расширять круг при пересчёте одного товара (A ↔ B ↔ C).
MAX_EXPAND_ROUNDS = 5


def enabled() -> bool:
    """Автоматический пересчёт (импорт, проверка карточки, ночь). Команда работает всегда."""
    return bool(getattr(settings, "CROSS_SOURCE_DUPLICATES_ENABLED", False))


def normalize_gtin(value) -> str:
    """EAN-8/UPC-12/EAN-13/GTIN-14 → 14 цифр: UPC Nike у FLO и EAN того же размера совпадут."""
    digits = str(value or "").strip()
    if not digits.isdigit() or not 8 <= len(digits) <= 14 or not digits.strip("0"):
        return ""
    return digits.zfill(14)


def article_key(brand_name, mpn) -> str:
    """Бренд + артикул без знаков: «DV5456-106» у FLO и «DV5456.106» совпадут."""
    brand = re.sub(r"[^0-9a-z]", "", str(brand_name or "").casefold())
    article = re.sub(r"[^0-9A-Z]", "", str(mpn or "").upper())
    if not brand or len(article) < 5:
        return ""
    return f"{brand}|{article}"


def source_of(external_id: str) -> str:
    for prefix, source in SOURCE_PREFIXES.items():
        if str(external_id or "").startswith(prefix):
            return source
    return ""


@dataclass
class Member:
    """Цвет товара одного продавца."""

    variant_id: int
    product_id: int  # Product (базовая строка)
    source: str
    price: Decimal | None
    currency: str
    available: bool
    visible: bool  # variant.is_active
    product_active: bool
    article: str
    gtins: set[str] = field(default_factory=set)
    row: CrossSourceDuplicate | None = None

    def rank(self) -> tuple:
        # Дороже — выше; без цены — ниже всех; при равной цене остаётся показанный.
        return (self.price is not None, self.price or Decimal("0"), self.visible, -self.variant_id)


@dataclass
class Decision:
    product_type: str
    shown: Member
    hidden: list[tuple[Member, str, str]]  # (цвет, match, reason)


def choose_shown(members: list[Member]) -> tuple[Member, str]:
    """Правила 2 и 4: самое дорогое среди тех, у кого есть размеры; нет ни у кого — самое дорогое."""
    in_stock = [m for m in members if m.available]
    shown = max(in_stock or members, key=Member.rank)
    top = max(members, key=Member.rank)
    reason = CrossSourceDuplicate.Reason.PRICE
    if top is not shown and (top.price or 0) > (shown.price or 0):
        reason = CrossSourceDuplicate.Reason.STOCK
    return shown, reason


def build_components(members: Iterable[Member]) -> list[tuple[list[Member], dict[int, str]]]:
    """Группы одинаковых цветов разных продавцов и признак, по которому узнали каждый цвет."""
    members = list(members)
    by_id = {m.variant_id: m for m in members}
    parent = {m.variant_id: m.variant_id for m in members}
    match_of: dict[int, str] = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Member, b: Member, match: str):
        parent[find(a.variant_id)] = find(b.variant_id)
        for m in (a, b):
            if match_of.get(m.variant_id) != CrossSourceDuplicate.Match.EAN:
                match_of[m.variant_id] = match

    common: dict[tuple[int, int], int] = defaultdict(int)
    by_gtin: dict[str, list[Member]] = defaultdict(list)
    for m in members:
        for code in m.gtins:
            by_gtin[code].append(m)
    for rows in by_gtin.values():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a.source != b.source:
                    common[tuple(sorted((a.variant_id, b.variant_id)))] += 1
    for (a_id, b_id), count in common.items():
        a, b = by_id[a_id], by_id[b_id]
        if count >= min(MIN_COMMON_GTINS, len(a.gtins), len(b.gtins)):
            union(a, b, CrossSourceDuplicate.Match.EAN)

    # Запасной признак — только если у одной из сторон штрихкодов нет:
    # разные штрихкоды при одном артикуле — это разные товары.
    by_article: dict[str, list[Member]] = defaultdict(list)
    for m in members:
        if m.article:
            by_article[m.article].append(m)
    for rows in by_article.values():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if a.source != b.source and (not a.gtins or not b.gtins):
                    union(a, b, CrossSourceDuplicate.Match.ARTICLE)

    groups: dict[int, list[Member]] = defaultdict(list)
    for m in members:
        groups[find(m.variant_id)].append(m)
    return [(group, match_of) for group in groups.values() if len(group) > 1]


class CrossSourceDuplicateService:
    def __init__(self, product_types: Iterable[str] = tuple(TYPE_MODELS)):
        self.product_types = [t for t in product_types if t in TYPE_MODELS]

    # --- загрузка -------------------------------------------------------------

    @staticmethod
    def _source_q(variant_model):
        q = Q()
        for prefix in SOURCE_PREFIXES:
            q |= Q(external_id__startswith=prefix)
        return variant_model.objects.filter(q)

    def _load(self, product_type: str, variant_ids=None, product_ids=None) -> dict[int, Member]:
        variant_model, size_model, _ = TYPE_MODELS[product_type]
        qs = self._source_q(variant_model)
        if variant_ids is not None:
            qs = qs.filter(id__in=list(variant_ids))
        if product_ids is not None:
            qs = qs.filter(product__base_product_id__in=list(product_ids))
        rows = qs.values(
            "id", "external_id", "product__base_product_id",
            "product__base_product__is_active", "product__base_product__brand__name",
            "price", "currency", "is_active", "is_available", "mpn",
        )
        members: dict[int, Member] = {}
        for row in rows:
            if not row["product__base_product_id"]:
                continue
            members[row["id"]] = Member(
                variant_id=row["id"],
                product_id=row["product__base_product_id"],
                source=source_of(row["external_id"]),
                price=row["price"],
                currency=(row["currency"] or "").upper(),
                available=bool(row["is_available"]),
                visible=bool(row["is_active"]),
                product_active=bool(row["product__base_product__is_active"]),
                article=article_key(row["product__base_product__brand__name"], row["mpn"]),
            )
        if not members:
            return members
        # Подзапрос, а не список id: при полном проходе цветов десятки тысяч.
        ids = qs.values("id")
        for variant_id, code in size_model.objects.filter(variant_id__in=ids).exclude(gtin="").values_list(
            "variant_id", "gtin"
        ):
            if variant_id in members:
                members[variant_id].gtins.add(code)
        for row in CrossSourceDuplicate.objects.filter(product_type=product_type, hidden_variant_id__in=ids):
            if row.hidden_variant_id in members:
                members[row.hidden_variant_id].row = row
        return members

    def _neighbour_ids(self, product_type: str, members: dict[int, Member]) -> set[int]:
        """Цвета другого продавца, которые могут совпасть с уже загруженными."""
        variant_model, size_model, _ = TYPE_MODELS[product_type]
        ids: set[int] = set()
        gtins = {code for m in members.values() for code in m.gtins}
        if gtins:
            ids.update(size_model.objects.filter(gtin__in=list(gtins)).values_list("variant_id", flat=True))
        articles = {m.article for m in members.values() if m.article}
        if articles:
            # Артикул сравнивается без знаков, а хранится как у продавца («DV5456-106»):
            # в БД отбираем по первым символам, точное сравнение — здесь.
            prefix_q = Q()
            for article in articles:
                prefix_q |= Q(mpn__istartswith=article.split("|", 1)[1][:4])
            candidates = self._source_q(variant_model).filter(prefix_q).values_list(
                "id", "mpn", "product__base_product__brand__name"
            )
            for vid, mpn, brand in candidates:
                if article_key(brand, mpn) in articles:
                    ids.add(vid)
        loaded = set(members)
        rows = CrossSourceDuplicate.objects.filter(product_type=product_type)
        ids.update(rows.filter(shown_variant_id__in=list(loaded)).values_list("hidden_variant_id", flat=True))
        ids.update(
            v for v in rows.filter(hidden_variant_id__in=list(loaded)).values_list("shown_variant_id", flat=True) if v
        )
        return ids - loaded

    def load_members(self, product_type: str, product_ids=None) -> dict[int, Member]:
        if product_ids is None:
            return self._load(product_type)
        members = self._load(product_type, product_ids=product_ids)
        for _ in range(MAX_EXPAND_ROUNDS):
            extra = self._neighbour_ids(product_type, members)
            if not extra:
                break
            members.update(self._load(product_type, variant_ids=extra))
        return members

    # --- решение --------------------------------------------------------------

    @staticmethod
    def _eligible(member: Member, hidden_products: set[int]) -> bool:
        """В сравнении участвуют цвета, которые на сайте или скрыты нами.

        Цвет или карточка, снятые по другой причине (пропал у продавца, скрыт
        владельцем), не участвуют: их пара снова показывается.
        """
        visible_or_ours = member.visible or member.row is not None
        product_ok = member.product_active or member.product_id in hidden_products
        return visible_or_ours and product_ok

    def plan(self, product_type: str, members: dict[int, Member]) -> list[Decision]:
        hidden_products = self._hidden_products(product_type, {m.product_id for m in members.values()})
        eligible = [m for m in members.values() if self._eligible(m, hidden_products)]
        decisions = []
        for group, match_of in build_components(eligible):
            currencies = {m.currency for m in group}
            if len(currencies) > 1:
                logger.warning("cross_source_duplicates: разные валюты в группе %s", [m.variant_id for m in group])
                continue
            shown, reason = choose_shown(group)
            hidden = [
                (m, match_of.get(m.variant_id, CrossSourceDuplicate.Match.EAN), reason)
                for m in group
                if m is not shown
            ]
            decisions.append(Decision(product_type, shown, hidden))
        return decisions

    @staticmethod
    def _hidden_products(product_type: str, product_ids: set[int]) -> set[int]:
        """Карточки, снятые этим механизмом целиком."""
        return set(
            CrossSourceDuplicate.objects.filter(
                product_type=product_type, product_hidden=True, hidden_product_id__in=list(product_ids)
            ).values_list("hidden_product_id", flat=True)
        )

    # --- применение -----------------------------------------------------------

    @transaction.atomic
    def apply(self, product_type: str, members: dict[int, Member], decisions: list[Decision]) -> dict[str, int]:
        variant_model = TYPE_MODELS[product_type][0]
        stats = {"hidden": 0, "shown": 0, "kept": 0}
        # До удаления строк: по ним видно, какие карточки сняты целиком.
        hidden_before = self._hidden_products(product_type, {m.product_id for m in members.values()})
        target: dict[int, tuple[Member, Member, str, str]] = {}
        for decision in decisions:
            for member, match, reason in decision.hidden:
                target[member.variant_id] = (member, decision.shown, match, reason)

        touched_products: set[int] = set()
        for member in members.values():
            if member.variant_id in target:
                _, shown, match, reason = target[member.variant_id]
                values = {
                    "shown_variant_id": shown.variant_id,
                    "shown_product_id": shown.product_id,
                    "hidden_product_id": member.product_id,
                    "match": match,
                    "reason": reason,
                    "hidden_price": member.price,
                    "shown_price": shown.price,
                    "currency": member.currency,
                }
                if member.row is None:
                    CrossSourceDuplicate.objects.update_or_create(
                        product_type=product_type, hidden_variant_id=member.variant_id, defaults=values
                    )
                    stats["hidden"] += 1
                else:
                    CrossSourceDuplicate.objects.filter(pk=member.row.pk).update(**values)
                    stats["kept"] += 1
                if member.visible:
                    variant_model.objects.filter(pk=member.variant_id).update(is_active=False)
                # И без смены цвета: у карточки мог пропасть последний показанный цвет.
                touched_products.add(member.product_id)
            elif member.row is not None:
                # Показанный или больше ни с кем не совпадающий цвет — снова на сайт.
                CrossSourceDuplicate.objects.filter(pk=member.row.pk).delete()
                variant_model.objects.filter(pk=member.variant_id).update(is_active=True)
                stats["shown"] += 1
                touched_products.add(member.product_id)

        for product_id in touched_products:
            self._sync_product(product_type, product_id, was_hidden=product_id in hidden_before)
        return stats

    def _sync_product(self, product_type: str, product_id: int, *, was_hidden: bool) -> None:
        """Карточка без показанных цветов снимается, с показанным цветом — возвращается;
        цена, фото и размеры карточки — по показанным цветам."""
        product_size_model = TYPE_MODELS[product_type][2]
        product = Product.objects.filter(pk=product_id).first()
        if product is None:
            return
        domain = product.domain_item
        if domain is product:
            return
        domain_model = type(domain)
        rows = CrossSourceDuplicate.objects.filter(product_type=product_type, hidden_product_id=product_id)
        active = list(domain.variants.filter(is_active=True).order_by("sort_order", "id"))
        if not active:
            if rows.exists() and (product.is_active or was_hidden):
                Product.objects.filter(pk=product_id).update(is_active=False)
                domain_model.objects.filter(pk=domain.pk).update(is_active=False)
                rows.update(product_hidden=True)
            return
        if was_hidden:
            rows.update(product_hidden=False)
            Product.objects.filter(pk=product_id).update(is_active=True)
            domain_model.objects.filter(pk=domain.pk).update(is_active=True)
        self._refresh_aggregates(product, domain, active, product_size_model)

    @staticmethod
    def _refresh_aggregates(product: Product, domain, active: list, product_size_model) -> None:
        """Как хвост ``ScraperIntegrationService._sync_fashion_variants``, но через update():
        пересчёт может идти после проверки карточки, где сигналы Product не нужны."""
        from apps.scrapers.services import DEFAULT_ASSUMED_STOCK_QUANTITY, ScraperIntegrationService

        default = next((v for v in active if v.price is not None), active[0])
        any_avail = any(v.is_available for v in active)
        total_stock = sum((v.stock_quantity or 0) for v in active if v.stock_quantity)
        stock = DEFAULT_ASSUMED_STOCK_QUANTITY if any_avail else (total_stock if total_stock > 0 else None)
        values = {"price": default.price, "is_available": any_avail, "stock_quantity": stock}
        if default.currency:
            values["currency"] = default.currency
        if default.main_image:
            values["main_image"] = default.main_image
        type(domain).objects.filter(pk=domain.pk).update(**values)
        Product.objects.filter(pk=product.pk).update(**values)
        ScraperIntegrationService()._sync_product_size_rows(domain, product_size_model, variants=active)

    # --- точки входа ----------------------------------------------------------

    def resolve(self, product_ids=None, *, dry_run: bool = False) -> dict:
        """Пересчёт для товаров (или всего каталога FLO + SuperStep при product_ids=None)."""
        report = {"groups": 0, "hidden": 0, "shown": 0, "kept": 0, "decisions": []}
        for product_type in self.product_types:
            members = self.load_members(product_type, product_ids)
            if not members:
                continue
            decisions = self.plan(product_type, members)
            report["groups"] += len(decisions)
            report["decisions"].extend(decisions)
            if dry_run:
                continue
            stats = self.apply(product_type, members, decisions)
            for key in ("hidden", "shown", "kept"):
                report[key] += stats[key]
        return report

    def unhide_all(self) -> int:
        """Откат: все скрытые этим механизмом цвета и карточки — снова на сайт."""
        count = 0
        for product_type in self.product_types:
            members = self._load(
                product_type,
                variant_ids=CrossSourceDuplicate.objects.filter(product_type=product_type).values_list(
                    "hidden_variant_id", flat=True
                ),
            )
            count += self.apply(product_type, members, [])["shown"]
        # Строки без цвета (вариант удалён) — просто убрать.
        CrossSourceDuplicate.objects.all().delete()
        return count


def resolve_for_products(product_ids: Iterable[int]) -> None:
    """Пересчёт после обновления цены/наличия товара. Ошибка не ломает импорт и проверку карточки."""
    ids = [pid for pid in product_ids if pid]
    if not ids or not enabled():
        return
    product_types = set(
        Product.objects.filter(pk__in=ids, product_type__in=list(TYPE_MODELS)).values_list("product_type", flat=True)
    )
    if not product_types:
        return
    try:
        CrossSourceDuplicateService(product_types).resolve(ids)
    except Exception:
        logger.exception("cross_source_duplicates: пересчёт для %s не удался", ids)


def hidden_variant_ids(product_type: str, variant_ids: Iterable[int]) -> set[int]:
    """Цвета, скрытые как дубль: парсер и проверка карточки не возвращают их на сайт сами."""
    ids = [v for v in variant_ids if v]
    if product_type not in TYPE_MODELS or not ids:
        return set()
    return set(
        CrossSourceDuplicate.objects.filter(product_type=product_type, hidden_variant_id__in=ids).values_list(
            "hidden_variant_id", flat=True
        )
    )


def duplicate_redirect_target(slug: str) -> tuple[str, str] | None:
    """Скрытая карточка или скрытый цвет → (slug показанной карточки, slug показанного цвета).

    Для resolve: адрес скрытого дубля временно ведёт на показанный, а не отдаёт 404.
    """
    if not slug:
        return None
    row = None
    product = Product.objects.filter(slug=slug, is_active=False).only("id").first()
    if product is not None:
        row = (
            CrossSourceDuplicate.objects.filter(hidden_product=product, product_hidden=True)
            .order_by("-updated_at")
            .first()
        )
    if row is None:
        for product_type, (variant_model, _, _) in TYPE_MODELS.items():
            variant_id = variant_model.objects.filter(slug=slug, is_active=False).values_list("id", flat=True).first()
            if variant_id:
                row = CrossSourceDuplicate.objects.filter(
                    product_type=product_type, hidden_variant_id=variant_id
                ).first()
                if row is not None:
                    break
    if row is None or row.shown_product_id is None:
        return None
    shown = Product.objects.filter(pk=row.shown_product_id, is_active=True).values_list("slug", flat=True).first()
    if not shown:
        return None
    variant_model = TYPE_MODELS[row.product_type][0]
    variant_slug = (
        variant_model.objects.filter(pk=row.shown_variant_id, is_active=True).values_list("slug", flat=True).first()
        or ""
    )
    return shown, variant_slug
