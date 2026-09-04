from __future__ import annotations

import logging
import time

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from .watchdog import (
    ProbeResult,
    format_failure_notification,
    format_recovery_notification,
    run_public_probes,
    send_admin_telegram_notification,
)

logger = logging.getLogger(__name__)

STATE_KEY = "monitoring:production-watchdog:v1:state"
LOCK_KEY = "monitoring:production-watchdog:v1:lock"


def _load_state() -> tuple[dict, bool]:
    try:
        raw = cache.get(STATE_KEY)
    except Exception:  # noqa: BLE001 - watchdog must still alert on Redis trouble
        logger.exception("production_watchdog_state_read_failed")
        return {"active": False, "failures": 0, "last_alert_at": 0.0}, False
    if not isinstance(raw, dict):
        raw = {}
    return {
        "active": raw.get("active") is True,
        "failures": max(0, int(raw.get("failures", 0) or 0)),
        "last_alert_at": max(0.0, float(raw.get("last_alert_at", 0.0) or 0.0)),
    }, True


def _store_state(state: dict, *, timeout: int) -> None:
    try:
        cache.set(STATE_KEY, state, timeout=timeout)
    except Exception:  # noqa: BLE001 - alert delivery is more important than state
        logger.exception("production_watchdog_state_write_failed")


def _log_probe(result: ProbeResult) -> None:
    log = logger.info if result.ok else logger.warning
    log(
        "production_watchdog_probe",
        extra={
            "watchdog_probe": result.name,
            "watchdog_ok": result.ok,
            "watchdog_latency_ms": result.latency_ms,
            "watchdog_status_code": result.status_code,
            "watchdog_reason": result.reason,
        },
    )


@shared_task(name="apps.monitoring.tasks.run_production_watchdog", ignore_result=True)
def run_production_watchdog() -> dict:
    if not getattr(settings, "PRODUCTION_WATCHDOG_ENABLED", False):
        return {"status": "disabled"}

    interval = max(60, int(settings.PRODUCTION_WATCHDOG_INTERVAL_SECONDS))
    threshold = max(1, int(settings.PRODUCTION_WATCHDOG_FAILURE_THRESHOLD))
    repeat_seconds = max(interval, int(settings.PRODUCTION_WATCHDOG_REPEAT_SECONDS))
    timeout_seconds = max(1, int(settings.PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS))

    lock_acquired: bool | None = None
    try:
        try:
            lock_acquired = cache.add(LOCK_KEY, "1", timeout=max(30, interval - 5))
        except Exception:  # noqa: BLE001 - cache failure is itself observable via readiness
            logger.exception("production_watchdog_lock_failed")
        if lock_acquired is False:
            return {"status": "locked"}

        state, state_available = _load_state()
        results = run_public_probes(
            settings.PRODUCTION_WATCHDOG_BASE_URL,
            timeout_seconds=timeout_seconds,
        )
        for result in results:
            _log_probe(result)

        failed = [item for item in results if not item.ok]
        now = time.time()
        state_timeout = max(86_400, repeat_seconds * 2)

        if failed:
            state["failures"] += 1
            # If Redis/cache state is unavailable, do not suppress the only alert
            # that can explain readiness failure.
            effective_failures = state["failures"] if state_available else threshold
            due = effective_failures >= threshold and (
                not state["active"]
                or now - state["last_alert_at"] >= repeat_seconds
            )
            delivered = False
            if due:
                delivered = send_admin_telegram_notification(
                    format_failure_notification(results, effective_failures)
                )
                if delivered:
                    state["active"] = True
                    state["last_alert_at"] = now
            _store_state(state, timeout=state_timeout)
            return {
                "status": "alerted" if delivered else "failing",
                "failed_checks": [item.name for item in failed],
                "consecutive_failures": effective_failures,
            }

        state["failures"] = 0
        if state["active"]:
            delivered = send_admin_telegram_notification(
                format_recovery_notification(results)
            )
            if delivered:
                state["active"] = False
                state["last_alert_at"] = 0.0
            _store_state(state, timeout=state_timeout)
            return {"status": "recovered" if delivered else "recovery_pending"}

        _store_state(state, timeout=state_timeout)
        return {"status": "healthy"}
    finally:
        if lock_acquired:
            try:
                cache.delete(LOCK_KEY)
            except Exception:  # noqa: BLE001
                logger.exception("production_watchdog_unlock_failed")
