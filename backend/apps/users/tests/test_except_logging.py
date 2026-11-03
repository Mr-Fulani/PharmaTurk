"""TD-017: точные типы ошибок и запись причины в журнал в apps.users."""
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError

from apps.users.backends import MultiFieldAuthBackend, User
from apps.users.serializers import PublicUserProfileSerializer
from apps.users.views import UserProfileViewSet


def _phone_login(filter_error):
    with patch.object(User.objects, "get", side_effect=User.DoesNotExist), patch.object(
        User.objects, "filter", side_effect=filter_error
    ):
        return MultiFieldAuthBackend().authenticate(
            None, username="+90 555 111 22 33", password="secret"
        )


def test_phone_lookup_database_error_is_logged_and_login_fails(caplog):
    with caplog.at_level(logging.WARNING, logger="apps.users.backends"):
        assert _phone_login(DatabaseError("db gone")) is None
    assert "Phone login lookup failed: DatabaseError: db gone" in caplog.text


def test_phone_lookup_unexpected_error_is_not_swallowed():
    with pytest.raises(RuntimeError):
        _phone_login(RuntimeError("bug"))


def test_public_profile_testimonial_avatar_failure_is_logged(caplog):
    serializer = PublicUserProfileSerializer(context={"request": None})
    user = SimpleNamespace(pk=7, avatar=None)

    with patch(
        "apps.feedback.models.Testimonial.objects.filter",
        side_effect=DatabaseError("db gone"),
    ), caplog.at_level(logging.WARNING, logger="apps.users.serializers"):
        assert serializer.get_avatar_url(user) is None
    assert "User 7: testimonial avatar unavailable: DatabaseError: db gone" in caplog.text


def test_rejected_avatar_upload_keeps_response_and_logs_reason(caplog):
    request = SimpleNamespace(
        FILES={
            "avatar": SimpleUploadedFile(
                "a.jpg", b"<script>alert(1)</script>", content_type="image/jpeg"
            )
        },
        user=SimpleNamespace(id=5),
    )

    with caplog.at_level(logging.INFO, logger="apps.users.views"):
        response = UserProfileViewSet().upload_avatar(request)

    assert response.status_code == 400
    assert response.data == {
        "error": "Недопустимое изображение. Разрешены JPEG, PNG и WebP до 5 МБ."
    }
    assert "Avatar upload rejected for user_id=5: InvalidImageError" in caplog.text
