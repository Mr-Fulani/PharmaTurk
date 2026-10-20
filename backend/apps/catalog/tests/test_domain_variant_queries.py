"""N+1 вариантов в доменных сериализаторах каталога.

Витрина бренда (/api/catalog/brands/<slug>/products) prefetch-ит variants,
variants__images и variants__sizes. Сериализаторы обязаны брать default/active
вариант, картинки и список вариантов из этого кэша: число запросов к таблицам
вариантов не должно расти с числом товаров на странице. Без prefetch ответ
прежний — его и сравниваем с ответом по кэшу.
"""

import re
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.models import prefetch_related_objects
from django.test.utils import CaptureQueriesContext
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.catalog.models import (
    Brand,
    Category,
    ClothingProduct,
    ClothingVariant,
    ClothingVariantImage,
    ClothingVariantSize,
    FurnitureProduct,
    FurnitureVariant,
    FurnitureVariantImage,
    HeadwearProduct,
    HeadwearVariant,
    HeadwearVariantImage,
    HeadwearVariantSize,
    IslamicClothingProduct,
    IslamicClothingVariant,
    IslamicClothingVariantImage,
    IslamicClothingVariantSize,
    JewelryProduct,
    JewelryVariant,
    JewelryVariantImage,
    JewelryVariantSize,
    PerfumeryProduct,
    PerfumeryVariant,
    PerfumeryVariantImage,
    ShoeProduct,
    ShoeVariant,
    ShoeVariantImage,
    ShoeVariantSize,
    UnderwearProduct,
    UnderwearVariant,
    UnderwearVariantImage,
    UnderwearVariantSize,
)
from apps.catalog.serializers import (
    ClothingProductSerializer,
    FurnitureProductSerializer,
    HeadwearProductSerializer,
    IslamicClothingProductSerializer,
    JewelryProductSerializer,
    PerfumeryProductSerializer,
    ShoeProductSerializer,
    UnderwearProductSerializer,
)

# домен: (товар, вариант, картинка варианта, размер варианта, поля размера, сериализатор)
DOMAINS = {
    "clothing": (
        ClothingProduct, ClothingVariant, ClothingVariantImage, ClothingVariantSize,
        {"size": "M"}, ClothingProductSerializer,
    ),
    "shoes": (
        ShoeProduct, ShoeVariant, ShoeVariantImage, ShoeVariantSize,
        {"size": "42"}, ShoeProductSerializer,
    ),
    "furniture": (
        FurnitureProduct, FurnitureVariant, FurnitureVariantImage, None,
        None, FurnitureProductSerializer,
    ),
    "jewelry": (
        JewelryProduct, JewelryVariant, JewelryVariantImage, JewelryVariantSize,
        {"size_value": 17, "size_display": "17"}, JewelryProductSerializer,
    ),
    "perfumery": (
        PerfumeryProduct, PerfumeryVariant, PerfumeryVariantImage, None,
        None, PerfumeryProductSerializer,
    ),
    "headwear": (
        HeadwearProduct, HeadwearVariant, HeadwearVariantImage, HeadwearVariantSize,
        {"size": "M"}, HeadwearProductSerializer,
    ),
    "underwear": (
        UnderwearProduct, UnderwearVariant, UnderwearVariantImage, UnderwearVariantSize,
        {"size": "M"}, UnderwearProductSerializer,
    ),
    "islamic_clothing": (
        IslamicClothingProduct, IslamicClothingVariant, IslamicClothingVariantImage,
        IslamicClothingVariantSize, {"size": "M"}, IslamicClothingProductSerializer,
    ),
}

_VARIANT_TABLE = re.compile(r'"catalog_\w*variant\w*"')


@pytest.fixture(autouse=True)
def _no_image_downloads(monkeypatch):
    """Сигнал автоскачивания картинок не ходит в сеть за тестовыми URL."""
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)


