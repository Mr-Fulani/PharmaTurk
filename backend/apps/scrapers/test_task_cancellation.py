import pytest

from apps.catalog.models import Category
from apps.scrapers.models import ScraperConfig, ScrapingSession, SiteScraperTask
from apps.scrapers.services import ScraperIntegrationService, ScraperTaskCancelled
from apps.scrapers.tasks import revoke_site_scraper_task, run_scraper_task


def _build_scraper_task(status: str = "running") -> SiteScraperTask:
    category = Category.objects.create(name=f"Test {status}", slug=f"test-{status}")
    config = ScraperConfig.objects.create(
        name=f"parser-{status}",
        parser_class="ilacfiyati",
        base_url="https://example.com",
        default_category=category,
    )
    return SiteScraperTask.objects.create(
        scraper_config=config,
        start_url="https://example.com/category",
        max_pages=1,
        max_products=10,
        max_images_per_product=3,
        status=status,
    )


@pytest.mark.django_db
def test_ensure_site_task_not_cancelled_raises_for_cancelled_task():
    task = _build_scraper_task(status="cancelled")

    with pytest.raises(ScraperTaskCancelled):
        ScraperIntegrationService._ensure_site_task_not_cancelled(task.id)


@pytest.mark.django_db
def test_run_scraper_task_returns_cancelled_before_start(monkeypatch):
    task = _build_scraper_task(status="cancelled")
    called = False

    def fake_run_scraper(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("run_scraper should not be called for cancelled task")

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", fake_run_scraper)

    result = run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
    )

    assert result["status"] == "cancelled"
    assert called is False


@pytest.mark.django_db
def test_run_scraper_task_does_not_chain_after_cancel(monkeypatch):
    task = _build_scraper_task(status="running")

    session = ScrapingSession.objects.create(
        scraper_config=task.scraper_config,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        status="cancelled",
    )
    session.products_found = 5
    session.products_created = 2
    session.products_updated = 1
    session.products_skipped = 0
    session.errors_count = 0
    session.pages_processed = 1
    session.save()

    def fake_run_scraper(*args, **kwargs):
        SiteScraperTask.objects.filter(id=task.id).update(status="cancelled")
        return session

    def fail_apply_async(*args, **kwargs):
        raise AssertionError("next chunk must not be queued after cancellation")

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(run_scraper_task, "apply_async", fail_apply_async)

    result = run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
    )

    assert result["status"] == "cancelled"


def test_revoke_site_scraper_task_uses_celery_control(monkeypatch):
    calls = []

    class DummyControl:
        def revoke(self, task_id, terminate, signal):
            calls.append((task_id, terminate, signal))

    monkeypatch.setattr("apps.scrapers.tasks.current_app.control", DummyControl())

    task = type("Task", (), {"task_id": "celery-123"})()
    revoked = revoke_site_scraper_task(task, terminate=True)

    assert revoked is True
    assert calls == [("celery-123", True, "SIGTERM")]
