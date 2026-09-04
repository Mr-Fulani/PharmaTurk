from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import Error, register


@register()
def production_watchdog_configuration_check(app_configs, **kwargs):
    if not getattr(settings, "PRODUCTION_WATCHDOG_ENABLED", False):
        return []

    errors = []
    base_url = getattr(settings, "PRODUCTION_WATCHDOG_BASE_URL", "")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_BASE_URL must be an HTTPS origin without a path.",
                id="monitoring.E001",
            )
        )
    if not getattr(settings, "TELEGRAM_BOT_TOKEN", ""):
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_ENABLED requires TELEGRAM_BOT_TOKEN.",
                id="monitoring.E002",
            )
        )
    if not getattr(settings, "TELEGRAM_CHAT_ID", ""):
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_ENABLED requires TELEGRAM_CHAT_ID.",
                id="monitoring.E003",
            )
        )
    interval = settings.PRODUCTION_WATCHDOG_INTERVAL_SECONDS
    threshold = settings.PRODUCTION_WATCHDOG_FAILURE_THRESHOLD
    repeat_seconds = settings.PRODUCTION_WATCHDOG_REPEAT_SECONDS
    timeout_seconds = settings.PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS
    if not 60 <= interval <= 3600:
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_INTERVAL_SECONDS must be between 60 and 3600.",
                id="monitoring.E004",
            )
        )
    if not 1 <= threshold <= 12:
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_FAILURE_THRESHOLD must be between 1 and 12.",
                id="monitoring.E005",
            )
        )
    if repeat_seconds < interval:
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_REPEAT_SECONDS must not be shorter than the interval.",
                id="monitoring.E006",
            )
        )
    if not 1 <= timeout_seconds <= 10:
        errors.append(
            Error(
                "PRODUCTION_WATCHDOG_REQUEST_TIMEOUT_SECONDS must be between 1 and 10.",
                id="monitoring.E007",
            )
        )
    return errors
