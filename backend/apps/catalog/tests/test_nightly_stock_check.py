"""Ночная сверка наличия: кандидаты вместо снятия, платные источники, предохранители пачки."""
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductSourceOffer
from apps.catalog.models_stock import StaleProductCandidate, StockCheckSourceState
from apps.catalog.services import nightly_stock_check as nightly
from apps.catalog.services.nightly_stock_check import NightlyStockCheckService, run_nightly_batch
from apps.catalog.services.product_card_source_refresh import ProductCardRefreshError
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, SiteScraperTask

NIGHT = datetime(2026, 10, 29, 2, 0)


class DummyLcwParser:
    pass


def _fake_registry(value):
    if value == "lcw":
        return DummyLcwParser
    host = (urlparse(str(value or "")).hostname or "").casefold()
    if host == "www.lcw.com":
        return DummyLcwParser
    return None


@pytest.fixture(autouse=True)
def nightly_settings(settings, monkeypatch):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"nightly-stock-{uuid4().hex}",
        }
    }
    settings.NIGHTLY_STOCK_CHECK_ENABLED = True
    settings.NIGHTLY_STOCK_CHECK_SOURCES = ["lcw"]
    settings.NIGHTLY_STOCK_CHECK_PAID_SOURCES = ["flo", "zara"]
    settings.NIGHTLY_STOCK_CHECK_RATE_PER_MINUTE = {"default": 6}
    settings.NIGHTLY_STOCK_CHECK_MIN_SAMPLE = 5
    settings.NIGHTLY_STOCK_CHECK_MAX_LOSS_SHARE = 0.75
    settings.NIGHTLY_STOCK_CHECK_MAX_CONSECUTIVE_ERRORS = 3
    settings.SCRAPER_GONE_REQUIRES_REVIEW = True
    settings.SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE = 1000
    settings.SOURCE_OFFER_SOURCE_RATE_PER_MINUTE = {}
    settings.SOURCE_OFFER_DEFAULT_CONCURRENCY = 2
    settings.SOURCE_OFFER_SOURCE_CONCURRENCY = {}
    settings.SOURCE_OFFER_MANUAL_ONLY_SOURCES = ["instagram"]
    monkeypatch.setattr("apps.catalog.services.source_offer_verification.get_parser", _fake_registry)
    monkeypatch.setattr("apps.catalog.services.product_card_source_refresh.get_parser", _fake_registry)
    alerts = []
    monkeypatch.setattr(nightly, "_alert", alerts.append)
    cache.clear()
    yield alerts
    cache.clear()


def _lcw_product(index=1, *, available=True):
    url = f"https://www.lcw.com/urun-{index}-o-{index}"
    product = Product.objects.create(
        name=f"LCW tabak {index}",
        slug=f"lcw-tabak-{index}-{uuid4().hex[:8]}",
        product_type="tableware",
        price=Decimal("100.00"),
        currency="TRY",
        external_id=f"lcw-{index}",
        external_url=url,
        is_available=available,
    )
    ProductSourceOffer.objects.create(
        product=product,
        parser_key="lcw",
        canonical_url=url,
        source_domain="www.lcw.com",
        external_product_id=f"lcw-{index}",
        source_price=Decimal("100.00"),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )
    return product


def _scraped(product, *, available=True):
    return ScrapedProduct(
        name="Supplier title",
        description="",
        price=110,
        currency="TRY",
        url=product.external_url,
        external_id=product.external_id,
        source="lcw",
        is_available=available,
    )


def _lcw_config(**kwargs):
    category = Category.objects.create(name="LCW", slug=f"lcw-{uuid4().hex[:8]}")
    return ScraperConfig.objects.create(
        name="LCW", parser_class="lcw", base_url="https://www.lcw.com", default_category=category, **kwargs
    )


def _gone(_target):
    raise ProductCardRefreshError("source_not_found", "Supplier product was not found", retryable=False)


# --- источники и платный прокси ----------------------------------------------------------


def test_paid_sources_are_never_checked_even_if_listed(settings):
    settings.NIGHTLY_STOCK_CHECK_SOURCES = ["lcw", "FLO", "ikea", "zara", "lcw"]
    assert nightly.nightly_sources() == ["lcw", "ikea"]


@pytest.mark.django_db
def test_source_with_paid_proxy_config_is_not_fetched():
    product = _lcw_product()
    _lcw_config(use_proxy=True)
    calls = []

    class Parser(DummyLcwParser):
        def __init__(self, **kwargs):
            calls.append(kwargs)

    service = NightlyStockCheckService()
    target = service._target(product)
    target = type(target)(product=target.product, offer=target.offer, parser_class=Parser)
    with pytest.raises(ProductCardRefreshError) as error:
        service._fetch_product(target)

    assert error.value.code == "paid_access_unavailable"
    assert calls == []


