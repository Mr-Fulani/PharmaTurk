"""Валютные задачи — только crontab: интервалы beat сбрасывались каждым деплоем."""

from celery.schedules import crontab
from django.conf import settings


def test_rates_update_every_four_hours_by_crontab():
    entry = settings.CELERY_BEAT_SCHEDULE["currency-update-rates"]

    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].hour == {0, 4, 8, 12, 16, 20}
    assert entry["schedule"].minute == {5}


def test_prices_recalculated_daily_after_night_window():
    """Раз в 24 ч по интервалу не срабатывало: деплоев бывает несколько в сутки."""
    schedule = settings.CELERY_BEAT_SCHEDULE
    entry = schedule["currency-update-prices"]

    assert isinstance(entry["schedule"], crontab)
    assert entry["schedule"].hour == {5}
    assert entry["schedule"].minute == {0}
    assert entry["kwargs"] == {"batch_size": 200}

    # Ни одна другая ночная задача с конкретным часом не стартует в 05:xx.
    all_hours = set(range(24))
    for name, other in schedule.items():
        other_schedule = other["schedule"]
        if name == "currency-update-prices" or not isinstance(other_schedule, crontab):
            continue
        if other_schedule.hour != all_hours:
            assert 5 not in other_schedule.hour, name
