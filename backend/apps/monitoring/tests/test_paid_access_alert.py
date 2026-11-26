"""Оповещение об отказе Bright Data: только на реальный отказ и не чаще раза в сутки."""

from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from django.core.cache import cache

from apps.http_errors import ExternalAccessBlockedError, PaidAccessUnavailableError
from apps.monitoring.paid_access_alert import (
    CACHE_KEY,
    is_paid_access_failure,
    report_paid_access_failure,
)

SEND = "apps.monitoring.watchdog.send_admin_telegram_notification"


@pytest.fixture(autouse=True)
def local_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"paid-access-alert-{uuid4().hex}",
        }
    }
    cache.clear()
    yield
    cache.clear()


def _unlocker_refusal():
    return PaidAccessUnavailableError(
        source="Bright Data Web Unlocker", status_code=402, url="https://api.brightdata.com/request"
    )


def _wrapped(cause):
    try:
        try:
            raise cause
        except Exception as exc:
            raise RuntimeError("Supplier request failed") from exc
    except RuntimeError as wrapped:
        return wrapped


@pytest.mark.parametrize(
    "exc",
    [
        _unlocker_refusal(),
        _wrapped(_unlocker_refusal()),
        httpx.ProxyError("407 Account is suspended"),
        _wrapped(httpx.ProxyError("402 Payment Required")),
        RuntimeError("Tunnel connection failed: 407 Proxy Authentication Required"),
        RuntimeError("Received HTTP code 407 from proxy after CONNECT"),
        ExternalAccessBlockedError(source="Zara", status_code=407, url="https://www.zara.com/tr/"),
    ],
)
def test_provider_refusal_is_recognised(exc):
    assert is_paid_access_failure(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        None,
        ExternalAccessBlockedError(source="Zara", status_code=403, url="https://www.zara.com/tr/"),
        httpx.ConnectTimeout("timed out"),
        httpx.ProxyError("Connection reset by peer"),
        RuntimeError("Supplier returned HTTP 402"),
        RuntimeError("price 407 TRY"),
    ],
)
def test_shop_and_network_errors_are_not_provider_refusals(exc):
    assert is_paid_access_failure(exc) is False


def test_alert_is_sent_once_a_day_in_plain_russian():
    with patch(SEND, return_value=True) as send:
        assert report_paid_access_failure("zara", _unlocker_refusal()) is True
        assert report_paid_access_failure("akakce", httpx.ProxyError("407 Account is suspended")) is False

    send.assert_called_once()
    text = send.call_args.args[0]
    assert "Bright Data" in text and "zara" in text
    assert "проверить баланс" in text
    assert "последние сохранённые цены" in text


def test_no_alert_for_ordinary_shop_error():
    with patch(SEND) as send:
        assert report_paid_access_failure("zara", httpx.ConnectTimeout("timed out")) is False
    send.assert_not_called()
    assert cache.get(CACHE_KEY) is None


def test_alert_can_be_switched_off(settings):
    settings.PAID_ACCESS_ALERT_ENABLED = False
    with patch(SEND) as send:
        assert report_paid_access_failure("zara", _unlocker_refusal()) is False
    send.assert_not_called()


def test_failed_delivery_is_retried_later_not_on_every_refusal():
    with patch(SEND, return_value=False) as send:
        assert report_paid_access_failure("zara", _unlocker_refusal()) is False
        assert report_paid_access_failure("zara", _unlocker_refusal()) is False
    send.assert_called_once()


def test_alert_never_breaks_the_caller():
    with patch(SEND, side_effect=RuntimeError("telegram down")):
        assert report_paid_access_failure("zara", _unlocker_refusal()) is False