# --- пропажа у продавца ------------------------------------------------------------------


@pytest.mark.django_db
def test_gone_product_becomes_candidate_and_stays_on_sale_in_review_mode(monkeypatch):
    product = _lcw_product()
    service = NightlyStockCheckService()
    monkeypatch.setattr(service, "_fetch_product", _gone)

    result = service.run(product.pk)

    assert result["error_code"] == "source_not_found"
    product.refresh_from_db()
    assert product.is_available is True
    candidate = StaleProductCandidate.objects.get(product=product)
    assert candidate.status == StaleProductCandidate.Status.CANDIDATE
    assert candidate.source_url == product.external_url
    assert product.source_offers.get().availability_status == ProductSourceOffer.AvailabilityStatus.IN_STOCK

    # Следующая ночь подтверждает пропажу: тот же кандидат, счётчик растёт, срок не сбрасывается.
    first_seen = candidate.first_seen_at
    service.run(product.pk)
    candidate.refresh_from_db()
    assert candidate.gone_checks == 2
    assert candidate.first_seen_at == first_seen


@pytest.mark.django_db
def test_gone_product_is_taken_off_sale_without_review(settings, monkeypatch):
    settings.SCRAPER_GONE_REQUIRES_REVIEW = False
    product = _lcw_product()
    service = NightlyStockCheckService()
    monkeypatch.setattr(service, "_fetch_product", _gone)

    service.run(product.pk)

    product.refresh_from_db()
    assert product.is_available is False
    assert StaleProductCandidate.objects.filter(product=product).exists()


@pytest.mark.django_db
def test_one_missing_colour_url_is_not_a_candidate(monkeypatch):
    product = _lcw_product()
    ProductSourceOffer.objects.create(
        product=product,
        parser_key="lcw",
        canonical_url="https://www.lcw.com/urun-1-red-o-2",
        source_domain="www.lcw.com",
        external_product_id="lcw-1",
        variant_key="red",
        source_price=Decimal("100.00"),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
    )
    service = NightlyStockCheckService()
    monkeypatch.setattr(service, "_fetch_product", _gone)

    service.run(product.pk)

    assert not StaleProductCandidate.objects.filter(product=product).exists()
    product.refresh_from_db()
    assert product.is_available is True


@pytest.mark.django_db
def test_found_again_clears_candidate(monkeypatch):
    product = _lcw_product()
    now = timezone.now()
    StaleProductCandidate.objects.create(
        product=product, parser_key="lcw", source_url=product.external_url,
        first_seen_at=now, last_gone_at=now,
    )
    service = NightlyStockCheckService()
    monkeypatch.setattr(service, "_fetch_product", lambda target: _scraped(product, available=False))
    before = (True, product.price)
    state = StockCheckSourceState.objects.create(parser_key="lcw", stats={})

    result = service.run(product.pk)
    outcome = nightly._record(state, product.pk, before, result)

    assert result["status"] == "succeeded"
    assert outcome == "ok"
    assert not StaleProductCandidate.objects.filter(product=product).exists()
    product.refresh_from_db()
    assert product.is_available is False
    assert product.price == Decimal("110.00")
    assert state.stats["became_unavailable"] == 1
    assert state.stats["price_changed"] == 1


@pytest.mark.django_db
def test_dismissed_candidate_keeps_owner_decision(monkeypatch):
    product = _lcw_product()
    now = timezone.now()
    StaleProductCandidate.objects.create(
        product=product, parser_key="lcw", source_url=product.external_url,
        first_seen_at=now, last_gone_at=now, status=StaleProductCandidate.Status.DISMISSED,
    )
    service = NightlyStockCheckService()
    monkeypatch.setattr(service, "_fetch_product", _gone)

    service.run(product.pk)

    assert StaleProductCandidate.objects.get(product=product).status == StaleProductCandidate.Status.DISMISSED


# --- пачка: окно, темп, курсор, предохранители -------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeService:
    """Вместо сети: помечает товар «закончился» или отвечает заданной ошибкой."""

    def __init__(self, clock, *, unavailable=False, error=None, duration=2.0):
        self.clock = clock
        self.unavailable = unavailable
        self.error = error
        self.duration = duration
        self.calls = []

    def run(self, product_id):
        self.calls.append(product_id)
        self.clock.now += self.duration
        if self.error:
            return {"status": "failed", "error_code": self.error}
        if self.unavailable:
            Product.objects.filter(pk=product_id).update(is_available=False)
        return {"status": "succeeded", "changes": {}}


def _night():
    return timezone.make_aware(NIGHT)


