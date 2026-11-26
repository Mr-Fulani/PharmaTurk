from io import BytesIO
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from api.views import TempImageUploadThrottle, TempImageUploadUserThrottle
from apps.feedback.throttles import (
    PRODUCT_FEEDBACK_WRITE_THROTTLES,
    TESTIMONIAL_CREATE_THROTTLES,
)
from apps.feedback.views import (
    ProductQuestionViewSet,
    ProductReviewViewSet,
    _looks_like_video,
)
from apps.recommendations.throttles import (
    RecommendationAnonThrottle,
    RecommendationUserThrottle,
    VisualSearchAnonThrottle,
    VisualSearchUserThrottle,
)

ANON_CAPABLE = [
    TempImageUploadThrottle,
    TempImageUploadUserThrottle,
    VisualSearchAnonThrottle,
    VisualSearchUserThrottle,
    RecommendationAnonThrottle,
    RecommendationUserThrottle,
    *TESTIMONIAL_CREATE_THROTTLES,
]


def _anon_request(forwarded_for):
    return SimpleNamespace(
        user=AnonymousUser(),
        META={
            "HTTP_X_REAL_IP": "203.0.113.7",
            "HTTP_X_FORWARDED_FOR": forwarded_for,
            "REMOTE_ADDR": "172.18.0.2",
        },
    )


@pytest.mark.parametrize("throttle_class", ANON_CAPABLE)
def test_anonymous_limit_ignores_client_supplied_forwarded_for(throttle_class):
    throttle = throttle_class()

    first = throttle.get_cache_key(_anon_request("198.51.100.1"), None)
    second = throttle.get_cache_key(_anon_request("198.51.100.2"), None)

    assert first == second
    assert "203.0.113.7" in first


def test_every_limit_counts_in_its_own_bucket():
    classes = ANON_CAPABLE + PRODUCT_FEEDBACK_WRITE_THROTTLES
    scopes = [throttle_class.scope for throttle_class in classes]

    assert len(set(scopes)) == len(scopes)
    assert not {"anon", "user"} & set(scopes)


def test_product_reviews_and_questions_are_rate_limited_on_write():
    for view_class, actions in (
        (ProductReviewViewSet, ("create", "partial_update")),
        (ProductQuestionViewSet, ("create",)),
    ):
        for action in actions:
            view = view_class()
            view.action = action
            assert [type(t) for t in view.get_throttles()] == PRODUCT_FEEDBACK_WRITE_THROTTLES


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32, True),
        (b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 32, True),
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 32, True),
        (b"PK\x03\x04 not a video at all", False),
        (b"", False),
    ],
)
def test_review_video_is_checked_by_content(content, expected):
    uploaded = BytesIO(content)

    assert _looks_like_video(uploaded) is expected
    assert uploaded.tell() == 0


def test_api_description_is_for_staff_only():
    assert settings.SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] == [
        "rest_framework.permissions.IsAdminUser"
    ]
