import uuid

import pytest

from apps.catalog.models import Brand, Category, ClothingProduct, ClothingVariant
from apps.orders.models import Cart, CartItem
from apps.orders.serializers import CartItemSerializer, resolve_variant_product


@pytest.mark.django_db
def test_cart_variant_keeps_parent_variant_and_size_for_return_link():
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name="Clothing", slug=f"clothing-{suffix}")
    brand = Brand.objects.create(name=f"Brand {suffix}", slug=f"brand-{suffix}")
    parent = ClothingProduct.objects.create(
        name="Variant product",
        slug=f"variant-product-{suffix}",
        category=category,
        brand=brand,
        price=100,
        currency="TRY",
        is_active=True,
    )
    variant = ClothingVariant.objects.create(
        product=parent,
        name="Red",
        slug=f"variant-red-{suffix}",
        color="red",
        price=110,
        currency="TRY",
        is_active=True,
    )
    shadow = resolve_variant_product("clothing", variant.slug)
    cart = Cart.objects.create(session_key=f"variant-cart-{suffix}")
    item = CartItem.objects.create(
        cart=cart,
        product=shadow,
        chosen_size="M",
        quantity=1,
        price=110,
    )
    serializer = CartItemSerializer()

    assert serializer.get_product_parent_slug(item) == parent.slug
    assert serializer.get_product_variant_slug(item) == variant.slug
    assert item.chosen_size == "M"
