from config.settings import CELERY_BEAT_SCHEDULE


def test_source_offer_background_refresh_is_not_scheduled_or_registered():
    assert "catalog-refresh-source-offers" not in CELERY_BEAT_SCHEDULE
    assert all(
        entry.get("task") != "catalog.refresh_source_offers"
        for entry in CELERY_BEAT_SCHEDULE.values()
    )

    from apps.catalog import tasks

    assert not hasattr(tasks, "refresh_source_offers_task")