@pytest.mark.django_db
def test_batch_does_nothing_outside_quiet_hours_or_when_disabled(settings):
    _lcw_product()
    day = timezone.make_aware(datetime(2026, 10, 29, 14, 0))
    assert run_nightly_batch(now=day)["status"] == "outside_window"
    settings.NIGHTLY_STOCK_CHECK_ENABLED = False
    assert run_nightly_batch(now=_night())["status"] == "disabled"


@pytest.mark.django_db
def test_batch_paces_requests_and_continues_from_cursor():
    products = [_lcw_product(index) for index in range(1, 5)]
    clock = FakeClock()
    service = FakeService(clock)

    run_nightly_batch(now=_night(), budget_seconds=110, clock=clock, sleep=clock.sleep, service=service)

    # 6 карточек в минуту: следующая не раньше чем через 10 с после начала предыдущей.
    assert service.calls == [p.pk for p in products[:2]]
    assert clock.sleeps == [8.0]
    state = StockCheckSourceState.objects.get(parser_key="lcw")
    assert state.cursor_pk == products[1].pk
    assert state.catalog_size == 4
    assert state.stats["checked"] == 2

    second = FakeService(clock)
    run_nightly_batch(now=_night(), budget_seconds=200, clock=clock, sleep=clock.sleep, service=second)
    assert second.calls == [p.pk for p in products[2:]]
    state.refresh_from_db()
    # Каталог кончился — круг закрыт, следующая ночь начнёт сначала.
    assert state.cursor_pk == 0
    assert state.last_full_cycle_at is not None
    assert state.stats["stopped"] == "cycle_done"


@pytest.mark.django_db
def test_out_of_stock_products_are_not_opened_at_night():
    in_stock = _lcw_product(1)
    _lcw_product(2, available=False)
    clock = FakeClock()
    service = FakeService(clock)

    run_nightly_batch(now=_night(), budget_seconds=600, clock=clock, sleep=clock.sleep, service=service)

    assert service.calls == [in_stock.pk]


@pytest.mark.django_db
def test_mass_loss_pauses_source_and_alerts(nightly_settings):
    products = [_lcw_product(index) for index in range(1, 11)]
    clock = FakeClock()
    service = FakeService(clock, unavailable=True)

    run_nightly_batch(now=_night(), budget_seconds=3000, clock=clock, sleep=clock.sleep, service=service)

    # Предохранитель срабатывает на 5-й проверке (5 из 5 «закончились» > 75 %), дальше — ни одного запроса.
    assert len(service.calls) == 5
    assert Product.objects.filter(pk__in=[p.pk for p in products[5:]], is_available=True).count() == 5
    state = StockCheckSourceState.objects.get(parser_key="lcw")
    assert "сбой парсера" in state.paused_reason
    assert len(nightly_settings) == 1 and "на паузе" in nightly_settings[0]

    # Пауза держится и следующей ночью — пока человек не очистит поле.
    later = FakeService(clock)
    result = run_nightly_batch(
        now=timezone.make_aware(datetime(2026, 10, 30, 2, 0)),
        budget_seconds=600, clock=clock, sleep=clock.sleep, service=later,
    )
    assert later.calls == []
    assert result["sources"]["lcw"] == "paused"


@pytest.mark.django_db
def test_consecutive_source_errors_stop_source_until_next_night():
    for index in range(1, 8):
        _lcw_product(index)
    clock = FakeClock()
    service = FakeService(clock, error="source_unavailable")

    run_nightly_batch(now=_night(), budget_seconds=3000, clock=clock, sleep=clock.sleep, service=service)
    assert len(service.calls) == 3

    again = FakeService(clock)
    run_nightly_batch(now=_night(), budget_seconds=3000, clock=clock, sleep=clock.sleep, service=again)
    assert again.calls == []

    next_night = FakeService(clock)
    run_nightly_batch(
        now=timezone.make_aware(datetime(2026, 10, 30, 2, 0)),
        budget_seconds=3000, clock=clock, sleep=clock.sleep, service=next_night,
    )
    assert next_night.calls


@pytest.mark.django_db
def test_source_is_skipped_while_its_scraper_runs():
    _lcw_product()
    config = _lcw_config()
    SiteScraperTask.objects.create(scraper_config=config, status="running", task_type="site")
    clock = FakeClock()
    service = FakeService(clock)

    result = run_nightly_batch(now=_night(), budget_seconds=600, clock=clock, sleep=clock.sleep, service=service)

    assert service.calls == []
    assert result["sources"]["lcw"] == "scraper_running"


@pytest.mark.django_db
def test_only_one_batch_runs_at_a_time():
    cache.add(nightly.BATCH_LOCK_KEY, "other", timeout=60)
    assert run_nightly_batch(now=_night())["status"] == "already_running"


