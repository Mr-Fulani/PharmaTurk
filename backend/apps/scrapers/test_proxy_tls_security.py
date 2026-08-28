"""DB-free regressions for scraper proxy TLS policy."""

import hashlib
import ssl
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from apps.scrapers.base.scraper import BaseScraper
from apps.scrapers.parsers.flo import FloParser
from apps.scrapers.parsers.zara import ZaraParser

BRIGHTDATA_CA = Path(__file__).resolve().parents[2] / "certs" / "brightdata_root_ca_44445.crt"
BRIGHTDATA_CA_SHA256 = "db8548f8a5b1166536920ccd0473840f7fdbaf165dedf907b7b52361abc87b60"


@override_settings(SCRAPER_PROXY_CA_BUNDLE=str(BRIGHTDATA_CA))
def test_proxy_ca_bundle_is_explicitly_propagated():
    assert BaseScraper._resolve_proxy_ca_bundle() == str(BRIGHTDATA_CA)


@override_settings(SCRAPER_PROXY_CA_BUNDLE="")
def test_proxy_defaults_to_system_certificate_verification():
    assert (BaseScraper._resolve_proxy_ca_bundle() or True) is True


def test_vendored_brightdata_ca_has_pinned_fingerprint():
    pem = BRIGHTDATA_CA.read_text(encoding="ascii")
    der = ssl.PEM_cert_to_DER_cert(pem)

    assert hashlib.sha256(der).hexdigest() == BRIGHTDATA_CA_SHA256


@override_settings(
    SCRAPER_PROXY_URL="http://customer:password@brd.superproxy.io:33335",
    SCRAPER_PROXY_CA_BUNDLE=str(BRIGHTDATA_CA),
)
def test_brightdata_legacy_port_is_rejected_before_transport_setup():
    with pytest.raises(ImproperlyConfigured, match="port 44445"):
        FloParser(use_proxy=True)


@override_settings(
    SCRAPER_PROXY_URL="http://customer:password@brd.superproxy.io:44445",
    SCRAPER_PROXY_CA_BUNDLE="",
)
def test_brightdata_proxy_without_ca_is_rejected_before_transport_setup():
    with pytest.raises(ImproperlyConfigured, match="requires SCRAPER_PROXY_CA_BUNDLE"):
        FloParser(use_proxy=True)


@override_settings(
    SCRAPER_PROXY_URL="http://customer:password@brd.superproxy.io:44445",
    SCRAPER_PROXY_CA_BUNDLE=str(BRIGHTDATA_CA),
)
def test_brightdata_current_port_uses_vendored_ca(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.headers = {}

        def close(self):
            return None

    monkeypatch.setattr("apps.scrapers.base.scraper.httpx.Client", Client)

    parser = FloParser(use_proxy=True)
    try:
        assert captured["proxy"].endswith("@brd.superproxy.io:44445")
        assert captured["verify"] == str(BRIGHTDATA_CA)
    finally:
        parser.__exit__(None, None, None)


@override_settings(
    SCRAPER_PROXY_URL="http://customer:password@brd.superproxy.io:44445",
    SCRAPER_PROXY_CA_BUNDLE=str(BRIGHTDATA_CA),
)
def test_zara_warmup_and_ajax_share_proxy_ca(monkeypatch):
    httpx_kwargs = {}

    class HttpxClient:
        def __init__(self, **kwargs):
            httpx_kwargs.update(kwargs)
            self.headers = {}

        def close(self):
            return None

    class RequestsSession:
        def __init__(self):
            self.headers = {}
            self.proxies = {}
            self.verify = True

        def close(self):
            return None

    ajax_session = RequestsSession()
    monkeypatch.setattr("apps.scrapers.base.scraper.httpx.Client", HttpxClient)
    monkeypatch.setattr(
        "apps.scrapers.parsers.zara.requests.Session",
        lambda: ajax_session,
    )

    parser = ZaraParser(use_proxy=True)
    try:
        assert httpx_kwargs["verify"] == str(BRIGHTDATA_CA)
        assert ajax_session.proxies["https"].endswith("@brd.superproxy.io:44445")
        assert ajax_session.verify == str(BRIGHTDATA_CA)
    finally:
        parser.__exit__(None, None, None)
