import sys
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError
from django.contrib.auth import get_user_model
from kombu.exceptions import OperationalError
from django.contrib.auth.models import AnonymousUser
from PIL import Image
from rest_framework.test import APIClient, APIRequestFactory

from api.authentication import JWTSafeAuthentication
from apps.recommendations.serializers import VisualSearchRequestSerializer
from apps.recommendations.services.image_encoder import (
    CLIPEncoder,
    _normalize_clip_image_features,
)
from apps.recommendations.services.safe_image_fetcher import UnsafeImageURLError
from apps.recommendations.tasks import encode_search_image
from apps.recommendations.throttles import (
    VisualSearchAnonThrottle,
    VisualSearchUserThrottle,
)
from apps.recommendations.views import RecommendationViewSet


def test_clip_image_features_support_legacy_tensor_response():
    import torch

    features = _normalize_clip_image_features(torch.ones((1, 512)))

    assert tuple(features.shape) == (1, 512)
    assert features.norm(dim=-1).item() == pytest.approx(1.0)


def test_clip_image_features_support_transformers_five_response():
    import torch

    response = SimpleNamespace(pooler_output=torch.full((1, 512), 2.0))
    features = _normalize_clip_image_features(response)

    assert tuple(features.shape) == (1, 512)
    assert features.norm(dim=-1).item() == pytest.approx(1.0)


@pytest.mark.parametrize("shape", [(1, 768), (2, 512), (512,)])
def test_clip_image_features_reject_unexpected_shape(shape):
    import torch

    with pytest.raises(ValueError, match="Unexpected CLIP image feature shape"):
        _normalize_clip_image_features(torch.ones(shape))


@pytest.mark.parametrize("limit", [0, -1, 25, "not-a-number"])
def test_visual_search_rejects_invalid_limit(limit):
    serializer = VisualSearchRequestSerializer(
        data={"image_url": "https://images.example/a.jpg", "limit": limit}
    )
    assert not serializer.is_valid()
    assert "limit" in serializer.errors


def test_visual_search_request_defaults_to_twenty_results():
    serializer = VisualSearchRequestSerializer(
        data={"image_url": "https://images.example/a.jpg"}
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["limit"] == 20


def test_visual_search_rejects_oversized_url_and_userinfo():
    oversized = "https://images.example/" + ("a" * 2048)
    for image_url in (oversized, "https://user:secret@images.example/a.jpg"):
        serializer = VisualSearchRequestSerializer(data={"image_url": image_url})
        assert not serializer.is_valid()
        assert "image_url" in serializer.errors


def test_visual_search_throttles_have_explicit_rates_and_identity_behavior():
    anon_request = SimpleNamespace(
        user=AnonymousUser(),
        META={"REMOTE_ADDR": "203.0.113.10"},
        headers={},
    )
    user_request = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True, pk=42),
        META={"REMOTE_ADDR": "203.0.113.11"},
        headers={},
    )

    anon = VisualSearchAnonThrottle()
    user = VisualSearchUserThrottle()
    assert anon.parse_rate(anon.rate) == (5, 60)
    assert user.parse_rate(user.rate) == (20, 60)
    assert anon.get_cache_key(anon_request, None) is not None
    assert anon.get_cache_key(user_request, None) is None
    assert user.get_cache_key(user_request, None).endswith("42")


def test_view_selects_visual_search_throttles_by_action():
    view = RecommendationViewSet()
    view.action = "search_by_image"
    throttles = view.get_throttles()
    assert [type(throttle) for throttle in throttles] == [
        VisualSearchAnonThrottle,
        VisualSearchUserThrottle,
    ]


def test_visual_search_action_uses_csrf_independent_jwt_authentication():
    assert RecommendationViewSet.search_by_image.kwargs["authentication_classes"] == [
        JWTSafeAuthentication,
    ]


