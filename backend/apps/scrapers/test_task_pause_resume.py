import pytest

from apps.catalog.models import Category
from apps.scrapers.admin import SiteScraperTaskAdmin
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
def test_run_keeps_resume_page_at_chunk_start_while_chaining(monkeypatch):
    # Чанк нашёл товары и не достиг лимита → ставит следующий чанк в цепочку.
    # resume_page остаётся на странице текущего чанка (сброс в 1 — только при
    # полном завершении). Так при сбое воркера «Продолжить» возьмёт верную страницу.
    task = _build_task(status="running")
    task.start_url = "https://ilacfiyati.com/ilaclar"
    task.save(update_fields=["start_url"])
    session = ScrapingSession.objects.create(
        scraper_config=task.scraper_config,
        start_url=task.start_url,
        max_pages=1,
        max_products=10,
        max_images_per_product=3,
        status="completed",
    )
    session.products_found = 5
    session.save()

    class _Next:
        id = "celery-next"

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", lambda *a, **k: session)
    monkeypatch.setattr(run_scraper_task, "apply_async", lambda *a, **k: _Next())

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


@pytest.mark.django_db
def test_live_progress_is_saved_after_first_product(monkeypatch):
    task = _build_task(status="running")
    session = ScrapingSession.objects.create(
        scraper_config=task.scraper_config,
        start_url="https://example.com/category/items",
        max_pages=1,
        max_products=10,
        max_images_per_product=3,
        status="running",
    )

    class Parser:
        SUPPORTS_PAGE_CHUNKING = False

        def parse_product_list(self, *args, **kwargs):
            yield object()

    service = ScraperIntegrationService()
    monkeypatch.setattr(
        service,
        "_process_scraped_products",
        lambda *args, **kwargs: {"found": 1, "created": 1, "updated": 0, "skipped": 0, "errors": 0},
    )

    service._run_parser_scraping(
        Parser(),
        session,
        session.start_url,
        site_task_id=task.id,
    )

    session.refresh_from_db()
    task.refresh_from_db()
    assert session.products_found == 1
    assert task.products_found == 1
    assert task.products_created == 1
    assert task.session_id == session.id


def test_site_task_admin_list_displays_configured_subcategory():
    category_index = SiteScraperTaskAdmin.list_display.index("target_category")

    assert SiteScraperTaskAdmin.list_display[category_index + 1] == "target_subcategory_path"
    assert "target_subcategory" in SiteScraperTaskAdmin.list_select_related


def test_site_task_admin_displays_subcategory_hierarchy_below_root(db):
    root = Category.objects.create(name="Мебель", slug="furniture-admin-path")
    room = Category.objects.create(name="Спальня", slug="bedroom-admin-path", parent=root)
    leaf = Category.objects.create(name="Комоды", slug="dressers-admin-path", parent=room)
    task = SiteScraperTask(target_category=root, target_subcategory=leaf)

    assert SiteScraperTaskAdmin.target_subcategory_path(None, task) == "Спальня › Комоды"


def test_site_task_admin_allows_configuring_brand_override():
    parsing_fields = SiteScraperTaskAdmin.fieldsets[0][1]["fields"]
    subcategory_index = SiteScraperTaskAdmin.list_display.index("target_subcategory_path")

    assert "target_brand" in parsing_fields
    assert "target_brand" in SiteScraperTaskAdmin.raw_id_fields
    assert SiteScraperTaskAdmin.list_display[subcategory_index + 1] == "target_brand"
    assert "target_brand" in SiteScraperTaskAdmin.list_select_related


def test_site_task_admin_list_displays_configured_gender():
    brand_index = SiteScraperTaskAdmin.list_display.index("target_brand")
    task = SiteScraperTask(gender="men")

    assert SiteScraperTaskAdmin.list_display[brand_index + 1] == "gender_display"
    assert SiteScraperTaskAdmin.gender_display(None, task) == "Мужской"

    task.gender = ""
    assert SiteScraperTaskAdmin.gender_display(None, task) is None
