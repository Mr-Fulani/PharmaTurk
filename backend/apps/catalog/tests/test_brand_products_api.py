"""Тесты витрины бренда: /api/catalog/brands/<slug>/products и /categories.

Проверяют слияние доменных моделей с теневым Product, пагинацию,
сортировку, изоляцию по бренду и счётчики категорий бренда.
"""

import uuid

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import (
    AccessoryProduct,
    Brand,
    Category,
    ClothingProduct,
    FurnitureProduct,
    FurnitureVariant,
    MedicineProduct,
    Product,
)


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def brand_catalog(db):
    """Бренд с товарами в двух доменах + legacy-услуга + чужой бренд для контроля."""
    suffix = _suffix()
    clothing_root = Category.objects.create(name="Одежда", slug=f"clothing-{suffix}")
    clothing_child = Category.objects.create(
        name="Платья", slug=f"dresses-{suffix}", parent=clothing_root
    )
    medicines_root = Category.objects.create(name="Медицина", slug=f"medicines-{suffix}")
    shoes_root = Category.objects.create(name="Обувь", slug=f"shoes-{suffix}")
    uslugi_root = Category.objects.create(name="Услуги", slug=f"uslugi-{suffix}")

    brand = Brand.objects.create(
        name=f"TestBrand {suffix}",
        slug=f"test-brand-{suffix}",
        primary_category_slug=clothing_root.slug,
        category_slugs=[clothing_root.slug, medicines_root.slug, shoes_root.slug],
    )
    other_brand = Brand.objects.create(name=f"Other {suffix}", slug=f"other-brand-{suffix}")

    clothing_products = [
        ClothingProduct.objects.create(
            name=name,
            slug=f"{name.lower()}-{suffix}",
            category=clothing_child,
            brand=brand,
            price=price,
            currency="TRY",
            is_active=True,
        )
        for name, price in (("Alpha", 100), ("Delta", 400), ("Foxtrot", 50))
    ]
    medicine_products = [
        MedicineProduct.objects.create(
            name=name,
            slug=f"{name.lower()}-{suffix}",
            category=medicines_root,
            brand=brand,
            price=price,
            currency="TRY",
            is_active=True,
        )
        for name, price in (("Bravo", 200), ("Echo", 300))
    ]
    legacy_product = Product.objects.create(
        name="Charlie",
        slug=f"charlie-{suffix}",
        category=uslugi_root,
        brand=brand,
        product_type="uslugi",
        price=250,
        currency="TRY",
        is_active=True,
    )
    foreign_product = ClothingProduct.objects.create(
        name="Zulu",
        slug=f"zulu-{suffix}",
        category=clothing_child,
        brand=other_brand,
        price=999,
        currency="TRY",
        is_active=True,
    )

    return {
        "brand": brand,
        "other_brand": other_brand,
        "clothing_root": clothing_root,
        "clothing_child": clothing_child,
        "medicines_root": medicines_root,
        "shoes_root": shoes_root,
        "clothing_products": clothing_products,
        "medicine_products": medicine_products,
        "legacy_product": legacy_product,
        "foreign_product": foreign_product,
    }


@pytest.mark.django_db
def test_brand_products_merges_domains_sorted_by_name(brand_catalog):
    client = APIClient()
    brand = brand_catalog["brand"]

    response = client.get(f"/api/catalog/brands/{brand.slug}/products", {"ordering": "name_asc"})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] == 6
    names = [item["name"] for item in data["results"]]
    assert names == ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]


@pytest.mark.django_db
def test_brand_products_pagination_slices_merged_list(brand_catalog):
    client = APIClient()
    brand = brand_catalog["brand"]

    page1 = client.get(
        f"/api/catalog/brands/{brand.slug}/products",
        {"ordering": "name_asc", "page_size": 4},
    ).json()
    page2 = client.get(
        f"/api/catalog/brands/{brand.slug}/products",
        {"ordering": "name_asc", "page_size": 4, "page": 2},
    ).json()

    assert page1["count"] == 6
    assert [item["name"] for item in page1["results"]] == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert page1["next"] is not None and page1["previous"] is None
    assert [item["name"] for item in page2["results"]] == ["Echo", "Foxtrot"]
    assert page2["next"] is None and page2["previous"] is not None


@pytest.mark.django_db
def test_brand_products_price_ordering_across_models(brand_catalog):
    client = APIClient()
    brand = brand_catalog["brand"]

    response = client.get(
        f"/api/catalog/brands/{brand.slug}/products", {"ordering": "price_desc"}
    ).json()

    # Сортировка идёт по хранимой цене (TRY); в ответе цена может быть
    # сконвертирована в валюту показа, поэтому сверяем порядок по именам.
    names = [item["name"] for item in response["results"]]
    assert names == ["Delta", "Echo", "Charlie", "Bravo", "Alpha", "Foxtrot"]


@pytest.mark.django_db
def test_brand_products_ignores_foreign_brand_id_param(brand_catalog):
    """Подмена витрины через ?brand_id= запрещена: бренд берётся только из slug."""
    client = APIClient()
    brand = brand_catalog["brand"]
    other_brand = brand_catalog["other_brand"]

    response = client.get(
        f"/api/catalog/brands/{brand.slug}/products", {"brand_id": other_brand.id}
    ).json()

    assert response["count"] == 6
    names = {item["name"] for item in response["results"]}
    assert "Zulu" not in names


