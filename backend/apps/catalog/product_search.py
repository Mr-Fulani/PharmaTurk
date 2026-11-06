"""Поиск товаров на сайте по подготовленному тексту. Устройство — docs/PRODUCT_SEARCH.md.

Текст товара (``ProductSearchIndex``) собирается из названия и его переводов,
бренда, производителя, действующего вещества, SKU, штрихкодов, артикула
источника и кода ATC и приводится к одному виду (``normalize_search_text``).
Запрос нормализуется так же и делится на слова: каждое слово должно найтись
в тексте (числа необязательны, если есть другие слова). Найденное сортируется
по точности совпадения.

Вторая очередь (``search_language``): в текст добавляются бренд и торговое название
кириллицей, тип товара и пол по-русски и по-английски, названия раздела; в запросе
отсекаются окончания и учитываются синонимы. Если ничего не нашлось — другая
раскладка, чтение латиницы кириллицей и обратно, исправление опечатки (``search_plan``).

Пока таблица индекса пуста (до первого ``rebuild_product_search_index --apply``
на проде), поиск и сигналы работают по-старому: ``name__icontains``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import connection, transaction
from django.db.models import Case, IntegerField, Prefetch, Q, Value, When
from django.db.models.functions import Length
from django.db.models.signals import post_save

from .search_language import (
    PHRASE_SYNONYMS,
    QUERY_REPLACEMENTS,
    QUERY_SYNONYMS,
    STOP_WORDS,
    VITAMIN_STEMS,
    TYPO_CANDIDATE_THRESHOLD,
    TYPO_MIN_LENGTH,
    closest_word,
    cyrillic_to_latin,
    latin_reading,
    latin_to_cyrillic,
    letter_twin,
    stem,
    switch_layout,
)

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


# Типы товаров, у которых тип и пол из словаря карточек не ищутся: в названиях
# лекарств турецкие слова словаря («SET», «BOT») — не тип товара.
_MEDICAL_TYPES = {"medicines", "supplements", "medical_equipment"}


def _vocab():
    from apps.ai.services.rules import vocab

    return vocab


_PHRASES: dict[tuple[str, ...], tuple[str, str]] = {}


def _kind_phrases() -> dict[tuple[str, ...], tuple[str, str]]:
    """Нормализованная фраза названия (турецкая или английская) → (тип или пол по-русски, по-английски)."""
    if not _PHRASES:
        vocab = _vocab()
        for key, kind in vocab.KINDS.items():
            _PHRASES[tuple(normalize_search_text(key).split())] = (kind.ru, kind.en)
        for key, (ru, en) in vocab.AUDIENCE.items():
            _PHRASES[tuple(normalize_search_text(key).split())] = (ru.lstrip("="), en)
    return _PHRASES


def kind_words(names: Iterable[str]) -> list[str]:
    """Тип товара и пол из названия по-русски и по-английски: «Kadın Spor Ayakkabı» →
    «женский Women's», «кроссовки Sneakers». Самая длинная фраза словаря с каждого слова."""
    phrases = _kind_phrases()
    longest = max(map(len, phrases))
    found: list[str] = []
    for name in names:
        words = normalize_search_text(name).split()
        index = 0
        while index < len(words):
            for size in range(min(longest, len(words) - index), 0, -1):
                value = phrases.get(tuple(words[index:index + size]))
                if value:
                    found += value
                    index += size
                    break
            else:
                index += 1
    return found


_CATEGORY_DEPTH = 3  # раздел, его родитель и родитель родителя (загружены одним запросом)


def _category_names(category) -> list[str]:
    """Названия раздела товара и разделов выше («Кроссовки», «Женская обувь», «Обувь»)."""
    names: list[str] = []
    for level in range(_CATEGORY_DEPTH):
        if category is None:
            break
        names += [category.name, *_translation_values(category, "name")]
        # У последнего загруженного уровня parent отложен (only): его не трогаем, иначе запрос на товар.
        category = category.parent if level < _CATEGORY_DEPTH - 1 and category.parent_id else None
    return names


