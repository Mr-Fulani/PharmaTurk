from io import BytesIO
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from PIL import Image

from apps.catalog.views import _proxy_image_host_allowed, proxy_image
from apps.recommendations.services.safe_image_fetcher import UpstreamImageError


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(1, 2, 3)).save(output, format="PNG")
    return output.getvalue()


class ProxyImageHostValidationTests(SimpleTestCase):
    def test_allows_exact_cdn_hosts_and_subdomains(self):
        self.assertTrue(_proxy_image_host_allowed("https://scontent.cdninstagram.com/a.jpg"))
        self.assertTrue(_proxy_image_host_allowed("https://instagram.fist1-1.fna.fbcdn.net/a.jpg"))
        self.assertFalse(_proxy_image_host_allowed("https://bucket.r2.dev/a.jpg"))
        self.assertTrue(_proxy_image_host_allowed("https://cdn.mudaroba.com/a.jpg"))

    def test_rejects_substring_spoof_credentials_and_plain_http(self):
        unsafe_urls = [
            "http://127.0.0.1/?cdninstagram.com",
            "https://cdninstagram.com.attacker.example/a.jpg",
            "https://attacker.example/?host=cdninstagram.com",
            "https://cdninstagram.com@attacker.example/a.jpg",
        ]
        for url in unsafe_urls:
            with self.subTest(url=url):
                self.assertFalse(_proxy_image_host_allowed(url))

    @override_settings(R2_PUBLIC_URL="https://media.example.com")
    def test_configured_r2_public_host_is_allowed_exactly(self):
        self.assertTrue(_proxy_image_host_allowed("https://media.example.com/a.png"))
        self.assertFalse(_proxy_image_host_allowed("https://media.example.com.evil.test/a.png"))


class ProxyImageViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("apps.catalog.views.fetch_public_image_bytes")
    def test_unsafe_url_is_rejected_before_network(self, fetch_image):
        request = self.factory.get(
            "/api/catalog/proxy-image/",
            {"url": "http://127.0.0.1/?cdninstagram.com"},
        )

        response = proxy_image(request)

        self.assertEqual(response.status_code, 400)
        fetch_image.assert_not_called()

    @patch("apps.catalog.views.fetch_public_image_bytes")
    def test_valid_fetched_image_is_returned_with_detected_mime(self, fetch_image):
        fetch_image.return_value = (_png_bytes(), "image/png")
        request = self.factory.get(
            "/api/catalog/proxy-image/",
            {"url": "https://scontent.cdninstagram.com/a.png"},
        )

        response = proxy_image(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    @patch("apps.catalog.views._proxy_image_cache_miss_allowed", return_value=False)
    @patch("apps.catalog.views.fetch_public_image_bytes")
    def test_unique_upstream_fetches_are_rate_limited(self, fetch_image, _allowed):
        request = self.factory.get(
            "/api/catalog/proxy-image/",
            {"url": "https://scontent.cdninstagram.com/rate-limited.png"},
        )

        response = proxy_image(request)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
        fetch_image.assert_not_called()

    @patch("apps.catalog.views.fetch_public_image_bytes", side_effect=UpstreamImageError())
    def test_upstream_failure_returns_small_placeholder(self, _fetch_image):
        request = self.factory.get(
            "/api/catalog/proxy-image/",
            {"url": "https://scontent.cdninstagram.com/missing.jpg"},
        )

        response = proxy_image(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/gif")
        self.assertLess(len(response.content), 100)
