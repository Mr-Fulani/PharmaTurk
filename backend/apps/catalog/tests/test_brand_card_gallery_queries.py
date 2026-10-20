"""N+1 галереи товара и переводов ключей атрибутов на странице бренда.

Витрина бренда (/api/catalog/brands/<slug>/products) prefetch-ит images и
dynamic_attributes__attribute_key__translations. Главная картинка, галерея
карточки и название ключа атрибута берутся из этого кэша: число запросов к
таблицам картинок товара и переводов ключей не растёт с числом товаров. Без
prefetch ответ прежний — его и сравниваем с ответом по кэшу.
"""

import re
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.models import prefetch_related_objects
from django.test.utils import CaptureQueriesContext
from django.utils import translation
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from apps.catalog.models import (
    Brand,
    Category,
    ClothingProduct,
    ClothingProductImage,
    ClothingVariant,
    ClothingVariantImage,
    ElectronicsProduct,
    ElectronicsProductImage,
    FurnitureProduct,
    FurnitureProductImage,
    FurnitureVariant,
    FurnitureVariantImage,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    HeadwearProduct,
    HeadwearProductImage,
    HeadwearVariant,
    HeadwearVariantImage,
    IslamicClothingProduct,
    IslamicClothingProductImage,
    IslamicClothingVariant,
    IslamicClothingVariantImage,
    JewelryProduct,
    JewelryProductImage,
    JewelryVariant,
    JewelryVariantImage,
    ProductAttributeValue,
    ShoeProduct,
    ShoeProductImage,
    ShoeVariant,
    ShoeVariantImage,
    UnderwearProduct,
    UnderwearProductImage,
    UnderwearVariant,
    UnderwearVariantImage,
)
from apps.catalog.serializers import (
    ClothingProductSerializer,
    ElectronicsProductSerializer,
    FurnitureProductSerializer,
    HeadwearProductSerializer,
    IslamicClothingProductSerializer,
    JewelryProductSerializer,
    ShoeProductSerializer,
    UnderwearProductSerializer,
)
from apps.catalog.views import BrandViewSet

# домен: (товар, картинка товара, вариант, картинка варианта, сериализатор)
DOMAINS = {
    "clothing": (
        ClothingProduct, ClothingProductImage, ClothingVariant, ClothingVariantImage,
        ClothingProductSerializer,
    ),
    "shoes": (
        ShoeProduct, ShoeProductImage, ShoeVariant, ShoeVariantImage,
        ShoeProductSerializer,
    ),
    "electronics": (
        ElectronicsProduct, ElectronicsProductImage, None, None,
        ElectronicsProductSerializer,
    ),
    "furniture": (
        FurnitureProduct, FurnitureProductImage, FurnitureVariant, FurnitureVariantImage,
        FurnitureProductSerializer,
    ),
    "jewelry": (
        JewelryProduct, JewelryProductImage, JewelryVariant, JewelryVariantImage,
        JewelryProductSerializer,
    ),
    "headwear": (
        HeadwearProduct, HeadwearProductImage, HeadwearVariant, HeadwearVariantImage,
        HeadwearProductSerializer,
    ),
    "underwear": (
        UnderwearProduct, UnderwearProductImage, UnderwearVariant, UnderwearVariantImage,
        UnderwearProductSerializer,
    ),
    "islamic_clothing": (
        IslamicClothingProduct, IslamicClothingProductImage, IslamicClothingVariant,
        IslamicClothingVariantImage, IslamicClothingProductSerializer,
    ),
}

_WATCHED_TABLE = re.compile(r'"catalog_(\w*productimage|globalattributekeytranslation)"')


@pytest.fixture(autouse=True)
def _no_image_downloads(monkeypatch):
    """Сигнал автоскачивания картинок не ходит в сеть за тестовыми URL."""
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)


def _attribute_keys(suffix):
    """Ключ с RU/EN, ключ только с турецким переводом и ключ без переводов."""
    material = GlobalAttributeKey.objects.create(slug=f"material-{suffix}", sort_order=0)
    GlobalAttributeKeyTranslation.objects.create(key_obj=material, locale="ru", name="Материал")
    GlobalAttributeKeyTranslation.objects.create(key_obj=material, locale="en", name="Material")
    pattern = GlobalAttributeKey.objects.create(slug=f"desen-{suffix}", sort_order=1)
    GlobalAttributeKeyTranslation.objects.create(key_obj=pattern, locale="tr", name="Desen")
    raw = GlobalAttributeKey.objects.create(slug=f"raw-{suffix}", sort_order=2)
    return [material, pattern, raw]


