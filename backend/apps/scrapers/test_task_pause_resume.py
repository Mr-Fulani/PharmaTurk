import pytest

from apps.catalog.models import Category
from apps.scrapers.models import ScraperConfig, ScrapingSession, SiteScraperTask
from apps.scrapers.services import ScraperIntegrationService, ScraperTaskPaused
from apps.scrapers.tasks import run_scraper_task


def _build_task(status: str = "running", **extra) -> SiteScraperTask:
    category = Category.objects.create(name=f"T {status}", slug=f"t-{status}")
    config = ScraperConfig.objects.create(
        name=f"p-{status}",
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
        **extra,
    )


@pytest.mark.django_db
def test_ensure_raises_paused_for_paused_task():
    task = _build_task(status="paused")
    with pytest.raises(ScraperTaskPaused):
        ScraperIntegrationService._ensure_site_task_not_cancelled(task.id)


@pytest.mark.django_db
def test_run_returns_paused_before_start_and_records_resume_page(monkeypatch):
    task = _build_task(status="paused")

    def must_not_run(*args, **kwargs):
        raise AssertionError("run_scraper не должен вызываться у paused-задачи")

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", must_not_run)

    result = run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
        start_page=4,
    )

    assert result["status"] == "paused"
    task.refresh_from_db()
    assert task.resume_page == 4


@pytest.mark.django_db
def test_run_records_resume_page_at_chunk_start(monkeypatch):
    task = _build_task(status="running")
    session = ScrapingSession.objects.create(
        scraper_config=task.scraper_config,
        start_url=task.start_url,
        max_pages=1,
        max_products=10,
        max_images_per_product=3,
        status="completed",
    )
    session.products_found = 0
    session.save()

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", lambda *a, **k: session)
    monkeypatch.setattr(run_scraper_task, "apply_async", lambda *a, **k: None)

    run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
        start_page=3,
    )

    task.refresh_from_db()
    assert task.resume_page == 3


@pytest.mark.django_db
def test_run_finalizes_paused_at_boundary_without_chaining(monkeypatch):
    task = _build_task(status="running")
    session = ScrapingSession.objects.create(
        scraper_config=task.scraper_config,
        start_url=task.start_url,
        max_pages=1,
        max_products=10,
        max_images_per_product=3,
        status="cancelled",
    )
    session.products_found = 7
    session.products_created = 3
    session.products_updated = 1
    session.products_skipped = 3
    session.save()

    def fake_run_scraper(*args, **kwargs):
        SiteScraperTask.objects.filter(id=task.id).update(status="paused")
        return session

    def fail_chain(*args, **kwargs):
        raise AssertionError("paused-задача не должна продолжать цепочку")

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", fake_run_scraper)
    monkeypatch.setattr(run_scraper_task, "apply_async", fail_chain)

    result = run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
    )

    assert result["status"] == "paused"
    task.refresh_from_db()
    assert task.status == "paused"
    assert task.products_found == 7
    assert task.products_created == 3


@pytest.mark.django_db
def test_admin_resume_passes_start_page_and_accumulated_totals(monkeypatch):
    from django.contrib.admin.sites import site as admin_site
    from apps.scrapers.admin import SiteScraperTaskAdmin

    task = _build_task(status="paused", resume_page=5)
    task.products_found = 40
    task.products_created = 10
    task.products_updated = 2
    task.products_skipped = 28
    task.save()

    captured = {}

    class _Result:
        id = "celery-resume"

    def fake_delay(config_id, **kwargs):
        captured["config_id"] = config_id
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr("apps.scrapers.admin.run_scraper_task.delay", fake_delay)

    admin = SiteScraperTaskAdmin(SiteScraperTask, admin_site)
    admin._enqueue_site_task(task, reset_stats=False, resume=True)

    assert captured["config_id"] == task.scraper_config_id
    assert captured["start_page"] == 5
    assert captured["total_scraped"] == 40
    assert captured["total_created"] == 10
    assert captured["total_updated"] == 2
    assert captured["total_skipped"] == 28

    task.refresh_from_db()
    assert task.status == "running"
    # счётчики НЕ сброшены при возобновлении
    assert task.products_found == 40


@pytest.mark.django_db
def test_admin_rerun_resets_resume_page(monkeypatch):
    from django.contrib.admin.sites import site as admin_site
    from apps.scrapers.admin import SiteScraperTaskAdmin

    task = _build_task(status="paused", resume_page=9)
    task.products_found = 50
    task.save()

    class _Result:
        id = "celery-rerun"

    monkeypatch.setattr(
        "apps.scrapers.admin.run_scraper_task.delay",
        lambda *a, **k: _Result(),
    )

    admin = SiteScraperTaskAdmin(SiteScraperTask, admin_site)
    admin._enqueue_site_task(task, reset_stats=True)

    task.refresh_from_db()
    assert task.resume_page == 1
    assert task.products_found == 0
