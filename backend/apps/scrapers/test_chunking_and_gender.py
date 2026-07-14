"""Регрессии: авточепочка только для пагинируемых парсеров + пол из настроек задачи.

Покрывает три бага (см. fix/scrapers-chunking-gender):
1. LCW падал на start_page — теперь start_page/чепочка только при SUPPORTS_PAGE_CHUNKING.
2. Счётчик раздувался (510 при 104) — непагинируемый парсер не чепочится повторно.
3. Пол можно задать в настройках задачи и он проставляется товарам.
"""

import pytest
from types import SimpleNamespace

from django.conf import settings

from apps.catalog.models import Brand, Category
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession, SiteScraperTask
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser
from apps.scrapers.parsers.ikea import IkeaParser
from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.parsers.ummaland import UmmalandParser
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.tasks import run_scraper_task


def test_scraper_task_is_requeued_when_worker_is_lost():
    """Активный чанк должен вернуться в очередь после пересоздания worker."""
    assert run_scraper_task.acks_late is True
    assert run_scraper_task.reject_on_worker_lost is True


def test_visibility_timeout_is_longer_than_scraper_hard_limit():
    """Redis не должен повторно выдать чанк, пока первый worker ещё работает."""
    scraper_hard_limit = settings.CELERY_TASK_ANNOTATIONS[
        "apps.scrapers.tasks.run_scraper_task"
    ]["time_limit"]

    assert settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"] > scraper_hard_limit
    assert settings.CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS["visibility_timeout"] > scraper_hard_limit
    assert settings.CELERY_VISIBILITY_TIMEOUT > scraper_hard_limit
    assert settings.CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS is True


def test_only_paginating_parser_supports_chunking():
    # Настоящая пагинация (ilacfiyati ?pg=, lcw ?sayfa=) → чепочка безопасна.
    assert IlacFiyatiParser.SUPPORTS_PAGE_CHUNKING is True
    assert LcwParser.SUPPORTS_PAGE_CHUNKING is True
    assert IkeaParser.SUPPORTS_PAGE_CHUNKING is True
    # UmmaLand берёт весь листинг из API за один проход → чепочка переоткрыла бы те же товары.
    assert UmmalandParser.SUPPORTS_PAGE_CHUNKING is False


def test_ilacfiyati_chunking_only_for_listing_not_product():
    assert IlacFiyatiParser.supports_page_chunking_for_url("https://ilacfiyati.com/ilaclar")
    assert IlacFiyatiParser.supports_page_chunking_for_url("https://ilacfiyati.com/takviye-edici-gida")
    assert not IlacFiyatiParser.supports_page_chunking_for_url(
        "https://ilacfiyati.com/ilaclar/lasirin-20-mg-tablet-20-tablet"
    )


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
    task.start_url = "https://ilacfiyati.com/ilaclar"
    task.save(update_fields=["start_url"])
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


@pytest.mark.django_db
def test_ikea_chains_one_api_page_per_worker_run(monkeypatch):
    task = _build_task("ikea")
    task.start_url = "https://www.ikea.com.tr/kategori/kanepeler"
    task.save(update_fields=["start_url"])
    session = _session_with_products(task)
    captured_run = {}

    def fake_run_scraper(*args, **kwargs):
        captured_run.update(kwargs)
        session.max_pages = kwargs["max_pages"]
        return session

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", fake_run_scraper)
    queued = {}

    def capture_apply_async(*args, **kwargs):
        queued.update(kwargs.get("kwargs", {}))
        return SimpleNamespace(id="next-ikea-chunk")

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

    assert captured_run["max_pages"] == 1
    assert queued["start_page"] == 2
    assert queued["max_pages"] == 1