def build_search_row(product, domain=None, cyrillic_names: Iterable[str] = ()) -> dict[str, str]:
    """Поля ``ProductSearchIndex`` товара. ``domain`` — его доменная запись (лекарство, одежда…),
    ``cyrillic_names`` — торговое название кириллицей из словаря ``medicine_brand``."""
    names = [product.name, *_translation_values(product, "name")]
    codes = [getattr(product, field, "") for field in _PRODUCT_FIELDS]
    details: list = []
    product_type = str(product.product_type or "").replace("-", "_")
    if domain is not None:
        names += [domain.name, *_translation_values(domain, "name")]
        details += [getattr(domain, field, "") for field in _DOMAIN_FIELDS]
        details += _translation_values(domain, "active_ingredient")
        details.append(latin_reading(normalize_search_text(getattr(domain, "manufacturer", ""))))
        for relation in _VARIANT_RELATIONS:
            manager = getattr(domain, relation, None)
            if manager is not None and hasattr(manager, "all"):
                for variant in manager.all():
                    codes += [getattr(variant, field, "") for field in _VARIANT_FIELDS]
    about: list = []
    if product_type == "medicines":
        # Торговое название кириллицей: из словаря и чтением латиницы («NUROFEN» → «нурофен»).
        from apps.ai.services.medicine_title import title_brand

        names += [*cyrillic_names, latin_reading(normalize_search_text(title_brand(product.name)))]
    elif product_type not in _MEDICAL_TYPES:
        about += kind_words(names)
    audience = _vocab().AUDIENCE.get(str(product.gender or ""))
    if audience:
        about += [audience[0].lstrip("="), audience[1]]
    about += _category_names(product.category if product.category_id else None)
    brand = product.brand
    brands = []
    if brand is not None and brand.slug != _PLACEHOLDER_BRAND_SLUG:
        brands = [brand.name, *_translation_values(brand, "name")]
        # Как бренд пишут по-русски: словарь карточек («nike» → «найк») и чтение латиницы.
        brand_key = normalize_search_text(brand.name)
        brands += [_vocab().BRAND_RU.get(brand_key, ""), latin_reading(brand_key)]
    name_text = _unique_lines(names)
    brand_text = _unique_lines(brands)
    text = _unique_lines([name_text, brand_text, *details, *about, *codes])
    return {"name": name_text, "brand": brand_text, "text": text.replace("\n", " ")}


def search_index_ready() -> bool:
    """Индекс заполнен бэкафиллом. До этого поиск и сигналы работают по-старому."""
    from .models_search import ProductSearchIndex

    return ProductSearchIndex.objects.exists()


