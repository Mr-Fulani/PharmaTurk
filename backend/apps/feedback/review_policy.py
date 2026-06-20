from django.conf import settings


def _has_purchased_product(user, product_type: str, product_slug: str) -> bool:
    from apps.catalog.serializers import FavoriteSerializer
    from apps.orders.models import Order, OrderItem

    items = OrderItem.objects.filter(
        order__user=user,
        order__status=Order.OrderStatus.DELIVERED,
        product__isnull=False,
        product__product_type=product_type,
    ).select_related("product")

    for item in items:
        product = item.product
        if product.slug == product_slug:
            return True
        external_data = product.external_data or {}
        parent_slug = FavoriteSerializer._get_variant_parent_slug(product, external_data)
        if parent_slug == product_slug:
            return True
    return False


def can_user_review(user, product_type: str, product_slug: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    policy = getattr(settings, "PRODUCT_REVIEW_ACCESS_POLICY", "authenticated").strip().lower()
    if policy == "purchased":
        return _has_purchased_product(user, product_type, product_slug)
    return True
