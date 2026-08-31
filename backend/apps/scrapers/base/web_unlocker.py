"""Bounded Bright Data Web Unlocker transport for trusted supplier pages."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Collection
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.http_errors import raise_for_blocked_status


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnlockedResponse:
    """Validated target response returned by the Unlocker API."""

    text: str
    status_code: int
    final_url: str


class WebUnlockerResponseError(httpx.RequestError):
    """The provider returned a successful HTTP response without usable content."""

    def __init__(self, message: str, *, target_url: str) -> None:
        super().__init__(message, request=httpx.Request("GET", target_url))


class BrightDataWebUnlockerClient:
    """Small synchronous client with a fixed endpoint and strict target allowlist.

    The caller supplies only a server-owned target URL. The provider endpoint is
    intentionally not configurable, which prevents an environment typo from sending
    the bearer token to another host.
    """

    ENDPOINT = "https://api.brightdata.com/request"
    DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
    _ZONE_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
    _COUNTRY_RE = re.compile(r"^[a-z]{2}$")

    def __init__(
        self,
        *,
        api_key: str,
        zone: str,
        allowed_hosts: Collection[str],
        timeout: float,
        country: str = "tr",
        render: bool = False,
        expect_text: str = "window.productDetail",
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.zone = str(zone or "").strip()
        self.allowed_hosts = {
            str(host or "").strip().casefold().rstrip(".")
            for host in allowed_hosts
            if str(host or "").strip()
        }
        self.country = str(country or "").strip().casefold()
        self.render = bool(render)
        self.expect_text = str(expect_text or "").strip()
        self.max_response_bytes = max(1024, int(max_response_bytes))
        self._validate_configuration()
        self.client = httpx.Client(
            timeout=max(1.0, float(timeout)),
            follow_redirects=False,
            http2=True,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls,
        *,
        allowed_hosts: Collection[str],
        timeout: float,
    ) -> "BrightDataWebUnlockerClient":
        return cls(
            api_key=getattr(settings, "BRIGHTDATA_WEB_UNLOCKER_API_KEY", ""),
            zone=getattr(settings, "BRIGHTDATA_WEB_UNLOCKER_ZONE", ""),
            allowed_hosts=allowed_hosts,
            timeout=timeout,
            country=getattr(settings, "FLO_WEB_UNLOCKER_COUNTRY", "tr"),
            render=getattr(settings, "FLO_WEB_UNLOCKER_RENDER", False),
            expect_text=getattr(
                settings,
                "FLO_WEB_UNLOCKER_EXPECT_TEXT",
                "window.productDetail",
            ),
            max_response_bytes=getattr(
                settings,
                "FLO_WEB_UNLOCKER_MAX_RESPONSE_BYTES",
                cls.DEFAULT_MAX_RESPONSE_BYTES,
            ),
        )

    def _validate_configuration(self) -> None:
        if not self.api_key:
            raise ImproperlyConfigured("BRIGHTDATA_WEB_UNLOCKER_API_KEY is required")
        if not self._ZONE_RE.fullmatch(self.zone):
            raise ImproperlyConfigured(
                "BRIGHTDATA_WEB_UNLOCKER_ZONE must contain only letters, digits, '_' or '-'"
            )
        if not self.allowed_hosts:
            raise ImproperlyConfigured("Web Unlocker target allowlist must not be empty")
        if not self._COUNTRY_RE.fullmatch(self.country):
            raise ImproperlyConfigured("FLO_WEB_UNLOCKER_COUNTRY must be a two-letter code")
        if len(self.expect_text) > 256 or any(char in self.expect_text for char in "\r\n"):
            raise ImproperlyConfigured(
                "FLO_WEB_UNLOCKER_EXPECT_TEXT must be a single line up to 256 characters"
            )

    def _validate_target_url(self, target_url: str) -> str:
        url = str(target_url or "").strip()
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Web Unlocker target URL has an invalid port") from exc
        if (
            parsed.scheme.casefold() != "https"
            or hostname not in self.allowed_hosts
            or parsed.username
            or parsed.password
            or port not in (None, 443)
        ):
            raise ValueError("Web Unlocker target URL is not an allowed HTTPS supplier URL")
        return url

    @staticmethod
    def _target_envelope(response: httpx.Response) -> dict[str, Any] | None:
        content_type = str(response.headers.get("content-type") or "").casefold()
        if "json" not in content_type:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict) and "body" in payload:
            return payload
        return None

    @staticmethod
    def _status_code(value: Any, *, target_url: str) -> int:
        try:
            status_code = int(value)
        except (TypeError, ValueError) as exc:
            raise WebUnlockerResponseError(
                "Web Unlocker response has an invalid target status",
                target_url=target_url,
            ) from exc
        if status_code < 100 or status_code > 599:
            raise WebUnlockerResponseError(
                "Web Unlocker response has an invalid target status",
                target_url=target_url,
            )
        return status_code

    def _validate_body(self, body: Any, *, target_url: str) -> str:
        if not isinstance(body, str) or not body.strip():
            raise WebUnlockerResponseError(
                "Web Unlocker returned an empty target response",
                target_url=target_url,
            )
        if len(body.encode("utf-8")) > self.max_response_bytes:
            raise WebUnlockerResponseError(
                "Web Unlocker target response exceeds the configured size limit",
                target_url=target_url,
            )
        return body

    def fetch(self, target_url: str) -> UnlockedResponse:
        """Fetch one trusted URL. Bright Data owns CAPTCHA retries internally."""

        url = self._validate_target_url(target_url)
        payload: dict[str, Any] = {
            "zone": self.zone,
            "url": url,
            "format": "raw",
            "country": self.country,
        }
        if self.render:
            payload["render"] = "true"

        if self.expect_text:
            # With the REST endpoint, target headers belong in the JSON
            # envelope. Sending this as a header on api.brightdata.com makes
            # Bright Data ignore the expectation and an HTTP-200 CAPTCHA page
            # can be returned as if it were a valid product response.
            payload["headers"] = {
                "x-unblock-expect": json.dumps(
                    {"text": self.expect_text},
                    separators=(",", ":"),
                )
            }

        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self.client.post(
                self.ENDPOINT,
                headers=request_headers,
                json=payload,
            )
        except httpx.RequestError:
            logger.warning(
                "flo_web_unlocker_request",
                extra={
                    "outcome": "transport_error",
                    "target_host": urlparse(url).hostname or "",
                    "render": self.render,
                },
            )
            raise
        logger.info(
            "flo_web_unlocker_request",
            extra={
                "outcome": "response",
                "target_host": urlparse(url).hostname or "",
                "status_code": response.status_code,
                "response_bytes": len(response.content),
                "render": self.render,
            },
        )
        raise_for_blocked_status(
            status_code=response.status_code,
            url=self.ENDPOINT,
            source="Bright Data Web Unlocker",
        )
        response.raise_for_status()
        if len(response.content) > self.max_response_bytes:
            raise WebUnlockerResponseError(
                "Web Unlocker response exceeds the configured size limit",
                target_url=url,
            )

        envelope = self._target_envelope(response)
        if envelope is None:
            target_status = response.status_code
            body = response.text
        else:
            target_status = self._status_code(
                envelope.get("status_code", response.status_code),
                target_url=url,
            )
            body = envelope.get("body")

        raise_for_blocked_status(
            status_code=target_status,
            url=url,
            source="FLO",
        )
        if target_status >= 400:
            target_response = httpx.Response(
                target_status,
                request=httpx.Request("GET", url),
            )
            target_response.raise_for_status()

        return UnlockedResponse(
            text=self._validate_body(body, target_url=url),
            status_code=target_status,
            # The synchronous raw API does not document a final target URL.
            # Parser-level SKU validation below is therefore authoritative.
            final_url=url,
        )

    def close(self) -> None:
        self.client.close()