def _product_queryset():
    from .models import BrandTranslation, CategoryTranslation, Product, ProductTranslation

    return (
        Product.objects.order_by("pk")
        .select_related("brand", "category__parent__parent")
        .only(
            "pk", "name", "product_type", "gender", "brand", "brand__name", "brand__slug",
            "category", "category__name", "category__parent", "category__parent__name",
            "category__parent__parent", "category__parent__parent__name",
            *_PRODUCT_FIELDS,
        )
        .prefetch_related(
            Prefetch("translations", queryset=ProductTranslation.objects.only("pk", "product_id", "name")),
            Prefetch("brand__translations", queryset=BrandTranslation.objects.only("pk", "brand_id", "name")),
            *(
                Prefetch(f"{path}__translations", queryset=CategoryTranslation.objects.only("pk", "category_id", "name"))
                for path in ("category", "category__parent", "category__parent__parent")
            ),
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


def _medicine_cyrillic_names(products) -> dict[int, list[str]]:
    """product_id → торговое название кириллицей из словаря ``medicine_brand`` (PR #167),
    так же, как его пишет SEO лекарства (``content_generator``)."""
    from apps.ai.services.medicine_memory import peek
    from apps.ai.services.medicine_seo import BRAND_NAMESPACE, cyrillic_brand
    from apps.ai.services.medicine_title import paragraph_brand, title_brand

    brands = {
        product.pk: (title_brand(product.name), paragraph_brand(product.name))
        for product in products
        if str(product.product_type or "") == "medicines"
    }
    keys = {key for pair in brands.values() for key in pair if key}
    found = peek(BRAND_NAMESPACE, keys) if keys else {}
    result = {}
    for pk, (brand, short) in brands.items():
        ru = cyrillic_brand(brand, short, found) if brand else ""
        if ru:
            result[pk] = [ru]
    return result


def _rows_for(products):
    domains = _domain_records(products)
    cyrillic = _medicine_cyrillic_names(products)
    for product in products:
        yield product.pk, build_search_row(product, domains.get(product.pk), cyrillic.get(product.pk, ()))


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
    """Пересчёт текста товаров после сохранения. Пустой индекс не трогается (см. модуль).

    Строка с тем же текстом не переписывается: ночная сверка и парсеры сохраняют
    товары часто, а текст меняется редко. Возвращает число записанных строк.
    """
    from .models_search import ProductSearchIndex

    ids = {pk for pk in product_ids if pk}
    if not ids or not search_index_ready():
        return 0
    current = {
        pk: (name, brand, text)
        for pk, name, brand, text in ProductSearchIndex.objects.filter(product_id__in=ids).values_list(
            "product_id", "name", "brand", "text"
        )
    }
    return write_search_rows([
        (pk, fields)
        for pk, fields in iter_search_rows(ids)
        if current.get(pk) != (fields["name"], fields["brand"], fields["text"])
    ])


# --- запрос ------------------------------------------------------------------

_MIN_RANKED_QUERY = 3


def search_words(search: str) -> tuple[str, list[str]]:
    """(нормализованный запрос, обязательные слова). Числа необязательны рядом со словами."""
    query = normalize_search_text(search)
    words = query.split()
    required = [word for word in words if not word.isdigit()] or words
    return query, required


@dataclass(frozen=True)
class SearchPlan:
    """По какому тексту искать. ``mode``: words — запрос как есть; layout — другая раскладка;
    translit — латиница прочитана кириллицей или наоборот; typo — исправлена опечатка."""

    query: str
    mode: str = "words"

    @property
    def corrected(self) -> bool:
        return self.mode != "words"


def _whole_word(field: str, word: str) -> Q:
    return (
        Q(**{field: word})
        | Q(**{f"{field}__startswith": f"{word} "})
        | Q(**{f"{field}__endswith": f" {word}"})
        | Q(**{f"{field}__contains": f" {word} "})
    )


def _word_start(field: str, word: str) -> Q:
    return Q(**{f"{field}__startswith": word}) | Q(**{f"{field}__contains": f" {word}"})


def word_condition(word: str, field: str, *, alone: bool = False) -> Q:
    """Одно слово запроса: основа без окончания, синонимы, буква витамина в другом алфавите.

    Рядом с другими словами одна буква («витамин с») ищется целым словом, две («он», «d3») —
    с начала слова, иначе их найдёт почти любой текст. Только LIKE: каждое условие идёт
    по триграммному индексу.
    """
    twin = letter_twin(word)
    spellings = [word, twin] if twin else [word]
    if not alone and len(word) <= 2 and not word.isdigit():
        match = _whole_word if len(word) == 1 else _word_start
        condition = Q()
        for spelling in spellings:
            condition |= match(field, spelling)
        return condition
    base = stem(word)
    if base in QUERY_REPLACEMENTS:
        variants = list(QUERY_REPLACEMENTS[base])
    else:
        variants = [base, *QUERY_SYNONYMS.get(base, ()), *spellings[1:]]
    condition = Q()
    for variant in dict.fromkeys(variants):
        condition |= Q(**{f"{field}__contains": variant})
    return condition


def _required_words(words: list[str]) -> list[str]:
    """Слова, которые должны найтись: без предлогов и союзов («капли в нос» → «капли», «нос»),
    кроме буквы после «витамин» («витамин с»). Запрос из одних предлогов ищется как есть."""
    kept = [
        word
        for index, word in enumerate(words)
        if word not in STOP_WORDS or (len(word) == 1 and index and stem(words[index - 1]).startswith(VITAMIN_STEMS))
    ]
    return kept or words


def _search_condition(query: str, field: str) -> Optional[Q]:
    _, words = search_words(query)
    if not words:
        return None
    condition = Q()
    text = f" {' '.join(words)} "
    for phrase, variants in PHRASE_SYNONYMS.items():
        if f" {phrase} " in text:
            text = text.replace(f" {phrase} ", " ")
            phrase_condition = Q()
            for variant in variants:
                phrase_condition |= Q(**{f"{field}__contains": variant})
            condition &= phrase_condition
    words = _required_words(text.split()) if text.strip() else []
    for word in words:
        condition &= word_condition(word, field, alone=len(words) == 1)
    return condition


def _index_has(query: str) -> bool:
    from .models_search import ProductSearchIndex

    condition = _search_condition(query, "text")
    return condition is not None and ProductSearchIndex.objects.filter(condition).exists()


def _words_found(words: list[str]) -> list[bool]:
    """Есть ли каждое слово в индексе — одним запросом ``SELECT EXISTS(…), EXISTS(…)``."""
    from .models_search import ProductSearchIndex

    parts, params = [], []
    for word in words:
        sql, word_params = (
            ProductSearchIndex.objects.filter(word_condition(word, "text", alone=True)).values("pk")[:1]
            .query.sql_with_params()
        )
        parts.append(f"EXISTS({sql})")
        params += word_params
    with connection.cursor() as cursor:
        cursor.execute("SELECT " + ", ".join(parts), params)
        return list(cursor.fetchone())


def _typo_candidates(words: list[str]) -> list[str]:
    """Тексты товаров, где есть слово, похожее на одно из ``words`` (триграммный индекс)."""
    from .models_search import ProductSearchIndex

    table = ProductSearchIndex._meta.db_table
    condition = " OR ".join(["text %%> %s"] * len(words))
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)", [str(TYPO_CANDIDATE_THRESHOLD)]
        )
        cursor.execute(f"SELECT text FROM {table} WHERE {condition} LIMIT %s", [*words, 300 * len(words)])
        return [row[0] for row in cursor.fetchall()]


