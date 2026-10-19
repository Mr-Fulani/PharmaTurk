"""Ретенция логов парсеров: пачками, по crontab, без потери свежих данных."""

from datetime import timedelta

import pytest
from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from apps.catalog.models import Category
from apps.scrapers.models import ScrapedProductLog, ScraperConfig, ScrapingSession
from apps.scrapers.tasks import cleanup_old_sessions


def _session(config, age_days):
    session = ScrapingSession.objects.create(scraper_config=config, status="completed")
    ScrapingSession.objects.filter(pk=session.pk).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    return session


def _log(session, age_days, n=1):
    for i in range(n):
        log = ScrapedProductLog.objects.create(
            session=session,
            external_id=f"ext-{session.pk}-{age_days}-{i}",
            external_url="https://e.com/p",
            product_name="Товар",
            action="created",
            scraped_data={"payload": "x" * 100},
        )
        ScrapedProductLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )


@pytest.mark.django_db
def test_deletes_only_rows_older_than_retention_in_batches():
    category = Category.objects.create(name="Тест", slug="cleanup-test")
    config = ScraperConfig.objects.create(
        name="cleanup-cfg", parser_class="lcw", base_url="https://e.com", default_category=category
    )
    old_session = _session(config, 40)
    fresh_session = _session(config, 5)
    _log(old_session, 40, n=5)
    # Свежий лог старой сессии уходит каскадом вместе с сессией.
    _log(old_session, 10)
    _log(fresh_session, 35, n=2)
    _log(fresh_session, 1, n=3)

    result = cleanup_old_sessions.run(days_to_keep=30, batch_size=2)

    assert result["status"] == "success"
    assert result["deleted_logs"] == 7
    assert result["deleted_sessions"] == 1
    assert list(ScrapingSession.objects.values_list("pk", flat=True)) == [fresh_session.pk]
    assert ScrapedProductLog.objects.count() == 3
    assert not ScrapedProductLog.objects.filter(
        created_at__lt=timezone.now() - timedelta(days=30)
    ).exists()


@pytest.mark.django_db
def test_nothing_to_delete_is_noop():
    result = cleanup_old_sessions.run(days_to_keep=30)

    assert result["deleted_logs"] == 0
    assert result["deleted_sessions"] == 0


@pytest.mark.parametrize("kwargs", [{"days_to_keep": 0}, {"batch_size": 0}, {"batch_size": 10_001}])
def test_rejects_unsafe_arguments(kwargs):
    with pytest.raises(ValueError):
        cleanup_old_sessions.run(**kwargs)


def test_cleanup_runs_nightly_by_crontab():
    """Интервал в 7 дней сбрасывался каждым деплоем (state beat в слое контейнера)."""
    entry = settings.CELERY_BEAT_SCHEDULE["cleanup-scraper-sessions"]

    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].hour == {4}
    assert entry["schedule"].minute == {20}
    assert entry["args"] == (30,)
