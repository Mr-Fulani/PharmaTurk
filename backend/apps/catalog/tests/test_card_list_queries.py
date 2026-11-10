"""Списки разделов с view=card: только поля карточки, без N+1 и детоаста.

Ответ view=card сжимается до полей карточки (compact_card_product_payload).
Раньше полный сериализатор сначала считал всё остальное — вложенные
категорию и бренд со счётчиками, SEO, атрибуты с переводами ключей: обувь
давала ~230 SQL на страницу из 12 товаров (docs/CATALOG_LIST_PERFORMANCE.md).
"""

import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.request import Request
from rest_framework.test import APIClient

from apps.catalog.card_payload import compact_card_product_payload
from apps.catalog.models import ClothingProduct, ShoeProduct
from apps.catalog.tests.test_brand_storefront_performance import _medicine, medicine_brand  # noqa: F401
from apps.catalog.tests.test_domain_variant_queries import DOMAINS, _add_products, _brand_with_category
from apps.catalog.views import ClothingProductViewSet, ShoeProductViewSet
from apps.feedback.review_aggregates import attach_review_aggregates

ENDPOINTS = {
    "clothing": "/api/catalog/clothing/products",
    "shoes": "/api/catalog/shoes/products",
    "furniture": "/api/catalog/furniture/products",
    "jewelry": "/api/catalog/jewelry/products",
    "headwear": "/api/catalog/headwear/products",
    "underwear": "/api/catalog/underwear/products",
    "islamic_clothing": "/api/catalog/islamic-clothing/products",
}

# Запросы, которых в карточке быть не должно: счётчик товаров бренда,
# переводы ключей атрибутов, счётчики подкатегорий.
_FORBIDDEN = re.compile(
    r'COUNT\(\*\) AS "__count" FROM "catalog_product" WHERE \("catalog_product"."brand_id"'
    r'|FROM "catalog_globalattributekeytranslation"'
    r'|COUNT\(\*\) AS "__count" FROM "catalog_category"'
)


@pytest.fixture(autouse=True)
def _no_image_downloads(monkeypatch):
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)


def _params(category, **extra):
    return {"category_slug": category.slug, "ordering": "name_asc", "page_size": 12, **extra}


def _card(client, url, category):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url, _params(category, view="card"))
    assert response.status_code == 200
    return response.json(), [query["sql"] for query in ctx.captured_queries]


def _expected_cards(client, url, category):
    """Прежний ответ: полный список, сжатый до карточки, + отзывы."""
    full = client.get(url, _params(category)).json()
    rows = [compact_card_product_payload(row) for row in full["results"]]
    attach_review_aggregates(rows)
    return full, rows


@pytest.mark.django_db
@pytest.mark.parametrize("domain", sorted(ENDPOINTS))
def test_card_list_matches_compacted_full_list(domain):
    brand, category, suffix = _brand_with_category(domain)
    _add_products(domain, brand, category, suffix, start=0, count=3)
    client = APIClient()
    url = ENDPOINTS[domain]

    card, _ = _card(client, url, category)
    full, expected = _expected_cards(client, url, category)

    assert card["count"] == full["count"] == 3
    assert card["results"] == expected
    assert all(row["brand_id"] == brand.id for row in card["results"])


@pytest.mark.django_db
@pytest.mark.parametrize("domain", sorted(ENDPOINTS))
def test_card_list_queries_do_not_grow_with_products(domain):
    brand, category, suffix = _brand_with_category(domain)
    client = APIClient()
    url = ENDPOINTS[domain]

    _add_products(domain, brand, category, suffix, start=0, count=2)
    small, small_sql = _card(client, url, category)
    _add_products(domain, brand, category, suffix, start=2, count=6)
    large, large_sql = _card(client, url, category)

    assert len(small["results"]) == 2 and len(large["results"]) == 8
    # «<=»: ContentType фасетов кэшируется процессом после первого ответа.
    assert len(large_sql) <= len(small_sql), "\n".join(large_sql)
    assert [sql for sql in large_sql if _FORBIDDEN.search(sql)] == []
    # Дампы парсеров карточке не нужны: выборка страницы их не читает
    # (подзапрос копий вариантов с алиасом U0 читает только индекс).
    table = DOMAINS[domain][0]._meta.db_table
    page_sql = [sql for sql in large_sql if sql.startswith(f'SELECT "{table}"."id", "{table}"."name"')]
    assert page_sql and all(f'"{table}"."external_data"' not in sql for sql in page_sql)


