from types import SimpleNamespace

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.contrib import admin
from django.conf import settings

from apps.catalog.models import Category, MedicineProduct
from apps.scrapers.admin import SiteScraperTaskAdmin
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, ScrapingSession, SiteScraperTask
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.tasks import run_stub_refresh_task


class _FakeParser:
    seen_urls = []
    soft_limit_on_call = None

    def __init__(self, **_kwargs):
        self.delay_range = (0, 0)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def configure_request_identity(self, **_kwargs):
        return None

    def parse_product_detail(self, url):
        self.__class__.seen_urls.append(url)
        if self.__class__.soft_limit_on_call == len(self.__class__.seen_urls):
            raise SoftTimeLimitExceeded()
        return ScrapedProduct(name="STUB", url=url, source="ilacfiyati")


def _build_stub_task(*, max_products=100):
    category = Category.objects.create(name="Medicine", slug="stub-refresh-medicine")
    config = ScraperConfig.objects.create(
        name="stub-refresh-ilacfiyati",
        parser_class="ilacfiyati",
        base_url="https://ilacfiyati.com/ilaclar",
        default_category=category,
    )
    task = SiteScraperTask.objects.create(
        scraper_config=config,
        task_type="stub_refresh",
        max_pages=1,
        max_products=max_products,
        max_images_per_product=3,
        status="running",
    )
    return config, task


def _create_stubs(count):
    return [
        MedicineProduct.objects.create(
            name=f"STUB {index}",
            slug=f"stub-refresh-{index}",
            price=1,
            currency="TRY",
            external_url=f"https://ilacfiyati.com/ilaclar/stub-{index}",
            external_data={"source": "ilacfiyati", "is_stub": True},
        )
        for index in range(count)
    ]


_REAL_UPDATE = ScraperIntegrationService._update_existing_product


@pytest.fixture(autouse=True)
def _stub_refresh_fakes(monkeypatch):
    _FakeParser.seen_urls = []
    _FakeParser.soft_limit_on_call = None
    monkeypatch.setattr(
        "apps.scrapers.parsers.registry.get_parser",
        lambda _parser_class: _FakeParser,
    )
    monkeypatch.setattr(
        ScraperIntegrationService,
        "_update_existing_product",
        lambda _self, _session, _scraped, product: ("updated", product),
    )


def test_stub_refresh_has_worker_loss_and_scraper_time_limit_guards():
    assert run_stub_refresh_task.acks_late is True
    assert run_stub_refresh_task.reject_on_worker_lost is True
    assert settings.CELERY_TASK_ANNOTATIONS[
        "apps.scrapers.tasks.run_stub_refresh_task"
    ] == {
        "time_limit": 60 * 60 * 2,
        "soft_time_limit": 60 * 60,
    }


@pytest.mark.django_db
def test_stub_refresh_chains_with_stable_id_cursor(monkeypatch):
    config, task = _build_stub_task()
    stubs = _create_stubs(5)
    monkeypatch.setattr("apps.scrapers.tasks._STUB_REFRESH_BATCH_SIZE", 2)
    queued = {}

    def capture_next(*_args, **kwargs):
        queued.clear()
        queued.update(kwargs["kwargs"])
        return SimpleNamespace(id="next-stub-chunk")

    monkeypatch.setattr(run_stub_refresh_task, "apply_async", capture_next)

    first = run_stub_refresh_task.run(
        site_task_id=task.id,
        scraper_config_id=config.id,
    )
    first_next = dict(queued)

    assert _FakeParser.seen_urls == [stub.external_url for stub in stubs[:2]]
    assert first["offset"] == 2
    assert first_next == {
        "site_task_id": task.id,
        "scraper_config_id": config.id,
        "offset": 2,
        "after_id": stubs[1].id,
    }

    run_stub_refresh_task.run(**first_next)

    assert _FakeParser.seen_urls == [stub.external_url for stub in stubs[:4]]
    task.refresh_from_db()
    assert task.products_found == 4
    assert task.products_updated == 4
    assert queued["after_id"] == stubs[3].id


