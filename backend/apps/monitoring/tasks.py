from __future__ import annotations

import logging
import time

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from . import db_backup, resources
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
BACKUP_LOCK_KEY = "monitoring:db-backup:v1:lock"
RESOURCES_STATE_KEY = "monitoring:server-resources:v1:state"


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


def _run_backup_job(stage: str, job) -> dict:
    """Бэкап и его проверка не идут одновременно; без кэша бэкап важнее блокировки."""
    if not getattr(settings, "DB_BACKUP_ENABLED", False):
        return {"status": "disabled"}
    try:
        lock_acquired = cache.add(BACKUP_LOCK_KEY, "1", timeout=2 * 60 * 60)
    except Exception:  # noqa: BLE001
        logger.exception("db_backup_lock_failed")
        lock_acquired = None
    if lock_acquired is False:
        return {"status": "locked"}
    try:
        return job()
    except Exception as exc:  # noqa: BLE001 - любой сбой бэкапа должен дойти до админа
        logger.exception("db_backup_failed", extra={"db_backup_stage": stage})
        error = str(exc)[:500] if isinstance(exc, db_backup.BackupError) else (
            f"{type(exc).__name__}: {str(exc)[:300]}"
        )
        send_admin_telegram_notification(
            f"🔴 Бэкап базы Mudaroba: {stage} — сбой\n{error}\nЧто делать: docs/DB_BACKUP.md"
        )
        return {"status": "failed", "error": error}
    finally:
        if lock_acquired:
            try:
                cache.delete(BACKUP_LOCK_KEY)
            except Exception:  # noqa: BLE001
                logger.exception("db_backup_unlock_failed")


def _backup_and_ping() -> dict:
    result = db_backup.create_backup()
    db_backup.ping_heartbeat()
    return result


def _check_backup() -> dict:
    result = db_backup.verify_latest_backup()
    restore = result.get("restore") or {}
    if restore.get("status") == "skipped":
        logger.warning("db_backup_restore_check_skipped", extra={"reason": restore["reason"]})
        send_admin_telegram_notification(
            f"⚠️ Бэкап базы Mudaroba: пробное восстановление пропущено — {restore['reason']}"
        )
    return result


@shared_task(name="apps.monitoring.tasks.run_database_backup", ignore_result=True)
def run_database_backup() -> dict:
    return _run_backup_job("ежедневная копия", _backup_and_ping)


@shared_task(name="apps.monitoring.tasks.check_database_backup", ignore_result=True)
def check_database_backup() -> dict:
    return _run_backup_job("еженедельная проверка", _check_backup)


@shared_task(name="apps.monitoring.tasks.check_server_resources", ignore_result=True)
def check_server_resources() -> dict:
    """Диск и Redis на пределе — в Telegram тем же каналом, что watchdog.

    Новая проблема — сразу, та же — не чаще SERVER_RESOURCES_REPEAT_SECONDS,
    после исправления всех — сообщение о восстановлении. Состояние в кэше; если
    кэш недоступен, алерт не подавляется.
    """
    if not getattr(settings, "SERVER_RESOURCES_MONITOR_ENABLED", False):
        return {"status": "disabled"}
    problems = {problem.key: problem for problem in resources.collect_problems()}
    try:
        state = cache.get(RESOURCES_STATE_KEY) or {}
    except Exception:  # noqa: BLE001 - Redis-кэш сам может быть причиной
        logger.exception("server_resources_state_read_failed")
        state = {}
    active = set(state.get("active") or ())
    now = time.time()
    status = "healthy"
    if problems:
        due = bool(set(problems) - active) or now - float(state.get("last_alert_at") or 0) >= int(
            settings.SERVER_RESOURCES_REPEAT_SECONDS
        )
        status = "problem"
        if due and send_admin_telegram_notification(resources.format_problems(list(problems.values()))):
            state["last_alert_at"] = now
            status = "alerted"
    elif active and send_admin_telegram_notification("✅ Mudaroba: диск и Redis снова в норме"):
        status = "recovered"
    elif active:
        problems = {key: None for key in active}  # восстановление не доставлено — повторим
    state["active"] = sorted(problems)
    try:
        cache.set(RESOURCES_STATE_KEY, state, timeout=7 * 86_400)
    except Exception:  # noqa: BLE001
        logger.exception("server_resources_state_write_failed")
    if status != "healthy":
        logger.warning("server_resources", extra={"server_resources_problems": sorted(problems)})
    return {"status": status, "problems": sorted(problems)}
