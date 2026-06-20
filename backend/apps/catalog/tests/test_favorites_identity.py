import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import (
    Favorite,
    MedicineProduct,
    PerfumeryProduct,
    PerfumeryVariant,
    PerfumeryVariantImage,
    Product,
    Service,
)
from apps.catalog.serializers import (
    AddToFavoriteSerializer,
    FavoriteSerializer,
    resolve_product_for_favorites_api,
)


@pytest.mark.django_db
def test_public_product_id_wins_over_colliding_domain_pk():
    collision_id = 800_000 + int(uuid.uuid4().hex[:5], 16)
    wrong_medicine = MedicineProduct.objects.create(
        id=collision_id,
        name="Wrong medicine",
        slug=f"wrong-medicine-{uuid.uuid4().hex}",
        price=10,
        is_active=True,
    )
    public_product = Product.objects.create(
        id=collision_id,
        name="Public glasses",
        slug=f"public-glasses-{uuid.uuid4().hex}",
        product_type="medicines",
        price=20,
        is_active=True,
    )
    # Создание Product(product_type="medicines") авто-создаёт доменную тень
    # MedicineProduct (base_product=public_product). Берём её, а не создаём дубль —
    # иначе коллизия по unique slug.
    expected_medicine = MedicineProduct.objects.get(base_product=public_product)

    resolved, product_type = resolve_product_for_favorites_api(collision_id, "medicines")

    assert product_type == "medicines"
    assert resolved.pk == expected_medicine.pk
    assert resolved.pk != wrong_medicine.pk


@pytest.mark.django_db
def test_perfumery_variant_slug_creates_stable_favorite_identity():
    suffix = uuid.uuid4().hex
    perfume = PerfumeryProduct.objects.create(
        name="Variant perfume",
        slug=f"variant-perfume-{suffix}",
        price=100,
        gender="unisex",
        is_active=True,
    )
    variant = PerfumeryVariant.objects.create(
        product=perfume,
        name="50 ml",
        slug=f"variant-perfume-50-{suffix}",
        price=110,
        is_active=True,
    )
    PerfumeryVariantImage.objects.create(
        variant=variant,
        image_url="https://cdn.example.com/favorite-variant-1.jpg",
        is_main=True,
    )
    PerfumeryVariantImage.objects.create(
        variant=variant,
        image_url="https://cdn.example.com/favorite-variant-2.jpg",
        sort_order=1,
    )

    serializer = AddToFavoriteSerializer(data={
        "product_type": "perfumery",
        "product_slug": variant.slug,
    })

    assert serializer.is_valid(), serializer.errors
    shadow = serializer.validated_data["_product"]
    assert shadow.product_type == "perfumery"
    assert shadow.external_data["source_variant_slug"] == variant.slug
    assert serializer.validated_data["_chosen_size"] == ""

    favorite = Favorite.objects.create(
        session_key=f"variant-parent-{suffix}",
        content_type=ContentType.objects.get_for_model(Product),
        object_id=shadow.pk,
    )
    favorite_product = FavoriteSerializer(favorite).data["product"]
    assert favorite_product["favorite_variant_slug"] == variant.slug
    assert favorite_product["favorite_parent_slug"] == perfume.slug
    assert len(favorite_product["images"]) == 2


@pytest.mark.django_db
def test_size_free_check_and_remove_match_legacy_sized_favorite():
    suffix = uuid.uuid4().hex
    product = Product.objects.create(
        name="Legacy sized favorite",
        slug=f"legacy-sized-favorite-{suffix}",
        product_type="accessories",
        price=20,
        is_active=True,
    )
    favorite = Favorite.objects.create(
        session_key=f"legacy-sized-{suffix}",
        content_type=ContentType.objects.get_for_model(Product),
        object_id=product.pk,
        chosen_size="XL",
    )
    client = APIClient()
    headers = {"HTTP_X_CART_SESSION": f"legacy-sized-{suffix}"}

    check_response = client.get(
        "/api/catalog/favorites/check",
        {"product_id": product.pk, "product_type": "accessories"},
        **headers,
    )
    assert check_response.status_code == status.HTTP_200_OK
    assert check_response.data["is_favorite"] is True

    remove_response = client.delete(
        "/api/catalog/favorites/remove",
        {"product_id": product.pk, "product_type": "accessories"},
        format="json",
        **headers,
    )
    assert remove_response.status_code == status.HTTP_200_OK
    assert not Favorite.objects.filter(pk=favorite.pk).exists()


@pytest.mark.django_db
def test_service_slug_resolves_for_favorites_without_cart_product_shadow():
    service = Service.objects.create(
        name="Favorite service",
        slug=f"favorite-service-{uuid.uuid4().hex}",
        price=100,
        is_active=True,
    )

    serializer = AddToFavoriteSerializer(data={
        "product_type": "uslugi",
        "product_slug": service.slug,
    })

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["_product"] == service
    assert serializer.validated_data["_product_type"] == "uslugi"
    assert serializer.validated_data["_chosen_size"] == ""


@pytest.mark.django_db
def test_remove_by_favorite_id_deletes_exact_row_despite_product_id_collisions():
    product = Product.objects.create(
        name="Exact favorite",
        slug=f"exact-favorite-{uuid.uuid4().hex}",
        product_type="accessories",
        price=30,
        is_active=True,
    )
    favorite = Favorite.objects.create(
        session_key="favorite-identity-session",
        content_type=ContentType.objects.get_for_model(Product),
        object_id=product.pk,
    )
    client = APIClient()

    response = client.delete(
        "/api/catalog/favorites/remove",  # router trailing_slash=False
        {"favorite_id": favorite.pk},
        format="json",
        HTTP_X_CART_SESSION="favorite-identity-session",
    )

    assert response.status_code == status.HTTP_200_OK
    assert not Favorite.objects.filter(pk=favorite.pk).exists()
