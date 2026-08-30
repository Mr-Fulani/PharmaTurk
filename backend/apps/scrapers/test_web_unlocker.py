"""Security and response-contract tests for the FLO Web Unlocker transport."""

from __future__ import annotations

import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.http_errors import ExternalAccessBlockedError
from apps.scrapers.base.web_unlocker import (
    BrightDataWebUnlockerClient,
    UnlockedResponse,
    WebUnlockerResponseError,
)
from apps.scrapers.parsers import flo as flo_module
from apps.scrapers.parsers.flo import FloParser


TARGET = "https://www.flo.com.tr/urun/model-10001"


def _client(handler, **overrides):
    kwargs = {
        "api_key": "test-token",
        "zone": "flo_unlocker",
        "allowed_hosts": {"flo.com.tr", "www.flo.com.tr"},
        "timeout": 5,
        "country": "tr",
        "transport": httpx.MockTransport(handler),
    }
    kwargs.update(overrides)
    return BrightDataWebUnlockerClient(**kwargs)


def test_unlocker_posts_only_to_fixed_endpoint_with_server_credentials():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html>window.productDetail = {}</html>",
        )

    client = _client(handler, render=True)
    try:
        result = client.fetch(TARGET)
    finally:
        client.close()

    assert captured == {
        "url": BrightDataWebUnlockerClient.ENDPOINT,
        "authorization": "Bearer test-token",
        "payload": {
            "zone": "flo_unlocker",
            "url": TARGET,
            "format": "raw",
            "country": "tr",
            "render": "true",
        },
    }
    assert result.text.startswith("<html>")
    assert result.status_code == 200
    assert result.final_url == TARGET


def test_unlocker_accepts_documented_json_response_envelope():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status_code": 200,
                "headers": {"content-type": "text/html"},
                "body": "<html>window.productDetail = {}</html>",
            },
        )

    client = _client(handler)
    try:
        result = client.fetch(TARGET)
    finally:
        client.close()

    assert "window.productDetail" in result.text


@pytest.mark.parametrize(
    "url",
    [
        "http://www.flo.com.tr/urun/model-10001",
        "https://flo.com.tr.evil.example/urun/model-10001",
        "https://user:password@www.flo.com.tr/urun/model-10001",
        "https://www.flo.com.tr:444/urun/model-10001",
    ],
)
def test_unlocker_rejects_untrusted_target_before_network(url):
    calls = []
    client = _client(lambda request: calls.append(request) or httpx.Response(200, text="x"))
    try:
        with pytest.raises(ValueError, match="allowed HTTPS supplier URL"):
            client.fetch(url)
    finally:
        client.close()

    assert calls == []


@pytest.mark.parametrize("status_code", [401, 403, 407])
def test_unlocker_auth_and_access_failures_are_typed(status_code):
    client = _client(lambda _request: httpx.Response(status_code, text="denied"))
    try:
        with pytest.raises(ExternalAccessBlockedError) as error:
            client.fetch(TARGET)
    finally:
        client.close()

    assert error.value.status_code == status_code
    assert "test-token" not in str(error.value)


@pytest.mark.parametrize("target_status", [404, 410, 429, 503])
def test_unlocker_preserves_target_http_failures(target_status):
    client = _client(
        lambda _request: httpx.Response(
            200,
            json={"status_code": target_status, "headers": {}, "body": "failure"},
        )
    )
    try:
        with pytest.raises(httpx.HTTPStatusError) as error:
            client.fetch(TARGET)
    finally:
        client.close()

    assert error.value.response.status_code == target_status
    assert str(error.value.request.url) == TARGET


def test_unlocker_rejects_empty_and_oversized_content():
    empty = _client(lambda _request: httpx.Response(200, text="   "))
    try:
        with pytest.raises(WebUnlockerResponseError, match="empty"):
            empty.fetch(TARGET)
    finally:
        empty.close()

    oversized = _client(
        lambda _request: httpx.Response(200, text="x" * 2048),
        max_response_bytes=1024,
    )
    try:
        with pytest.raises(WebUnlockerResponseError, match="size limit"):
            oversized.fetch(TARGET)
    finally:
        oversized.close()


@pytest.mark.parametrize(
    ("api_key", "zone", "message"),
    [
        ("", "flo_unlocker", "API_KEY"),
        ("secret", "bad zone!", "ZONE"),
    ],
)
def test_unlocker_configuration_fails_closed(api_key, zone, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        BrightDataWebUnlockerClient(
            api_key=api_key,
            zone=zone,
            allowed_hosts={"www.flo.com.tr"},
            timeout=5,
        )


@override_settings(
    FLO_WEB_UNLOCKER_ENABLED=True,
    SCRAPER_PROXY_URL="http://customer:password@brd.superproxy.io:33335",
    SCRAPER_PROXY_CA_BUNDLE="",
)
def test_flo_uses_unlocker_without_constructing_native_proxy(monkeypatch):
    calls = []

    class StubUnlocker:
        def fetch(self, url):
            calls.append(url)
            return UnlockedResponse("<html>ok</html>", 200, url)

        def close(self):
            calls.append("closed")

    stub = StubUnlocker()

    class Factory:
        @staticmethod
        def from_settings(**kwargs):
            assert kwargs["allowed_hosts"] == ["flo.com.tr", "www.flo.com.tr"]
            return stub

    monkeypatch.setattr(flo_module, "BrightDataWebUnlockerClient", Factory)
    parser = FloParser(use_proxy=True, use_web_unlocker=True)
    try:
        assert parser.proxy_url == ""
        assert parser._make_request(TARGET) == "<html>ok</html>"
        assert parser._make_offer_request(TARGET, include_final_url=True) == (
            "<html>ok</html>",
            TARGET,
        )
    finally:
        parser.__exit__(None, None, None)

    assert calls == [TARGET, TARGET, "closed"]


@override_settings(FLO_WEB_UNLOCKER_ENABLED=False)
def test_flo_does_not_activate_paid_transport_from_constructor_flag_alone(monkeypatch):
    class Factory:
        @staticmethod
        def from_settings(**_kwargs):
            pytest.fail("disabled Web Unlocker must not be constructed")

    monkeypatch.setattr(flo_module, "BrightDataWebUnlockerClient", Factory)
    parser = FloParser(use_web_unlocker=True)
    try:
        assert parser.web_unlocker is None
    finally:
        parser.__exit__(None, None, None)
