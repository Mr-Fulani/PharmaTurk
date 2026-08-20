from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.test import APIRequestFactory

from api.views import HealthCheckView, LivenessCheckView


def test_readiness_returns_200_when_database_is_available():
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value = cursor

    request = APIRequestFactory().get("/api/health/")
    with (
        patch("api.views.connection.cursor", return_value=cursor_context),
        patch("api.views.cache") as cache,
    ):
        cache.get.return_value = "ok"
        response = HealthCheckView.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"status": "ok", "db": True, "cache": True}
    cursor.execute.assert_called_once_with("SELECT 1;")


def test_readiness_returns_503_when_database_is_unavailable():
    request = APIRequestFactory().get("/api/health/")
    with (
        patch("api.views.connection.cursor", side_effect=RuntimeError("db down")),
        patch("api.views.cache") as cache,
    ):
        cache.get.return_value = "ok"
        response = HealthCheckView.as_view()(request)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data == {"status": "unavailable", "db": False, "cache": True}


def test_readiness_returns_503_when_cache_is_unavailable():
    cursor_context = MagicMock()
    cursor_context.__enter__.return_value.fetchone.return_value = (1,)
    request = APIRequestFactory().get("/api/health/")
    with (
        patch("api.views.connection.cursor", return_value=cursor_context),
        patch("api.views.cache.set", side_effect=RuntimeError("cache down")),
    ):
        response = HealthCheckView.as_view()(request)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data == {"status": "unavailable", "db": True, "cache": False}


def test_liveness_does_not_touch_database():
    request = APIRequestFactory().get("/api/live/")
    with patch("api.views.connection.cursor") as cursor, patch("api.views.cache") as cache:
        response = LivenessCheckView.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"status": "ok"}
    cursor.assert_not_called()
    cache.assert_not_called()
