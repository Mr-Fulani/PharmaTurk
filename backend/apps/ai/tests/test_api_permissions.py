from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework import permissions, status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai.views import (
    AIModerationQueueViewSet,
    AIProcessingLogViewSet,
    AIStatsView,
    AITemplateViewSet,
    GenerateContentView,
    ProcessProductView,
)


AI_API_CLASSES = (
    AIProcessingLogViewSet,
    AIModerationQueueViewSet,
    AITemplateViewSet,
    GenerateContentView,
    ProcessProductView,
    AIStatsView,
)

AI_ENDPOINTS = (
    (AIProcessingLogViewSet.as_view({"get": "list"}), "get", "/api/ai/logs/", {}),
    (AIModerationQueueViewSet.as_view({"get": "list"}), "get", "/api/ai/moderation/", {}),
    (AITemplateViewSet.as_view({"get": "list"}), "get", "/api/ai/templates/", {}),
    (GenerateContentView.as_view(), "post", "/api/ai/generate/", {}),
    (ProcessProductView.as_view(), "post", "/api/ai/process/1/", {"product_id": 1}),
    (AIStatsView.as_view(), "get", "/api/ai/stats/", {}),
)


@pytest.fixture
def request_factory():
    return APIRequestFactory()


@pytest.mark.parametrize("view_class", AI_API_CLASSES)
def test_all_ai_api_classes_are_staff_only(view_class):
    assert view_class.permission_classes == [permissions.IsAdminUser]


@pytest.mark.parametrize(("view", "method", "url", "view_kwargs"), AI_ENDPOINTS)
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
def test_ai_endpoints_reject_non_staff_before_view_logic(
    request_factory,
    view,
    method,
    url,
    view_kwargs,
    user,
    expected_status,
):
    request = getattr(request_factory, method)(url, {}, format="json")
    if user is not None:
        force_authenticate(request, user=user)

    response = view(request, **view_kwargs)

    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("view", "url", "payload", "view_kwargs"),
    (
        (
            GenerateContentView.as_view(),
            "/api/ai/generate/",
            {"product_id": 1},
            {},
        ),
        (
            ProcessProductView.as_view(),
            "/api/ai/process/1/",
            {},
            {"product_id": 1},
        ),
    ),
)
def test_non_staff_cannot_enqueue_ai_processing(
    request_factory,
    view,
    url,
    payload,
    view_kwargs,
):
    request = request_factory.post(url, payload, format="json")
    force_authenticate(
        request,
        user=SimpleNamespace(is_authenticated=True, is_staff=False),
    )

    with patch("apps.ai.views.enqueue_product_ai_task") as enqueue:
        response = view(request, **view_kwargs)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    enqueue.assert_not_called()


@pytest.mark.parametrize(
    ("view", "url", "payload", "view_kwargs"),
    (
        (
            GenerateContentView.as_view(),
            "/api/ai/generate/",
            {"product_id": 1},
            {},
        ),
        (
            ProcessProductView.as_view(),
            "/api/ai/process/1/",
            {},
            {"product_id": 1},
        ),
    ),
)
def test_staff_can_enqueue_ai_processing(
    request_factory,
    view,
    url,
    payload,
    view_kwargs,
):
    request = request_factory.post(url, payload, format="json")
    force_authenticate(
        request,
        user=SimpleNamespace(is_authenticated=True, is_staff=True),
    )

    with patch("apps.ai.views.enqueue_product_ai_task") as enqueue:
        enqueue.return_value = (SimpleNamespace(id=7), "task-123", True)
        response = view(request, **view_kwargs)

    assert response.status_code == status.HTTP_202_ACCEPTED
    enqueue.assert_called_once()
