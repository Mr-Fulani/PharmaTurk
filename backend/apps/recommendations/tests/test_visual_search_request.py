from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
from django.contrib.auth.models import AnonymousUser
from PIL import Image
from rest_framework.test import APIRequestFactory

from apps.recommendations.serializers import VisualSearchRequestSerializer
from apps.recommendations.services.image_encoder import CLIPEncoder
from apps.recommendations.services.safe_image_fetcher import UnsafeImageURLError
from apps.recommendations.throttles import (
    VisualSearchAnonThrottle,
    VisualSearchUserThrottle,
)
from apps.recommendations.views import RecommendationViewSet


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
    ), patch.object(CLIPEncoder, "encode_image") as encode, patch.object(
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


def test_successful_empty_search_preserves_response_contract():
    engine = Mock()
    engine.find_similar_by_image_vector.return_value = []
    with patch(
        "apps.recommendations.views.fetch_search_image",
        return_value=Image.new("RGB", (8, 8)),
    ), patch.object(
        CLIPEncoder,
        "encode_image",
        return_value=np.zeros(512, dtype=np.float32),
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
        CLIPEncoder,
        "encode_image",
        return_value=np.zeros(512, dtype=np.float32),
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