@pytest.mark.django_db
def test_public_visual_search_ignores_unrelated_django_session_csrf():
    """An admin/session cookie must not turn this AllowAny action into HTTP 403."""
    user = get_user_model().objects.create_user(
        email="visual-session@example.test",
        username="visual-session",
        password="not-used",
    )
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)

    with patch(
        "apps.recommendations.views.fetch_search_image",
        side_effect=UnsafeImageURLError(),
    ), patch.object(RecommendationViewSet, "get_throttles", return_value=[]):
        response = client.post(
            "/api/recommendations/search_by_image/",
            {"image_url": "http://127.0.0.1/private", "limit": 3},
            format="json",
        )

    assert response.status_code == 400
    assert response.data["error"] == "invalid_image_url"


def _post_visual_search(payload):
    request = APIRequestFactory().post(
        "/api/recommendations/search_by_image/",
        payload,
        format="json",
    )
    view = RecommendationViewSet.as_view({"post": "search_by_image"})
    with patch.object(RecommendationViewSet, "get_throttles", return_value=[]):
        return view(request)


def test_view_rejects_invalid_limit_before_fetching_image():
    with patch("apps.recommendations.views.fetch_search_image") as fetch_image:
        response = _post_visual_search(
            {"image_url": "https://images.example/a.jpg", "limit": 1000}
        )
    assert response.status_code == 400
    assert response.data == {"error": "invalid_limit"}
    fetch_image.assert_not_called()


def test_view_rejects_unsafe_image_before_qdrant_or_clip():
    with patch(
        "apps.recommendations.views.fetch_search_image",
        side_effect=UnsafeImageURLError(),
    ), patch.object(encode_search_image, "apply_async") as encode, patch.object(
        RecommendationViewSet,
        "_get_engine",
    ) as get_engine:
        response = _post_visual_search(
            {"image_url": "http://127.0.0.1/private", "limit": 12}
        )
    assert response.status_code == 400
    assert response.data["error"] == "invalid_image_url"
    encode.assert_not_called()
    get_engine.assert_not_called()


def _encoded_result(vector=(0.0,) * 512, error=None):
    result = Mock()
    result.get.return_value = list(vector) if vector is not None else None
    result.get.side_effect = error
    return result


def test_successful_empty_search_preserves_response_contract():
    engine = Mock()
    engine.find_similar_by_image_vector.return_value = []
    with patch(
        "apps.recommendations.views.fetch_search_image",
        return_value=Image.new("RGB", (8, 8)),
    ), patch.object(
        encode_search_image,
        "apply_async",
        return_value=_encoded_result(),
    ), patch.object(
        RecommendationViewSet,
        "_get_engine",
        return_value=engine,
    ):
        response = _post_visual_search(
            {"image_url": "https://images.example/a.jpg", "limit": 12}
        )
    assert response.status_code == 200
    assert response.data == {"results": []}
    engine.find_similar_by_image_vector.assert_called_once()


def test_unexpected_backend_error_is_generic():
    with patch(
        "apps.recommendations.views.fetch_search_image",
        return_value=Image.new("RGB", (8, 8)),
    ), patch.object(
        encode_search_image,
        "apply_async",
        return_value=_encoded_result(),
    ), patch.object(
        RecommendationViewSet,
        "_get_engine",
        side_effect=RuntimeError("internal-secret-detail"),
    ):
        response = _post_visual_search(
            {"image_url": "https://images.example/a.jpg", "limit": 12}
        )
    assert response.status_code == 503
    assert response.data == {"error": "search_unavailable"}
    assert "internal-secret-detail" not in str(response.data)


