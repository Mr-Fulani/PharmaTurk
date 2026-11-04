"""Две страницы ilacfiyati одного препарата («близнецы») — один товар на сайте.

У импортного препарата без турецкого штрихкода ilacfiyati держит две страницы с одним
служебным номером «1111111…»: страницу фирмы с ценой (часто в €) и страницу TEB
с «0,00 TL». Товар у нас определяется ссылкой источника, поэтому вторая страница
становилась вторым товаром «Цена по запросу». Изредка так же дублируется и настоящий
штрихкод 869….

Правило (docs/ILACFIYATI_TWIN_PAGES.md): у страниц одного штрихкода, совпадающих по
названию в источнике (препарат, дозировка, форма, количество) и составу, остаётся
одна — с ценой, при равенстве — более ранняя. Остальные скрываются
(``is_active=False``, ничего не удаляется), их адрес ведёт 301 на оставленную.
Любое расхождение — «на проверку человеку», ничего не скрывается.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

HIDE = "hide"
REVIEW = "review"
# Пометка в external_data скрытого близнеца: pk оставленного товара.
TWIN_OF_KEY = "ilacfiyati_twin_of"

_TR_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c", "µ": "mc", "μ": "mc", "×": "x",
})
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+")
_THOUSANDS_RE = re.compile(r"\d{1,3}(?:\.\d{3})+")
# Одно и то же разными словами и языками: страница фирмы и страница TEB пишут
# «30 TB» и «30 TABLETS», «TOZ» и «POWDER». Ампула и флакон — одна форма: страница TEB
# называет «AMP.» любую инъекционную упаковку, у той же страницы фирмы — «VIAL»
# (на проде 04.11 — 22 пары). Таблетка и капсула — разные формы: такие пары на проверку.
_SYNONYM_GROUPS = {
    "tablet": ("tb", "tbl", "tablets", "tabs", "tab", "tabletten", "tablette", "filmtabletten",
               "drj", "draje", "dragee"),
    "kapsul": ("kaps", "kap", "cap", "caps", "capsul", "capsule", "capsules", "kapseln", "kapsel"),
    "flakon": ("flk", "vial", "vials", "vyal", "durchstechflasche", "durchstechflaschen",
               "amp", "ampul", "ampule", "ampulle", "ampullen", "ampoule", "ampoules"),
    "powder": ("toz", "pow", "pwdr", "pulver", "povder"),
    "sachet": ("sachets", "sacht", "poset", "sase"),
    "solution": ("sol", "solusyon", "cozelti", "losung"),
    "suspension": ("susp", "suspansiyon"),
    "granule": ("granul", "granules", "granulat"),
    "vaccine": ("asi",),
    "g": ("gr", "gram", "gramm"),
    "mg": ("mgr",),
    "mcg": ("ug", "mcgr", "mikrogramm"),
    "damla": ("drops",),
    "surup": ("syrup",),
    "krem": ("cream",),
}
_SYNONYMS = {alias: word for word, aliases in _SYNONYM_GROUPS.items() for alias in aliases}
# Слова, которые не отличают упаковку: «пленочное покрытие», «штук», союзы. «ORAL» отличает:
# «ORAL SOLUTION» и «SOLUTION» (инъекция) — разные формы.
_FILLER = {"film", "kapli", "coated", "fc", "adet", "and", "ve", "with", "x"}
# Единицы, к которым привязано число: «25 MG 50 TABLET» и «50 MG 25 TABLET» — разные упаковки.
_UNITS = {"mg", "mcg", "g", "kg", "ml", "l", "iu", "ui", "ie", "u", "mmol", "meq", "oz"}
_INGREDIENT_FILLER = {"and", "ve", "with", "ile"}
_INGREDIENT_SYNONYMS = {"asit": "acid", "asidi": "acid"}
# Транслитерация: страницы пишут вещество по-турецки и по-английски
# («Lityum Karbonat» / «Lithium Carbonate», «Sultiam» / «Sulthiame»).
_SPELLING = (("ph", "f"), ("th", "t"), ("w", "v"), ("y", "i"), ("j", "g"))
# «1X15» — то же, что «15».
_SINGLE_PACK_RE = re.compile(r"(?<![\d.,])1\s*x\s*(?=\d)")
# «-2» в конце адреса ilacfiyati — номер повтора страницы, а не дозировка.
_URL_REPEAT_SUFFIX_RE = re.compile(r"(?<=[a-z])-\d+$")


def _fold(text: str) -> str:
    return str(text or "").translate(_TR_FOLD).casefold()


def _spelling(word: str) -> str:
    for old, new in _SPELLING:
        word = word.replace(old, new)
    word = re.sub(r"c(?=[ei])", "s", word).replace("c", "k")
    word = re.sub(r"(.)\1+", r"\1", word)
    for ending in ("s", "e"):
        if len(word) > 4 and word.endswith(ending):
            word = word[:-1]
    return word


def _number(raw: str) -> str:
    if _THOUSANDS_RE.fullmatch(raw):
        raw = raw.replace(".", "")
    try:
        value = Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return raw
    return format(value.normalize(), "f")


def _name_tokens(name: str) -> list[str]:
    return _TOKEN_RE.findall(_SINGLE_PACK_RE.sub("", _fold(name)))


def name_identity(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(слова, числа) названия в источнике — без регистра, пунктуации, синонимов форм и
    различий написания."""
    words, numbers = set(), []
    for token in _name_tokens(name):
        if token[0].isdigit():
            numbers.append(_number(token))
            continue
        token = _SYNONYMS.get(token, token)
        if token not in _FILLER:
            words.add(_spelling(token))
    return tuple(sorted(words)), tuple(sorted(numbers))


