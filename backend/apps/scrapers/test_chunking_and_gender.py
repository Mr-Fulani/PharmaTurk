"""Регрессии: авточепочка только для пагинируемых парсеров + пол из настроек задачи.

Покрывает три бага (см. fix/scrapers-chunking-gender):
1. LCW падал на start_page — теперь start_page/чепочка только при SUPPORTS_PAGE_CHUNKING.
2. Счётчик раздувался (510 при 104) — непагинируемый парсер не чепочится повторно.
3. Пол можно задать в настройках задачи и он проставляется товарам.
"""

import pytest
from types import SimpleNamespace

from apps.catalog.models import Category
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession, SiteScraperTask
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser
from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.parsers.ummaland import UmmalandParser
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.tasks import run_scraper_task


def test_only_paginating_parser_supports_chunking():
    # Настоящая пагинация по ?pg= → чепочка безопасна.
    assert IlacFiyatiParser.SUPPORTS_PAGE_CHUNKING is True
    # Один проход (страница/API целиком) → чепочка переоткрыла бы те же товары.
    assert LcwParser.SUPPORTS_PAGE_CHUNKING is False
    assert UmmalandParser.SUPPORTS_PAGE_CHUNKING is False


def _build_task(parser_class: str) -> SiteScraperTask:
    category = Category.objects.create(name=f"Cat {parser_class}", slug=f"cat-{parser_class}")
    config = ScraperConfig.objects.create(
        name=f"parser-{parser_class}",
        parser_class=parser_class,
        base_url="https://example.com",
        default_category=category,
        max_pages_per_run=10,
    )
    return SiteScraperTask.objects.create(
        scraper_config=config,
        start_url="https://example.com/category",
        max_pages=10,
        max_products=1000,
        max_images_per_product=3,
        status="running",
    )


def _session_with_products(task: SiteScraperTask) -> ScrapingSession:
    session = ScrapingSession.objects.create(
        scraper_config=task.scraper_config,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        status="completed",
    )
    session.products_found = 5
    session.products_updated = 5
    session.pages_processed = 1
    session.save()
    return session


@pytest.mark.django_db
def test_non_paginating_parser_does_not_chain(monkeypatch):
    """ummaland: нашли товары, лимит не достигнут — но чепочки быть не должно."""
    task = _build_task("ummaland")
    session = _session_with_products(task)

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", lambda *a, **k: session)

    def fail_apply_async(*args, **kwargs):
        raise AssertionError("непагинируемый парсер не должен ставить следующий чанк")

    monkeypatch.setattr(run_scraper_task, "apply_async", fail_apply_async)

    result = run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
    )

    assert result["status"] == "success"
    task.refresh_from_db()
    assert task.status == "completed"


@pytest.mark.django_db
def test_paginating_parser_chains_next_chunk(monkeypatch):
    """ilacfiyati: нашли товары, лимит не достигнут — следующий чанк ставится."""
    task = _build_task("ilacfiyati")
    session = _session_with_products(task)

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", lambda *a, **k: session)

    queued = {}

    def capture_apply_async(*args, **kwargs):
        queued.update(kwargs.get("kwargs", {}))
        return SimpleNamespace(id="next-chunk-id")

    monkeypatch.setattr(run_scraper_task, "apply_async", capture_apply_async)

    run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
        start_page=1,
    )

    # Следующий чанк стартует со страницы start_page + chunk_pages.
    assert queued.get("start_page") == 1 + task.max_pages
    task.refresh_from_db()
    assert task.status == "running"


def test_gender_override_sets_attribute_when_specified():
    service = ScraperIntegrationService()
    product = ScrapedProduct(name="Футболка", attributes={})

    session = SimpleNamespace(_override_gender="men")
    service._apply_gender_override(session, product)
    assert product.attributes["gender"] == "men"


def test_gender_override_noop_when_empty():
    service = ScraperIntegrationService()
    product = ScrapedProduct(name="Футболка", attributes={"gender": "women"})

    session = SimpleNamespace(_override_gender="")
    service._apply_gender_override(session, product)
    # Пол в задаче не выбран — не трогаем то, что определил парсер.
    assert product.attributes["gender"] == "women"
