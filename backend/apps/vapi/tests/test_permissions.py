from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.vapi.views import (
    VapiAdminAPIView,
    VapiFullSyncView,
    VapiProductDetailsView,
    VapiPullView,
    VapiSearchView,
    VapiSyncCategoriesView,
)


VAPI_ENDPOINTS = (
    (VapiPullView, "/api/vapi/pull/?page=1&page_size=5", "apps.vapi.views.pull_products.delay"),
    (
        VapiProductDetailsView,
        "/api/vapi/product-details/?product_id=external-1",
        "apps.vapi.views.pull_product_details.delay",
    ),
    (
        VapiSearchView,
        "/api/vapi/search/?query=aspirin&limit=5",
        "apps.vapi.views.search_products_task.delay",
    ),
    (
        VapiSyncCategoriesView,
        "/api/vapi/sync-categories/",
        "apps.vapi.views.sync_categories_and_brands.delay",
    ),
    (
        VapiFullSyncView,
        "/api/vapi/full-sync/?max_pages=2",
        "apps.vapi.views.full_catalog_sync.delay",
    ),
)


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.mark.parametrize(("view_class", "url", "task_path"), VAPI_ENDPOINTS)
def test_vapi_endpoints_share_staff_only_base(view_class, url, task_path):
    assert issubclass(view_class, VapiAdminAPIView)
    assert view_class.permission_classes == [IsAdminUser]


@pytest.mark.parametrize(("view_class", "url", "task_path"), VAPI_ENDPOINTS)
@pytest.mark.parametrize(
    ("user", "expected_status"),
    (
        (None, status.HTTP_401_UNAUTHORIZED),
        (
            SimpleNamespace(is_authenticated=True, is_staff=False),
            status.HTTP_403_FORBIDDEN,
        ),
    ),
)
def test_vapi_endpoints_reject_non_staff_without_queueing(
    request_factory,
    view_class,
    url,
    task_path,
    user,
    expected_status,
):
    request = request_factory.post(url)
    if user is not None:
        force_authenticate(request, user=user)

    with patch(task_path) as enqueue:
        response = view_class.as_view()(request)

    assert response.status_code == expected_status
    enqueue.assert_not_called()


@pytest.mark.parametrize(("view_class", "url", "task_path"), VAPI_ENDPOINTS)
def test_vapi_endpoints_allow_staff_to_queue(
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
        enqueue.return_value.id = "task-123"
        response = view_class.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    enqueue.assert_called_once()