def number_units(name: str) -> tuple[tuple[str, str], ...]:
    """Числа названия с единицей сразу после них («20 X 5 ML» → (20, ""), (5, ml))."""
    tokens = _name_tokens(name)
    pairs = []
    for index, token in enumerate(tokens):
        if token[0].isdigit():
            following = tokens[index + 1] if index + 1 < len(tokens) else ""
            following = _SYNONYMS.get(following, following)
            pairs.append((_number(token), following if following in _UNITS else ""))
    return tuple(sorted(pairs))


def _name_letters(name: str) -> str:
    """Слова названия подряд: «HAZIRENJEKTOR» = «HAZIR ENJEKTOR»."""
    return "".join(
        _spelling(_SYNONYMS.get(token, token)) for token in _name_tokens(name)
        if not token[0].isdigit() and _SYNONYMS.get(token, token) not in _FILLER
    )


def ingredient_identity(text: str) -> frozenset:
    """Основы слов состава без порядка («A/B/C» = «B, A ve C»): первые шесть букв после
    транслитерации; пусто — состав неизвестен. Разное вещество («Psödoefedrin» /
    «Fenilefrin» у TYLOL HOT D) остаётся разным."""
    return frozenset(
        _spelling(_INGREDIENT_SYNONYMS.get(token, token))[:6] for token in _TOKEN_RE.findall(_fold(text))
        # Числа состава пишут по-разному («3-4» / «3,4-»); дозировку сравнивает название.
        if token not in _INGREDIENT_FILLER and len(token) > 1 and not token[0].isdigit()
    )


def url_numbers_outside_name(url: str, name: str) -> list[str]:
    """Числа адреса страницы, которых нет в её названии (PREKUNIL: адрес «500-mg», название «750 MG»).

    Адрес теряет запятую («0,5 ML» → «05-ml» или «0-5-ml»), поэтому число названия
    подходит и целиком без разделителей, и по частям.
    """
    slug = str(url or "").split("?", 1)[0].rstrip("/").rsplit("/ilaclar/", 1)[-1].split("/", 1)[0]
    if not slug or slug == str(url or ""):
        return []
    slug = _URL_REPEAT_SUFFIX_RE.sub("", _fold(slug))
    allowed = set()
    for token in re.findall(r"\d+(?:[.,]\d+)*", _fold(name)):
        allowed.add(re.sub(r"[.,]", "", token))
        allowed.update(re.split(r"[.,]", token))
    return sorted(number for number in re.findall(r"\d+", slug) if number not in allowed)


