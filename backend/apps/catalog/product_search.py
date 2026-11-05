"""Поиск товаров на сайте по подготовленному тексту. Устройство — docs/PRODUCT_SEARCH.md.

Текст товара (``ProductSearchIndex``) собирается из названия и его переводов,
бренда, производителя, действующего вещества, SKU, штрихкодов, артикула
источника и кода ATC и приводится к одному виду (``normalize_search_text``).
Запрос нормализуется так же и делится на слова: каждое слово должно найтись
в тексте (числа необязательны, если есть другие слова). Найденное сортируется
по точности совпадения.

Пока таблица индекса пуста (до первого ``rebuild_product_search_index --apply``
на проде), поиск и сигналы работают по-старому: ``name__icontains``.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from django.contrib.postgres.search import TrigramSimilarity
from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, Q, Value, When
from django.db.models.signals import post_save

# Турецкие и прочие латинские буквы с диакритикой → латиница, ё → е.
# Заглавная İ отдельно: ``"İ".lower()`` даёт «i» с комбинируемой точкой (U+0307).
_CHAR_MAP = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ç": "c", "ç": "c",
    "Ğ": "g", "ğ": "g", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u",
    "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
    "Ä": "a", "ä": "a", "À": "a", "à": "a", "Á": "a", "á": "a",
    "É": "e", "é": "e", "È": "e", "è": "e", "Ê": "e", "ê": "e", "Ë": "e", "ë": "e",
    "Í": "i", "í": "i", "Ï": "i", "ï": "i", "Ó": "o", "ó": "o", "Ô": "o", "ô": "o",
    "Ú": "u", "ú": "u", "Ñ": "n", "ñ": "n",
    "Ё": "е", "ё": "е", "̇": "",
})
# Всё, кроме букв и цифр (дефисы, точки, скобки, «_»), — разделитель слов.
_SEPARATORS = re.compile(r"[\W_]+")
# «U.S.» → «us», «T-Shirt» → «tshirt»: склеенное написание тоже ищется.
_LETTER_JOINERS = re.compile(r"(?<=[^\W\d_])[.\-'’](?=[^\W\d_])")

# Поля доменной записи и её вариантов, которые попадают в текст.
_DOMAIN_FIELDS = ("manufacturer", "active_ingredient", "atc_code", "barcode", "gtin", "mpn", "external_id")
_VARIANT_FIELDS = ("sku", "barcode", "gtin")
_VARIANT_RELATIONS = ("variants", "book_variants")
_PRODUCT_FIELDS = ("sku", "barcode", "gtin", "mpn", "external_id")
# Бренд-заглушка «Другое» (signals.set_default_other_brand) — не бренд товара.
_PLACEHOLDER_BRAND_SLUG = "other"


def normalize_search_text(value) -> str:
    """Нижний регистр, ё→е, İ/ı/ş/ç/ğ/ö/ü → латиница, всё кроме букв и цифр → пробел."""
    text = str(value or "").translate(_CHAR_MAP).lower().translate(_CHAR_MAP)
    return " ".join(part for part in _SEPARATORS.split(text) if part)


def _normalized_variants(value) -> list[str]:
    """Нормализованное значение и слова его склеенного написания («U.S.» → «us»)."""
    normal = normalize_search_text(value)
    if not normal:
        return []
    words = set(normal.split())
    joined = normalize_search_text(_LETTER_JOINERS.sub("", str(value)))
    extra = [word for word in joined.split() if word not in words]
    return [normal, " ".join(extra)] if extra else [normal]


def _unique_lines(values: Iterable) -> str:
    lines: list[str] = []
    for value in values:
        for line in _normalized_variants(value):
            if line and line not in lines:
                lines.append(line)
    return "\n".join(lines)


def _translation_values(obj, field: str) -> list:
    translations = getattr(obj, "translations", None)
    if translations is None:
        return []
    return [getattr(row, field, "") for row in translations.all()]


def build_search_row(product, domain=None) -> dict[str, str]:
    """Поля ``ProductSearchIndex`` товара. ``domain`` — его доменная запись (лекарство, одежда…)."""
    names = [product.name, *_translation_values(product, "name")]
    codes = [getattr(product, field, "") for field in _PRODUCT_FIELDS]
    details: list = []
    if domain is not None:
        names += [domain.name, *_translation_values(domain, "name")]
        details += [getattr(domain, field, "") for field in _DOMAIN_FIELDS]
        details += _translation_values(domain, "active_ingredient")
        for relation in _VARIANT_RELATIONS:
            manager = getattr(domain, relation, None)
            if manager is not None and hasattr(manager, "all"):
                for variant in manager.all():
                    codes += [getattr(variant, field, "") for field in _VARIANT_FIELDS]
    brand = product.brand
    brands = []
    if brand is not None and brand.slug != _PLACEHOLDER_BRAND_SLUG:
        brands = [brand.name, *_translation_values(brand, "name")]
    name_text = _unique_lines(names)
    brand_text = _unique_lines(brands)
    text = _unique_lines([name_text, brand_text, *details, *codes])
    return {"name": name_text, "brand": brand_text, "text": text.replace("\n", " ")}


def search_index_ready() -> bool:
    """Индекс заполнен бэкафиллом. До этого поиск и сигналы работают по-старому."""
    from .models_search import ProductSearchIndex

    return ProductSearchIndex.objects.exists()


def _product_queryset():
    from .models import BrandTranslation, Product, ProductTranslation

    return (
        Product.objects.order_by("pk")
        .select_related("brand")
        .only("pk", "name", "product_type", "brand", "brand__name", "brand__slug", *_PRODUCT_FIELDS)
        .prefetch_related(
            Prefetch("translations", queryset=ProductTranslation.objects.only("pk", "product_id", "name")),
            Prefetch("brand__translations", queryset=BrandTranslation.objects.only("pk", "brand_id", "name")),
        )
    )


def _domain_records(products) -> dict[int, object]:
    """product_id → доменная запись типа товара, с переводами и вариантами."""
    from .domain_sync import domain_models

    models_by_type = domain_models()
    ids_by_type: dict[str, list[int]] = {}
    for product in products:
        product_type = str(product.product_type or "").replace("-", "_")
        if product_type in models_by_type:
            ids_by_type.setdefault(product_type, []).append(product.pk)

    records: dict[int, object] = {}
    for product_type, ids in ids_by_type.items():
        model = models_by_type[product_type]
        field_names = {field.name for field in model._meta.get_fields()}
        translation_model = model._meta.get_field("translations").related_model
        translation_fields = ["pk", "product_id", "name"] + (
            ["active_ingredient"] if "active_ingredient" in {f.name for f in translation_model._meta.concrete_fields} else []
        )
        prefetches = [Prefetch("translations", queryset=translation_model.objects.only(*translation_fields))]
        for relation in _VARIANT_RELATIONS:
            if relation in field_names:
                variant_model = model._meta.get_field(relation).related_model
                parent = model._meta.get_field(relation).field.name
                variant_fields = [f for f in _VARIANT_FIELDS if f in {x.name for x in variant_model._meta.concrete_fields}]
                prefetches.append(Prefetch(relation, queryset=variant_model.objects.only("pk", parent, *variant_fields)))
        only = ["pk", "name", "base_product_id", *(f for f in _DOMAIN_FIELDS if f in field_names)]
        for record in model.objects.filter(base_product_id__in=ids).only(*only).prefetch_related(*prefetches):
            records[record.base_product_id] = record
    return records


def iter_search_rows(product_ids: Optional[Iterable[int]] = None, *, batch_size: int = 500):
    """(product_id, поля индекса) — для всех товаров или для product_ids."""
    queryset = _product_queryset()
    if product_ids is not None:
        queryset = queryset.filter(pk__in=list(product_ids))
    batch = []
    for product in queryset.iterator(chunk_size=batch_size):
        batch.append(product)
        if len(batch) >= batch_size:
            yield from _rows_for(batch)
            batch = []
    if batch:
        yield from _rows_for(batch)


def _rows_for(products):
    domains = _domain_records(products)
    for product in products:
        yield product.pk, build_search_row(product, domains.get(product.pk))


def write_search_rows(rows) -> int:
    """Записывает [(product_id, поля)] одной пачкой (вставка или обновление)."""
    from .models_search import ProductSearchIndex

    objects = [ProductSearchIndex(product_id=pk, **fields) for pk, fields in rows]
    if objects:
        ProductSearchIndex.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["product"],
            update_fields=["name", "brand", "text", "updated_at"],
        )
    return len(objects)


def reindex_products(product_ids: Iterable[int]) -> int:
    """Пересчёт текста товаров после сохранения. Пустой индекс не трогается (см. модуль)."""
    ids = {pk for pk in product_ids if pk}
    if not ids or not search_index_ready():
        return 0
    return write_search_rows(list(iter_search_rows(ids)))


# --- запрос ------------------------------------------------------------------


def search_words(search: str) -> tuple[str, list[str]]:
    """(нормализованный запрос, обязательные слова). Числа необязательны рядом со словами."""
    query = normalize_search_text(search)
    words = query.split()
    required = [word for word in words if not word.isdigit()] or words
    return query, required


def filter_by_search(queryset, search: str, *, prefix: str = ""):
    """Фильтр по словам запроса. ``prefix`` — путь до Product («base_product__» у доменных)."""
    if not search_index_ready():
        return queryset.filter(name__icontains=search)
    query, words = search_words(search)
    if not words:
        return queryset.none()
    for word in words:
        queryset = queryset.filter(**{f"{prefix}search_index__text__contains": word})
    return queryset


def order_by_relevance(queryset, search: str, *, prefix: str = ""):
    """Точное название или бренд → название начинается с запроса → запрос с начала
    слова в названии → похожесть названия → наличие → новизна."""
    query, _ = search_words(search)
    if not query or not search_index_ready():
        return queryset.order_by("-created_at")
    names = f"{prefix}search_index__name"
    brand = f"{prefix}search_index__brand"
    exact = f"(?n)^{query}$"
    tier = Case(
        When(Q(**{f"{names}__regex": exact}) | Q(**{f"{brand}__regex": exact}), then=Value(0)),
        When(**{f"{names}__regex": f"(?n)^{query}( |$)"}, then=Value(1)),
        When(**{f"{names}__regex": f"(?n)^{query}"}, then=Value(2)),
        When(**{f"{names}__regex": f"(^|\\s){query}"}, then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )
    return queryset.annotate(
        search_tier=tier,
        search_similarity=TrigramSimilarity("name", query),
    ).order_by("search_tier", "-search_similarity", "-is_available", "-created_at", "-id")


# --- сигналы -----------------------------------------------------------------


def _schedule(product_ids) -> None:
    ids = {pk for pk in product_ids if pk}
    if ids:
        transaction.on_commit(lambda: reindex_products(ids))


def _product_saved(sender, instance, **kwargs):
    _schedule([instance.pk])


def _product_translation_saved(sender, instance, **kwargs):
    _schedule([instance.product_id])


def _domain_saved(sender, instance, **kwargs):
    _schedule([instance.base_product_id])


def _domain_translation_saved(sender, instance, **kwargs):
    domain_model = sender._meta.get_field("product").related_model
    _schedule(domain_model.objects.filter(pk=instance.product_id).values_list("base_product_id", flat=True))


def connect_signals() -> None:
    from .domain_sync import domain_models
    from .models import Product, ProductTranslation

    post_save.connect(_product_saved, sender=Product, dispatch_uid="product_search_product")
    post_save.connect(
        _product_translation_saved, sender=ProductTranslation, dispatch_uid="product_search_translation"
    )
    for product_type, model in domain_models().items():
        post_save.connect(_domain_saved, sender=model, dispatch_uid=f"product_search_domain_{product_type}")
        translation_model = model._meta.get_field("translations").related_model
        post_save.connect(
            _domain_translation_saved,
            sender=translation_model,
            dispatch_uid=f"product_search_domain_translation_{product_type}",
        )
