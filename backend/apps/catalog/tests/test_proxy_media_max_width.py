"""Тесты уменьшения изображений в proxy_media (?max_width= / ?w=)."""

import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from PIL import Image


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def small_jpeg_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (600, 400), color=(10, 100, 200)).save(buf, format='JPEG')
    return buf.getvalue()


def _proxy_media_view():
    # Importing catalog.views builds category prefetches and normally checks the
    # live schema. The proxy view itself does not need a database connection.
    with patch(
        'apps.catalog.models.service_portfolio_translation_fields_ready',
        return_value=False,
    ):
        from apps.catalog.views import proxy_media

    return proxy_media


def test_proxy_media_max_width_returns_smaller_webp(rf, small_jpeg_bytes):
    proxy_media = _proxy_media_view()

    cache.clear()
    mock_storage = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = io.BytesIO(small_jpeg_bytes)
    cm.__exit__.return_value = None
    mock_storage.open.return_value = cm

    with override_settings(R2_PUBLIC_URL='https://test.r2.dev'):
        with patch(
            'apps.catalog.utils.media_path.resolve_existing_media_storage_key',
            return_value='products/card_test.jpg',
        ):
            with patch('django.core.files.storage.default_storage', mock_storage):
                req = rf.get(
                    '/api/catalog/proxy-media/',
                    {'path': 'products/card_test.jpg', 'max_width': '200'},
                )
                resp = proxy_media(req)

    assert resp.status_code == 200
    assert resp['Content-Type'] == 'image/webp'
    data = resp.content
    assert len(data) < len(small_jpeg_bytes)
    img = Image.open(io.BytesIO(data))
    assert img.format == 'WEBP'
    assert max(img.size) <= 200


def test_proxy_media_max_width_does_not_decode_oversized_image(rf):
    proxy_media = _proxy_media_view()

    class SizedBytesIO(io.BytesIO):
        @property
        def size(self):
            return len(self.getbuffer())

    cache.clear()
    resize_source = SizedBytesIO(b'image header')
    resize_cm = MagicMock()
    resize_cm.__enter__.return_value = resize_source
    resize_cm.__exit__.return_value = None
    original_source = SizedBytesIO(b'original image bytes')

    mock_storage = MagicMock()
    mock_storage.open.side_effect = [resize_cm, original_source]

    oversized_image = MagicMock()
    oversized_image.size = (8000, 4000)

    with override_settings(R2_PUBLIC_URL='https://test.r2.dev'):
        with patch(
            'apps.catalog.utils.media_path.resolve_existing_media_storage_key',
            return_value='products/oversized.jpg',
        ):
            with patch('django.core.files.storage.default_storage', mock_storage):
                with patch('PIL.Image.open', return_value=oversized_image):
                    with patch('PIL.ImageOps.exif_transpose') as exif_transpose:
                        req = rf.get(
                            '/api/catalog/proxy-media/',
                            {'path': 'products/oversized.jpg', 'max_width': '480'},
                        )
                        resp = proxy_media(req)

    assert resp.status_code == 200
    assert resp['Content-Type'] == 'image/jpeg'
    exif_transpose.assert_not_called()


def test_proxy_media_does_not_expose_receipt_storage_keys(rf):
    proxy_media = _proxy_media_view()
    mock_storage = MagicMock()

    with override_settings(R2_PUBLIC_URL='https://test.r2.dev', R2_PREFIX='dev'):
        with patch(
            'apps.catalog.utils.media_path.resolve_existing_media_storage_key',
            return_value='dev/receipts/ORDER123.pdf',
        ):
            with patch('django.core.files.storage.default_storage', mock_storage):
                req = rf.get(
                    '/api/catalog/proxy-media/',
                    {'path': 'receipts/ORDER123.pdf'},
                )
                resp = proxy_media(req)

    assert resp.status_code == 404
    mock_storage.open.assert_not_called()


def test_proxy_media_rejects_unsatisfiable_range(rf):
    proxy_media = _proxy_media_view()

    class SizedBytesIO(io.BytesIO):
        @property
        def size(self):
            return len(self.getbuffer())

    source = SizedBytesIO(b'0123456789')
    mock_storage = MagicMock()
    mock_storage.open.return_value = source

    with override_settings(R2_PUBLIC_URL='https://test.r2.dev'):
        with patch(
            'apps.catalog.utils.media_path.resolve_existing_media_storage_key',
            return_value='products/demo/video.mp4',
        ):
            with patch('django.core.files.storage.default_storage', mock_storage):
                req = rf.get(
                    '/api/catalog/proxy-media/',
                    {'path': 'products/demo/video.mp4'},
                    HTTP_RANGE='bytes=100-200',
                )
                resp = proxy_media(req)

    assert resp.status_code == 416
    assert resp['Content-Range'] == 'bytes */10'
    assert resp['Accept-Ranges'] == 'bytes'
