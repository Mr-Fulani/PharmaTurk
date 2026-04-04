"""Тесты уменьшения изображений в proxy_media (?max_width= / ?w=)."""

import io
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from PIL import Image

from apps.catalog.views import proxy_media


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def small_jpeg_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (600, 400), color=(10, 100, 200)).save(buf, format='JPEG')
    return buf.getvalue()


@pytest.mark.django_db
def test_proxy_media_max_width_returns_smaller_webp(rf, small_jpeg_bytes):
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
