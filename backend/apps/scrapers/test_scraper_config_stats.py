"""Статистика ScraperConfig после прогона: не откатывает правки админа, снимает «Ошибку»."""

import pytest
from django.utils import timezone

from apps.catalog.models import Category
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService


def _config(**overrides):
    category, _ = Category.objects.get_or_create(slug="stats-test", defaults={"name": "Stats test"})
    payload = {
        "name": "stats-cfg",
        "default_category": category,
        "parser_class": "zara",
        "base_url": "https://www.zara.com/tr/",
        "status": "error",
        "last_error_at": timezone.now(),
        "last_error_message": "HTTP 403 от 15.07",
    }
    payload.update(overrides)
    return ScraperConfig.objects.create(**payload)


def _session(config, **overrides):
    payload = {"scraper_config": config, "status": "completed", "products_found": 4}
    payload.update(overrides)
    return ScrapingSession.objects.create(**payload)


@pytest.mark.django_db
def test_success_clears_old_error_and_reactivates_config():
    config = _config()

    ScraperIntegrationService()._update_scraper_stats(config, _session(config), success=True)

    config.refresh_from_db()
    assert config.status == "active"
    assert config.last_error_message == ""
    assert config.last_error_at is None
    assert (config.total_runs, config.successful_runs, config.total_products_scraped) == (1, 1, 4)


@pytest.mark.django_db
def test_run_end_keeps_admin_changes_made_during_the_run():
    config = _config(status="active", use_proxy=False, is_enabled=True)
    stale = ScraperConfig.objects.get(pk=config.pk)  # объект, загруженный при старте задачи
    ScraperConfig.objects.filter(pk=config.pk).update(
        use_proxy=True, is_enabled=False, cookies={"sessionid": "x"}, total_runs=5,
    )

    ScraperIntegrationService()._update_scraper_stats(stale, _session(config), success=True)

    config.refresh_from_db()
    assert (config.use_proxy, config.is_enabled, config.cookies) == (True, False, {"sessionid": "x"})
    assert config.total_runs == 6
    assert stale.total_runs == 6


@pytest.mark.django_db
def test_success_does_not_override_manual_maintenance_status():
    config = _config(status="maintenance")

    ScraperIntegrationService()._update_scraper_stats(config, _session(config), success=True)

    config.refresh_from_db()
    assert config.status == "maintenance"


@pytest.mark.django_db
def test_failure_records_error():
    config = _config(status="active", last_error_message="", last_error_at=None)
    session = _session(config, status="failed", error_message="timed out")

    ScraperIntegrationService()._update_scraper_stats(config, session, success=False)

    config.refresh_from_db()
    assert config.status == "error"
    assert config.last_error_message == "timed out"
    assert config.last_error_at is not None