@pytest.mark.django_db
def test_night_report_is_plain_and_sent_once(nightly_settings):
    StockCheckSourceState.objects.create(
        parser_key="lcw",
        night=timezone.localdate(),
        catalog_size=300,
        stats={"checked": 100, "became_unavailable": 40, "became_available": 2, "price_changed": 7,
               "gone": 3, "new_candidates": 3, "errors": 1, "rejected": 0},
    )

    first = nightly.send_night_report()
    second = nightly.send_night_report()

    assert first["status"] == "sent"
    assert second["status"] == "already_reported"
    text = nightly_settings[0]
    assert "LC Waikiki: проверено 100 из 300 (весь каталог — примерно за 3 ночи)" in text
    assert "Закончились: 40" in text
    assert "Нет у продавца: 3" in text


# --- признак «товара нет» на настоящих парсерах ------------------------------------------


def _real_target(monkeypatch, parser_class, url, routes):
    """Настоящий парсер, сеть подменена: routes — путь → (статус, тело, Location)."""
    import httpx

    from apps.catalog.services.product_card_source_refresh import RefreshTarget

    def handler(request):
        status, body, location = routes.get(request.url.path, (404, "<html>yok</html>", None))
        headers = {"Location": location} if location else {}
        return httpx.Response(status, text=body, headers=headers)

    class Mocked(parser_class):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
            self.delay_range = (0, 0)

    host = urlparse(url).hostname
    monkeypatch.setattr(
        "apps.catalog.services.product_card_source_refresh.get_parser",
        lambda value: Mocked if host in str(value) or value == parser_class(base_url=f"https://{host}").get_name() else None,
    )
    offer = ProductSourceOffer(
        parser_key=parser_class(base_url=f"https://{host}").get_name(), canonical_url=url,
        source_domain=host,
    )
    product = Product(pk=1, name="x", product_type="clothing")
    return RefreshTarget(product=product, offer=offer, parser_class=Mocked)


def _fetch(target):
    """Запрос и проверка ответа — как в service.run, без записи в БД."""
    service = NightlyStockCheckService()
    service._scraper_config = lambda offer: None
    scraped = service._fetch_product(target)
    service._validated_snapshots(target, scraped)
    return scraped


@pytest.mark.django_db
def test_lcw_removed_product_redirected_to_home_is_gone(monkeypatch):
    from apps.scrapers.parsers.lcw import LcwParser

    url = "https://www.lcw.com/kadin-elbise-siyah-o-9999999"
    target = _real_target(monkeypatch, LcwParser, url, {
        "/kadin-elbise-siyah-o-9999999": (301, "", "https://www.lcw.com/"),
        "/": (200, "<html><body><h1>LC Waikiki Anasayfa</h1></body></html>", None),
    })

    with pytest.raises(ProductCardRefreshError) as error:
        _fetch(target)

    assert error.value.code == "source_not_found"


@pytest.mark.django_db
def test_lcw_sold_out_page_is_out_of_stock_not_gone(monkeypatch):
    from apps.scrapers.parsers.lcw import LcwParser
    from apps.scrapers.test_lcw_parser import LCW_DETAIL_2026_10_HTML

    path = "/regular-fit-ince-kumas-tisort-03-beyaz-o-5271243"
    sold_out = LCW_DETAIL_2026_10_HTML.replace(", 245, ", ", 0, ").replace(", 489, ", ", 0, ").replace(", 58, ", ", 0, ")
    target = _real_target(monkeypatch, LcwParser, f"https://www.lcw.com{path}", {path: (200, sold_out, None)})

    scraped = _fetch(target)

    variants = scraped.attributes["fashion_variants"]
    assert variants and not any(variant["is_available"] for variant in variants)


@pytest.mark.django_db
def test_lcw_temporary_error_is_not_gone(monkeypatch):
    from apps.scrapers.parsers.lcw import LcwParser

    path = "/kadin-elbise-siyah-o-9999999"
    target = _real_target(monkeypatch, LcwParser, f"https://www.lcw.com{path}", {path: (503, "busy", None)})

    with pytest.raises(Exception) as error:
        _fetch(target)

    assert getattr(error.value, "code", "") != "source_not_found"


@pytest.mark.django_db
def test_ummaland_404_is_gone(monkeypatch):
    from apps.scrapers.parsers.ummaland import UmmalandParser

    url = "https://ummaland.com/product/udalennaya-kniga/"
    target = _real_target(monkeypatch, UmmalandParser, url, {})

    with pytest.raises(ProductCardRefreshError) as error:
        _fetch(target)

    assert error.value.code == "source_not_found"
