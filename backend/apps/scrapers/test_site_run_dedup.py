"""Each fresh catalogue run is isolated; resume and retries keep dedup state."""
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.admin.sites import site as admin_site
from django.core.cache import cache

from apps.scrapers.admin import SiteScraperTaskAdmin
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScrapingSession, SiteScraperTask
from apps.scrapers.services import (
    ScraperIntegrationService,
    ScraperTaskSuperseded,
    _scraper_task_product_cache_key,
)
from apps.scrapers.tasks import run_scraper_task
from apps.scrapers.test_task_pause_resume import _build_task


class RepeatingParser:
    SUPPORTS_PAGE_CHUNKING = True
    REPORTS_PAGES_PROCESSED = True
    max_products = 100
    pages_processed = 1
    has_more_pages = True

    def parse_product_list(self, *args, **kwargs):
        yield ScrapedProduct(name="Same medicine", source="ilacfiyati", external_id="same-card",
                             url="https://ilacfiyati.com/ilaclar/same-card")


SUCCESS = {"found": 1, "created": 0, "updated": 1, "skipped": 0, "errors": 0}


@pytest.fixture
def scenario(db, monkeypatch):
    task = _build_task()
    task.start_url = "https://ilacfiyati.com/ilaclar"
    task.save(update_fields=["start_url"])
    queued = Mock(return_value=SimpleNamespace(id="queued-chunk"))
    monkeypatch.setattr("apps.scrapers.admin.run_scraper_task.delay", queued)
    admin = SiteScraperTaskAdmin(SiteScraperTask, admin_site)
    service = ScraperIntegrationService()
    process = Mock(return_value=dict(SUCCESS))
    monkeypatch.setattr(service, "_process_scraped_products", process)

    def chunk():
        session = ScrapingSession.objects.create(
            scraper_config=task.scraper_config, start_url=task.start_url,
            max_pages=1, max_products=100, status="running",
        )
        return service._run_parser_scraping(
            RepeatingParser(), session, task.start_url, site_task_id=task.pk,
        )[1]

    return SimpleNamespace(task=task, admin=admin, process=process, chunk=chunk, queued=queued)


def test_fresh_run_reprocesses_card_without_flushing_other_cache(scenario):
    s = scenario
    cache.set("unrelated-cache-entry", "keep")
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    assert s.chunk() == SUCCESS
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    assert s.chunk() == SUCCESS
    assert s.process.call_count == 2
    assert cache.get("unrelated-cache-entry") == "keep"


def test_same_run_and_resume_do_not_reprocess_card(scenario):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    assert s.chunk() == SUCCESS
    assert s.chunk()["found"] == 0
    s.task.refresh_from_db()
    s.task.status = "paused"
    s.task.save(update_fields=["status"])
    s.admin._enqueue_site_task(s.task, reset_stats=False, resume=True)
    assert s.chunk()["found"] == 0
    assert s.process.call_count == 1


def test_failed_save_can_retry_in_same_run(scenario):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    s.process.side_effect = [dict(SUCCESS, updated=0, errors=1), dict(SUCCESS)]
    assert s.chunk()["errors"] == 1
    assert s.chunk() == SUCCESS
    assert s.process.call_count == 2


def test_fresh_run_ignores_legacy_task_only_cache(scenario):
    s = scenario
    legacy_key = _scraper_task_product_cache_key(s.task.pk, "ilacfiyati:same-card")
    cache.set(legacy_key, True)
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    assert s.chunk() == SUCCESS
    assert cache.get(legacy_key) is True


def test_legacy_resume_keeps_old_cache_until_explicit_restart(scenario):
    s = scenario
    assert s.task.run_token is None
    legacy_key = _scraper_task_product_cache_key(s.task.pk, "ilacfiyati:same-card")
    cache.set(legacy_key, True)
    s.admin._enqueue_site_task(s.task, reset_stats=False, resume=True)
    s.task.refresh_from_db()
    assert s.task.run_token is None
    assert s.queued.call_args.kwargs["site_run_token"] == ""
    assert s.chunk()["found"] == 0
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    assert s.task.run_token is not None
    assert s.chunk() == SUCCESS


