"""TD-017: запасные ветки рекомендаций пишут причину в журнал."""
import logging
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from apps.recommendations.services import safe_image_fetcher as fetcher
from apps.recommendations.tasks import _working_product_image_url


def test_storage_check_failures_fall_through_and_are_logged(caplog):
    first_image = SimpleNamespace(
        image_file=SimpleNamespace(name="products/b.jpg", url="https://cdn.example/b.jpg")
    )
    images = Mock()
    images.exclude.return_value.first.return_value = first_image
    product = SimpleNamespace(
        pk=11,
        main_image_file=SimpleNamespace(name="products/a.jpg", url="https://cdn.example/a.jpg"),
        main_image="https://cdn.example/media/products/m.jpg",
        images=images,
    )
    storage = Mock()
    storage.exists.side_effect = [OSError("r2 down"), OSError("r2 down"), True]

    with patch("django.core.files.storage.default_storage", storage), patch(
        "apps.catalog.signals.is_internal_storage_url", return_value=True
    ), patch(
        "apps.catalog.signals._get_path_from_storage_url", return_value="products/m.jpg"
    ), caplog.at_level(logging.WARNING, logger="apps.recommendations.tasks"):
        assert _working_product_image_url(product) == "https://cdn.example/b.jpg"

    assert "Product 11: storage check for products/a.jpg failed: OSError: r2 down" in caplog.text
    assert "Product 11: storage check for products/m.jpg failed: OSError: r2 down" in caplog.text


def test_release_conn_failure_keeps_image_and_is_logged(caplog):
    data = BytesIO()
    Image.new("RGB", (16, 16)).save(data, "PNG")
    png = data.getvalue()
    response = Mock(status=200, headers={"Content-Type": "image/png"})
    response.stream.return_value = [png]
    response.release_conn.side_effect = OSError("socket closed")
    pool = Mock()
    pool.urlopen.return_value = response

    with patch.object(fetcher, "HTTPSConnectionPool", return_value=pool), caplog.at_level(
        logging.DEBUG, logger=fetcher.__name__
    ):
        result = fetcher.fetch_public_image_bytes(
            "https://images.example/photo.png",
            resolver=lambda host, port, **kwargs: [(2, 1, 6, "", ("93.184.216.34", port))],
        )

    assert result == (png, "image/png")
    assert "Image fetch release_conn failed: OSError" in caplog.text


def test_temp_image_url_failure_returns_none_and_is_logged(caplog):
    key = "temp/" + "c" * 32 + ".png"
    storage = Mock()
    storage.url.side_effect = RuntimeError("storage misconfigured")

    with patch.object(fetcher, "default_storage", storage), caplog.at_level(
        logging.WARNING, logger=fetcher.__name__
    ):
        assert fetcher._load_exact_temp_image(f"https://shop.example/media/{key}", Mock()) is None

    assert f"Temp image URL for {key} unavailable: RuntimeError: storage misconfigured" in caplog.text
    storage.open.assert_not_called()