# Проверяется не больше стольких слов и исправляется не больше трёх: запрос из 30 выдуманных
# слов — те же два запроса к базе (проверка слов и кандидаты), а не по запросу на слово.
_TYPO_MAX_CHECKS = 6
_TYPO_MAX_FIXES = 3


def _typo_correction(query: str) -> str:
    """Запрос, в котором слова без совпадений заменены похожими словами каталога, или пусто."""
    words = query.split()
    positions = [i for i, word in enumerate(words) if len(word) >= TYPO_MIN_LENGTH and not word.isdigit()]
    positions = positions[:_TYPO_MAX_CHECKS]
    if not positions:
        return ""
    found = _words_found([words[i] for i in positions])
    missing = [i for i, ok in zip(positions, found) if not ok][:_TYPO_MAX_FIXES]
    if not missing:
        return ""
    texts = _typo_candidates([words[i] for i in missing])
    changed = False
    for index in missing:
        replacement = closest_word(words[index], texts)
        if replacement:
            words[index], changed = replacement, True
    return " ".join(words) if changed else ""


def _alternatives(search: str, query: str):
    layout = normalize_search_text(switch_layout(search))
    # Буква на клавише-знаке («х» — «[») пропадает при нормализации: «худи» → «elb», часть
    # другого слова. Такую раскладку не пробуем, как и слова короче 4 букв.
    if len(layout.replace(" ", "")) == len(query.replace(" ", "")) and max(map(len, layout.split()), default=0) >= 4:
        yield "layout", layout
    if re.search("[а-я]", query):
        yield "translit", cyrillic_to_latin(query)
    if re.search("[a-z]", query):
        yield "translit", " ".join(latin_to_cyrillic(word) or word for word in query.split())


