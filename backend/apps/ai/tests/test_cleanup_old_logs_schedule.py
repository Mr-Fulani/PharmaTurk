"""Чистка AI-логов — по crontab: интервал в 7 дней сбрасывался каждым деплоем."""

from celery.schedules import crontab
from django.conf import settings


def test_ai_logs_cleanup_runs_weekly_by_crontab():
    entry = settings.CELERY_BEAT_SCHEDULE["ai-cleanup-old-logs"]

    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].day_of_week == {0}  # воскресенье
    assert entry["schedule"].hour == {4}
    assert entry["schedule"].minute == {40}
    assert entry["kwargs"] == {"days": 30}
