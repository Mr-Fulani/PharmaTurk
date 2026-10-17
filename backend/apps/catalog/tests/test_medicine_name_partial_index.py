import pytest
from django.db import connection
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.catalog.views import MedicineProductViewSet


@pytest.mark.django_db
def test_medicine_card_name_order_can_use_partial_index():
    """Предикат 0209 обязан доказываться из SQL, который строит ORM для карточек."""
    request = Request(APIRequestFactory().get(
        "/api/catalog/medicines/products",
        {"view": "card", "ordering": "name_asc", "page_size": 12},
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

    assert "catalog_medicine_nonstub_name_idx" in plan