@pytest.mark.django_db
def test_stub_refresh_never_exceeds_total_product_limit(monkeypatch):
    config, task = _build_stub_task(max_products=3)
    stubs = _create_stubs(5)
    monkeypatch.setattr("apps.scrapers.tasks._STUB_REFRESH_BATCH_SIZE", 10)

    def fail_chain(*_args, **_kwargs):
        raise AssertionError("a completed total limit must not queue another chunk")

    monkeypatch.setattr(run_stub_refresh_task, "apply_async", fail_chain)

    result = run_stub_refresh_task.run(
        site_task_id=task.id,
        scraper_config_id=config.id,
    )

    assert _FakeParser.seen_urls == [stub.external_url for stub in stubs[:3]]
    assert result["offset"] == 3
    task.refresh_from_db()
    assert task.status == "completed"
    assert task.products_found == 3
    assert task.products_updated == 3


@pytest.mark.django_db
def test_stub_refresh_soft_limit_queues_from_last_durable_checkpoint(monkeypatch):
    config, task = _build_stub_task(max_products=5)
    stubs = _create_stubs(3)
    _FakeParser.soft_limit_on_call = 2
    queued = {}

    def capture_next(*_args, **kwargs):
        queued.update(kwargs["kwargs"])
        return SimpleNamespace(id="soft-limit-continuation")

    monkeypatch.setattr(run_stub_refresh_task, "apply_async", capture_next)

    result = run_stub_refresh_task.run(
        site_task_id=task.id,
        scraper_config_id=config.id,
    )

    assert result["status"] == "continued"
    assert queued == {
        "site_task_id": task.id,
        "scraper_config_id": config.id,
        "offset": 1,
        "after_id": stubs[0].id,
    }
    task.refresh_from_db()
    assert task.status == "running"
    assert task.task_id == "soft-limit-continuation"
    assert task.products_found == 1
    assert task.products_updated == 1
    assert task.errors_count == 0
    session = ScrapingSession.objects.get(task_id="")
    assert session.status == "failed"
    assert session.products_found == 1
    assert "мягкого лимита" in session.error_message


@pytest.mark.django_db
def test_stub_refresh_redelivery_uses_database_checkpoint(monkeypatch):
    config, task = _build_stub_task(max_products=3)
    stubs = _create_stubs(3)
    task.products_found = 1
    task.products_updated = 1
    task.stub_cursor_id = stubs[0].id
    task.save(update_fields=["products_found", "products_updated", "stub_cursor_id"])
    monkeypatch.setattr("apps.scrapers.tasks._STUB_REFRESH_BATCH_SIZE", 1)
    queued = {}

    def capture_next(*_args, **kwargs):
        queued.update(kwargs["kwargs"])
        return SimpleNamespace(id="redelivered-next")

    monkeypatch.setattr(run_stub_refresh_task, "apply_async", capture_next)

    result = run_stub_refresh_task.run(
        site_task_id=task.id,
        scraper_config_id=config.id,
        offset=0,
        after_id=0,
    )

    assert _FakeParser.seen_urls == [stubs[1].external_url]
    assert result["offset"] == 2
    assert queued["offset"] == 2
    assert queued["after_id"] == stubs[1].id
    task.refresh_from_db()
    assert task.products_found == 2
    assert task.products_updated == 2


@pytest.mark.django_db
def test_stub_refresh_admin_rerun_resets_durable_cursor(monkeypatch):
    _config, task = _build_stub_task(max_products=5)
    task.products_found = 4
    task.products_updated = 3
    task.stub_cursor_id = 12345
    task.save(
        update_fields=["products_found", "products_updated", "stub_cursor_id"]
    )
    queued = {}

    def capture_delay(**kwargs):
        queued.update(kwargs)
        return SimpleNamespace(id="admin-rerun")

    monkeypatch.setattr(
        "apps.scrapers.admin.run_stub_refresh_task.delay",
        capture_delay,
    )
    task_admin = SiteScraperTaskAdmin(SiteScraperTask, admin.AdminSite())

    task_admin._enqueue_site_task(task, reset_stats=True)

    task.refresh_from_db()
    assert task.products_found == 0
    assert task.products_updated == 0
    assert task.stub_cursor_id == 0
    assert task.task_id == "admin-rerun"
    assert queued == {
        "site_task_id": task.id,
        "scraper_config_id": task.scraper_config_id,
        "offset": 0,
    }


STUB_URL = "https://ilacfiyati.com/ilaclar/largopen-1-gr-film-tablet-16-tablet"