def test_run_token_is_durable_rotates_on_restart_only_and_is_queued(scenario):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    s.task.refresh_from_db()
    first_token = s.task.run_token
    assert isinstance(first_token, uuid.UUID)
    assert s.queued.call_args.kwargs["site_run_token"] == str(first_token)
    s.admin._enqueue_site_task(s.task, reset_stats=False, resume=True)
    s.task.refresh_from_db()
    assert s.task.run_token == first_token
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    s.task.refresh_from_db()
    assert s.task.run_token != first_token


def test_chain_carries_same_token_to_service_and_next_chunk(scenario, monkeypatch):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    session = ScrapingSession.objects.create(
        scraper_config=s.task.scraper_config, start_url=s.task.start_url,
        max_pages=1, max_products=10, status="completed", products_found=1,
        products_updated=1, pages_processed=1,
    )
    run = Mock(return_value=session)
    chain = Mock(return_value=SimpleNamespace(id="next-chunk"))
    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", run)
    monkeypatch.setattr(run_scraper_task, "apply_async", chain)
    result = run_scraper_task.run(
        s.task.scraper_config_id, site_task_id=s.task.pk, start_url=s.task.start_url,
        site_run_token=str(s.task.run_token), max_pages=1, max_products=10,
    )
    assert result["status"] == "success"
    assert run.call_args.kwargs["site_run_token"] == str(s.task.run_token)
    assert chain.call_args.kwargs["kwargs"]["site_run_token"] == str(s.task.run_token)
    s.task.refresh_from_db()
    assert s.task.run_token == uuid.UUID(run.call_args.kwargs["site_run_token"])


@pytest.mark.parametrize("old_token", ["", str(uuid.UUID(int=1))])
def test_old_queued_chunk_cannot_take_over_new_run(scenario, monkeypatch, old_token):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    before = SiteScraperTask.objects.filter(pk=s.task.pk).values().get()
    run = Mock(side_effect=AssertionError("Stale chunk must not run"))
    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", run)
    result = run_scraper_task.run(
        s.task.scraper_config_id, site_task_id=s.task.pk, site_run_token=old_token,
    )
    assert result["status"] == "superseded"
    assert SiteScraperTask.objects.filter(pk=s.task.pk).values().get() == before
    run.assert_not_called()


def test_service_rejects_old_run_even_with_matching_celery_id(scenario):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    with pytest.raises(ScraperTaskSuperseded):
        ScraperIntegrationService._ensure_site_task_not_cancelled(
            s.task.pk, s.task.task_id, str(uuid.UUID(int=1)),
        )


def test_pre_release_message_without_token_cannot_join_new_run(scenario, monkeypatch):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    before = SiteScraperTask.objects.filter(pk=s.task.pk).values().get()
    run = Mock(side_effect=AssertionError("Pre-release chunk must not run"))
    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", run)
    run_scraper_task.push_request(id="old-delivery-without-token")
    try:
        result = run_scraper_task.run(s.task.scraper_config_id, site_task_id=s.task.pk)
    finally:
        run_scraper_task.pop_request()
    assert result["status"] == "superseded"
    assert SiteScraperTask.objects.filter(pk=s.task.pk).values().get() == before
    run.assert_not_called()


def test_old_chunk_cannot_finalize_new_run(scenario, monkeypatch):
    s = scenario
    s.admin._enqueue_site_task(s.task, reset_stats=True)
    original_token = s.task.run_token
    session = ScrapingSession.objects.create(
        scraper_config=s.task.scraper_config, start_url=s.task.start_url,
        max_pages=1, max_products=10, status="completed", products_found=1,
    )
    before = {}

    def restart_during_processing(*args, **kwargs):
        s.task.refresh_from_db()
        s.admin._enqueue_site_task(s.task, reset_stats=True)
        before.update(SiteScraperTask.objects.filter(pk=s.task.pk).values().get())
        return session

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", restart_during_processing)
    result = run_scraper_task.run(
        s.task.scraper_config_id, site_task_id=s.task.pk,
        site_run_token=str(original_token),
    )
    assert result["status"] == "superseded"
    assert SiteScraperTask.objects.filter(pk=s.task.pk).values().get() == before