def _add_products(domain, brand, category, suffix, start, count):
    """Товары без собственных картинок — карточка берёт их у вариантов.

    Чётные товары — с двумя активными вариантами (карточная галерея расцветок),
    нечётные — с одним; у каждого ещё один неактивный вариант. Главная картинка
    варианта — вторая по порядку, чтобы различались «is_main» и «первая».
    """
    product_model, variant_model, image_model, size_model, size_fields, _ = DOMAINS[domain]
    products = []
    for index in range(start, start + count):
        product = product_model.objects.create(
            name=f"Item {index}",
            slug=f"item-{domain.replace('_', '-')}-{index}-{suffix}",
            category=category,
            brand=brand,
            price=100,
            currency="TRY",
            is_active=True,
            **({"gender": "unisex"} if domain == "perfumery" else {}),
        )
        active_count = 2 if index % 2 == 0 else 1
        for position in range(active_count + 1):
            extra = {"color": f"color-{position}"} if domain != "perfumery" else {}
            variant = variant_model.objects.create(
                product=product,
                name=f"Item {index} v{position}",
                slug=f"item-{domain.replace('_', '-')}-{index}-v{position}-{suffix}",
                **extra,
                price=150 + position,
                old_price=200 + position,
                currency="TRY",
                is_active=position < active_count,
                sort_order=position,
            )
            for image_position in range(2):
                image_model.objects.create(
                    variant=variant,
                    image_url=f"https://cdn.example.com/{suffix}/{index}/{position}/{image_position}.jpg",
                    sort_order=image_position,
                    is_main=image_position == 1,
                )
            if size_model is not None:
                size_model.objects.create(variant=variant, **size_fields)
        products.append(product)
    return products


def _brand_with_category(domain):
    suffix = uuid.uuid4().hex[:8]
    category = Category.objects.create(name=f"Cat {domain}", slug=f"cat-{domain.replace('_', '-')}-{suffix}")
    brand = Brand.objects.create(name=f"Brand {domain} {suffix}", slug=f"brand-{domain.replace('_', '-')}-{suffix}")
    return brand, category, suffix


def _brand_page_variant_queries(client, brand):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(f"/api/catalog/brands/{brand.slug}/products", {"page_size": 24})
    assert response.status_code == 200
    variant_sql = [query["sql"] for query in ctx.captured_queries if _VARIANT_TABLE.search(query["sql"])]
    return response.json(), variant_sql


@pytest.mark.django_db
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_brand_page_variant_queries_do_not_grow_with_products(domain):
    brand, category, suffix = _brand_with_category(domain)
    client = APIClient()

    _add_products(domain, brand, category, suffix, start=0, count=2)
    small_page, small_queries = _brand_page_variant_queries(client, brand)
    _add_products(domain, brand, category, suffix, start=2, count=4)
    large_page, large_queries = _brand_page_variant_queries(client, brand)

    assert small_page["count"] == 2
    assert large_page["count"] == 6
    assert all(row["active_variant_slug"] for row in large_page["results"])
    assert len(large_queries) == len(small_queries), "\n".join(large_queries)


def _request():
    return Request(APIRequestFactory().get("/"))


def _contexts(variant_slug):
    request = _request()
    retrieve_view = SimpleNamespace(action="retrieve")
    return {
        "card": {"request": request},
        "detail": {"request": request, "view": retrieve_view},
        "detail_variant": {
            "request": request,
            "view": retrieve_view,
            "active_variant_slug": variant_slug,
        },
        "missing_variant": {"request": request, "active_variant_slug": "no-such-variant"},
    }


@pytest.mark.django_db
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_prefetched_variants_give_same_payload_as_database(domain):
    """Ответ по prefetch-кэшу совпадает с прежним ответом через запросы к БД."""
    brand, category, suffix = _brand_with_category(domain)
    products = _add_products(domain, brand, category, suffix, start=0, count=2)
    product_model, *_, serializer_class = DOMAINS[domain]
    lookups = ["variants", "variants__images"]
    if DOMAINS[domain][3] is not None:
        lookups.append("variants__sizes")

    for product in products:
        second_variant = product.variants.filter(is_active=True).order_by("sort_order").last()
        for name, context in _contexts(second_variant.slug).items():
            plain = product_model.objects.get(pk=product.pk)
            prefetched = product_model.objects.get(pk=product.pk)
            prefetch_related_objects([prefetched], *lookups)

            expected = serializer_class(plain, context=context).data
            actual = serializer_class(prefetched, context=context).data

            assert actual == expected, (domain, product.slug, name)
