from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
from PIL import Image, features

from apps.recommendations.services import safe_image_fetcher as fetcher


def _dns(*addresses: str):
    def resolver(host, port, **kwargs):
        return [
            (2 if ":" not in address else 10, 1, 6, "", (address, port))
            for address in addresses
        ]

    return resolver


def _image_bytes(image_format: str, size=(16, 16)) -> bytes:
    data = BytesIO()
    Image.new("RGB", size=size, color=(20, 40, 60)).save(data, image_format)
    return data.getvalue()


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=()):
        self.status = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.released = False

    def stream(self, **kwargs):
        yield from self._chunks

    def release_conn(self):
        self.released = True


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://images.example/a.jpg",
        "//images.example/a.jpg",
        "https://user:pass@images.example/a.jpg",
        "https://images.example:444/a.jpg",
        "https://images.example/a.jpg#fragment",
        "https://%31%32%37.0.0.1/a.jpg",
    ],
)
def test_rejects_unsafe_url_shapes(url):
    with pytest.raises(fetcher.UnsafeImageURLError):
        fetcher.resolve_public_image_url(url, resolver=_dns("93.184.216.34"))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
    ],
)
def test_rejects_non_global_dns_answers(address):
    with pytest.raises(fetcher.UnsafeImageURLError):
        fetcher.resolve_public_image_url(
            "https://images.example/a.jpg",
            resolver=_dns(address),
        )


def test_rejects_mixed_public_and_private_dns_answers():
    with pytest.raises(fetcher.UnsafeImageURLError):
        fetcher.resolve_public_image_url(
            "https://images.example/a.jpg",
            resolver=_dns("93.184.216.34", "10.0.0.7"),
        )


def test_https_connection_is_pinned_but_keeps_original_tls_identity():
    png = _image_bytes("PNG")
    response = FakeResponse(
        headers={"Content-Type": "image/png", "Content-Length": str(len(png))},
        chunks=[png],
    )
    pool = Mock()
    pool.urlopen.return_value = response

    with patch.object(fetcher, "HTTPSConnectionPool", return_value=pool) as pool_cls:
        data, content_type = fetcher.fetch_public_image_bytes(
            "https://images.example/photo.png?size=small",
            resolver=_dns("93.184.216.34"),
        )

    assert data == png
    assert content_type == "image/png"
    kwargs = pool_cls.call_args.kwargs
    assert kwargs["host"] == "93.184.216.34"
    assert kwargs["server_hostname"] == "images.example"
    assert kwargs["assert_hostname"] == "images.example"
    request_args, request_kwargs = pool.urlopen.call_args
    assert request_args[:2] == ("GET", "/photo.png?size=small")
    assert request_kwargs["headers"]["Host"] == "images.example"
    assert request_kwargs["redirect"] is False


def test_redirect_target_is_resolved_and_private_target_is_rejected():
    @contextmanager
    def redirect_response(target, address):
        yield FakeResponse(
            status=302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    def resolver(host, port, **kwargs):
        address = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
        return [(2, 1, 6, "", (address, port))]

    with patch.object(fetcher, "_open_pinned_response", redirect_response):
        with pytest.raises(fetcher.UnsafeImageURLError):
            fetcher.fetch_public_image_bytes(
                "https://images.example/start",
                resolver=resolver,
            )


def test_rejects_more_than_three_redirects():
    @contextmanager
    def redirect_response(target, address):
        yield FakeResponse(status=302, headers={"Location": f"{target.url}/next"})

    with patch.object(fetcher, "_open_pinned_response", redirect_response):
        with pytest.raises(fetcher.UnsafeImageURLError):
            fetcher.fetch_public_image_bytes(
                "https://images.example/start",
                resolver=_dns("93.184.216.34"),
            )


def test_rejects_declared_oversized_response_without_streaming():
    response = FakeResponse(
        headers={
            "Content-Type": "image/jpeg",
            "Content-Length": str(fetcher.MAX_IMAGE_BYTES + 1),
        },
    )
    response.stream = Mock(side_effect=AssertionError("must not stream"))
    with pytest.raises(fetcher.ImageTooLargeError):
        fetcher._read_bounded_response(response)
    response.stream.assert_not_called()


def test_rejects_stream_that_crosses_hard_byte_limit():
    response = FakeResponse(
        headers={"Content-Type": "image/jpeg"},
        chunks=[b"a" * fetcher.MAX_IMAGE_BYTES, b"b"],
    )
    with pytest.raises(fetcher.ImageTooLargeError):
        fetcher._read_bounded_response(response)


@pytest.mark.parametrize("content_type", ["text/html", "application/octet-stream", "image/gif"])
def test_rejects_non_supported_content_type(content_type):
    response = FakeResponse(headers={"Content-Type": content_type}, chunks=[b"data"])
    with pytest.raises(fetcher.InvalidImageError):
        fetcher._read_bounded_response(response)


def test_rejects_mime_and_actual_format_mismatch():
    with pytest.raises(fetcher.InvalidImageError):
        fetcher.validate_image_bytes(
            _image_bytes("PNG"),
            expected_content_type="image/jpeg",
        )


def test_rejects_excessive_pixel_count_before_decode():
    data = BytesIO()
    Image.new("1", size=(4097, 4097)).save(data, "PNG")
    with pytest.raises(fetcher.ImageTooLargeError):
        fetcher.validate_image_bytes(data.getvalue())


def test_rejects_unsupported_actual_format():
    with pytest.raises(fetcher.InvalidImageError):
        fetcher.validate_image_bytes(_image_bytes("GIF"))


@pytest.mark.parametrize(
    ("image_format", "content_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_accepts_supported_images(image_format, content_type):
    if image_format == "WEBP" and not features.check("webp"):
        pytest.skip("Pillow was built without WebP")
    validated = fetcher.validate_image_bytes(
        _image_bytes(image_format),
        expected_content_type=content_type,
    )
    assert validated.format == image_format
    assert validated.image.mode == "RGB"
    assert validated.image.size == (16, 16)


def test_exact_generated_temp_url_reads_storage_without_http():
    filename = "a" * 32 + ".png"
    key = f"temp/{filename}"
    storage = Mock()
    storage.url.return_value = f"/media/{key}"
    storage.open.return_value = BytesIO(_image_bytes("PNG"))
    request = Mock()
    request.build_absolute_uri.side_effect = lambda value: f"https://shop.example{value}"

    with patch.object(fetcher, "default_storage", storage), patch.object(
        fetcher,
        "_open_pinned_response",
        side_effect=AssertionError("temp image must not use HTTP"),
    ):
        image = fetcher.fetch_search_image(
            f"https://shop.example/media/{key}",
            request=request,
        )

    assert image.size == (16, 16)
    storage.open.assert_called_once_with(key, "rb")


def test_similar_but_non_exact_temp_url_is_not_read_from_storage():
    filename = "b" * 32 + ".png"
    storage = Mock()
    storage.url.return_value = f"/media/temp/{filename}"
    request = Mock()
    request.build_absolute_uri.return_value = f"https://shop.example/media/temp/{filename}"

    with patch.object(fetcher, "default_storage", storage):
        with pytest.raises(fetcher.UnsafeImageURLError):
            fetcher.fetch_search_image(
                f"https://evil.example/media/temp/{filename}",
                request=request,
                resolver=_dns("127.0.0.1"),
            )
    storage.open.assert_not_called()
