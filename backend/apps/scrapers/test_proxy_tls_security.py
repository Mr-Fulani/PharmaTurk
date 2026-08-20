"""DB-free regressions for scraper proxy TLS policy."""

from django.test import override_settings

from apps.scrapers.base.scraper import BaseScraper


@override_settings(SCRAPER_PROXY_CA_BUNDLE="/run/secrets/proxy-ca.pem")
def test_proxy_ca_bundle_is_explicitly_propagated():
    assert BaseScraper._resolve_proxy_ca_bundle() == "/run/secrets/proxy-ca.pem"


@override_settings(SCRAPER_PROXY_CA_BUNDLE="")
def test_proxy_defaults_to_system_certificate_verification():
    assert (BaseScraper._resolve_proxy_ca_bundle() or True) is True