def _add_products(domain, brand, category, keys, suffix, start, count):
    """Товары без main_image — карточка берёт картинку из галереи товара.

    У чётных товаров главная картинка галереи — вторая по порядку, у нечётных
    главной нет (берётся первая). У каждого третьего — вариант с картинкой:
    галерея карточки сливает кадры варианта и товара.
    """
    product_model, image_model, variant_model, variant_image_model, _ = DOMAINS[domain]
    slug_base = f"gallery-{domain.replace('_', '-')}"
    products = []
    for index in range(start, start + count):
        product = product_model.objects.create(
            name=f"Item {index}",
            slug=f"{slug_base}-{index}-{suffix}",
            category=category,
            brand=brand,
            price=100,
            currency="TRY",
            is_active=True,
        )
        for image_position in range(2):
            image_model.objects.create(
                product=product,
                image_url=f"https://cdn.example.com/{suffix}/{index}/p{image_position}.jpg",
                sort_order=image_position,
                is_main=index % 2 == 0 and image_position == 1,
            )
        if variant_model is not None and index % 3 == 0:
            variant = variant_model.objects.create(
                product=product,
                name=f"Item {index} v0",
                slug=f"{slug_base}-{index}-v0-{suffix}",
                color="black",
                price=150,
                currency="TRY",
                is_active=True,
                sort_order=0,
            )
            variant_image_model.objects.create(
                variant=variant,
                image_url=f"https://cdn.example.com/{suffix}/{index}/v0.jpg",
                sort_order=0,
                is_main=True,
            )
        for position, key in enumerate(keys):
            ProductAttributeValue.objects.create(
                content_object=product,
                attribute_key=key,
                value=f"value {position}",
                sort_order=position,
            )
        products.append(product)
    return products


def _brand_with_category(domain):
    suffix = uuid.uuid4().hex[:8]
    slug_part = domain.replace("_", "-")
    category = Category.objects.create(name=f"Cat {domain}", slug=f"cat-gallery-{slug_part}-{suffix}")
    brand = Brand.objects.create(name=f"Brand gallery {domain} {suffix}", slug=f"brand-gallery-{slug_part}-{suffix}")
    return brand, category, suffix


def _brand_page_watched_queries(client, brand):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(f"/api/catalog/brands/{brand.slug}/products", {"page_size": 24})
    assert response.status_code == 200
    watched = [query["sql"] for query in ctx.captured_queries if _WATCHED_TABLE.search(query["sql"])]
    return response.json(), watched


@pytest.mark.django_db
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_brand_page_gallery_and_attribute_key_queries_do_not_grow_with_products(domain):
    brand, category, suffix = _brand_with_category(domain)
    keys = _attribute_keys(suffix)
    client = APIClient()

    _add_products(domain, brand, category, keys, suffix, start=0, count=2)
    small_page, small_queries = _brand_page_watched_queries(client, brand)
    _add_products(domain, brand, category, keys, suffix, start=2, count=4)
    large_page, large_queries = _brand_page_watched_queries(client, brand)

    assert small_page["count"] == 2
    assert large_page["count"] == 6
    assert all(row["images"] for row in large_page["results"])
    assert all(len(row["dynamic_attributes"]) == len(keys) for row in large_page["results"])
    assert len(large_queries) == len(small_queries), "\n".join(large_queries)


@pytest.mark.django_db
@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_prefetched_gallery_and_attribute_keys_give_same_payload_as_database(domain):
    """Ответ по prefetch-кэшу страницы бренда совпадает с ответом через запросы к БД."""
    brand, category, suffix = _brand_with_category(domain)
    keys = _attribute_keys(suffix)
    products = _add_products(domain, brand, category, keys, suffix, start=0, count=4)
    product_model, *_, serializer_class = DOMAINS[domain]
    lookups = [
        name for name in BrandViewSet.BRAND_CARD_PREFETCH
        if BrandViewSet._is_valid_relation_path(product_model, name)
    ]
    assert "dynamic_attributes__attribute_key__translations" in lookups
    request = Request(APIRequestFactory().get("/"))
    contexts = {
        "card": {"request": request},
        "detail": {"request": request, "view": SimpleNamespace(action="retrieve")},
    }

    for product in products:
        for lang in ("ru", "en", "en-us", "tr"):
            for name, context in contexts.items():
                plain = product_model.objects.get(pk=product.pk)
                prefetched = product_model.objects.get(pk=product.pk)
                prefetch_related_objects([prefetched], *lookups)

                with translation.override(lang):
                    expected = serializer_class(plain, context=context).data
                    actual = serializer_class(prefetched, context=context).data

                assert actual == expected, (domain, product.slug, lang, name)
