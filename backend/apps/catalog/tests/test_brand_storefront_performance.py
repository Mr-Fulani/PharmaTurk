"""Скорость витрины бренда: /api/catalog/brands/<slug>, /products, /categories.

На проде (октябрь 2026) страница бренда открывалась 2–7 с: условия на
external_data детоастили дампы парсеров, у каждого из 24 товаров заново
считались счётчики категорий, detail аннотировал COUNT через JOIN.
"""

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import Brand, Category, MedicineProduct, Product
from apps.catalog.views import BrandViewSet


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _medicine(brand, category, name, **extra):
    product = MedicineProduct.objects.create(
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{_suffix()}",
        category=category,
        brand=brand,
        price=100,
        currency="TRY",
        is_active=True,
        is_available=True,
        **extra,
    )
    # Shadow Product создаётся и привязывается сигналом уже после create().
    product.refresh_from_db()
    return product


@pytest.fixture
def medicine_brand(db):
    suffix = _suffix()
    category = Category.objects.create(name="Медицина", slug=f"medicines-{suffix}")
    brand = Brand.objects.create(
        name=f"Pharma {suffix}",
        slug=f"pharma-{suffix}",
        primary_category_slug=category.slug,
        category_slugs=[category.slug],
    )
    return brand, category


def _cat_count_queries(captured):
    """Запросы CategorySerializer.get_products_count: GROUP BY по всем товарам и услугам."""
    return [
        q["sql"] for q in captured
        if 'AS "cnt"' in q["sql"] and "brand_id" not in q["sql"]
    ]


@pytest.mark.django_db
def test_brand_storefront_excludes_service_domain_rows(medicine_brand):
    """Варианты и заглушки исключаются подзапросами — как прежними условиями на external_data."""
    brand, category = medicine_brand
    _medicine(brand, category, "Visible")

    own_variant = _medicine(brand, category, "Own variant")
    MedicineProduct.objects.filter(pk=own_variant.pk).update(external_data={"source_variant_id": 7})
    Product.objects.filter(pk=own_variant.base_product_id).update(external_data={})

    stub_base = _medicine(brand, category, "Stub base")
    assert stub_base.base_product_id is not None
    Product.objects.filter(pk=stub_base.base_product_id).update(external_data={"is_stub": True})

    variant_base = _medicine(brand, category, "Variant base")
    Product.objects.filter(pk=variant_base.base_product_id).update(
        external_data={"source_variant_slug": "parent"}
    )

    # Без shadow Product строка остаётся публичной (как при прежнем LEFT JOIN).
    orphan = _medicine(brand, category, "Orphan")
    MedicineProduct.objects.filter(pk=orphan.pk).update(base_product=None)

    client = APIClient()
    products = client.get(f"/api/catalog/brands/{brand.slug}/products", {"ordering": "name_asc"})
    categories = client.get(f"/api/catalog/brands/{brand.slug}/categories")

    assert products.status_code == 200
    assert products.json()["count"] == 2
    assert [row["name"] for row in products.json()["results"]] == ["Orphan", "Visible"]
    assert categories.json()["results"][0]["product_count"] == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "model",
    [model for model, excluded in BrandViewSet()._brand_source_models() if excluded is None],
    ids=lambda model: model.__name__,
)
def test_brand_source_exclusions_can_use_partial_indexes(model):
    """Предикаты 0217 обязаны доказываться из SQL витрины для каждой доменной модели."""
    queryset, _ = BrandViewSet()._brand_base_queryset(model, brand_id=1)
    sql, params = queryset.values_list("id", "name").query.sql_with_params()

    with connection.cursor() as cursor:
        # На пустой тестовой БД планировщик выберет seq scan; запрещаем его,
        # чтобы проверить именно применимость частичных индексов.
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert f"{model._meta.db_table}_source_variant_idx" in plan
    assert "catalog_product_nonpublic_id_idx" in plan


@pytest.mark.django_db
def test_brand_products_counts_categories_once_per_page(medicine_brand):
    """Батч-кэш категорий общий на страницу: счётчики не пересчитываются на каждый товар."""
    brand, category = medicine_brand
    for index in range(5):
        _medicine(brand, category, f"Drug {index}")

    with CaptureQueriesContext(connection) as one:
        response = APIClient().get(f"/api/catalog/brands/{brand.slug}/products", {"page_size": 1})
    assert response.status_code == 200
    with CaptureQueriesContext(connection) as five:
        response = APIClient().get(f"/api/catalog/brands/{brand.slug}/products", {"page_size": 5})
    assert len(response.json()["results"]) == 5

    # Product + Service — один раз на запрос, сколько бы товаров ни было.
    assert len(_cat_count_queries(five.captured_queries)) == len(_cat_count_queries(one.captured_queries)) <= 2
    # Вложенная категория/бренд сериализуются один раз; на товар остаются
    # только его собственные связи.
    assert len(five.captured_queries) - len(one.captured_queries) <= 4 * 4


@pytest.mark.django_db
def test_brand_products_card_view_is_compact(medicine_brand):
    """view=card: те же товары и порядок, но без вложенных бренда/категории и длинных инструкций."""
    brand, category = medicine_brand
    for index in range(3):
        _medicine(brand, category, f"Drug {index}", description="Инструкция. " * 500)

    client = APIClient()
    full = client.get(f"/api/catalog/brands/{brand.slug}/products", {"ordering": "name_asc"}).json()
    with CaptureQueriesContext(connection) as ctx:
        card = client.get(
            f"/api/catalog/brands/{brand.slug}/products",
            {"ordering": "name_asc", "view": "card"},
        ).json()

    assert card["count"] == full["count"] == 3
    assert [row["id"] for row in card["results"]] == [row["id"] for row in full["results"]]
    for row in card["results"]:
        assert "brand" not in row and "category" not in row
        assert row["brand_id"] == brand.id
        assert len(row["description"]) <= 240
        assert row["price_formatted"]
    # Счётчики вложенных категорий в карточке не нужны и не считаются.
    assert _cat_count_queries(ctx.captured_queries) == []


@pytest.mark.django_db
def test_brand_detail_count_is_exact_without_join_annotation(medicine_brand):
    """Detail: точный products_count отдельным COUNT, без аннотации через JOIN всех товаров."""
    brand, category = medicine_brand
    _medicine(brand, category, "Public")
    stub = _medicine(brand, category, "Stub")
    Product.objects.filter(pk=stub.base_product_id).update(external_data={"is_stub": True})

    with CaptureQueriesContext(connection) as ctx:
        response = APIClient().get(f"/api/catalog/brands/{brand.slug}")

    assert response.status_code == 200
    assert response.json()["products_count"] == 1
    brand_queries = [q["sql"] for q in ctx.captured_queries if 'FROM "catalog_brand"' in q["sql"]]
    assert brand_queries and all("catalog_product" not in sql for sql in brand_queries)
    # Счётчик — один COUNT по частичному индексу 0208 (brand_id + публичный предикат).
    count_queries = [q["sql"] for q in ctx.captured_queries if 'COUNT(*) AS "__count"' in q["sql"]]
    assert len(count_queries) == 1
