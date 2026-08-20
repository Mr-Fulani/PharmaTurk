"""Bounded, SSRF-safe image loading for public visual search."""
from __future__ import annotations

import ipaddress
import re
import socket
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Iterator, Mapping
from urllib.parse import urljoin, urlsplit

import certifi
from django.core.files.storage import default_storage
from PIL import Image
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util import Timeout


MAX_URL_LENGTH = 2048
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_SIDE = 8192
MAX_REDIRECTS = 3
READ_CHUNK_SIZE = 64 * 1024
ALLOWED_PORTS = frozenset({80, 443})
ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp"}
)
ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
CONTENT_TYPE_FORMATS = {
    "image/jpeg": frozenset({"JPEG"}),
    "image/jpg": frozenset({"JPEG"}),
    "image/png": frozenset({"PNG"}),
    "image/webp": frozenset({"WEBP"}),
}
FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
TEMP_KEY_RE = re.compile(
    r"(?:^|/)temp/(?P<filename>[0-9a-f]{32}\.(?:jpg|jpeg|png|webp))$",
    re.IGNORECASE,
)


class ImageFetchError(Exception):
    """Base error safe to collapse into the public invalid-image response."""

    code = "invalid_image"

    def __init__(self) -> None:
        super().__init__(self.code)


class UnsafeImageURLError(ImageFetchError):
    code = "unsafe_image_url"


class UpstreamImageError(ImageFetchError):
    code = "image_fetch_failed"


class ImageTooLargeError(ImageFetchError):
    code = "image_too_large"


class InvalidImageError(ImageFetchError):
    code = "invalid_image"


@dataclass(frozen=True)
class ValidatedImage:
    image: Image.Image
    format: str


@dataclass(frozen=True)
class ResolvedImageURL:
    url: str
    scheme: str
    hostname: str
    port: int
    host_header: str
    request_target: str
    addresses: tuple[str, ...]


Resolver = Callable[..., list]


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return ""


def _parse_url(url: str, *, restrict_ports: bool) -> tuple[str, str, int, str, str]:
    if not isinstance(url, str):
        raise UnsafeImageURLError()
    url = url.strip()
    if not url or len(url) > MAX_URL_LENGTH or any(char in url for char in "\r\n\t"):
        raise UnsafeImageURLError()

    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except (TypeError, ValueError):
        raise UnsafeImageURLError() from None

    if scheme not in {"http", "https"} or not hostname or username is not None or password is not None:
        raise UnsafeImageURLError()
    if parsed.fragment or "%" in hostname or any(ord(char) < 33 for char in hostname):
        raise UnsafeImageURLError()

    raw_hostname = hostname.rstrip(".")
    if not raw_hostname:
        raise UnsafeImageURLError()
    try:
        ipaddress.ip_address(raw_hostname)
        normalized_hostname = raw_hostname
    except ValueError:
        try:
            normalized_hostname = raw_hostname.encode("idna").decode("ascii").lower()
        except UnicodeError:
            raise UnsafeImageURLError() from None

    effective_port = port if port is not None else (443 if scheme == "https" else 80)
    if restrict_ports and effective_port not in ALLOWED_PORTS:
        raise UnsafeImageURLError()

    default_port = 443 if scheme == "https" else 80
    host_for_header = (
        f"[{normalized_hostname}]"
        if ":" in normalized_hostname
        else normalized_hostname
    )
    if effective_port != default_port:
        host_for_header = f"{host_for_header}:{effective_port}"
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return scheme, normalized_hostname, effective_port, host_for_header, request_target


def validate_image_url_syntax(url: str) -> None:
    """Cheap request validation; network destinations are checked at fetch time."""

    _parse_url(url, restrict_ports=False)


def resolve_public_image_url(
    url: str,
    *,
    resolver: Resolver | None = None,
) -> ResolvedImageURL:
    """Resolve once and reject the whole hostname if any answer is non-global."""

    scheme, hostname, port, host_header, request_target = _parse_url(
        url,
        restrict_ports=True,
    )
    resolver = resolver or socket.getaddrinfo
    try:
        answers = resolver(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror):
        raise UpstreamImageError() from None

    addresses: list[str] = []
    for answer in answers:
        try:
            raw_address = str(answer[4][0]).split("%", 1)[0]
            address = ipaddress.ip_address(raw_address)
        except (IndexError, TypeError, ValueError):
            raise UnsafeImageURLError() from None
        if not address.is_global:
            raise UnsafeImageURLError()
        normalized = str(address)
        if normalized not in addresses:
            addresses.append(normalized)
    if not addresses:
        raise UpstreamImageError()

    return ResolvedImageURL(
        url=url.strip(),
        scheme=scheme,
        hostname=hostname,
        port=port,
        host_header=host_header,
        request_target=request_target,
        addresses=tuple(addresses),
    )


