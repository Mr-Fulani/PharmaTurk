"""Fail-fast validation for settings that must never use production defaults."""
import re
from urllib.parse import unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured


UNSAFE_SECRET_KEYS = {
    "",
    "please-change-me",
    "please_change_me",
    "change-me",
    "change_me",
    "changeme",
}
UNSAFE_DATABASE_PASSWORDS = UNSAFE_SECRET_KEYS | {
    "mudaroba",
    "pharmaturk",
    "postgres",
    "password",
}


def validate_production_settings(
    *,
    debug: bool,
    secret_key: str,
    allowed_hosts: list[str],
    crypto_dummy_mode: bool = False,
) -> None:
    if debug:
        return
    if secret_key.strip().lower() in UNSAFE_SECRET_KEYS or len(secret_key) < 32:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be a non-placeholder value of at least 32 characters "
            "when DJANGO_DEBUG=0."
        )
    normalized_hosts = {str(host).strip() for host in allowed_hosts}
    if not normalized_hosts or "" in normalized_hosts or "*" in normalized_hosts:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must explicitly list production hosts when DJANGO_DEBUG=0."
        )
    if crypto_dummy_mode:
        raise ImproperlyConfigured(
            "CRYPTO_DUMMY_MODE is development-only and must be disabled when DJANGO_DEBUG=0."
        )


def validate_telegram_webhook_settings(
    *,
    debug: bool,
    bot_token: str,
    webhook_secret: str,
) -> None:
    """Require Telegram's secret-token header whenever the bot is enabled."""
    if debug or not bot_token:
        return
    normalized = webhook_secret.strip().lower()
    if normalized in UNSAFE_SECRET_KEYS or len(webhook_secret) < 32:
        raise ImproperlyConfigured(
            "TELEGRAM_WEBHOOK_SECRET must be a non-placeholder value of at least "
            "32 characters when Telegram is enabled in production."
        )


def validate_database_url(*, debug: bool, database_url: str) -> None:
    """Reject missing/default PostgreSQL credentials before production boot."""
    if debug:
        return
    try:
        parsed = urlsplit(database_url)
        password = unquote(parsed.password or "").strip().lower()
        database = parsed.path.strip("/")
        if (
            parsed.scheme.lower() not in {"postgres", "postgresql"}
            or not parsed.hostname
            or not parsed.username
            or not database
            or len(password) < 16
            or password in UNSAFE_DATABASE_PASSWORDS
        ):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "DATABASE_URL must contain a PostgreSQL host, database, user and "
            "non-placeholder password of at least 16 characters when DJANGO_DEBUG=0."
        ) from exc


def validate_redis_separation(
    *,
    debug: bool,
    broker_url: str,
    cache_url: str,
    result_url: str,
) -> None:
    """Keep cache eviction and Celery queue/result data in distinct targets."""
    if debug:
        return

    def target(value: str):
        try:
            parsed = urlsplit(value)
            database = parsed.path.rstrip("/") or "/0"
            if (
                parsed.scheme.lower() not in {"redis", "rediss"}
                or not parsed.hostname
                or not re.fullmatch(r"/\d+", database)
            ):
                raise ValueError
            return (
                parsed.scheme.lower(),
                (parsed.hostname or "").lower(),
                parsed.port or 6379,
                database,
            )
        except (TypeError, ValueError) as exc:
            raise ImproperlyConfigured("Redis connection URLs are invalid.") from exc

    targets = {target(broker_url), target(cache_url), target(result_url)}
    if len(targets) != 3:
        raise ImproperlyConfigured(
            "REDIS_URL, REDIS_CACHE_URL and CELERY_RESULT_BACKEND_URL must use "
            "three distinct Redis databases/targets when DJANGO_DEBUG=0."
        )
