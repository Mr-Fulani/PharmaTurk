"""Ранг медикаментов для сортировки «Популярные» (порядок по умолчанию).

Ранг считается в фоне и хранится в ``MedicineProduct.sort_rank``: список
читается упорядоченным сканом частичного индекса (миграция 0212), без JOIN-ов
и агрегатов в запросе. Разряды по убыванию важности:

    tier * 1_000_000            есть цена (+2), в наличии (+1): без цены — в конце
    is_featured * 100_000       ручной буст менеджера
    min(interest, 9_999) * 10   спрос: заявки, корзины, избранное, проверки цены
    quality (0..3)              фото (+2), русское описание (+1)

При равном ранге порядок задаёт id (новые выше), см. MedicineProductViewSet.
"""

from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Sum

TIER_WEIGHT = 1_000_000
FEATURED_WEIGHT = 100_000
INTEREST_CAP = 9_999
INTEREST_WEIGHT = 10

ORDER_WEIGHT = 10
CART_WEIGHT = 3
FAVORITE_WEIGHT = 3
MARKET_CHECK_WEIGHT = 2


def compute_sort_rank(
    *,
    has_price: bool,
    is_available: bool,
    is_featured: bool,
    interest: int,
    has_image: bool,
    has_ru_description: bool,
) -> int:
    tier = (2 if has_price else 0) + (1 if is_available else 0)
    quality = (2 if has_image else 0) + (1 if has_ru_description else 0)
    return (
        tier * TIER_WEIGHT
        + (FEATURED_WEIGHT if is_featured else 0)
        + min(interest, INTEREST_CAP) * INTEREST_WEIGHT
        + quality
    )


def _interest_by_base_product() -> Counter:
    """Взвешенный спрос по id shadow-Product медикамента."""
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
            model.objects.filter(product__product_type="medicines")
            .values("product_id")
            .annotate(n=aggregate)
            .values_list("product_id", "n")
        )
        for product_id, n in rows:
            interest[product_id] += (n or 0) * weight

    # Избранное медикамента хранится и на доменной модели, и (legacy) на Product.
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


def recompute_medicine_sort_ranks(batch_size: int = 1000) -> int:
    """Пересчитывает sort_rank активных медикаментов; возвращает число изменённых."""
    from apps.catalog.models import MedicineProduct, MedicineProductTranslation

    base_interest = _interest_by_base_product()
    domain_favorites = _favorite_counts(MedicineProduct)
    with_gallery = set(
        MedicineProduct.objects.filter(gallery_images__isnull=False).values_list("id", flat=True)
    )
    with_base_images = set(
        MedicineProduct.objects.filter(base_product__images__isnull=False).values_list("id", flat=True)
    )
    with_ru_description = set(
        MedicineProductTranslation.objects.filter(locale="ru")
        .exclude(description="")
        .values_list("product_id", flat=True)
    )

    # only(): external_data весит мегабайты на строку — не читаем его.
    medicines = MedicineProduct.objects.filter(is_active=True).only(
        "id", "price", "is_available", "is_featured", "main_image",
        "main_image_file", "base_product_id", "sort_rank",
    )
    changed = []
    for medicine in medicines.iterator(chunk_size=batch_size):
        interest = (
            base_interest.get(medicine.base_product_id, 0)
            + domain_favorites.get(medicine.id, 0) * FAVORITE_WEIGHT
        )
        rank = compute_sort_rank(
            has_price=bool(medicine.price),
            is_available=medicine.is_available,
            is_featured=medicine.is_featured,
            interest=interest,
            has_image=bool(
                medicine.main_image
                or medicine.main_image_file
                or medicine.id in with_gallery
                or medicine.id in with_base_images
            ),
            has_ru_description=medicine.id in with_ru_description,
        )
        if rank != medicine.sort_rank:
            medicine.sort_rank = rank
            changed.append(medicine)

    # bulk_update не вызывает save(): ни shadow-sync, ни updated_at не трогаем.
    MedicineProduct.objects.bulk_update(changed, ["sort_rank"], batch_size=batch_size)
    return len(changed)
