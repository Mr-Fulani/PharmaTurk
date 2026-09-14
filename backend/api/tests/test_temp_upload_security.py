from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient, APIRequestFactory

from api.authentication import JWTSafeAuthentication
from api.views import (
    TempImageUploadThrottle,
    TempImageUploadUserThrottle,
    TempImageUploadView,
    _read_validated_temp_image,
)
from apps.recommendations.services.safe_image_fetcher import (
    ImageTooLargeError,
    InvalidImageError,
    MAX_IMAGE_BYTES,
)


def _image_bytes(image_format="PNG", size=(16, 16)):
    data = BytesIO()
    Image.new("RGB", size=size, color=(30, 60, 90)).save(data, image_format)
    return data.getvalue()


@pytest.mark.parametrize(
    ("image_format", "extension"),
    [("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")],
)
def test_upload_uses_actual_image_format_for_canonical_extension(image_format, extension):
    data = _image_bytes(image_format)
    upload = SimpleUploadedFile("misleading.gif", data, content_type="image/gif")
    validated_data, detected_extension = _read_validated_temp_image(upload)
    assert validated_data == data
    assert detected_extension == extension


def test_upload_reads_only_max_bytes_plus_one():
    upload = SimpleUploadedFile(
        "large.jpg",
        b"x" * (MAX_IMAGE_BYTES + 1),
        content_type="image/jpeg",
    )
    with pytest.raises(ImageTooLargeError):
        _read_validated_temp_image(upload)


def test_upload_rejects_unsupported_actual_format():
    upload = SimpleUploadedFile(
        "fake.jpg",
        _image_bytes("GIF"),
        content_type="image/jpeg",
    )
    with pytest.raises(InvalidImageError):
        _read_validated_temp_image(upload)


def test_upload_rejects_excessive_decoded_pixels():
    data = BytesIO()
    Image.new("1", size=(4097, 4097)).save(data, "PNG")
    upload = SimpleUploadedFile("large-pixels.png", data.getvalue(), content_type="image/png")
    with pytest.raises(ImageTooLargeError):
        _read_validated_temp_image(upload)


def _post_upload(upload):
    request = APIRequestFactory().post(
        "/api/upload/temp/",
        {"file": upload},
        format="multipart",
    )
    view = TempImageUploadView.as_view()
    with patch.object(TempImageUploadView, "get_throttles", return_value=[]):
        return view(request)


def test_upload_uses_csrf_independent_jwt_authentication():
    assert TempImageUploadView.authentication_classes == [JWTSafeAuthentication]


@pytest.mark.django_db
def test_public_upload_ignores_unrelated_django_session_csrf():
    """An admin/session cookie must not turn this AllowAny endpoint into 403."""
    user = get_user_model().objects.create_user(
        email="upload-session@example.test",
        username="upload-session",
        password="not-used",
    )
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    upload = SimpleUploadedFile(
        "photo.png",
        _image_bytes("PNG"),
        content_type="image/png",
    )
    storage = Mock()
    storage.save.side_effect = lambda name, content: name
    storage.url.side_effect = lambda name: f"/media/{name}"

    with patch("api.views.default_storage", storage), patch.object(
        TempImageUploadView,
        "get_throttles",
        return_value=[],
    ):
        response = client.post("/api/upload/temp/", {"file": upload}, format="multipart")

    assert response.status_code == 201
    assert response.data["url"].startswith("http://testserver/media/temp/")


def test_endpoint_saves_rewound_content_with_canonical_extension():
    data = _image_bytes("PNG")
    upload = SimpleUploadedFile("photo.jpg", data, content_type="image/jpeg")
    storage = Mock()

    def save(name, content):
        assert name.startswith("temp/") and name.endswith(".png")
        assert content.tell() == 0
        assert content.read() == data
        return name

    storage.save.side_effect = save
    storage.url.side_effect = lambda name: f"/media/{name}"
    with patch("api.views.default_storage", storage):
        response = _post_upload(upload)

    assert response.status_code == 201
    assert response.data["url"].startswith("http://testserver/media/temp/")


def test_storage_error_response_is_generic():
    upload = SimpleUploadedFile(
        "photo.png",
        _image_bytes("PNG"),
        content_type="image/png",
    )
    storage = Mock()
    storage.save.side_effect = RuntimeError("storage-secret-detail")
    with patch("api.views.default_storage", storage):
        response = _post_upload(upload)

    assert response.status_code == 500
    assert response.data == {"error": "Ошибка сохранения изображения"}
    assert "storage-secret-detail" not in str(response.data)


def test_upload_throttles_have_explicit_rates_and_identity_behavior():
    anon_request = SimpleNamespace(
        user=AnonymousUser(),
        META={"REMOTE_ADDR": "203.0.113.20"},
        headers={},
    )
    user_request = SimpleNamespace(
        user=SimpleNamespace(is_authenticated=True, pk=73),
        META={"REMOTE_ADDR": "203.0.113.21"},
        headers={},
    )
    anon = TempImageUploadThrottle()
    user = TempImageUploadUserThrottle()

    assert anon.parse_rate(anon.rate) == (10, 60)
    assert user.parse_rate(user.rate) == (30, 60)
    assert anon.get_cache_key(anon_request, None) is not None
    assert anon.get_cache_key(user_request, None) is None
    assert user.get_cache_key(user_request, None).endswith("73")
