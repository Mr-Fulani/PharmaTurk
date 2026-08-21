from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import site as admin_site
from django.core.cache import cache

from apps.catalog.models import Category
from apps.scrapers.admin import InstagramScraperTaskAdmin
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import (
    InstagramScraperTask,
    ScraperConfig,
    ScrapingSession,
)
from apps.scrapers.services import (
    ScraperIntegrationService,
    ScraperTaskCancelled,
    ScraperTaskPaused,
)
from apps.scrapers.tasks import (
    revoke_instagram_scraper_task,
    run_instagram_scraper_task,
)


def _category(suffix: str = "instagram") -> Category:
    return Category.objects.create(
        name=f"Instagram {suffix}",
        slug=f"instagram-{suffix}",
    )


def _config(category: Category) -> ScraperConfig:
    return ScraperConfig.objects.create(
        name="instagram",
        parser_class="instagram",
        base_url="https://www.instagram.com",
        default_category=category,
    )


def _task(category: Category, status: str = "running", **kwargs) -> InstagramScraperTask:
    return InstagramScraperTask.objects.create(
        instagram_username="example.shop",
        target_category=category,
        max_posts=10,
        status=status,
        **kwargs,
    )


@pytest.mark.django_db
def test_instagram_control_check_raises_for_pause_and_cancel():
    category = _category("control")
    task = _task(category, status="paused")

    with pytest.raises(ScraperTaskPaused):
        ScraperIntegrationService._ensure_instagram_task_active(task.id)

    task.status = "cancelled"
    task.save(update_fields=["status"])
    with pytest.raises(ScraperTaskCancelled):
        ScraperIntegrationService._ensure_instagram_task_active(task.id)


@pytest.mark.django_db
def test_instagram_celery_task_completes_and_writes_final_log(monkeypatch):
    category = _category("complete")
    config = _config(category)
    task = _task(category)
    session = ScrapingSession.objects.create(
        scraper_config=config,
        start_url="https://www.instagram.com/example.shop/",
        max_pages=10,
        max_products=10,
        status="completed",
        products_found=2,
        products_created=1,
        products_updated=1,
        pages_processed=2,
    )
    monkeypatch.setattr(
        ScraperIntegrationService,
        "run_scraper",
        lambda *args, **kwargs: session,
    )

    result = run_instagram_scraper_task.run(task.id)

    task.refresh_from_db()
    assert result["status"] == "success"
    assert task.status == "completed"
    assert task.session_id == session.id
    assert task.products_found == 2
    assert task.posts_processed == 2
    assert "--- Итог ---" in task.log_output
    assert "Товаров найдено: 2" in task.log_output


@pytest.mark.django_db
def test_instagram_task_returns_before_start_when_paused(monkeypatch):
    category = _category("prepaused")
    task = _task(category, status="paused")
    called = False

    def must_not_run(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", must_not_run)

    result = run_instagram_scraper_task.run(task.id)

    assert result["status"] == "paused"
    assert called is False


@pytest.mark.django_db
def test_instagram_live_progress_saves_each_product_and_log(monkeypatch):
    cache.clear()
    category = _category("progress")
    config = _config(category)
    task = _task(category)
    session = ScrapingSession.objects.create(
        scraper_config=config,
        start_url="https://www.instagram.com/example.shop/",
        max_pages=10,
        max_products=10,
        status="running",
    )
    product = ScrapedProduct(
        name="Instagram product",
        description="Достаточно длинное описание",
        url="https://www.instagram.com/p/POST1/",
        images=["https://cdn.example/POST1.jpg"],
        external_id="POST1",
        source="instagram",
    )

    class Parser:
        max_products = 10

        def configure_task_callbacks(self, **callbacks):
            self.callbacks = callbacks

        def parse_product_list(self, *args, **kwargs):
            self.callbacks["control_callback"]()
            self.callbacks["product_callback"](product)
            self.callbacks["progress_callback"](1, 10, "POST1", True, "")
            return []

    service = ScraperIntegrationService()
    monkeypatch.setattr(
        service,
        "_process_scraped_products",
        lambda *args, **kwargs: {
            "found": 1,
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        },
    )

    _, results = service._run_parser_scraping(
        Parser(),
        session,
        session.start_url,
        instagram_task_id=task.id,
        instagram_run_token=str(task.run_token),
    )

    task.refresh_from_db()
    assert results == {
        "found": 1,
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert task.posts_processed == 1
    assert task.products_found == 1
    assert task.products_created == 1
    assert "POST1: товар создан" in task.log_output


@pytest.mark.django_db
def test_admin_enqueue_is_async_and_resume_preserves_counters(monkeypatch):
    category = _category("admin")
    task = _task(
        category,
        status="paused",
        posts_processed=3,
        products_found=2,
        products_created=2,
    )
    captured = {}

    def fake_delay(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="instagram-celery-1")

    monkeypatch.setattr(
        "apps.scrapers.admin.run_instagram_scraper_task.delay",
        fake_delay,
    )
    model_admin = InstagramScraperTaskAdmin(InstagramScraperTask, admin_site)

    model_admin._enqueue_instagram_task(task, reset_stats=False, resume=True)

    task.refresh_from_db()
    assert captured == {"instagram_task_id": task.id, "resume": True}
    assert task.status == "running"
    assert task.task_id == "instagram-celery-1"
    assert task.products_found == 2
    assert task.posts_processed == 3


def test_revoke_instagram_task_uses_celery_control(monkeypatch):
    calls = []

    class DummyControl:
        def revoke(self, task_id, terminate, signal):
            calls.append((task_id, terminate, signal))

    monkeypatch.setattr("apps.scrapers.tasks.current_app.control", DummyControl())
    task = SimpleNamespace(task_id="instagram-celery-2")

    assert revoke_instagram_scraper_task(task, terminate=True) is True
    assert calls == [("instagram-celery-2", True, "SIGTERM")]