class _FullCardParser(_FakeParser):
    barcode = "8699536090115"

    def parse_product_detail(self, url):
        return ScrapedProduct(
            name="LARGOPEN 1 GR FILM TABLET 16 TABLET", source="ilacfiyati", url=url,
            external_id="largopen-1-gr-film-tablet-16-tablet", price=204.49, currency="TRY",
            description="Полное описание карточки источника.",
            images=["https://ilacfiyati.com/dosyalar/largopen.jpg"],
            barcode=self.barcode,
            attributes={
                "barcode": self.barcode, "atc_code": "J01CR02",
                "active_ingredient": "Amoksisilin trihidrat, potasyum klavulanat",
                "manufacturer": "Bilim",
            },
        )


def _real_stub(monkeypatch):
    """Заглушка аналога, созданная тем же путём, что и в парсере."""
    from apps.catalog.models import CategoryType, Product

    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    kind, _ = CategoryType.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})
    root, _ = Category.objects.update_or_create(
        slug="medicines", defaults={"name": "Медицина", "category_type": kind, "parent": None},
    )
    config = ScraperConfig.objects.create(
        name="stub-real-ilacfiyati", parser_class="ilacfiyati",
        base_url="https://ilacfiyati.com", default_category=root,
    )
    session = ScrapingSession.objects.create(scraper_config=config, start_url=STUB_URL, max_pages=1, max_products=1)
    # Как у аналога: МНН и ATC унаследованы от родительского препарата.
    _, product = ScraperIntegrationService()._create_new_product(session, ScrapedProduct(
        name="LARGOPEN 1 GR 16 TABLET", url=STUB_URL, category="medicines", source="ilacfiyati",
        external_id="largopen-1-gr-film-tablet-16-tablet", barcode="8699536090115",
        attributes={
            "is_stub": True, "active_ingredient": "amoksisilin", "atc_code": "J01CA04",
            "barcode": "8699536090115",
        },
    ))
    task = SiteScraperTask.objects.create(
        scraper_config=config, task_type="stub_refresh", max_pages=1, max_products=10, status="running",
    )
    return config, task, product


@pytest.mark.django_db
def test_stub_refresh_turns_stub_into_full_card(monkeypatch):
    downloads = []
    monkeypatch.setattr(
        "apps.scrapers.services.download_and_optimize_parsed_media",
        lambda url, *args, **kwargs: downloads.append(url) or "https://cdn.example/parsed/largopen.jpg",
    )
    monkeypatch.setattr(ScraperIntegrationService, "_update_existing_product", _REAL_UPDATE)
    monkeypatch.setattr("apps.scrapers.parsers.registry.get_parser", lambda _name: _FullCardParser)
    config, task, product = _real_stub(monkeypatch)

    run_stub_refresh_task.apply(kwargs={"site_task_id": task.id, "scraper_config_id": config.id}).get()

    product.refresh_from_db()
    task.refresh_from_db()
    medicine = MedicineProduct.objects.get(base_product=product)
    assert (task.products_updated, task.products_skipped) == (1, 0)
    assert (str(product.price), product.currency) == ("204.49", "TRY")
    assert product.external_data.get("is_stub") is False
    assert medicine.external_data.get("is_stub") is False
    assert downloads == ["https://ilacfiyati.com/dosyalar/largopen.jpg"]


@pytest.mark.django_db
def test_stub_refresh_counts_conflicting_card_as_skipped(monkeypatch):
    monkeypatch.setattr(ScraperIntegrationService, "_update_existing_product", _REAL_UPDATE)
    monkeypatch.setattr("apps.scrapers.services.download_and_optimize_parsed_media", lambda *a, **k: "")
    parser = type("OtherBarcodeParser", (_FullCardParser,), {"barcode": "8690000000000"})
    monkeypatch.setattr("apps.scrapers.parsers.registry.get_parser", lambda _name: parser)
    config, task, product = _real_stub(monkeypatch)

    run_stub_refresh_task.apply(kwargs={"site_task_id": task.id, "scraper_config_id": config.id}).get()

    task.refresh_from_db()
    product.refresh_from_db()
    assert (task.products_updated, task.products_skipped) == (0, 1)
    assert product.external_data.get("is_stub") is True
