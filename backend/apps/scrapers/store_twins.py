"""Один и тот же товар у двух магазинов (Intersport, SuperStep, SPX): на сайте — более дорогой.

Решение владельца 13.11.2026 («Оставить более дорогую», как у FLO ↔ SuperStep): у магазинов
общий код товара (артикул и цвет производителя: ``intersport-EQYTG03218.6459`` и
``spx-EQYTG03218.6459``). Новый товар не создаётся, если у соседа такой же уже есть и он не
дешевле; если новый дороже — он создаётся, а соседний скрывается (``hide_store_twin``).
Ничего не удаляется: скрытый остаётся в базе с пометкой ``store_twin_of``, его адреса ведут
308 на оставленный. Парсер скрытый товар обновляет, но на сайт не возвращает (``is_active``
обновление не трогает).
"""

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

STORE_TWIN_OF_KEY = "store_twin_of"


def is_pricier(new_price, existing_price) -> bool:
    """Новый дороже соседа. Без одной из цен — нет: оставляем то, что уже на сайте."""
    if new_price in (None, "") or existing_price in (None, ""):
        return False
    return float(new_price) > float(existing_price)


def hide_store_twin(hidden, keep) -> list[str]:
    """Скрыть ``hidden`` в пользу ``keep``: is_active=False у Product и доменной карточки,
    его адреса (текущий и прежние) — в ProductSlugHistory на ``keep``. Возвращает эти адреса.

    QuerySet.update, а не save(): save() доменной карточки синхронизировал бы её в Product
    (DEVELOPMENT_RULES §3.13) и записал бы адрес в историю на самого скрытого.
    """
    from apps.catalog.models import Product, ProductSlugHistory
    from apps.catalog.services.product_resolve import RESOLVE_CACHE_PREFIX

    domain = type(hidden.domain_item) if hidden.domain_item is not None else None
    with transaction.atomic():
        current = Product.objects.select_for_update().get(pk=hidden.pk)
        external = dict(current.external_data) if isinstance(current.external_data, dict) else {}
        external[STORE_TWIN_OF_KEY] = keep.pk
        Product.objects.filter(pk=hidden.pk).update(is_active=False, external_data=external, updated_at=timezone.now())
        slugs = {current.slug}
        if domain is not None:
            domain.objects.filter(base_product_id=hidden.pk).update(is_active=False)
            slugs.update(domain.objects.filter(base_product_id=hidden.pk).values_list("slug", flat=True))
        slugs.update(ProductSlugHistory.objects.filter(product_id=hidden.pk).values_list("old_slug", flat=True))
        slugs -= {"", None}
        for slug in sorted(slugs):
            ProductSlugHistory.objects.update_or_create(
                old_slug=slug, defaults={"product_id": keep.pk, "product_type": hidden.product_type},
            )
            cache.delete(RESOLVE_CACHE_PREFIX + slug)
    hidden.is_active = False
    hidden.external_data = external
    return sorted(slugs)