@contextmanager
def _open_pinned_response(
    target: ResolvedImageURL,
    address: str,
) -> Iterator[object]:
    """Connect to the vetted IP while retaining the original HTTPS identity."""

    timeout = Timeout(connect=3.0, read=5.0, total=10.0)
    common = {
        "host": address,
        "port": target.port,
        "timeout": timeout,
        "maxsize": 1,
        "block": True,
        "retries": False,
    }
    if target.scheme == "https":
        pool = HTTPSConnectionPool(
            **common,
            cert_reqs=ssl.CERT_REQUIRED,
            ca_certs=certifi.where(),
            server_hostname=target.hostname,
            assert_hostname=target.hostname,
        )
    else:
        pool = HTTPConnectionPool(**common)

    response = None
    try:
        response = pool.urlopen(
            "GET",
            target.request_target,
            headers={
                "Host": target.host_header,
                "User-Agent": "Mudaroba-VisualSearch/1.0",
                "Accept": "image/jpeg,image/png,image/webp",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
            preload_content=False,
            redirect=False,
            retries=False,
            release_conn=False,
        )
        yield response
    finally:
        if response is not None:
            try:
                response.release_conn()
            except Exception:
                pass
        pool.close()


def _read_bounded_response(response: object) -> tuple[bytes, str]:
    headers = getattr(response, "headers", {}) or {}
    content_type = _header(headers, "Content-Type").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImageError()
    content_encoding = _header(headers, "Content-Encoding").strip().lower()
    if content_encoding and content_encoding != "identity":
        raise InvalidImageError()

    content_length = _header(headers, "Content-Length").strip()
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            raise InvalidImageError() from None
        if declared_size < 0:
            raise InvalidImageError()
        if declared_size > MAX_IMAGE_BYTES:
            raise ImageTooLargeError()

    chunks: list[bytes] = []
    total = 0
    try:
        stream = response.stream(amt=READ_CHUNK_SIZE, decode_content=False)
        for chunk in stream:
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ImageTooLargeError()
            chunks.append(bytes(chunk))
    except ImageFetchError:
        raise
    except Exception:
        raise UpstreamImageError() from None
    return b"".join(chunks), content_type


def fetch_public_image_bytes(
    url: str,
    *,
    resolver: Resolver | None = None,
) -> tuple[bytes, str]:
    """Fetch an external image with manual redirects and DNS-pinned requests."""

    if not isinstance(url, str):
        raise UnsafeImageURLError()
    current_url = url.strip()
    visited: set[str] = set()
    for redirect_count in range(MAX_REDIRECTS + 1):
        if current_url in visited:
            raise UnsafeImageURLError()
        visited.add(current_url)
        target = resolve_public_image_url(current_url, resolver=resolver)

        redirect_url: str | None = None
        last_network_error: Exception | None = None
        for address in target.addresses:
            try:
                with _open_pinned_response(target, address) as response:
                    response_status = int(getattr(response, "status", 0))
                    if response_status in REDIRECT_STATUSES:
                        if redirect_count >= MAX_REDIRECTS:
                            raise UnsafeImageURLError()
                        location = _header(getattr(response, "headers", {}) or {}, "Location")
                        if not location:
                            raise UpstreamImageError()
                        redirect_url = urljoin(target.url, location)
                    elif response_status == 200:
                        return _read_bounded_response(response)
                    else:
                        raise UpstreamImageError()
                break
            except ImageFetchError:
                raise
            except Exception as exc:  # transport errors are deliberately generic
                last_network_error = exc
                continue
        if redirect_url is not None:
            current_url = redirect_url
            continue
        if last_network_error is not None:
            raise UpstreamImageError() from None
        raise UpstreamImageError()
    raise UnsafeImageURLError()


def validate_image_bytes(
    data: bytes,
    *,
    expected_content_type: str | None = None,
) -> ValidatedImage:
    """Verify format and decoded dimensions before handing an image to CLIP."""

    if not data:
        raise InvalidImageError()
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError()
    try:
        with Image.open(BytesIO(data)) as probe:
            image_format = str(probe.format or "").upper()
            width, height = probe.size
            if image_format not in ALLOWED_IMAGE_FORMATS:
                raise InvalidImageError()
            if width <= 0 or height <= 0:
                raise InvalidImageError()
            if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
                raise ImageTooLargeError()
            if width * height > MAX_IMAGE_PIXELS:
                raise ImageTooLargeError()
            probe.verify()

        normalized_content_type = (expected_content_type or "").split(";", 1)[0].strip().lower()
        if normalized_content_type:
            expected_formats = CONTENT_TYPE_FORMATS.get(normalized_content_type)
            if not expected_formats or image_format not in expected_formats:
                raise InvalidImageError()

        with Image.open(BytesIO(data)) as source:
            source.load()
            image = source.convert("RGB").copy()
        return ValidatedImage(image=image, format=image_format)
    except ImageFetchError:
        raise
    except Exception:
        raise InvalidImageError() from None


def _read_storage_object(key: str) -> bytes:
    try:
        with default_storage.open(key, "rb") as file_obj:
            data = file_obj.read(MAX_IMAGE_BYTES + 1)
    except Exception:
        raise InvalidImageError() from None
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError()
    return data


def _load_exact_temp_image(url: str, request: object | None) -> ValidatedImage | None:
    """Read only the exact URL emitted for our UUID-named temp storage object."""

    if request is None or not isinstance(url, str) or len(url) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    match = TEMP_KEY_RE.search(parsed.path)
    if not match or parsed.query or parsed.fragment:
        return None

    key = f"temp/{match.group('filename').lower()}"
    try:
        generated_url = default_storage.url(key)
        if not generated_url.startswith(("http://", "https://")):
            generated_url = request.build_absolute_uri(generated_url)
    except Exception:
        return None
    if url != generated_url:
        return None
    return validate_image_bytes(_read_storage_object(key))


def fetch_search_image(
    url: str,
    *,
    request: object | None = None,
    resolver: Resolver | None = None,
) -> Image.Image:
    """Return a fully decoded image from exact temp storage or a public URL."""

    stored = _load_exact_temp_image(url, request)
    if stored is not None:
        return stored.image
    data, content_type = fetch_public_image_bytes(url, resolver=resolver)
    return validate_image_bytes(data, expected_content_type=content_type).image
