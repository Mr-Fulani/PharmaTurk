import pytest
from django.core.exceptions import ImproperlyConfigured

from config.security import (
    validate_production_settings,
    validate_database_url,
    validate_redis_separation,
    validate_telegram_webhook_settings,
)


@pytest.mark.parametrize("secret", ["", "please-change-me", "short-secret"])
def test_production_rejects_missing_placeholder_or_short_secret(secret):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        validate_production_settings(
            debug=False,
            secret_key=secret,
            allowed_hosts=["mudaroba.com"],
        )


@pytest.mark.parametrize("hosts", [[], [""], ["  "], ["*"], ["mudaroba.com", ""]])
def test_production_rejects_implicit_allowed_hosts(hosts):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_ALLOWED_HOSTS"):
        validate_production_settings(
            debug=False,
            secret_key="a-secure-ci-only-key-that-is-longer-than-32-characters",
            allowed_hosts=hosts,
        )


def test_explicit_production_settings_are_accepted():
    validate_production_settings(
        debug=False,
        secret_key="a-secure-ci-only-key-that-is-longer-than-32-characters",
        allowed_hosts=["mudaroba.com", "www.mudaroba.com"],
    )


def test_production_rejects_crypto_dummy_mode():
    with pytest.raises(ImproperlyConfigured, match="CRYPTO_DUMMY_MODE"):
        validate_production_settings(
            debug=False,
            secret_key="a-secure-ci-only-key-that-is-longer-than-32-characters",
            allowed_hosts=["mudaroba.com"],
            crypto_dummy_mode=True,
        )


def test_development_can_use_local_placeholders():
    validate_production_settings(
        debug=True,
        secret_key="please-change-me",
        allowed_hosts=["*"],
        crypto_dummy_mode=True,
    )


@pytest.mark.parametrize(
    "database_url",
    [
        "postgres://pharmaturk:pharmaturk@postgres:5432/pharmaturk",
        "postgres://mudaroba:mudaroba@postgres:5432/mudaroba",
        "postgres://pharmaturk:CHANGE_ME@postgres:5432/pharmaturk",
        "postgres://app:x@postgres:5432/pharmaturk",
        "postgres://user@postgres:5432/database",
        "sqlite:///database.sqlite3",
        "not-a-url",
    ],
)
def test_production_rejects_incomplete_or_placeholder_database_url(database_url):
    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL"):
        validate_database_url(debug=False, database_url=database_url)


def test_production_accepts_explicit_postgres_credentials():
    validate_database_url(
        debug=False,
        database_url="postgresql://app:a-long-db-only-secret@postgres:5432/mudaroba",
    )


def test_production_telegram_bot_requires_strong_webhook_secret():
    with pytest.raises(ImproperlyConfigured, match="TELEGRAM_WEBHOOK_SECRET"):
        validate_telegram_webhook_settings(
            debug=False,
            bot_token="123:bot-token",
            webhook_secret="change-me",
        )


def test_disabled_or_development_telegram_does_not_require_secret():
    validate_telegram_webhook_settings(
        debug=False,
        bot_token="",
        webhook_secret="",
    )
    validate_telegram_webhook_settings(
        debug=True,
        bot_token="123:bot-token",
        webhook_secret="",
    )


def test_production_redis_roles_must_be_separate():
    with pytest.raises(ImproperlyConfigured, match="three distinct Redis"):
        validate_redis_separation(
            debug=False,
            broker_url="redis://redis:6379/0",
            cache_url="redis://redis/0",
            result_url="redis://redis:6379/2",
        )


def test_production_redis_roles_accept_distinct_databases():
    validate_redis_separation(
        debug=False,
        broker_url="redis://redis:6379/0",
        cache_url="redis://redis:6379/1",
        result_url="redis://redis:6379/2",
    )


def test_production_redis_roles_do_not_treat_credentials_as_separate_targets():
    with pytest.raises(ImproperlyConfigured, match="three distinct Redis"):
        validate_redis_separation(
            debug=False,
            broker_url="redis://broker-user:one@redis:6379/0",
            cache_url="redis://cache-user:two@redis:6379/0",
            result_url="redis://result-user:three@redis:6379/0",
        )


@pytest.mark.parametrize(
    "invalid_url",
    ["not-a-url", "http://redis:6379/1", "redis:///1", "redis://redis/cache"],
)
def test_production_rejects_invalid_redis_urls(invalid_url):
    with pytest.raises(ImproperlyConfigured, match="Redis connection URLs are invalid"):
        validate_redis_separation(
            debug=False,
            broker_url="redis://redis:6379/0",
            cache_url=invalid_url,
            result_url="redis://redis:6379/2",
        )
