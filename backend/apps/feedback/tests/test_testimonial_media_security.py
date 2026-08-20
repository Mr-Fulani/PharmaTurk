from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from apps.feedback.views import (
    ProductReviewViewSet,
    _normalize_testimonial_image,
    _validate_testimonial_media_items,
    _validate_testimonial_video_file,
    _validate_testimonial_video_url,
)
from apps.recommendations.services.safe_image_fetcher import InvalidImageError


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1400, 700), color=(1, 2, 3)).save(output, format="PNG")
    return output.getvalue()


class TestimonialMediaSecurityTests(SimpleTestCase):
    def test_embed_video_hosts_are_exactly_allowlisted(self):
        self.assertEqual(
            _validate_testimonial_video_url("https://www.youtube.com/watch?v=abc"),
            "https://www.youtube.com/watch?v=abc",
        )
        for url in (
            "http://www.youtube.com/watch?v=abc",
            "https://youtube.com.attacker.example/watch?v=abc",
            "https://127.0.0.1/?youtube.com",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _validate_testimonial_video_url(url)

    def test_image_is_verified_resized_and_reencoded(self):
        upload = SimpleUploadedFile(
            "testimonial.png",
            _png_bytes(),
            content_type="image/png",
        )

        result = _normalize_testimonial_image(upload)

        with Image.open(result) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 1200)

    def test_spoofed_image_mime_is_rejected(self):
        upload = SimpleUploadedFile(
            "testimonial.jpg",
            _png_bytes(),
            content_type="image/jpeg",
        )
        with self.assertRaises(InvalidImageError):
            _normalize_testimonial_image(upload)

    def test_video_file_requires_matching_type_extension_and_size(self):
        valid = SimpleUploadedFile("clip.mp4", b"video", content_type="video/mp4")
        self.assertIs(_validate_testimonial_video_file(valid), valid)

        invalid = SimpleUploadedFile("clip.html", b"video", content_type="video/mp4")
        with self.assertRaises(ValueError):
            _validate_testimonial_video_file(invalid)

        oversized = SimpleUploadedFile("large.mp4", b"video", content_type="video/mp4")
        oversized.size = 20 * 1024 * 1024 + 1
        with self.assertRaises(ValueError):
            _validate_testimonial_video_file(oversized)

    def test_media_count_and_shape_are_bounded(self):
        with self.assertRaises(ValueError):
            _validate_testimonial_media_items(
                [
                    {"media_type": "video", "video_url": "https://youtu.be/a"},
                    {"media_type": "video", "video_url": "https://youtu.be/b"},
                    {"media_type": "video", "video_url": "https://youtu.be/c"},
                    {"media_type": "video", "video_url": "https://youtu.be/d"},
                ]
            )

    def test_product_review_images_use_the_same_bounded_normalization(self):
        upload = SimpleUploadedFile(
            "review.png",
            _png_bytes(),
            content_type="image/png",
        )

        media_type, normalized = ProductReviewViewSet._validate_media([upload])[0]

        self.assertEqual(media_type, "image")
        with Image.open(normalized) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 1200)