@pytest.mark.django_db
def test_ilacfiyati_product_url_does_not_chain(monkeypatch):
    task = _build_task("ilacfiyati")
    task.start_url = "https://ilacfiyati.com/ilaclar/lasirin-20-mg-tablet-20-tablet"
    task.save(update_fields=["start_url"])
    session = _session_with_products(task)

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", lambda *a, **k: session)

    def fail_apply_async(*args, **kwargs):
        raise AssertionError("одиночная карточка ilacfiyati не должна ставить следующий чанк")

    monkeypatch.setattr(run_scraper_task, "apply_async", fail_apply_async)

    result = run_scraper_task.run(
        scraper_config_id=task.scraper_config_id,
        start_url=task.start_url,
        max_pages=task.max_pages,
        max_products=task.max_products,
        max_images_per_product=task.max_images_per_product,
        site_task_id=task.id,
        start_page=9,
    )

    assert result["status"] == "success"
    task.refresh_from_db()
    assert task.status == "completed"
    assert task.resume_page == 1


@pytest.mark.django_db
def test_lcw_product_url_does_not_chain(monkeypatch):
    task = _build_task("lcw")
    task.start_url = (
        "https://www.lcw.com/"
        "erkek-100-hakiki-deri-4-cm-spor-lacivert-kemer-lacivert-o-4579317"
    )
    task.save(update_fields=["start_url"])
    session = _session_with_products(task)
    session.products_found = 1
    session.products_updated = 1
    session.save(update_fields=["products_found", "products_updated"])

    monkeypatch.setattr(ScraperIntegrationService, "run_scraper", lambda *a, **k: session)

    def fail_apply_async(*args, **kwargs):
        raise AssertionError("одиночный LCW-товар не должен ставить новый чанк")

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
    assert task.products_found == 1
    assert task.products_updated == 1


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


@pytest.mark.django_db
def test_task_brand_override_has_priority_over_config_brand():
    service = ScraperIntegrationService()
    task_brand = Brand.objects.create(name="Task Brand", slug="task-brand")
    config_brand = Brand.objects.create(name="Config Brand", slug="config-brand")
    product = ScrapedProduct(name="Товар", brand="Parsed Brand")
    session = SimpleNamespace(
        _override_brand=task_brand,
        scraper_config=SimpleNamespace(default_brand=config_brand),
    )

    service._apply_brand_mapping(session, product)

    assert product.brand == "Task Brand"
    assert product._brand_override == task_brand


@pytest.mark.django_db
def test_config_brand_is_used_when_task_brand_is_empty():
    service = ScraperIntegrationService()
    config_brand = Brand.objects.create(name="Config Brand", slug="config-brand")
    product = ScrapedProduct(name="Товар", brand="Parsed Brand")
    session = SimpleNamespace(
        _override_brand=None,
        scraper_config=SimpleNamespace(default_brand=config_brand),
    )

    service._apply_brand_mapping(session, product)

    assert product.brand == "Config Brand"
    assert product._brand_override is None


def test_ikea_parser_fetches_real_api_pages(monkeypatch):
    parser = IkeaParser(base_url="https://www.ikea.com.tr")
    parser.max_products = 10
    requested_pages = []

    def fake_category_products(category_slug, limit, *, language, page):
        requested_pages.append(page)
        if page == 2:
            return [{"sprCode": "11111111"}] * parser.API_PAGE_SIZE
        if page == 3:
            return [{"sprCode": "22222222"}]
        return []

    monkeypatch.setattr(parser.ikea_service, "get_category_products", fake_category_products)
    monkeypatch.setattr(
        parser.ikea_service,
        "fetch_items",
        lambda codes: [{"sprCode": code} for code in codes],
    )
    monkeypatch.setattr(
        parser.ikea_service,
        "collect_color_variant_details",
        lambda item: [item],
    )
    monkeypatch.setattr(
        parser,
        "_scraped_product_from_variant_details",
        lambda details, canonical_spr: ScrapedProduct(
            name=canonical_spr,
            external_id=canonical_spr,
        ),
    )

    products = list(
        parser.parse_product_list(
            "https://www.ikea.com.tr/kategori/kanepeler",
            max_pages=5,
            start_page=2,
        )
    )

    assert [product.external_id for product in products] == ["11111111", "22222222"]
    assert requested_pages == [2, 3]
    assert parser.pages_processed == 2