def test_web_search_queues_clip_and_never_imports_torch():
    """CLIP (torch ≈ 190 МБ + веса) живёт в celery_recsys, не в gunicorn-воркере."""
    engine = Mock()
    engine.find_similar_by_image_vector.return_value = []
    heavy_modules = (
        "torch",
        "transformers",
        "sentence_transformers",
        "apps.recommendations.services.image_encoder",
    )
    with patch.dict(sys.modules), patch(
        "apps.recommendations.views.fetch_search_image",
        return_value=Image.new("RGB", (1600, 1200)),
    ), patch.object(
        encode_search_image,
        "apply_async",
        return_value=_encoded_result(),
    ) as apply_async, patch.object(
        RecommendationViewSet,
        "_get_engine",
        return_value=engine,
    ):
        for name in heavy_modules:
            sys.modules.pop(name, None)
        response = _post_visual_search(
            {"image_url": "https://images.example/a.jpg", "limit": 12}
        )
        loaded = [name for name in heavy_modules if name in sys.modules]

    assert response.status_code == 200
    assert loaded == []
    (image_bytes,) = apply_async.call_args.kwargs["args"]
    assert apply_async.call_args.kwargs["expires"] == 15
    # Через брокер идёт уменьшенная копия, а не исходник до 5 МБ.
    assert Image.open(BytesIO(image_bytes)).size == (512, 384)
    apply_async.return_value.get.assert_called_once_with(timeout=15)
    vector = engine.find_similar_by_image_vector.call_args.kwargs["image_vector"]
    assert vector.dtype == np.float32
    assert vector.shape == (512,)


@pytest.mark.parametrize(
    "result_kwargs, apply_error",
    [
        ({"error": CeleryTimeoutError("The operation timed out.")}, None),
        ({"error": RuntimeError("CUDA out of memory")}, None),
        ({"vector": None}, None),
        ({}, OperationalError("broker unavailable")),
    ],
    ids=["timeout", "task-error", "encoder-unavailable", "broker-down"],
)
def test_encoding_failure_returns_search_unavailable(result_kwargs, apply_error):
    result = _encoded_result(**result_kwargs)
    with patch(
        "apps.recommendations.views.fetch_search_image",
        return_value=Image.new("RGB", (8, 8)),
    ), patch.object(
        encode_search_image,
        "apply_async",
        return_value=result,
        side_effect=apply_error,
    ), patch.object(RecommendationViewSet, "_get_engine") as get_engine:
        response = _post_visual_search(
            {"image_url": "https://images.example/a.jpg", "limit": 12}
        )

    assert response.status_code == 503
    assert response.data == {"error": "search_unavailable"}
    get_engine.assert_not_called()


def test_encode_task_validates_bytes_and_returns_plain_list():
    buffer = BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="JPEG")
    with patch.object(
        CLIPEncoder,
        "encode_image",
        return_value=np.ones(512, dtype=np.float32),
    ) as encode:
        vector = encode_search_image(buffer.getvalue())

    encode.assert_called_once_with(buffer.getvalue())
    assert vector == [1.0] * 512


def test_encode_task_returns_none_for_rejected_image():
    with patch.object(CLIPEncoder, "_encode_image_impl") as encode_impl:
        assert encode_search_image(b"not an image") is None
    encode_impl.assert_not_called()


def test_encode_task_has_own_queue_and_indexing_stays_in_recsys():
    from config.celery import app

    def queue_for(task_name):
        return app.amqp.router.route({}, task_name)["queue"].name

    assert queue_for(encode_search_image.name) == "recsys_search"
    assert queue_for("apps.recommendations.tasks.index_product_vectors") == "recsys"


@pytest.mark.parametrize(
    "queues, warmed",
    [({"recsys_search": None, "recsys": None}, True), ({"ai": None}, False)],
    ids=["celery_recsys", "other-worker"],
)
def test_only_visual_search_worker_preloads_clip_on_start(queues, warmed):
    from apps.recommendations.tasks import _warm_up_visual_search

    sender = SimpleNamespace(
        app=SimpleNamespace(
            amqp=SimpleNamespace(queues=SimpleNamespace(consume_from=queues))
        )
    )
    with patch.object(encode_search_image, "apply_async") as apply_async:
        _warm_up_visual_search(sender=sender)

    assert apply_async.called is warmed
    if warmed:
        (image_bytes,) = apply_async.call_args.kwargs["args"]
        assert Image.open(BytesIO(image_bytes)).format == "PNG"
        assert apply_async.call_args.kwargs["ignore_result"] is True
