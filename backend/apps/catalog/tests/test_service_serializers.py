import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Service, ServiceImage, validate_service_video_file_size
from apps.catalog.serializers import ServiceImageSerializer, ServiceSerializer


pytestmark = pytest.mark.django_db


def test_service_image_serializer_prefers_uploaded_video_file(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path

    service = Service.objects.create(name="Услуга", slug="usluga-video-gallery")
    media = ServiceImage.objects.create(
        service=service,
        video_file=SimpleUploadedFile("gallery-video.mp4", b"video-bytes", content_type="video/mp4"),
        alt_text="Видео в галерее",
    )

    data = ServiceImageSerializer(media).data

    assert data["video_url"].endswith(".mp4")
    assert data["video_file_url"] == data["video_url"]
    assert data["image_url"] in ("", None)


def test_service_serializer_includes_gallery_video_url():
    service = Service.objects.create(name="Услуга", slug="usluga-gallery-video")
    ServiceImage.objects.create(
        service=service,
        video_url="https://cdn.example.com/service-gallery.mp4",
        alt_text="Видео услуги",
        is_main=True,
        sort_order=1,
    )

    data = ServiceSerializer(service).data

    assert len(data["gallery"]) == 1
    assert data["gallery"][0]["video_url"] == "https://cdn.example.com/service-gallery.mp4"
    assert data["gallery"][0]["is_main"] is True


class _FakeSizedFile:
    def __init__(self, size):
        self.size = size
        self.name = "service-video.mp4"


def test_service_video_validator_rejects_large_files():
    with pytest.raises(ValidationError):
        validate_service_video_file_size(_FakeSizedFile(101 * 1024 * 1024))
