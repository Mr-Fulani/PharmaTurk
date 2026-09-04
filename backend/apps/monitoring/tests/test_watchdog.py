from unittest.mock import Mock, patch

import pytest
import requests
from django.core.cache import cache
from django.test import override_settings

from apps.monitoring.checks import production_watchdog_configuration_check
from apps.monitoring.tasks import STATE_KEY, run_production_watchdog
from apps.monitoring.watchdog import (
    ProbeResult,
    run_public_probes,
    send_admin_telegram_notification,
)


def _response(status_code=200, payload=None):
    response = Mock(status_code=status_code, ok=200 <= status_code < 300)
    response.json.return_value = payload
    return response


def _healthy_results():
    return [
        ProbeResult("homepage", True, 10, 200),
        ProbeResult("liveness", True, 11, 200),
        ProbeResult("readiness", True, 12, 200),
    ]


def _failing_results():
    return [
        ProbeResult("homepage", True, 10, 200),
        ProbeResult("liveness", True, 11, 200),
        ProbeResult("readiness", False, 12, 503, "http_503"),
    ]


def test_public_probes_validate_readiness_contract_without_following_redirects():
    get = Mock(
        side_effect=[
            _response(payload=None),
            _response(payload={"status": "ok"}),
            _response(payload={"status": "unavailable", "db": True, "cache": False}),
        ]
    )

    results = run_public_probes(
        "https://mudaroba.example",
        timeout_seconds=7,
        request_get=get,
    )

    assert [item.ok for item in results] == [True, True, False]
    assert results[-1].reason == "invalid_health_contract"
    assert all(call.kwargs["allow_redirects"] is False for call in get.call_args_list)
    assert all(call.kwargs["timeout"] == (3, 7) for call in get.call_args_list)


def test_public_probes_return_sanitized_network_failure():
    get = Mock(side_effect=requests.ConnectionError("private upstream detail"))

    results = run_public_probes(
        "https://mudaroba.example",
        timeout_seconds=5,
        request_get=get,
    )

    assert [item.reason for item in results] == ["connection_error"] * 3
    assert "private upstream detail" not in repr(results)


@override_settings(
    PRODUCTION_WATCHDOG_ENABLED=True,
    PRODUCTION_WATCHDOG_BASE_URL="http://mudaroba.example/path",
    PRODUCTION_WATCHDOG_INTERVAL_SECONDS=300,
    PRODUCTION_WATCHDOG_FAILURE_THRESHOLD=2,
    PRODUCTION_WATCHDOG_REPEAT_SECONDS=3600,
    PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS=10,
    TELEGRAM_BOT_TOKEN="",
    TELEGRAM_CHAT_ID="",
)
def test_enabled_watchdog_requires_https_origin_and_receiver():
    errors = production_watchdog_configuration_check(None)

    assert {error.id for error in errors} == {
        "monitoring.E001",
        "monitoring.E002",
        "monitoring.E003",
    }


@override_settings(PRODUCTION_WATCHDOG_ENABLED=False)
@patch("apps.monitoring.tasks.run_public_probes")
def test_disabled_watchdog_does_not_make_requests(run_probes):
    assert run_production_watchdog() == {"status": "disabled"}
    run_probes.assert_not_called()


@pytest.mark.django_db
@override_settings(
    PRODUCTION_WATCHDOG_ENABLED=True,
    PRODUCTION_WATCHDOG_BASE_URL="https://mudaroba.example",
    PRODUCTION_WATCHDOG_INTERVAL_SECONDS=300,
    PRODUCTION_WATCHDOG_FAILURE_THRESHOLD=2,
    PRODUCTION_WATCHDOG_REPEAT_SECONDS=3600,
    PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS=10,
)
@patch("apps.monitoring.tasks.send_admin_telegram_notification", return_value=True)
@patch("apps.monitoring.tasks.run_public_probes", side_effect=[_failing_results()] * 3)
def test_watchdog_alerts_once_after_consecutive_failures(run_probes, send):
    cache.delete(STATE_KEY)

    first = run_production_watchdog()
    second = run_production_watchdog()
    third = run_production_watchdog()

    assert first["status"] == "failing"
    assert second["status"] == "alerted"
    assert third["status"] == "failing"
    assert send.call_count == 1


@pytest.mark.django_db
@override_settings(
    PRODUCTION_WATCHDOG_ENABLED=True,
    PRODUCTION_WATCHDOG_BASE_URL="https://mudaroba.example",
    PRODUCTION_WATCHDOG_INTERVAL_SECONDS=300,
    PRODUCTION_WATCHDOG_FAILURE_THRESHOLD=1,
    PRODUCTION_WATCHDOG_REPEAT_SECONDS=3600,
    PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS=10,
)
@patch("apps.monitoring.tasks.send_admin_telegram_notification", return_value=True)
@patch(
    "apps.monitoring.tasks.run_public_probes",
    side_effect=[_failing_results(), _healthy_results(), _healthy_results()],
)
def test_watchdog_sends_one_recovery_and_resets_incident(run_probes, send):
    cache.delete(STATE_KEY)

    assert run_production_watchdog()["status"] == "alerted"
    assert run_production_watchdog()["status"] == "recovered"
    assert run_production_watchdog()["status"] == "healthy"
    assert send.call_count == 2


@override_settings(
    PRODUCTION_WATCHDOG_ENABLED=True,
    PRODUCTION_WATCHDOG_BASE_URL="https://mudaroba.example",
    PRODUCTION_WATCHDOG_INTERVAL_SECONDS=300,
    PRODUCTION_WATCHDOG_FAILURE_THRESHOLD=2,
    PRODUCTION_WATCHDOG_REPEAT_SECONDS=3600,
    PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS=10,
)
@patch("apps.monitoring.tasks.cache.set")
@patch("apps.monitoring.tasks.cache.get", side_effect=RuntimeError("cache unavailable"))
@patch("apps.monitoring.tasks.cache.add", side_effect=RuntimeError("cache unavailable"))
@patch("apps.monitoring.tasks.send_admin_telegram_notification", return_value=True)
@patch("apps.monitoring.tasks.run_public_probes", return_value=_failing_results())
def test_cache_failure_does_not_suppress_readiness_alert(
    run_probes,
    send,
    cache_add,
    cache_get,
    cache_set,
):
    result = run_production_watchdog()

    assert result["status"] == "alerted"
    assert result["consecutive_failures"] == 2
    send.assert_called_once()


@override_settings(TELEGRAM_BOT_TOKEN="secret-token", TELEGRAM_CHAT_ID="123")
def test_telegram_request_failure_never_logs_token(caplog):
    post = Mock(side_effect=requests.RequestException("https://api.telegram.org/botsecret-token"))

    assert send_admin_telegram_notification("alert", request_post=post) is False
    assert "secret-token" not in caplog.text


def test_watchdog_schedule_uses_serviced_default_queue(settings):
    entry = settings.CELERY_BEAT_SCHEDULE["monitoring-production-watchdog"]

    assert entry["task"] == "apps.monitoring.tasks.run_production_watchdog"
    assert entry["schedule"] == 300
    assert settings.CELERY_TASK_ROUTES["apps.monitoring.tasks.*"] == {"queue": "celery"}
