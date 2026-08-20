from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from apps.recommendations.services.safe_image_fetcher import InvalidImageError
from apps.users.avatar_security import normalize_avatar_upload


def _image_bytes(fmt: str, size=(1200, 600)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(20, 40, 60)).save(output, format=fmt)
    return output.getvalue()


class AvatarSecurityTests(SimpleTestCase):
    def test_valid_image_is_resized_and_reencoded_as_jpeg(self):
        upload = SimpleUploadedFile(
            "profile.png",
            _image_bytes("PNG"),
            content_type="image/png",
        )

        normalized = normalize_avatar_upload(upload)

        with Image.open(normalized) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 800)

    def test_declared_mime_must_match_decoded_format(self):
        upload = SimpleUploadedFile(
            "profile.jpg",
            _image_bytes("PNG"),
            content_type="image/jpeg",
        )

        with self.assertRaises(InvalidImageError):
            normalize_avatar_upload(upload)

    def test_non_image_payload_is_rejected(self):
        upload = SimpleUploadedFile(
            "profile.jpg",
            b"<script>alert(1)</script>",
            content_type="image/jpeg",
        )

        with self.assertRaises(InvalidImageError):
            normalize_avatar_upload(upload)
