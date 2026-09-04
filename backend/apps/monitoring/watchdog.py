from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    latency_ms: int
    status_code: int | None = None
    reason: str = ""


PROBE_PATHS = (
    ("homepage", "/"),
    ("liveness", "/api/live/"),
    ("readiness", "/api/health/"),
)


def normalize_https_origin(value: str) -> str:
    origin = (value or "").strip().rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("watchdog base URL must be an HTTPS origin")
    return origin


def _payload_is_healthy(name: str, response: requests.Response) -> bool:
    if name == "homepage":
        return True
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    if name == "liveness":
        return payload == {"status": "ok"}
    return (
        payload.get("status") == "ok"
        and payload.get("db") is True
        and payload.get("cache") is True
    )


def run_public_probes(
    base_url: str,
    *,
    timeout_seconds: int,
    request_get: Callable | None = None,
) -> list[ProbeResult]:
    origin = normalize_https_origin(base_url)
    get = request_get or requests.get
    results: list[ProbeResult] = []

    for name, path in PROBE_PATHS:
        started = time.monotonic()
        status_code = None
        reason = ""
        try:
            response = get(
                f"{origin}{path}",
                allow_redirects=False,
                headers={"User-Agent": "MudarobaProductionWatchdog/1.0"},
                timeout=(3, timeout_seconds),
            )
            status_code = response.status_code
            if response.status_code != 200:
                ok = False
                reason = f"http_{response.status_code}"
            else:
                ok = _payload_is_healthy(name, response)
                if not ok:
                    reason = "invalid_health_contract"
        except requests.Timeout:
            ok = False
            reason = "timeout"
        except requests.ConnectionError:
            ok = False
            reason = "connection_error"
        except requests.RequestException:
            ok = False
            reason = "request_error"

        latency_ms = max(0, round((time.monotonic() - started) * 1000))
        results.append(
            ProbeResult(
                name=name,
                ok=ok,
                latency_ms=latency_ms,
                status_code=status_code,
                reason=reason,
            )
        )

    return results


def format_failure_notification(results: list[ProbeResult], failure_count: int) -> str:
    lines = [
        "🚨 Mudaroba production недоступен",
        f"Последовательных неуспешных проверок: {failure_count}",
        "",
    ]
    for result in results:
        if not result.ok:
            lines.append(
                f"• {result.name}: {result.reason or 'failed'} "
                f"({result.latency_ms} ms)"
            )
    lines.extend(
        [
            "",
            "Runbook: docs/PRODUCTION_MONITORING_RUNBOOK.md",
        ]
    )
    return "\n".join(lines)


def format_recovery_notification(results: list[ProbeResult]) -> str:
    latency = ", ".join(f"{item.name}={item.latency_ms}ms" for item in results)
    return (
        "✅ Mudaroba production восстановлен\n"
        f"Все synthetic/readiness проверки успешны: {latency}"
    )


def send_admin_telegram_notification(
    text: str,
    *,
    request_post: Callable | None = None,
) -> bool:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""
    if not token or not chat_id:
        logger.error("production_watchdog_receiver_not_configured")
        return False

    post = request_post or requests.post
    try:
        response = post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=(3, 10),
        )
    except requests.RequestException:
        # Never log the exception: requests may include the tokenized URL.
        logger.warning("production_watchdog_telegram_request_failed")
        return False

    if not response.ok:
        logger.warning(
            "production_watchdog_telegram_http_failed",
            extra={"telegram_status_code": response.status_code},
        )
        return False
    try:
        delivered = response.json().get("ok") is True
    except ValueError:
        delivered = False
    if not delivered:
        logger.warning("production_watchdog_telegram_invalid_response")
    return delivered