# Длиннее запрос обрезается по слову: в шапке так не ищут, а каждое слово — условие SQL.
_MAX_QUERY = 100


def request_search_plan(request, search: str) -> Optional[SearchPlan]:
    """``search_plan`` один раз на HTTP-запрос: вьюсеты с фасетами вызывают ``get_queryset``
    3–4 раза, а запасные шаги (раскладка, опечатки) — это запросы к базе."""
    plans = getattr(request, "_product_search_plans", None)
    if plans is None:
        plans = {}
        setattr(request, "_product_search_plans", plans)
    if search not in plans:
        plans[search] = search_plan(search)
    return plans[search]


def search_plan(search: str) -> Optional[SearchPlan]:
    """Как искать запрос; ``None`` — индекс пуст, поиск по названию (см. модуль).

    Запрос как есть ничего не находит — пробуем другую раскладку («gfhfwtnfvjk» →
    «парацетамол»), чтение латиницы («paracetamol» → «парацетамол», «нурофен» → «nurofen»),
    затем исправление опечатки. Каждая проверка — ``EXISTS`` по индексу, только пока
    ничего не нашлось; найденный текст ищется и сортируется как обычный запрос.
    """
    if not search_index_ready():
        return None
    query = normalize_search_text(search)
    if len(query) > _MAX_QUERY:
        query = query[:_MAX_QUERY].rsplit(" ", 1)[0]
    if not query or _index_has(query):
        return SearchPlan(query)
    for mode, text in _alternatives(search, query):
        if text and text != query and _index_has(text):
            return SearchPlan(text, mode)
    corrected = _typo_correction(query)
    if corrected and _index_has(corrected):
        return SearchPlan(corrected, "typo")
    return SearchPlan(query)


def filter_by_search(queryset, search: str, *, prefix: str = "", plan: Optional[SearchPlan] = None):
    """Фильтр по словам запроса. ``prefix`` — путь до Product («base_product__» у доменных),
    ``plan`` — уже выбранный ``search_plan(search)``, чтобы не выбирать второй раз."""
    plan = plan or search_plan(search)
    if plan is None:
        return queryset.filter(name__icontains=search)
    condition = _search_condition(plan.query, f"{prefix}search_index__text")
    return queryset.none() if condition is None else queryset.filter(condition)


def _line_equals(field: str, value: str) -> Q:
    """Одна из строк многострочного поля равна value (только LIKE, без регулярок)."""
    return (
        Q(**{field: value})
        | Q(**{f"{field}__startswith": f"{value}\n"})
        | Q(**{f"{field}__endswith": f"\n{value}"})
        | Q(**{f"{field}__contains": f"\n{value}\n"})
    )