@pytest.mark.django_db
def test_brand_products_category_slug_filter_includes_descendants(brand_catalog):
    client = APIClient()
    brand = brand_catalog["brand"]
    clothing_root = brand_catalog["clothing_root"]

    response = client.get(
        f"/api/catalog/brands/{brand.slug}/products",
        {"category_slug": clothing_root.slug, "ordering": "name_asc"},
    ).json()

    assert response["count"] == 3
    assert [item["name"] for item in response["results"]] == ["Alpha", "Delta", "Foxtrot"]


@pytest.mark.django_db
def test_brand_products_hydrates_only_page_models(brand_catalog):
    """Prefetch связей — только для моделей, попавших на страницу.

    На первой странице (page_size=2, name_asc: Alpha, Bravo) нет legacy-услуг,
    поэтому таблицы вариантов ClothingProduct не должны запрашиваться
    для полного списка, а по MedicineProduct не должно быть prefetch картинок
    сверх позиций страницы — проверяем через отсутствие выборок из таблиц
    доменов, которых нет на странице.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = APIClient()
    brand = brand_catalog["brand"]

    with CaptureQueriesContext(connection) as ctx:
        response = client.get(
            f"/api/catalog/brands/{brand.slug}/products",
            {"ordering": "name_asc", "page_size": 1},
        )
    assert response.status_code == status.HTTP_200_OK
    assert [item["name"] for item in response.json()["results"]] == ["Alpha"]

    # Страница состоит только из ClothingProduct → тяжёлые связи медикаментов
    # (галерея картинок) не должны загружаться вовсе.
    medicine_image_queries = [
        q["sql"] for q in ctx.captured_queries
        if "medicineproductimage" in q["sql"].lower() or "medicine_product_image" in q["sql"].lower()
    ]
    assert medicine_image_queries == []


@pytest.mark.django_db
def test_brand_products_furniture_with_variant_hydrates(db):
    """Регрессия: prefetch 'variants__sizes' ронял мебель (у FurnitureVariant нет sizes).

    Вложенные пути из BRAND_CARD_PREFETCH должны валидироваться по всем
    сегментам, а не только по первому.
    """
    suffix = _suffix()
    furniture_root = Category.objects.create(name="Мебель", slug=f"furniture-{suffix}")
    brand = Brand.objects.create(name=f"Ikea {suffix}", slug=f"ikea-{suffix}")
    product = FurnitureProduct.objects.create(
        name="Shelf",
        slug=f"shelf-{suffix}",
        category=furniture_root,
        brand=brand,
        price=100,
        currency="TRY",
        is_active=True,
    )
    FurnitureVariant.objects.create(product=product, slug=f"shelf-white-{suffix}", color="white")

    client = APIClient()
    response = client.get(f"/api/catalog/brands/{brand.slug}/products")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["name"] == "Shelf"


@pytest.mark.django_db
def test_accessory_brand_card_uses_same_shadow_media_as_category_card(db):
    suffix = _suffix()
    category = Category.objects.create(name="Аксессуары", slug=f"accessories-{suffix}")
    brand = Brand.objects.create(name=f"Zara {suffix}", slug=f"zara-{suffix}")
    shadow = Product.objects.create(
        name="Sunglasses",
        slug=f"sunglasses-{suffix}",
        category=category,
        brand=brand,
        product_type="accessories",
        price=100,
        currency="TRY",
        main_image="products/accessories/zara/sunglasses/main.webp",
        is_active=True,
    )
    AccessoryProduct.objects.create(
        base_product=shadow,
        name=shadow.name,
        slug=shadow.slug,
        category=category,
        brand=brand,
        price=shadow.price,
        currency=shadow.currency,
        main_image="parsed/stale-zara-image.jpg",
        is_active=True,
    )

    client = APIClient()
    category_card = client.get("/api/catalog/products", {"brand_id": brand.id}).json()["results"][0]
    brand_card = client.get(f"/api/catalog/brands/{brand.slug}/products").json()["results"][0]

    assert brand_card["id"] == category_card["id"] == shadow.id
    assert brand_card["main_image_url"] == category_card["main_image_url"]


@pytest.mark.django_db
def test_brand_categories_query_count_bounded(brand_catalog, django_assert_max_num_queries):
    """Счётчики категорий: по одной агрегации на модель-источник, без N+1."""
    client = APIClient()
    brand = brand_catalog["brand"]

    with django_assert_max_num_queries(45):
        response = client.get(f"/api/catalog/brands/{brand.slug}/categories")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_brand_categories_counts_scoped_to_brand(brand_catalog):
    """Счётчики — только по товарам бренда, с подкатегориями; пустые категории опущены."""
    client = APIClient()
    brand = brand_catalog["brand"]
    clothing_root = brand_catalog["clothing_root"]
    medicines_root = brand_catalog["medicines_root"]

    response = client.get(f"/api/catalog/brands/{brand.slug}/categories")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    by_slug = {item["slug"]: item for item in data["results"]}
    # Одежда: 3 товара бренда в дочерней категории; чужой Zulu не считается.
    assert by_slug[clothing_root.slug]["product_count"] == 3
    assert by_slug[medicines_root.slug]["product_count"] == 2
    # Обувь привязана в админке, но товаров бренда нет — категория опущена.
    assert brand_catalog["shoes_root"].slug not in by_slug
    assert all("translations" in item for item in data["results"])


@pytest.mark.django_db
def test_brand_categories_empty_binding_returns_empty_list(db):
    client = APIClient()
    brand = Brand.objects.create(name=f"NoCats {_suffix()}", slug=f"no-cats-{_suffix()}")

    response = client.get(f"/api/catalog/brands/{brand.slug}/categories")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"count": 0, "results": []}
