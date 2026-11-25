"""Ранг товара для сортировки «Популярные» (порядок по умолчанию).

Используется доменами медикаментов и БАДов (RANKED_MODELS). Ранг считается в
фоне и хранится в ``sort_rank``: список читается упорядоченным сканом
частичного индекса (миграции 0212, 0214), без JOIN-ов и агрегатов в запросе.
Разряды по убыванию важности:

    demand * 4_000_000          спрос из поисковиков (SearchDemand, 0..500), см.
                                docs/CATALOG_SEARCH_DEMAND.md; решение владельца 25.11.2026:
                                товар со спросом стоит выше остальных даже без цены и наличия
    tier * 1_000_000            есть цена (+2), в наличии (+1): без цены — в конце
    is_featured * 100_000       ручной буст менеджера
    min(interest, 9_999) * 10   спрос: заявки, корзины, избранное, проверки цены
    quality (0..3)              фото (+2), русское описание (+1)

При равном ранге порядок задаёт id (новые выше), см. _ORDERING_MAP вьюсетов.
"""

import re
from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Sum

# Всё, что ниже спроса, занимает меньше 4 млн; 500 ступеней спроса помещаются в
# PositiveIntegerField (до 2 147 483 647), колонку и индекс менять не нужно.
DEMAND_WEIGHT = 4_000_000
DEMAND_LEVELS = 500
DEMAND_PREFIX_WORDS = 3
TIER_WEIGHT = 1_000_000
FEATURED_WEIGHT = 100_000
INTEREST_CAP = 9_999
INTEREST_WEIGHT = 10

ORDER_WEIGHT = 10
CART_WEIGHT = 3
FAVORITE_WEIGHT = 3
MARKET_CHECK_WEIGHT = 2


def ranked_models():
    from apps.catalog.models import MedicineProduct, SupplementProduct

    return (MedicineProduct, SupplementProduct)


def compute_sort_rank(
    *,
    has_price: bool,
    is_available: bool,
    is_featured: bool,
    interest: int,
    has_image: bool,
    has_ru_description: bool,
    demand: int = 0,
) -> int:
    tier = (2 if has_price else 0) + (1 if is_available else 0)
    quality = (2 if has_image else 0) + (1 if has_ru_description else 0)
    return (
        min(demand, DEMAND_LEVELS) * DEMAND_WEIGHT
        + tier * TIER_WEIGHT
        + (FEATURED_WEIGHT if is_featured else 0)
        + min(interest, INTEREST_CAP) * INTEREST_WEIGHT
        + quality
    )


def _name_words(name: str) -> list:
    return re.findall(r"[^\W_]+", (name or "").upper())


def demand_levels(product_type: str) -> dict:
    """Начало названия без пробелов и дефисов -> ступень спроса (1..DEMAND_LEVELS).

    Ступень — место частоты среди разных частот раздела: чем больше запросов, тем
    выше. Пока разных частот не больше DEMAND_LEVELS, порядок строго по частоте.
    """
    from apps.catalog.models_search import SearchDemand

    best = {}
    for prefix, frequency in SearchDemand.objects.filter(
        product_type=product_type, frequency__gt=0
    ).values_list("name_prefix", "frequency"):
        key = "".join(_name_words(prefix))
        if key:
            best[key] = max(frequency, best.get(key, 0))
    frequencies = sorted(set(best.values()))
    scale = max(len(frequencies), DEMAND_LEVELS)
    place = {frequency: index for index, frequency in enumerate(frequencies, start=1)}
    return {key: -(-place[frequency] * DEMAND_LEVELS // scale) for key, frequency in best.items()}


def demand_for_name(name: str, levels: dict) -> int:
    """Ступень спроса товара: совпадение первых 1–3 слов названия с ``SearchDemand``."""
    if not levels:
        return 0
    words = _name_words(name)[:DEMAND_PREFIX_WORDS]
    return max((levels.get("".join(words[:count]), 0) for count in range(1, len(words) + 1)), default=0)


def _interest_by_base_product(product_type: str) -> Counter:
    """Взвешенный спрос по id shadow-Product домена."""
    from apps.catalog.models import Product, ProductMarketCheck
    from apps.orders.models import CartItem, OrderItem

    interest = Counter()
    sources = (
        (OrderItem, Count("order", distinct=True), ORDER_WEIGHT),
        (CartItem, Count("cart", distinct=True), CART_WEIGHT),
        (ProductMarketCheck, Sum("request_count"), MARKET_CHECK_WEIGHT),
    )
    for model, aggregate, weight in sources:
        rows = (
            model.objects.filter(product__product_type=product_type)
            .values("product_id")
            .annotate(n=aggregate)
            .values_list("product_id", "n")
        )
        for product_id, n in rows:
            interest[product_id] += (n or 0) * weight

    # Избранное хранится и на доменной модели, и (legacy) на Product.
    for product_id, n in _favorite_counts(Product).items():
        interest[product_id] += n * FAVORITE_WEIGHT
    return interest


def _favorite_counts(model) -> dict:
    from apps.catalog.models import Favorite

    return dict(
        Favorite.objects.filter(content_type=ContentType.objects.get_for_model(model))
        .values("object_id")
        .annotate(n=Count("id"))
        .values_list("object_id", "n")
    )


def changed_sort_ranks(model, batch_size: int = 1000) -> list:
    """Активные товары модели, у которых ранг изменится (новый ранг уже в ``sort_rank``, без записи)."""
    translation_model = model._meta.get_field("translations").related_model

    base_interest = _interest_by_base_product(model._domain_product_type)
    domain_favorites = _favorite_counts(model)
    levels = demand_levels(model._domain_product_type)
    with_gallery = set(
        model.objects.filter(gallery_images__isnull=False).values_list("id", flat=True)
    )
    with_base_images = set(
        model.objects.filter(base_product__images__isnull=False).values_list("id", flat=True)
    )
    with_ru_description = set(
        translation_model.objects.filter(locale="ru")
        .exclude(description="")
        .values_list("product_id", flat=True)
    )

    # only(): external_data весит мегабайты на строку — не читаем его.
    fields = [
        "id", "name", "price", "is_available", "is_featured", "main_image",
        "main_image_file", "base_product_id", "sort_rank",
    ]
    products = model.objects.filter(is_active=True).only(*fields)
    changed = []
    for product in products.iterator(chunk_size=batch_size):
        interest = (
            base_interest.get(product.base_product_id, 0)
            + domain_favorites.get(product.id, 0) * FAVORITE_WEIGHT
        )
        rank = compute_sort_rank(
            has_price=bool(product.price),
            is_available=product.is_available,
            is_featured=product.is_featured,
            interest=interest,
            has_image=bool(
                product.main_image
                or product.main_image_file
                or product.id in with_gallery
                or product.id in with_base_images
            ),
            has_ru_description=product.id in with_ru_description,
            demand=demand_for_name(product.name, levels),
        )
        if rank != product.sort_rank:
            product.sort_rank = rank
            changed.append(product)
    return changed


def recompute_sort_ranks(model, batch_size: int = 1000) -> int:
    """Пересчитывает sort_rank активных товаров модели; возвращает число изменённых."""
    changed = changed_sort_ranks(model, batch_size)
    # bulk_update не вызывает save(): ни shadow-sync, ни updated_at не трогаем.
    model.objects.bulk_update(changed, ["sort_rank"], batch_size=batch_size)
    return len(changed)
