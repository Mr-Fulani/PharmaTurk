from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from api.throttles import COOKIE_CONSENT_THROTTLES, TrustedProxyIPRateThrottle
from apps.marketing.models import CookieConsent
from apps.marketing.views import CookieConsentView


def _consent_request(
    factory: APIRequestFactory,
    *,
    remote_addr: str,
    forwarded_for: str = "",
    real_ip: str = "",
):
    request = factory.post(
        reverse("cookie-consent"),
        {"consent": True},
        format="json",
        REMOTE_ADDR=remote_addr,
        HTTP_X_FORWARDED_FOR=forwarded_for,
        HTTP_X_REAL_IP=real_ip,
    )
    request.session = SimpleNamespace(session_key=None)
    return request


def test_cookie_consent_view_has_explicit_burst_and_sustained_limits():
    assert CookieConsentView.throttle_classes == COOKIE_CONSENT_THROTTLES
    assert len(COOKIE_CONSENT_THROTTLES) == 2
    assert {throttle.rate for throttle in COOKIE_CONSENT_THROTTLES} == {"10/min", "100/day"}
    assert all(issubclass(throttle, TrustedProxyIPRateThrottle) for throttle in COOKIE_CONSENT_THROTTLES)
    assert {
        throttle().parse_rate(throttle.rate)
        for throttle in COOKIE_CONSENT_THROTTLES
    } == {(10, 60), (100, 86_400)}


def test_cookie_consent_ignores_spoofed_x_forwarded_for_when_recording_ip():
    request = _consent_request(
        APIRequestFactory(),
        remote_addr="203.0.113.41",
        forwarded_for="198.51.100.250, 10.0.0.5",
    )

    with patch("apps.marketing.views.CookieConsent.objects.create") as create_consent:
        response = CookieConsentView.as_view()(request)

    assert response.status_code == 201
    assert create_consent.call_args.kwargs["ip_address"] == "203.0.113.41"
    assert create_consent.call_args.kwargs["ip_address"] != "198.51.100.250"


def test_cookie_consent_burst_limit_returns_429_and_xff_cannot_rotate_identity():
    burst_class = next(
        throttle for throttle in COOKIE_CONSENT_THROTTLES if throttle.rate.endswith("/min")
    )
    request_limit, _ = burst_class().parse_rate(burst_class.rate)
    factory = APIRequestFactory()
    view = CookieConsentView.as_view()
    cache.clear()

    with patch("apps.marketing.views.CookieConsent.objects.create") as create_consent:
        responses = [
            view(
                _consent_request(
                    factory,
                    remote_addr="203.0.113.42",
                    forwarded_for=f"198.51.100.{index + 1}",
                )
            )
            for index in range(request_limit + 1)
        ]

    assert all(response.status_code == 201 for response in responses[:-1])
    assert responses[-1].status_code == 429
    assert create_consent.call_count == request_limit


@pytest.mark.django_db
def test_cookie_consent_persists_nginx_trusted_ip_not_forwarded_chain():
    response = APIClient().post(
        reverse("cookie-consent"),
        {"consent": False},
        format="json",
        HTTP_X_REAL_IP="203.0.113.43",
        HTTP_X_FORWARDED_FOR="198.51.100.251, 10.0.0.6",
        REMOTE_ADDR="172.18.0.2",
    )

    assert response.status_code == 201
    consent = CookieConsent.objects.get()
    assert str(consent.ip_address) == "203.0.113.43"
    assert str(consent.ip_address) != "198.51.100.251"
