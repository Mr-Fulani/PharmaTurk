"""Validation and metadata-stripping normalization for stored user avatars."""
from __future__ import annotations

from io import BytesIO

from django.core.files.base import ContentFile

from apps.recommendations.services.safe_image_fetcher import (
    MAX_IMAGE_BYTES,
    ImageTooLargeError,
    validate_image_bytes,
)

AVATAR_MAX_SIDE = 800


def normalize_avatar_bytes(
    data: bytes,
    *,
    expected_content_type: str | None = None,
) -> ContentFile:
    """Return a decoded, bounded and metadata-free JPEG avatar."""
    validated = validate_image_bytes(
        data,
        expected_content_type=expected_content_type,
    )
    image = validated.image
    image.thumbnail((AVATAR_MAX_SIDE, AVATAR_MAX_SIDE))
    output = BytesIO()
    image.save(output, format="JPEG", quality=85, optimize=True)
    return ContentFile(output.getvalue(), name="avatar.jpg")


def normalize_avatar_upload(file_obj) -> ContentFile:
    """Read an uploaded file with a hard byte limit, then normalize it."""
    data = file_obj.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError()
    return normalize_avatar_bytes(
        data,
        expected_content_type=getattr(file_obj, "content_type", None),
    )
