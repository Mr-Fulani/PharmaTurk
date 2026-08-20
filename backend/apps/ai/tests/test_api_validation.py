from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.ai.serializers import (
    AIStatsQuerySerializer,
    AITemplateSerializer,
    GenerateContentRequestSerializer,
    ProcessProductRequestSerializer,
)
from apps.ai.views import AIStatsView, GenerateContentView, ProcessProductView


@pytest.fixture
def request_factory():
    return APIRequestFactory()


def _staff_request(request):
    force_authenticate(
        request,
        user=SimpleNamespace(is_authenticated=True, is_staff=True),
    )
    return request


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"product_id": 0},
        {"product_id": 1, "generate_description": "invalid"},
        {"product_id": 1, "categorize": "invalid"},
        {"product_id": 1, "analyze_images": "invalid"},
        {"product_id": 1, "use_images": "invalid"},
        {"product_id": 1, "auto_apply": "invalid"},
    ),
)
def test_generate_rejects_invalid_payload_without_queueing(request_factory, payload):
    request = _staff_request(
        request_factory.post("/api/ai/generate/", payload, format="json")
    )

    with patch("apps.ai.views.enqueue_product_ai_task") as enqueue:
        response = GenerateContentView.as_view()(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    enqueue.assert_not_called()


@pytest.mark.parametrize(
    ("product_id", "payload"),
    (
        (0, {}),
        (1, {"generate_description": "invalid"}),
        (1, {"categorize": "invalid"}),
        (1, {"analyze_images": "invalid"}),
        (1, {"use_images": "invalid"}),
        (1, {"auto_apply": "invalid"}),
    ),
)
def test_process_rejects_invalid_payload_without_queueing(
    request_factory,
    product_id,
    payload,
):
    request = _staff_request(
        request_factory.post(f"/api/ai/process/{product_id}/", payload, format="json")
    )

    with patch("apps.ai.views.enqueue_product_ai_task") as enqueue:
        response = ProcessProductView.as_view()(request, product_id=product_id)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    enqueue.assert_not_called()


@pytest.mark.parametrize("days", ("0", "366", "invalid"))
def test_stats_rejects_invalid_days_before_querying(request_factory, days):
    request = _staff_request(
        request_factory.get("/api/ai/stats/", {"days": days})
    )

    with patch("apps.ai.views.AIProcessingLog.objects.filter") as query:
        response = AIStatsView.as_view()(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    query.assert_not_called()


def test_generate_parses_use_images_and_other_booleans(request_factory):
    request = _staff_request(
        request_factory.post(
            "/api/ai/generate/",
            {
                "product_id": "7",
                "generate_description": "true",
                "categorize": "false",
                "analyze_images": "1",
                "use_images": "0",
                "auto_apply": "false",
            },
            format="json",
        )
    )

    with patch("apps.ai.views.enqueue_product_ai_task") as enqueue:
        enqueue.return_value = (SimpleNamespace(id=11), "task-123", True)
        response = GenerateContentView.as_view()(request)

    assert response.status_code == status.HTTP_202_ACCEPTED
    enqueue.assert_called_once_with(
        product_id=7,
        processing_type="full",
        auto_apply=False,
        options={
            "generate_description": True,
            "categorize": False,
            "analyze_images": True,
            "use_images": False,
        },
    )


def test_process_parses_booleans_before_queueing(request_factory):
    request = _staff_request(
        request_factory.post(
            "/api/ai/process/7/",
            {
                "generate_description": "false",
                "categorize": "true",
                "analyze_images": "0",
                "use_images": "1",
                "auto_apply": "true",
            },
            format="json",
        )
    )

    with patch("apps.ai.views.enqueue_product_ai_task") as enqueue:
        enqueue.return_value = (SimpleNamespace(id=12), "task-456", True)
        response = ProcessProductView.as_view()(request, product_id=7)

    assert response.status_code == status.HTTP_202_ACCEPTED
    enqueue.assert_called_once_with(
        product_id=7,
        processing_type="full",
        auto_apply=True,
        options={
            "generate_description": False,
            "categorize": True,
            "analyze_images": False,
            "use_images": True,
        },
    )


def test_ai_serializers_apply_numeric_boundaries_and_defaults():
    generate = GenerateContentRequestSerializer(data={"product_id": "1"})
    process = ProcessProductRequestSerializer(data={"product_id": "1"})
    stats_default = AIStatsQuerySerializer(data={})
    stats_max = AIStatsQuerySerializer(data={"days": "365"})

    assert generate.is_valid(), generate.errors
    assert process.is_valid(), process.errors
    assert stats_default.is_valid(), stats_default.errors
    assert stats_max.is_valid(), stats_max.errors
    assert generate.validated_data["product_id"] == 1
    assert process.validated_data == {
        "product_id": 1,
        "generate_description": True,
        "categorize": True,
        "analyze_images": True,
        "use_images": True,
        "auto_apply": False,
    }
    assert stats_default.validated_data["days"] == 30
    assert stats_max.validated_data["days"] == 365


def test_ai_template_metrics_are_read_only():
    serializer = AITemplateSerializer()

    assert serializer.fields["usage_count"].read_only
    assert serializer.fields["success_rate"].read_only