def order_by_relevance(queryset, search: str, *, prefix: str = "", plan: Optional[SearchPlan] = None):
    """Точное название или бренд → название начинается с запроса → запрос с начала
    слова в названии → остальное; внутри — короче название, в наличии, новее.

    Ключи сортировки считаются для всех совпадений, поэтому только дешёвые: LIKE и
    длина названия. Регулярки и ``similarity`` на 8,8 тыс. совпадений стоили ≈ 0,8 с
    (прод 05.11.2026 после выкатки: «пленочной оболочкой» 6 с вместе с детоастом).
    Запрос, в котором нет слова от 3 символов («кр», «ма», «a b»), — без сортировки по точности, сначала новые.
    """
    plan = plan or search_plan(search)
    query = plan.query if plan else ""
    longest = max((len(word) for word in query.split()), default=0)
    if longest < _MIN_RANKED_QUERY:
        return queryset.order_by("-created_at", "-id")
    names = f"{prefix}search_index__name"
    brand = f"{prefix}search_index__brand"
    tier = Case(
        When(_line_equals(names, query) | _line_equals(brand, query), then=Value(0)),
        When(Q(**{f"{names}__startswith": query}) | Q(**{f"{names}__contains": f"\n{query}"}), then=Value(1)),
        When(**{f"{names}__contains": f" {query}"}, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    return queryset.annotate(search_tier=tier, search_name_length=Length("name")).order_by(
        "search_tier", "search_name_length", "-is_available", "-created_at", "-id"
    )


# --- сигналы -----------------------------------------------------------------

# Поля, от которых зависит текст. save(update_fields=…) без них (наличие из ночной
# сверки, цена) пересчёт не запускает.
_PRODUCT_TRIGGERS = {"name", "brand", "brand_id", "product_type", "gender", "category", "category_id", *_PRODUCT_FIELDS}
_DOMAIN_TRIGGERS = {"name", "base_product", "base_product_id", *_DOMAIN_FIELDS}
_TRANSLATION_TRIGGERS = {"name", "active_ingredient", "locale", "product", "product_id"}
_VARIANT_TRIGGERS = {*_VARIANT_FIELDS, "product", "product_id"}


def _touches(kwargs, triggers) -> bool:
    update_fields = kwargs.get("update_fields")
    return update_fields is None or bool(set(update_fields) & triggers)


def schedule_reindex(product_ids) -> None:
    """Пересчёт после коммита. Ошибка пересчёта пишется в лог и не ломает save()."""
    ids = {pk for pk in product_ids if pk}
    if ids:
        transaction.on_commit(lambda: reindex_products(ids), robust=True)


def _product_saved(sender, instance, **kwargs):
    if _touches(kwargs, _PRODUCT_TRIGGERS):
        schedule_reindex([instance.pk])


def _product_translation_saved(sender, instance, **kwargs):
    if _touches(kwargs, _TRANSLATION_TRIGGERS):
        schedule_reindex([instance.product_id])


def _domain_saved(sender, instance, **kwargs):
    if _touches(kwargs, _DOMAIN_TRIGGERS):
        schedule_reindex([instance.base_product_id])


def _child_saver(parent_field: str, triggers: set):
    """Перевод или вариант доменной записи → товар этой записи."""

    def handler(sender, instance, **kwargs):
        if not _touches(kwargs, triggers):
            return
        domain_model = sender._meta.get_field(parent_field).related_model
        parent_id = getattr(instance, sender._meta.get_field(parent_field).attname)
        schedule_reindex(domain_model.objects.filter(pk=parent_id).values_list("base_product_id", flat=True))

    return handler


def connect_signals() -> None:
    from .domain_sync import domain_models
    from .models import Product, ProductTranslation

    post_save.connect(_product_saved, sender=Product, dispatch_uid="product_search_product")
    post_save.connect(
        _product_translation_saved, sender=ProductTranslation, dispatch_uid="product_search_translation"
    )
    for product_type, model in domain_models().items():
        post_save.connect(_domain_saved, sender=model, dispatch_uid=f"product_search_domain_{product_type}")
        translation = model._meta.get_field("translations")
        post_save.connect(
            _child_saver(translation.field.name, _TRANSLATION_TRIGGERS),
            sender=translation.related_model,
            weak=False,
            dispatch_uid=f"product_search_domain_translation_{product_type}",
        )
        for relation in _VARIANT_RELATIONS:
            if relation in {field.name for field in model._meta.get_fields()}:
                variants = model._meta.get_field(relation)
                post_save.connect(
                    _child_saver(variants.field.name, _VARIANT_TRIGGERS),
                    sender=variants.related_model,
                    weak=False,
                    dispatch_uid=f"product_search_variant_{product_type}_{relation}",
                )