@dataclass
class TwinPage:
    """Страница источника: уже сохранённый товар (``product``) или новая карточка."""

    source_name: str
    ingredient: str
    price: Optional[Decimal]
    is_available: bool
    pk: Optional[int] = None
    url: str = ""
    product: object = None

    @property
    def has_price(self) -> bool:
        return self.price is not None and self.price > 0


def page_from_product(product) -> TwinPage:
    external = product.external_data if isinstance(product.external_data, dict) else {}
    attrs = external.get("attributes") if isinstance(external.get("attributes"), dict) else {}
    return TwinPage(
        # name у товара с AI-результатом переведён — сравнивается турецкий оригинал.
        source_name=external.get("source_name") or product.name,
        # Поле active_ingredient мог переписать AI; исходник — в атрибутах парсера.
        ingredient=str(attrs.get("active_ingredient") or ""),
        price=product.price,
        is_available=bool(product.is_available),
        pk=product.pk,
        url=product.external_url or "",
        product=product,
    )


def page_from_scraped(scraped) -> TwinPage:
    attrs = scraped.attributes if isinstance(scraped.attributes, dict) else {}
    price = scraped.price
    return TwinPage(
        source_name=scraped.name,
        ingredient=str(attrs.get("active_ingredient") or ""),
        price=Decimal(str(price)) if price else None,
        is_available=bool(scraped.is_available),
        url=scraped.url or "",
    )


def mismatch_reason(keep: TwinPage, other: TwinPage) -> str:
    """Почему страницы могут быть разными препаратами; пусто — один и тот же."""
    keep_words, keep_numbers = name_identity(keep.source_name)
    other_words, other_numbers = name_identity(other.source_name)
    if keep_numbers != other_numbers:
        return "в названиях разные числа (дозировка или количество)"
    if number_units(keep.source_name) != number_units(other.source_name):
        return "в названиях те же числа, но при других единицах"
    if keep_words != other_words and _name_letters(keep.source_name) != _name_letters(other.source_name):
        extra = sorted(set(keep_words) ^ set(other_words))
        return "в названиях разные слова: " + ", ".join(extra)
    for page in (keep, other):
        extra = url_numbers_outside_name(page.url, page.source_name)
        if extra:
            return f"в адресе страницы другие числа, чем в названии: {', '.join(extra)}"
    keep_ingredient = ingredient_identity(keep.ingredient)
    other_ingredient = ingredient_identity(other.ingredient)
    # Одна страница может перечислять состав подробнее: сомнение — только если ни один
    # список не содержит другой.
    if (keep_ingredient and other_ingredient and not keep_ingredient <= other_ingredient
            and not other_ingredient <= keep_ingredient):
        return "разный состав"
    return ""


def _keeper_order(page: TwinPage):
    # С ценой раньше; среди равных — сохранённый раньше (новая страница — последней).
    return (not page.has_price, page.pk is None, page.pk or 0)


@dataclass
class TwinDecision:
    page: TwinPage
    keep: TwinPage
    action: str  # HIDE | REVIEW
    reason: str


