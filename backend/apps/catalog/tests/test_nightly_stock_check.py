"""Ночная сверка наличия: кандидаты вместо снятия, платные источники, предохранители пачки."""
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.catalog.models import Category, ClothingProduct, ClothingVariant, Product, ProductSourceOffer
from apps.catalog.models_stock import StaleProductCandidate, StockCheckSourceState
from apps.catalog.services import nightly_stock_check as nightly
from apps.catalog.services.nightly_stock_check import NightlyStockCheckService, run_nightly_batch
from apps.catalog.services.product_card_source_refresh import (
    ProductCardRefreshError,
    ProductCardSourceRefreshService,
)
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig, SiteScraperTask
from apps.scrapers.source_offers import record_scraped_product_offers

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


# --- товар с несколькими цветами: у каждого своя ссылка ----------------------------------


def _colour_url(colour):
    return f"https://www.lcw.com/elbise-{colour}-o-{colour}"


def _colour_matrix(colours, opened_url):
    """Ответ страницы цвета: как у LCW, на ней видны все живые цвета группы."""
    return ScrapedProduct(
        name="Supplier title",
        description="",
        price=100,
        currency="TRY",
        url=opened_url,
        external_id="lcw-elbise",
        source="lcw",
        is_available=True,
        attributes={
            "fashion_variants": [
                {
                    "external_id": colour,
                    "color": colour,
                    "price": 100,
                    "currency": "TRY",
                    "external_url": _colour_url(colour),
                    "is_available": True,
                    "sizes": [{"size": "M", "is_available": True}],
                }
                for colour in colours
            ]
        },
    )


def _lcw_dress(colours=("black", "red")):
    """Платье в нескольких цветах: предложения записаны так же, как после обхода парсером."""
    category = Category.objects.create(name="Elbise", slug=f"elbise-{uuid4().hex[:8]}")
    domain = ClothingProduct.objects.create(
        name="LCW elbise",
        slug=f"lcw-elbise-{uuid4().hex[:8]}",
        category=category,
        price=Decimal("100.00"),
        currency="TRY",
        external_id="lcw-elbise",
        external_url=_colour_url(colours[0]),
        external_data={"source": "lcw"},
        is_available=True,
    )
    domain.refresh_from_db()
    product = domain.base_product
    for colour in colours:
        ClothingVariant.objects.create(
            product=domain, name=colour, color=colour, sku=colour, external_id=colour,
            price=Decimal("100.00"), currency="TRY", is_available=True,
        )
    record_scraped_product_offers(
        product=product, scraped_product=_colour_matrix(colours, _colour_url(colours[0])), deactivate_missing=False
    )
    return product


class SellerSite:
    """Продавец вместо сети: страницы живых цветов открываются, остальные — «товара нет»."""

    def __init__(self, *live):
        self.live = set(live)
        self.opened = []

    def __call__(self, target):
        url = target.offer.canonical_url
        self.opened.append(url)
        if url not in {_colour_url(colour) for colour in self.live}:
            return _gone(target)
        return _colour_matrix(sorted(self.live), url)


def _pass_nights(site, nights=1):
    """Настоящие ночные пачки: одна проверка каждого товара за ночь."""
    clock = FakeClock()
    service = NightlyStockCheckService()
    service._fetch_product = site
    for _ in range(nights):
        site.night = getattr(site, "night", -1) + 1
        run_nightly_batch(
            now=_night() + timedelta(days=site.night), budget_seconds=600,
            clock=clock, sleep=clock.sleep, service=service,
        )


def _offers_of(product, colour):
    return product.source_offers.filter(canonical_url=_colour_url(colour))


def _variant_available(product, colour):
    return ClothingVariant.objects.get(product=product.domain_item, external_id=colour).is_available


@pytest.mark.django_db
def test_gone_colour_is_marked_and_next_check_opens_next_colour():
    product = _lcw_dress()
    site = SellerSite("red")

    _pass_nights(site)

    assert site.opened == [_colour_url("black")]
    assert not StaleProductCandidate.objects.filter(product=product).exists()
    assert StockCheckSourceState.objects.get(parser_key="lcw").stats["gone_colours"] == 1
    assert _offers_of(product, "black").get().last_error_code == "not_found"
    assert _variant_available(product, "black") is False

    # Раньше здесь снова открывалась чёрная ссылка, и красная не проверялась никогда.
    _pass_nights(site, nights=2)

    assert site.opened == [_colour_url("black"), _colour_url("red"), _colour_url("red")]
    assert not StaleProductCandidate.objects.filter(product=product).exists()
    product.refresh_from_db()
    assert product.is_available is True
    assert _variant_available(product, "red") is True


@pytest.mark.django_db
def test_product_becomes_candidate_when_all_colours_are_gone():
    product = _lcw_dress(("black", "red", "blue"))
    site = SellerSite()

    _pass_nights(site, nights=2)
    assert not StaleProductCandidate.objects.filter(product=product).exists()

    _pass_nights(site)

    candidate = StaleProductCandidate.objects.get(product=product)
    assert candidate.status == StaleProductCandidate.Status.CANDIDATE
    assert candidate.source_url == _colour_url("blue")
    assert candidate.gone_checks == 1
    assert StockCheckSourceState.objects.get(parser_key="lcw").stats["new_candidates"] == 1
    # Сверка только отмечает: товар на сайте и в продаже до решения владельца.
    product.refresh_from_db()
    assert product.is_active is True
    assert product.is_available is True
    last = _offers_of(product, "blue").get()
    assert last.availability_status == ProductSourceOffer.AvailabilityStatus.IN_STOCK

    # Дальше пропажа подтверждается каждую ночь, по очереди на всех ссылках.
    _pass_nights(site, nights=3)

    assert site.opened == [_colour_url(colour) for colour in ("black", "red", "blue") * 2]
    candidate.refresh_from_db()
    assert candidate.gone_checks == 4
    assert candidate.status == StaleProductCandidate.Status.CANDIDATE


