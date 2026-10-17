import pytest
from django.db import connection
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.catalog.views import MedicineProductViewSet


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ordering", "index_name"),
    [
        ("popular", "catalog_medicine_nonstub_rank_idx"),
        ("name_asc", "catalog_medicine_nonstub_name_id_idx"),
        ("name_desc", "catalog_medicine_nonstub_name_id_idx"),
        ("price_asc", "catalog_medicine_nonstub_price_asc_idx"),
        ("price_desc", "catalog_medicine_nonstub_price_desc_idx"),
    ],
)
def test_medicine_card_order_can_use_partial_index(ordering, index_name):
    """Предикаты 0212 обязаны доказываться из SQL, который строит ORM для карточек."""
    request = Request(APIRequestFactory().get(
        "/api/catalog/medicines/products",
        {"view": "card", "ordering": ordering, "page_size": 12},
    ))
    view = MedicineProductViewSet(request=request, action="list", format_kwarg=None)
    sql, params = view.get_queryset()[:12].query.sql_with_params()

    with connection.cursor() as cursor:
        # На пустой тестовой БД планировщик выберет seq scan; запрещаем его,
        # чтобы проверить именно применимость частичного индекса.
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute("SET LOCAL enable_sort = off")
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert index_name in plan