@pytest.mark.django_db
def test_brand_card_page_matches_full_page_and_does_not_grow():
    brand, category, suffix = _brand_with_category("shoes")
    client = APIClient()
    url = f"/api/catalog/brands/{brand.slug}/products"
    params = {"ordering": "name_asc", "page_size": 24}

    _add_products("shoes", brand, category, suffix, start=0, count=2)
    with CaptureQueriesContext(connection) as small:
        assert client.get(url, {**params, "view": "card"}).status_code == 200
    _add_products("clothing", brand, category, suffix, start=0, count=4)
    with CaptureQueriesContext(connection) as large:
        card = client.get(url, {**params, "view": "card"}).json()

    full = client.get(url, params).json()
    expected = [compact_card_product_payload(row) for row in full["results"]]
    attach_review_aggregates(expected)
    assert card["count"] == 6
    assert card["results"] == expected
    # Новый домен на странице добавляет свои prefetch-запросы, но не запросы на товар.
    large_sql = [query["sql"] for query in large.captured_queries]
    assert [sql for sql in large_sql if _FORBIDDEN.search(sql)] == []
    assert len(large_sql) - len(small.captured_queries) <= 12


@pytest.mark.django_db
@pytest.mark.parametrize("viewset, model", [
    (ShoeProductViewSet, ShoeProduct),
    (ClothingProductViewSet, ClothingProduct),
])
def test_source_variant_exclusion_uses_partial_index(rf, viewset, model):
    """Копии вариантов отсекаются подзапросом по индексу 0217, а не `?` в основном запросе."""
    view = viewset()
    view.request = Request(rf.get("/", {"view": "card"}))
    view.action = "list"
    view.format_kwarg = None
    queryset = view.get_queryset()
    sql, params = queryset.order_by().values("id").query.sql_with_params()

    table = model._meta.db_table
    assert f'"{table}"."external_data" ?' not in sql
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())
    assert f"{table}_source_variant_idx" in plan


@pytest.mark.django_db
def test_medicine_brand_card_page_does_not_grow(medicine_brand):
    """Лекарства без своих картинок берут их у теневого Product — prefetch, не запрос на товар."""
    from apps.catalog.models import ProductImage

    brand, category = medicine_brand
    client = APIClient()
    url = f"/api/catalog/brands/{brand.slug}/products"

    def add(index):
        medicine = _medicine(brand, category, f"Drug {index}", external_data={"raw": "x" * 5000})
        ProductImage.objects.create(
            product_id=medicine.base_product_id, image_url=f"https://cdn.example.com/{index}.jpg", is_main=True
        )

    add(0)
    with CaptureQueriesContext(connection) as one:
        first = client.get(url, {"view": "card", "ordering": "name_asc"}).json()
    for index in range(1, 6):
        add(index)
    with CaptureQueriesContext(connection) as six:
        page = client.get(url, {"view": "card", "ordering": "name_asc"}).json()

    assert first["results"][0]["main_image_url"]
    assert len(page["results"]) == 6 and all(row["main_image_url"] for row in page["results"])
    assert len(six.captured_queries) <= len(one.captured_queries)
    hydrate = [q["sql"] for q in six.captured_queries if q["sql"].startswith('SELECT "catalog_medicineproduct"."id", ')]
    assert hydrate and all('"catalog_medicineproduct"."external_data"' not in sql for sql in hydrate)


@pytest.mark.django_db
def test_brand_shadow_products_exclusion_uses_partial_index():
    """Теневые Product бренда: служебные строки — подзапросом по catalog_product_nonpublic_id_idx."""
    from apps.catalog.models import Product
    from apps.catalog.views import BrandViewSet

    queryset, _ = BrandViewSet()._brand_base_queryset(Product, brand_id=1, excluded_product_types={"shoes"})
    sql, params = queryset.values_list("id", "name").query.sql_with_params()

    assert '"catalog_product"."external_data" ?' not in sql
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())
    assert "catalog_product_nonpublic_id_idx" in plan
