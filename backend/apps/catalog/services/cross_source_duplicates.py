"""Одинаковые товары FLO и SuperStep: на сайте одно предложение — более дорогое.

Решения владельца 04.11.2026 (reports/superstep-parser-plan-2026-11-04.md, раздел 7.1),
устройство — docs/CROSS_SOURCE_DUPLICATES.md:

1. Тот же товар узнаём по штрихкодам производителя (EAN/UPC) размеров одного цвета;
   запасной признак, когда у одной стороны штрихкодов нет, — бренд + артикул
   производителя + цвет. По названию не сравниваем. В группе не больше одного цвета
   от каждого продавца: сомнительная группа (цепочка A ↔ B ↔ C) не объединяется.
2. Показываем более дорогое предложение, остальные скрываем (``is_active=False`` у цвета
   + строка ``CrossSourceDuplicate``), ничего не удаляем. Все цвета товара скрыты —
   снимается и сама карточка, её адрес временно ведёт на показанную.
3. Пересчёт после каждого обновления цены: цены поменялись местами — предложения тоже.
4. У более дорогого нет ни одного размера в наличии, а у дешёвого есть — показываем дешёвое.
   Размеров нет ни у кого — остаётся показанный сейчас (впервые — более дорогой).

«Скрыт нами» = есть строка CrossSourceDuplicate. Цвет, снятый продавцом (пропал из
карточки), и карточку, снятую «Неактуальными», механизм на сайт не возвращает: строка
удаляется (``forget_hidden_variants``) или снимается признак карточки
(``on_product_retired``). Скрытый цвет возвращается на сайт, только если продавец
недавно подтвердил его (``verify_hidden_duplicate``: живая проверка предложения или
свежий импорт); до подтверждения остаётся показанным текущий. Пересчёт идёт короткими
транзакциями под ``pg_advisory_xact_lock``, перед записью цвета и строки группы
перечитываются ``select_for_update``.

Сравниваем цену на сайте: цену продавца в лирах с нашей наценкой (бренд → раздел →
общая, ``get_effective_product_markup``). Наценка у двух предложений может различаться:
товар FLO и SuperStep ложится в разные разделы (и в разные строки бренда), у раздела
бывает своя наценка (``--section-markup``). Курс валюты у обоих один, порядок не меняет.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import (
    Brand,
    ClothingProductSize,
    ClothingVariant,
    ClothingVariantSize,
    CrossSourceDuplicate,
    HeadwearProductSize,
    HeadwearVariant,
    HeadwearVariantSize,
    Product,
    ProductSourceOffer,
    ShoeProductSize,
    ShoeVariant,
    ShoeVariantSize,
    UnderwearProductSize,
    UnderwearVariant,
    UnderwearVariantSize,
)
from apps.catalog.utils.product_markup import apply_markup_percent, get_effective_product_markup

logger = logging.getLogger(__name__)

# Префикс external_id цвета → продавец. Фильтр по префиксу не читает тяжёлый
# Product.external_data (дампы парсеров). Новый источник — docs/CROSS_SOURCE_DUPLICATES.md,
# «Как подключить новый источник к поиску дублей».
SOURCE_PREFIXES = {"flo-variant-": "flo", "superstep-variant-": "superstep"}
SOURCES = tuple(SOURCE_PREFIXES.values())
# Названия продавцов для отчёта (не путать с models_stock.SOURCE_TITLES ночной сверки).
SELLER_TITLES = {"flo": "FLO", "superstep": "SuperStep"}

TYPE_MODELS = {
    "shoes": (ShoeVariant, ShoeVariantSize, ShoeProductSize),
    "clothing": (ClothingVariant, ClothingVariantSize, ClothingProductSize),
    "headwear": (HeadwearVariant, HeadwearVariantSize, HeadwearProductSize),
    "underwear": (UnderwearVariant, UnderwearVariantSize, UnderwearProductSize),
}

# Сколько общих штрихкодов размеров нужно (один — только если у обоих цветов по одному).
MIN_COMMON_GTINS = 2
# Предохранитель расширения круга при пересчёте одного товара (A ↔ B ↔ C): обычно
# новых цветов нет уже на втором круге.
MAX_EXPAND_ROUNDS = 20
# Ключ pg_advisory_xact_lock: пересчёты (импорты, проверка карточки, ночь) идут по одному.
LOCK_KEY = 730_505_001
# Полный проход — пачками товаров, каждая своей короткой транзакцией: импорт ждёт
# блокировку не дольше одной пачки.
FULL_PASS_BATCH = 200
# Сколько живёт подтверждение продавца для возврата скрытого цвета на сайт.
CONFIRM_TTL = timedelta(hours=6)
# Без живой проверки источника подтверждением считается свежий импорт карточки.
IMPORT_CONFIRM_TTL = timedelta(hours=48)
VERIFY_DEDUPE_SECONDS = 30 * 60


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


_TR_FOLD = str.maketrans("ıİşŞçÇğĞöÖüÜ", "iissccggoouu")


def color_key(color) -> str:
    """Цвет целиком без регистра, знаков и турецких букв: «BEYAZ» = «Beyaz»,
    «Açık Gri» ≠ «Açık Mavi», «Beyaz-Siyah» ≠ «Beyaz». Сомнение — не объединяем."""
    return " ".join(re.findall(r"[a-z0-9]+", str(color or "").translate(_TR_FOLD).casefold()))


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
    brand_name: str = ""
    color: str = ""
    site_price: Decimal | None = None  # цена продавца с нашей наценкой
    gtins: set[str] = field(default_factory=set)
    row: CrossSourceDuplicate | None = None

    def rank(self) -> tuple:
        # Дороже — выше; без цены — ниже всех; при равной цене остаётся показанный.
        return (self.site_price is not None, self.site_price or Decimal("0"), self.visible, -self.variant_id)

    def showable(self, now) -> bool:
        """На сайте сейчас — или скрыт нами, но продавец недавно подтвердил его."""
        if self.row is None:
            return True
        return bool(self.row.confirmed_at and self.row.confirmed_at >= now - CONFIRM_TTL)


@dataclass
class Decision:
    product_type: str
    shown: Member
    hidden: list[tuple[Member, str, str]]  # (цвет, match, reason)


@dataclass
class Plan:
    decisions: list[Decision] = field(default_factory=list)
    # Не трогать: группа ждёт подтверждения продавца или сомнительна.
    frozen: set[int] = field(default_factory=set)
    # Скрытые цвета, которые нужно проверить у продавца, прежде чем вернуть.
    verify: set[int] = field(default_factory=set)


def choose_shown(members: list[Member]) -> tuple[Member, str]:
    """Правила 2 и 4: самое дорогое среди тех, у кого есть размеры.

    Размеров нет ни у кого — остаётся показанный сейчас: скрытый нами цвет без размеров
    может быть уже снят у продавца, менять одно «нет в наличии» на другое незачем.
    """
    in_stock = [m for m in members if m.available]
    if in_stock:
        shown = max(in_stock, key=Member.rank)
    else:
        shown = max([m for m in members if m.row is None] or members, key=Member.rank)
    top = max(members, key=Member.rank)
    reason = CrossSourceDuplicate.Reason.PRICE
    if top is not shown and (top.site_price or 0) > (shown.site_price or 0):
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

    by_gtin: dict[str, list[Member]] = defaultdict(list)
    for m in members:
        for code in m.gtins:
            by_gtin[code].append(m)
    # Штрихкод у двух цветов одного продавца (ошибка данных маркетплейса) — сомнительный,
    # по нему не сравниваем.
    usable = {
        code: rows for code, rows in by_gtin.items() if len({m.source for m in rows}) == len(rows)
    }
    usable_count: dict[int, int] = defaultdict(int)
    for rows in usable.values():
        for m in rows:
            usable_count[m.variant_id] += 1
    common: dict[tuple[int, int], int] = defaultdict(int)
    for rows in usable.values():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                common[tuple(sorted((a.variant_id, b.variant_id)))] += 1
    for (a_id, b_id), count in common.items():
        a, b = by_id[a_id], by_id[b_id]
        single = usable_count[a_id] == usable_count[b_id] == 1
        if count >= MIN_COMMON_GTINS or (count == 1 and single):
            union(a, b, CrossSourceDuplicate.Match.EAN)

    # Запасной признак — только если у одной из сторон штрихкодов нет (разные штрихкоды
    # при одном артикуле — разные товары) и с тем же цветом: у части артикулов
    # (adidas «B75806») цвета в коде нет.
    by_article: dict[str, list[Member]] = defaultdict(list)
    for m in members:
        if m.article:
            by_article[m.article].append(m)
    for rows in by_article.values():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if (
                    a.source != b.source
                    and (not a.gtins or not b.gtins)
                    and color_key(a.color)
                    and color_key(a.color) == color_key(b.color)
                ):
                    union(a, b, CrossSourceDuplicate.Match.ARTICLE)

    groups: dict[int, list[Member]] = defaultdict(list)
    for m in members:
        groups[find(m.variant_id)].append(m)
    result = []
    for group in groups.values():
        if len(group) < 2:
            continue
        if len({m.source for m in group}) != len(group):
            # Два цвета одного продавца в группе — склейка через третий; не объединяем.
            logger.info("cross_source_duplicates: сомнительная группа %s", sorted(m.variant_id for m in group))
            continue
        result.append((group, match_of))
    return result


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
            "price", "currency", "is_active", "is_available", "mpn", "color",
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
                brand_name=row["product__base_product__brand__name"] or "",
                color=row["color"] or "",
            )
        if not members:
            return members
        self._attach_site_prices(members.values())
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

    @staticmethod
    def _attach_site_prices(members: Iterable[Member]) -> None:
        """Цена на сайте = цена продавца × наценка карточки (одна на бренд + раздел)."""
        members = list(members)
        margins: dict[tuple, Decimal] = {}
        by_product: dict[int, Decimal] = {}
        products = Product.objects.filter(pk__in={m.product_id for m in members}).select_related(
            "brand", "category"
        ).only(  # без тяжёлого external_data карточки
            "id", "brand", "category", "brand__margin_percent", "category__margin_percent", "category__parent"
        )
        for product in products:
            key = (product.brand_id, product.category_id)
            if key not in margins:
                margins[key] = get_effective_product_markup(product)[0]
            by_product[product.pk] = margins[key]
        for m in members:
            if m.price is not None:
                m.site_price = apply_markup_percent(m.price, by_product.get(m.product_id, Decimal("0")))

    def _neighbour_ids(self, product_type: str, members: dict[int, Member]) -> set[int]:
        """Цвета другого продавца, которые могут совпасть с уже загруженными."""
        variant_model, size_model, _ = TYPE_MODELS[product_type]
        ids: set[int] = set()
        source_variants = self._source_q(variant_model)
        gtins = {code for m in members.values() for code in m.gtins}
        if gtins:
            ids.update(
                size_model.objects.filter(gtin__in=list(gtins), variant__in=source_variants).values_list(
                    "variant_id", flat=True
                )
            )
        articles = {m.article for m in members.values() if m.article}
        if articles:
            # Артикул сравнивается без знаков, а хранится как у продавца («DV5456-106»):
            # в БД отбираем цвета тех же брендов (индекс Product.brand), точное сравнение — здесь.
            brand_q = Q()
            for name in {m.brand_name for m in members.values() if m.article}:
                brand_q |= Q(name__iexact=name)
            brand_ids = list(Brand.objects.filter(brand_q).values_list("id", flat=True))
            candidates = (
                source_variants.filter(product__base_product__brand_id__in=brand_ids)
                .exclude(mpn="")
                .values_list("id", "mpn", "product__base_product__brand__name")
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
        attempted = set(members)
        for _ in range(MAX_EXPAND_ROUNDS):
            # attempted: id, которые не загрузились (цвет удалён), не ищем по кругу.
            extra = self._neighbour_ids(product_type, members) - attempted
            if not extra:
                return members
            attempted |= extra
            members.update(self._load(product_type, variant_ids=extra))
        logger.warning("cross_source_duplicates: круг товаров %s не замкнулся за %s шагов", product_ids, MAX_EXPAND_ROUNDS)
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

    def plan(self, product_type: str, members: dict[int, Member], *, hide_new: bool = True) -> Plan:
        """hide_new=False — как в apply: проверку у продавца ставим, только если её итог
        может что-то изменить (у FLO это платный запрос через прокси)."""
        now = timezone.now()
        hidden_products = self._hidden_products(product_type, {m.product_id for m in members.values()})
        eligible = [m for m in members.values() if self._eligible(m, hidden_products)]
        plan = Plan()
        grouped: set[int] = set()
        for group, match_of in build_components(eligible):
            grouped.update(m.variant_id for m in group)
            currencies = {m.currency for m in group}
            if len(currencies) > 1:
                logger.warning("cross_source_duplicates: разные валюты в группе %s", [m.variant_id for m in group])
                plan.frozen.update(m.variant_id for m in group)
                continue
            shown, reason = choose_shown(group)
            if not shown.showable(now):
                # Вернуть скрытый цвет можно только после подтверждения продавца; пока —
                # лучший из тех, кто может быть на сайте, или группа без изменений.
                # Без новых скрытий возврат возможен, только если показанного в группе нет.
                if hide_new or all(m.row is not None for m in group if m is not shown):
                    plan.verify.add(shown.variant_id)
                candidates = [m for m in group if m.showable(now)]
                if not candidates:
                    plan.frozen.update(m.variant_id for m in group)
                    continue
                shown, reason = choose_shown(candidates)
            hidden = [
                (m, match_of.get(m.variant_id, CrossSourceDuplicate.Match.EAN), reason)
                for m in group
                if m is not shown
            ]
            plan.decisions.append(Decision(product_type, shown, hidden))
        # Скрытый цвет без пары (показанный снят) возвращается тоже только после проверки.
        for m in eligible:
            if m.variant_id not in grouped and not m.showable(now):
                plan.verify.add(m.variant_id)
                plan.frozen.add(m.variant_id)
        return plan

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
    def apply(
        self,
        product_type: str,
        members: dict[int, Member],
        plan: Plan,
        *,
        hide_new: bool = True,
    ) -> dict[str, int]:
        """hide_new=False (автопересчёт выключен): новых скрытий нет, только поддержка
        уже скрытого — группа, где пришлось бы скрыть ещё один цвет, не меняется."""
        variant_model = TYPE_MODELS[product_type][0]
        # id цветов, а не счётчики: в полном проходе группа может попасть в две пачки.
        stats: dict[str, set[int]] = {"hidden": set(), "shown": set(), "kept": set()}
        # До удаления строк: по ним видно, какие карточки сняты целиком.
        hidden_before = self._hidden_products(product_type, {m.product_id for m in members.values()})
        # Перечитать цвета и строки под блокировкой: план мог устареть, пока шла загрузка
        # (импорт снял цвет и удалил его строку). Группа, где показывать уже некого, не
        # применяется — оба цвета не скрываются; цвет, строку которого удалил импорт,
        # не включается.
        fresh = dict(
            variant_model.objects.select_for_update().filter(pk__in=list(members)).values_list("id", "is_active")
        )
        fresh_rows = set(
            CrossSourceDuplicate.objects.select_for_update()
            .filter(product_type=product_type, hidden_variant_id__in=list(members))
            .values_list("hidden_variant_id", flat=True)
        )
        frozen = set(plan.frozen)
        target: dict[int, tuple[Member, Member, str, str]] = {}
        for decision in plan.decisions:
            shown = decision.shown
            ids = {shown.variant_id, *(m.variant_id for m, _, _ in decision.hidden)}
            shown_ok = fresh.get(shown.variant_id) or (
                shown.variant_id in fresh and shown.row is not None and shown.variant_id in fresh_rows
            )
            if not shown_ok:
                logger.warning("cross_source_duplicates: показанный цвет %s уже снят, группа пропущена", shown.variant_id)
                frozen |= ids
                continue
            if not hide_new and any(m.row is None for m, _, _ in decision.hidden):
                frozen |= ids
                continue
            for member, match, reason in decision.hidden:
                target[member.variant_id] = (member, shown, match, reason)
        now = timezone.now()

        touched_products: set[int] = set()
        for member in members.values():
            if member.variant_id not in fresh:
                continue
            if member.variant_id in frozen or (member.row is not None and member.variant_id not in fresh_rows):
                # Видимость не меняем (группа ждёт проверки или цвет снят продавцом), но
                # цену и наличие карточки пересчитываем по показанным цветам: проверка
                # карточки пишет их по всем цветам, включая скрытый.
                if member.row is not None:
                    touched_products.add(member.product_id)
                continue
            if member.variant_id in target:
                _, shown, match, reason = target[member.variant_id]
                values = {
                    "shown_variant_id": shown.variant_id,
                    "shown_product_id": shown.product_id,
                    "hidden_product_id": member.product_id,
                    "match": match,
                    "reason": reason,
                    "hidden_price": member.site_price,
                    "shown_price": shown.site_price,
                    "currency": member.currency,
                }
                if member.row is None:
                    CrossSourceDuplicate.objects.update_or_create(
                        product_type=product_type, hidden_variant_id=member.variant_id, defaults=values
                    )
                    stats["hidden"].add(member.variant_id)
                else:
                    CrossSourceDuplicate.objects.filter(pk=member.row.pk).update(**values, updated_at=now)
                    stats["kept"].add(member.variant_id)
                if fresh[member.variant_id]:
                    variant_model.objects.filter(pk=member.variant_id).update(is_active=False, updated_at=now)
                # И без смены цвета: у карточки мог пропасть последний показанный цвет.
                touched_products.add(member.product_id)
            elif member.row is not None:
                # Показанный (подтверждённый продавцом) или цвет снятой не нами карточки.
                CrossSourceDuplicate.objects.filter(pk=member.row.pk).delete()
                variant_model.objects.filter(pk=member.variant_id).update(is_active=True, updated_at=now)
                stats["shown"].add(member.variant_id)
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
        now = timezone.now()
        rows = CrossSourceDuplicate.objects.filter(product_type=product_type, hidden_product_id=product_id)
        active = list(domain.variants.filter(is_active=True).order_by("sort_order", "id"))
        if not active:
            if rows.exists() and (product.is_active or was_hidden):
                Product.objects.filter(pk=product_id).update(is_active=False, updated_at=now)
                domain_model.objects.filter(pk=domain.pk).update(is_active=False, updated_at=now)
                rows.update(product_hidden=True)
            return
        if was_hidden:
            rows.update(product_hidden=False)
            Product.objects.filter(pk=product_id).update(is_active=True, updated_at=now)
            domain_model.objects.filter(pk=domain.pk).update(is_active=True, updated_at=now)
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
        current = Product.objects.filter(pk=product.pk).values(*values).first() or {}
        if any(current.get(key) != value for key, value in values.items()):
            values["updated_at"] = timezone.now()
            type(domain).objects.filter(pk=domain.pk).update(**values)
            Product.objects.filter(pk=product.pk).update(**values)
        ScraperIntegrationService()._sync_product_size_rows(domain, product_size_model, variants=active)

    # --- точки входа ----------------------------------------------------------

    @staticmethod
    def _lock() -> None:
        """Один пересчёт за раз: два параллельных импорта не скроют оба цвета по старым планам."""
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_KEY])

    @staticmethod
    def _add_decisions(acc: dict, product_type: str, plan: Plan) -> None:
        for decision in plan.decisions:
            key = (product_type, frozenset(m.variant_id for m in [decision.shown, *(h[0] for h in decision.hidden)]))
            acc["decisions"][key] = decision  # группа из двух пачек — одна, решение последней
        acc["verify"] |= {(product_type, vid) for vid in plan.verify}

    def _resolve_batch(self, product_type: str, product_ids, *, hide_new: bool, acc: dict) -> None:
        with transaction.atomic():
            self._lock()
            members = self.load_members(product_type, product_ids)
            if not members:
                return
            plan = self.plan(product_type, members, hide_new=hide_new)
            stats = self.apply(product_type, members, plan, hide_new=hide_new)
        self._add_decisions(acc, product_type, plan)
        for key in ("hidden", "shown", "kept"):
            acc[key] |= {(product_type, vid) for vid in stats[key]}

    def resolve(self, product_ids=None, *, dry_run: bool = False, hide_new: bool = True) -> dict:
        """Пересчёт для товаров (или всего каталога FLO + SuperStep при product_ids=None)."""
        acc = {"decisions": {}, "verify": set(), "hidden": set(), "shown": set(), "kept": set()}
        for product_type in self.product_types:
            if product_ids is not None and not dry_run:
                self._resolve_batch(product_type, product_ids, hide_new=hide_new, acc=acc)
                continue
            # Отчёт и полный проход: сначала план без блокировки — по нему видно, какие
            # товары затронуты; запись — пачками, каждая своей транзакцией с перепроверкой.
            members = self.load_members(product_type, product_ids)
            if not members:
                continue
            plan = self.plan(product_type, members, hide_new=hide_new)
            if dry_run:
                self._add_decisions(acc, product_type, plan)
                continue
            involved = sorted(
                {m.product_id for d in plan.decisions for m in [d.shown, *(h[0] for h in d.hidden)]}
                | {m.product_id for m in members.values() if m.row is not None}
            )
            for start in range(0, len(involved), FULL_PASS_BATCH):
                self._resolve_batch(
                    product_type, involved[start:start + FULL_PASS_BATCH], hide_new=hide_new, acc=acc
                )
        if acc["verify"] and not dry_run:
            request_verification(acc["verify"])
        # Скрытый в одной пачке и оставленный скрытым в следующей — «скрыт», не «оставлен».
        kept = acc["kept"] - acc["hidden"]
        return {
            "groups": len(acc["decisions"]),
            "decisions": list(acc["decisions"].values()),
            "verify": acc["verify"],
            "hidden": len(acc["hidden"]),
            "shown": len(acc["shown"]),
            "kept": len(kept),
        }

    @transaction.atomic
    def unhide_all(self) -> int:
        """Откат: все скрытые этим механизмом цвета и карточки — снова на сайт, без проверок."""
        self._lock()
        count = 0
        for product_type in self.product_types:
            members = self._load(
                product_type,
                variant_ids=CrossSourceDuplicate.objects.filter(product_type=product_type).values_list(
                    "hidden_variant_id", flat=True
                ),
            )
            count += len(self.apply(product_type, members, Plan())["shown"])
        # Строки без цвета (вариант удалён) выбранных типов — просто убрать.
        CrossSourceDuplicate.objects.filter(product_type__in=self.product_types).delete()
        return count


def resolve_for_products(product_ids: Iterable[int]) -> None:
    """Пересчёт после обновления цены/наличия товара. Ошибка не ломает импорт и проверку карточки.

    Автопересчёт выключен — только поддержка уже скрытого (без новых скрытий): карточки со
    скрытыми цветами получают цену и наличие по показанным, а пара снятой карточки
    возвращается (после подтверждения продавца).
    """
    ids = [pid for pid in product_ids if pid]
    if not ids:
        return
    product_types = set(
        Product.objects.filter(pk__in=ids, product_type__in=list(TYPE_MODELS)).values_list("product_type", flat=True)
    )
    if not product_types:
        return
    try:
        service = CrossSourceDuplicateService(product_types)
        if enabled():
            service.resolve(ids)
        elif CrossSourceDuplicate.objects.filter(Q(hidden_product_id__in=ids) | Q(shown_product_id__in=ids)).exists():
            service.resolve(ids, hide_new=False)
    except Exception:
        logger.exception("cross_source_duplicates: пересчёт для %s не удался", ids)


def request_verification(items: Iterable[tuple[str, int]]) -> None:
    """Поставить проверку скрытых цветов у продавца (не чаще раза в 30 минут на цвет)."""
    from apps.catalog.tasks import verify_hidden_duplicate_task

    def enqueue(product_type: str, variant_id: int) -> None:
        # Ключ — после коммита: откат транзакции не должен на 30 минут запретить проверку.
        if cache.add(f"v1:xsdup:verify:{product_type}:{variant_id}", 1, VERIFY_DEDUPE_SECONDS):
            verify_hidden_duplicate_task.delay(product_type, variant_id)

    for product_type, variant_id in items:
        transaction.on_commit(lambda pt=product_type, vid=variant_id: enqueue(pt, vid))


def _check_at_seller(row: CrossSourceDuplicate, variant) -> str:
    """found / gone / unknown: есть ли цвет у продавца сейчас.

    Живая проверка — одно сохранённое предложение этого цвета (``check_offer`` источника);
    размер — тот, что был в наличии. Источник без живой проверки — подтверждением
    считается свежий импорт карточки, где цвет был в наличии.
    """
    from apps.catalog.services.source_offer_verification import SourceOfferVerificationService
    from apps.scrapers.base.offers import OfferAvailability, OfferCheckErrorCode

    verifier = SourceOfferVerificationService()
    sizes = variant.sizes.all()
    available_sizes = {s.size for s in sizes if s.is_available}
    offers = sorted(
        ProductSourceOffer.objects.filter(
            product_id=row.hidden_product_id, is_active=True, variant_key=variant.external_id
        ),
        key=lambda o: (o.size_key not in available_sizes, o.priority, o.pk),
    )
    offer = next((o for o in offers if verifier.is_enabled_for(o.parser_key)), None)
    if offer is not None:
        result = verifier.verify(offer, force=True)
        if result.is_success:
            if result.availability_status == OfferAvailability.DISCONTINUED:
                return "gone"
            return "found"
        if result.error and result.error.code in (OfferCheckErrorCode.NOT_FOUND, OfferCheckErrorCode.GONE):
            return "gone"
        return "unknown"
    synced = Product.objects.filter(pk=row.hidden_product_id).values_list("last_synced_at", flat=True).first()
    if synced and synced >= timezone.now() - IMPORT_CONFIRM_TTL and variant.is_available:
        return "found"
    return "unknown"


def verify_hidden_duplicate(product_type: str, variant_id: int) -> str:
    """Проверить скрытый цвет у продавца перед возвратом на сайт.

    found — подтверждение на CONFIRM_TTL и пересчёт; gone — цвет снят продавцом, строка
    удаляется, на сайт он не вернётся; unknown — ничего не меняем (повтор позже),
    показанным остаётся текущий.
    """
    if product_type not in TYPE_MODELS:
        return "unknown"
    variant_model = TYPE_MODELS[product_type][0]
    row = CrossSourceDuplicate.objects.filter(product_type=product_type, hidden_variant_id=variant_id).first()
    variant = variant_model.objects.filter(pk=variant_id).first()
    if row is None or variant is None:
        return "unknown"
    outcome = _check_at_seller(row, variant)
    if outcome == "found":
        CrossSourceDuplicate.objects.filter(pk=row.pk).update(confirmed_at=timezone.now())
    elif outcome == "gone":
        variant_model.objects.filter(pk=variant_id).update(
            is_available=False, stock_quantity=0, updated_at=timezone.now()
        )
        forget_hidden_variants(product_type, [variant_id])
    if outcome != "unknown":
        resolve_for_products([row.hidden_product_id])
    return outcome


def forget_hidden_variants(product_type: str, variant_ids: Iterable[int]) -> None:
    """Цвет пропал у продавца: он больше не «скрыт нами», а снят — на сайт не возвращаем."""
    ids = [v for v in variant_ids if v]
    if product_type in TYPE_MODELS and ids:
        CrossSourceDuplicate.objects.filter(product_type=product_type, hidden_variant_id__in=ids).delete()


def on_product_retired(product_id: int) -> None:
    """Карточку сняли «Неактуальные товары»: механизм её больше не возвращает, а пара
    этой карточки (если та была показанной) снова показывается — и при выключенном
    автопересчёте, после подтверждения продавца."""
    CrossSourceDuplicate.objects.filter(hidden_product_id=product_id).update(product_hidden=False)
    resolve_for_products([product_id])


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
