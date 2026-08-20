from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.vapi.serializers import (
    VapiFullSyncQuerySerializer,
    VapiProductDetailsQuerySerializer,
    VapiPullQuerySerializer,
    VapiSearchQuerySerializer,
)
from apps.vapi.views import (
    VapiFullSyncView,
    VapiProductDetailsView,
    VapiPullView,
    VapiSearchView,
)


INVALID_REQUESTS = (
    (VapiPullView, "/api/vapi/pull/?page=0", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?page=10001", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?page=invalid", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?page_size=0", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?page_size=101", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?category=%20", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?brand=%20", "apps.vapi.views.pull_products.delay"),
    (VapiPullView, "/api/vapi/pull/?search=%20", "apps.vapi.views.pull_products.delay"),
    (
        VapiProductDetailsView,
        "/api/vapi/product-details/",
        "apps.vapi.views.pull_product_details.delay",
    ),
    (
        VapiProductDetailsView,
        "/api/vapi/product-details/?product_id=%20",
        "apps.vapi.views.pull_product_details.delay",
    ),
    (
        VapiSearchView,
        "/api/vapi/search/?limit=10",
        "apps.vapi.views.search_products_task.delay",
    ),
    (
        VapiSearchView,
        "/api/vapi/search/?query=%20",
        "apps.vapi.views.search_products_task.delay",
    ),
    (
        VapiSearchView,
        "/api/vapi/search/?query=aspirin&limit=0",
        "apps.vapi.views.search_products_task.delay",
    ),
    (
        VapiSearchView,
        "/api/vapi/search/?query=aspirin&limit=101",
        "apps.vapi.views.search_products_task.delay",
    ),
    (
        VapiSearchView,
        "/api/vapi/search/?query=aspirin&limit=invalid",
        "apps.vapi.views.search_products_task.delay",
    ),
    (
        VapiFullSyncView,
        "/api/vapi/full-sync/?max_pages=0",
        "apps.vapi.views.full_catalog_sync.delay",
    ),
    (
        VapiFullSyncView,
        "/api/vapi/full-sync/?max_pages=101",
        "apps.vapi.views.full_catalog_sync.delay",
    ),
    (
        VapiFullSyncView,
        "/api/vapi/full-sync/?max_pages=invalid",
        "apps.vapi.views.full_catalog_sync.delay",
    ),
)


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.mark.parametrize(("view_class", "url", "task_path"), INVALID_REQUESTS)
def test_invalid_vapi_parameters_return_400_without_queueing(
    request_factory,
    view_class,
    url,
    task_path,
):
    request = request_factory.post(url)
    force_authenticate(
        request,
        user=SimpleNamespace(is_authenticated=True, is_staff=True),
    )

    with patch(task_path) as enqueue:
        response = view_class.as_view()(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    enqueue.assert_not_called()


@pytest.mark.parametrize(
    ("serializer_class", "payload"),
    (
        (VapiPullQuerySerializer, {"category": "x" * 129}),
        (VapiPullQuerySerializer, {"brand": "x" * 129}),
        (VapiPullQuerySerializer, {"search": "x" * 257}),
        (VapiProductDetailsQuerySerializer, {"product_id": "x" * 129}),
        (VapiSearchQuerySerializer, {"query": "x" * 257}),
    ),
)
def test_vapi_string_length_limits(serializer_class, payload):
    serializer = serializer_class(data=payload)

    assert not serializer.is_valid()


def test_vapi_pull_serializer_parses_boundaries_and_trims_strings():
    serializer = VapiPullQuerySerializer(
        data={
            "page": "10000",
            "page_size": "100",
            "category": " Medicines ",
            "brand": " Brand ",
            "search": " Aspirin ",
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {
        "page": 10_000,
        "page_size": 100,
        "category": "Medicines",
        "brand": "Brand",
        "search": "Aspirin",
    }


def test_vapi_query_serializers_apply_defaults_and_parse_values():
    pull = VapiPullQuerySerializer(data={})
    details = VapiProductDetailsQuerySerializer(data={"product_id": " external-1 "})
    search = VapiSearchQuerySerializer(data={"query": " aspirin "})
    full_sync = VapiFullSyncQuerySerializer(data={"max_pages": "100"})

    assert pull.is_valid(), pull.errors
    assert details.is_valid(), details.errors
    assert search.is_valid(), search.errors
    assert full_sync.is_valid(), full_sync.errors
    assert pull.validated_data == {"page": 1, "page_size": 100}
    assert details.validated_data["product_id"] == "external-1"
    assert search.validated_data == {"query": "aspirin", "limit": 50}
    assert full_sync.validated_data["max_pages"] == 100