def decide_group(pages: Iterable[TwinPage]) -> list[TwinDecision]:
    """Решение по каждой странице группы, кроме оставляемой."""
    pages = sorted(pages, key=_keeper_order)
    if len(pages) < 2:
        return []
    keep = pages[0]
    prices = {page.price for page in pages if page.has_price}
    decisions = []
    for page in pages[1:]:
        reason = mismatch_reason(keep, page)
        if reason:
            decisions.append(TwinDecision(page, keep, REVIEW, reason))
        elif len(prices) > 1:
            decisions.append(TwinDecision(page, keep, REVIEW, "у страниц разные цены"))
        elif not keep.is_available and page.is_available:
            decisions.append(TwinDecision(page, keep, REVIEW, "оставляемая страница не в наличии"))
        elif page.has_price:
            decisions.append(TwinDecision(page, keep, HIDE, "полный дубль: та же цена"))
        elif keep.has_price:
            decisions.append(TwinDecision(page, keep, HIDE, "вторая страница без цены"))
        else:
            decisions.append(TwinDecision(page, keep, HIDE, "обе страницы без цены, оставлена более ранняя"))
    return decisions


def _stub_q(prefix: str = "") -> Q:
    """Заглушка аналога (страница, которую видели только в таблице аналогов) — не близнец:
    её сам парсер дополнит при открытии страницы. Условие с has_key: у строки без ключа
    сравнение JSON дало бы NULL, и exclude() выкинул бы её."""
    return Q(**{f"{prefix}external_data__has_key": "is_stub"}) & Q(**{f"{prefix}external_data__is_stub": True})


def active_twins(barcode: str, *, exclude_pk: Optional[int] = None) -> list:
    """Показанные на сайте лекарства ilacfiyati с этим штрихкодом (Product)."""
    from apps.catalog.models import Product

    barcode = str(barcode or "").strip()
    if not barcode:
        return []
    qs = Product.objects.filter(
        product_type="medicines",
        is_active=True,
        medicine_item__is_active=True,
        medicine_item__barcode=barcode,
        external_url__contains="ilacfiyati.com",
    ).exclude(_stub_q())
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return list(qs.order_by("pk"))


def duplicate_barcode_groups() -> dict[str, list]:
    """{штрихкод: [Product, …]} — группы из двух и более показанных лекарств ilacfiyati."""
    from apps.catalog.models import MedicineProduct

    counts = Counter(
        MedicineProduct.objects.filter(
            is_active=True,
            base_product__is_active=True,
            base_product__external_url__contains="ilacfiyati.com",
        )
        .exclude(barcode="")
        .exclude(_stub_q("base_product__"))
        .values_list("barcode", flat=True)
    )
    return {barcode: active_twins(barcode) for barcode, count in sorted(counts.items()) if count > 1}


def hide_twin(product, keep) -> list[str]:
    """Скрыть близнеца: is_active=False у Product и MedicineProduct, его адрес — 301 на ``keep``.

    Возвращает slug, записанные в ProductSlugHistory. QuerySet.update — как у «Неактуальных
    товаров»: save() доменной карточки синхронизировал бы её в Product (DEVELOPMENT_RULES §3.13).
    """
    from apps.catalog.models import MedicineProduct, Product, ProductSlugHistory
    from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX

    external = dict(product.external_data) if isinstance(product.external_data, dict) else {}
    external[TWIN_OF_KEY] = keep.pk
    with transaction.atomic():
        Product.objects.filter(pk=product.pk).update(
            is_active=False, external_data=external, updated_at=timezone.now(),
        )
        MedicineProduct.objects.filter(base_product_id=product.pk).update(is_active=False)
        slugs = {product.slug}
        slugs.update(MedicineProduct.objects.filter(base_product_id=product.pk).values_list("slug", flat=True))
        slugs.discard("")
        slugs.discard(None)
        # Адрес снятой страницы ведёт на преемника (DEVELOPMENT_RULES §5.3–5.4), а не в 404.
        for slug in sorted(slugs):
            ProductSlugHistory.objects.update_or_create(
                old_slug=slug, defaults={"product_id": keep.pk, "product_type": "medicines"},
            )
            cache.delete(RESOLVE_CACHE_PREFIX + slug)
    product.is_active = False
    product.external_data = external
    return sorted(slugs)