@pytest.mark.django_db
def test_all_colours_gone_takes_product_off_sale_without_review(settings):
    settings.SCRAPER_GONE_REQUIRES_REVIEW = False
    product = _lcw_dress()

    _pass_nights(SellerSite(), nights=2)

    product.refresh_from_db()
    assert product.is_available is False
    assert StaleProductCandidate.objects.filter(product=product).exists()


@pytest.mark.django_db
def test_colour_returned_after_all_gone_clears_candidate():
    product = _lcw_dress()
    site = SellerSite()
    _pass_nights(site, nights=2)
    assert StaleProductCandidate.objects.filter(product=product).exists()

    site.live = {"red"}
    # Чёрная пропала по-прежнему; за ней очередь доходит до вернувшейся красной.
    _pass_nights(site, nights=2)

    assert site.opened[-2:] == [_colour_url("black"), _colour_url("red")]
    assert not StaleProductCandidate.objects.filter(product=product).exists()
    assert _offers_of(product, "red").get().last_error_code == ""
    assert _offers_of(product, "black").get().last_error_code == "not_found"
    product.refresh_from_db()
    assert product.is_available is True
    assert _variant_available(product, "red") is True


@pytest.mark.django_db
def test_returned_colour_seen_on_sibling_page_loses_its_mark():
    product = _lcw_dress()
    site = SellerSite("red")
    _pass_nights(site)
    assert _offers_of(product, "black").get().last_error_code == "not_found"

    site.live = {"black", "red"}
    _pass_nights(site)

    # Страницу чёрного цвета не открывали: его снова показала страница красного.
    assert site.opened[-1] == _colour_url("red")
    returned = _offers_of(product, "black").get()
    assert returned.last_error_code == ""
    assert returned.availability_status == ProductSourceOffer.AvailabilityStatus.IN_STOCK
    assert _variant_available(product, "black") is True


@pytest.mark.django_db
def test_live_offer_of_other_source_keeps_product_off_the_list():
    product = _lcw_dress(("black",))
    ProductSourceOffer.objects.create(
        product=product,
        parser_key="flo",
        canonical_url="https://www.flo.com.tr/urun/elbise-1",
        source_domain="www.flo.com.tr",
        source_price=Decimal("100.00"),
        source_currency="TRY",
    )

    _pass_nights(SellerSite(), nights=2)

    assert not StaleProductCandidate.objects.filter(product=product).exists()


@pytest.mark.django_db
def test_card_refresh_still_opens_first_url(settings):
    settings.PRODUCT_CARD_SOURCE_REFRESH_ENABLED = True
    settings.PRODUCT_CARD_SOURCE_REFRESH_SOURCES = ["lcw"]
    product = _lcw_dress()
    _pass_nights(SellerSite("red"))

    assert ProductCardSourceRefreshService()._target(product).offer.canonical_url == _colour_url("black")
    assert NightlyStockCheckService()._target(product).offer.canonical_url == _colour_url("red")


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
    assert "Новых неактуальных: 3" in text


@pytest.mark.django_db
def test_missing_colour_is_not_reported_as_a_stale_product(nightly_settings, monkeypatch):
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
    state = StockCheckSourceState.objects.create(parser_key="lcw", night=timezone.localdate(), catalog_size=1)

    nightly._record(state, product.pk, (True, product.price), service.run(product.pk))
    state.save()

    assert state.stats["gone_colours"] == 1 and state.stats["gone"] == 0
    assert not StaleProductCandidate.objects.exists()
    text = nightly.build_night_report()
    assert "Пропал один цвет из нескольких: 1" in text
    assert "Неактуальных товаров нет, решать ничего не нужно." in text
    assert "ждут вашего решения" not in text


@pytest.mark.django_db
def test_sold_out_products_are_not_called_stale_in_report():
    _lcw_product(1, available=False)
    _lcw_product(2, available=True)
    StockCheckSourceState.objects.create(
        parser_key="lcw", night=timezone.localdate(), catalog_size=1,
        stats={"checked": 1, "became_unavailable": 1},
    )

    text = nightly.build_night_report()

    assert "Закончились: 1" in text
    assert "Неактуальных товаров нет, решать ничего не нужно." in text
    assert "Нет в наличии у этих продавцов: 1. Это не неактуальные" in text
    assert "/admin/catalog/product/?sold_out=nightly" in text


@pytest.mark.django_db
def test_whole_product_gone_is_counted_as_new_stale_product(monkeypatch):
    product = _lcw_product()
    service = NightlyStockCheckService()
    monkeypatch.setattr(service, "_fetch_product", _gone)
    state = StockCheckSourceState.objects.create(parser_key="lcw", night=timezone.localdate(), catalog_size=1)

    nightly._record(state, product.pk, (True, product.price), service.run(product.pk))
    state.save()

    assert state.stats["gone"] == 1 and state.stats["new_candidates"] == 1
    assert state.stats["gone_colours"] == 0
    assert "Новых неактуальных: 1" in nightly.build_night_report()


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
