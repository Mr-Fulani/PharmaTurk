from decimal import Decimal
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from django.core.cache import cache

from apps.catalog.models import Category, Product, ProductSourceOffer
from apps.catalog.services.source_offer_verification import SourceOfferVerificationService
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckContext,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferNotFound,
    OfferSourceUnavailable,
    OfferStockPrecision,
)
from apps.scrapers.models import ScraperConfig


class DummyParser:
    calls = 0
    init_kwargs = []
    outcomes = []

    def __init__(self, base_url, **kwargs):
        self.base_url = base_url
        self.__class__.init_kwargs.append(kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def check_offer(self, context: OfferCheckContext):
        self.__class__.calls += 1
        outcome = self.__class__.outcomes.pop(0) if self.__class__.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is not None:
            return outcome
        return _success(context)


def _success(context, *, price="120.50", canonical_url=None):
    return OfferCheckResult(
        availability_status=OfferAvailability.IN_STOCK,
        stock_precision=OfferStockPrecision.BOOLEAN,
        canonical_url=canonical_url or context.canonical_url,
        source_price=Decimal(price),
        source_currency="TRY",
    )


def _fake_registry(value):
    if value == "zara":
        return DummyParser
    host = (urlparse(str(value or "")).hostname or "").casefold()
    if host == "www.zara.com" or host.endswith(".zara.com"):
        return DummyParser
    return None


@pytest.fixture(autouse=True)
def verification_settings(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"source-offer-tests-{uuid4().hex}",
        }
    }
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = []
    settings.SOURCE_OFFER_REQUEST_TIMEOUT_SECONDS = 1
    settings.SOURCE_OFFER_MAX_RETRIES = 0
    settings.SOURCE_OFFER_RETRY_BACKOFF_SECONDS = 0
    settings.SOURCE_OFFER_SUCCESS_CACHE_TTL = 120
    settings.SOURCE_OFFER_ERROR_CACHE_TTL = 15
    settings.SOURCE_OFFER_SINGLEFLIGHT_WAIT_SECONDS = 0
    settings.SOURCE_OFFER_CIRCUIT_FAILURE_THRESHOLD = 2
    settings.SOURCE_OFFER_CIRCUIT_RECOVERY_SECONDS = 60
    settings.SOURCE_OFFER_DEFAULT_CONCURRENCY = 2
    settings.SOURCE_OFFER_SOURCE_CONCURRENCY = {}
    settings.SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE = 100
    settings.SOURCE_OFFER_SOURCE_RATE_PER_MINUTE = {}
    settings.SCRAPER_PROXY_URL = ""
    cache.clear()
    DummyParser.calls = 0
    DummyParser.init_kwargs = []
    DummyParser.outcomes = []
    yield
    cache.clear()


@pytest.fixture
def offer(db):
    product = Product.objects.create(
        name="Verification product",
        slug=f"verification-product-{uuid4().hex}",
        product_type="clothing",
    )
    return ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/product-p1.html",
        external_product_id="zara-1",
        external_sku="SKU-1",
        availability_status=ProductSourceOffer.AvailabilityStatus.UNKNOWN,
        stock_precision=ProductSourceOffer.StockPrecision.UNKNOWN,
    )


@pytest.mark.django_db
def test_verification_uses_saved_offer_updates_db_and_caches(offer, monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    service = SourceOfferVerificationService()

    first = service.verify(offer)
    second = service.verify(offer)

    assert first.is_success is True
    assert second.source_price == Decimal("120.50")
    assert DummyParser.calls == 1
    assert DummyParser.init_kwargs == [{"timeout": 1.0, "max_retries": 0}]
    offer.refresh_from_db()
    assert offer.source_price == Decimal("120.50")
    assert offer.availability_status == ProductSourceOffer.AvailabilityStatus.IN_STOCK
    assert offer.last_successful_check_at is not None
    assert offer.consecutive_failures == 0


@pytest.mark.django_db
def test_historical_offer_uses_matching_active_proxy_config(
    offer,
    settings,
    monkeypatch,
):
    settings.SCRAPER_PROXY_URL = "http://proxy.example:8080"
    category = Category.objects.create(
        name="Proxy verification",
        slug=f"proxy-verification-{uuid4().hex}",
    )
    ScraperConfig.objects.create(
        name=f"zara-proxy-{uuid4().hex}",
        parser_class="zara",
        base_url="https://www.zara.com",
        default_category=category,
        use_proxy=True,
    )
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer, force=True)

    assert result.is_success is True
    assert DummyParser.init_kwargs == [{"timeout": 1.0, "max_retries": 0, "use_proxy": True}]


@pytest.mark.django_db
def test_offer_uses_proxy_from_matching_saved_config(
    offer,
    settings,
    monkeypatch,
):
    settings.SCRAPER_PROXY_URL = "http://proxy.example:8080"
    category = Category.objects.create(
        name="Saved proxy verification",
        slug=f"saved-proxy-verification-{uuid4().hex}",
    )
    config = ScraperConfig.objects.create(
        name=f"saved-zara-proxy-{uuid4().hex}",
        parser_class="zara",
        base_url="https://www.zara.com",
        default_category=category,
        use_proxy=True,
    )
    offer.parser_config = {
        "scraper_config_id": config.pk,
        "parser_class": "zara",
    }
    offer.save(update_fields=["parser_config", "updated_at"])
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer, force=True)

    assert result.is_success is True
    assert DummyParser.init_kwargs == [{"timeout": 1.0, "max_retries": 0, "use_proxy": True}]


@pytest.mark.django_db
def test_offer_does_not_use_proxy_from_mismatched_saved_config(
    offer,
    settings,
    monkeypatch,
):
    settings.SCRAPER_PROXY_URL = "http://proxy.example:8080"
    category = Category.objects.create(
        name="Wrong proxy verification",
        slug=f"wrong-proxy-verification-{uuid4().hex}",
    )
    config = ScraperConfig.objects.create(
        name=f"flo-proxy-{uuid4().hex}",
        parser_class="flo",
        base_url="https://www.flo.com.tr",
        default_category=category,
        use_proxy=True,
    )
    offer.parser_config = {"scraper_config_id": config.pk}
    offer.save(update_fields=["parser_config", "updated_at"])
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer, force=True)

    assert result.is_success is True
    assert DummyParser.init_kwargs == [{"timeout": 1.0, "max_retries": 0}]


@pytest.mark.django_db
def test_verification_flag_prevents_parser_call(offer, settings, monkeypatch):
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = False
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer)

    assert result.error.code == OfferCheckErrorCode.DISABLED
    assert result.availability_status == OfferAvailability.UNSUPPORTED
    assert DummyParser.calls == 0


@pytest.mark.django_db
def test_verification_rejects_saved_domain_parser_mismatch(offer, monkeypatch):
    offer.canonical_url = "https://evil.example/private"
    offer.source_domain = "evil.example"
    offer.save(update_fields=["canonical_url", "source_domain", "updated_at"])
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer)

    assert result.error.code == OfferCheckErrorCode.INVALID_SOURCE
    assert DummyParser.calls == 0


@pytest.mark.django_db
def test_verification_retries_only_retryable_errors(offer, settings, monkeypatch):
    settings.SOURCE_OFFER_MAX_RETRIES = 1
    DummyParser.outcomes = [
        OfferSourceUnavailable(
            OfferCheckErrorCode.TIMEOUT,
            "timeout",
            retryable=True,
        ),
        _success(SourceOfferVerificationService._context(offer)),
    ]
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer, force=True)

    assert result.is_success is True
    assert DummyParser.calls == 2


@pytest.mark.django_db
def test_verification_opens_circuit_after_retryable_failures(offer, monkeypatch):
    timeout_error = lambda: OfferSourceUnavailable(
        OfferCheckErrorCode.TIMEOUT,
        "timeout",
        retryable=True,
    )
    DummyParser.outcomes = [timeout_error(), timeout_error()]
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    service = SourceOfferVerificationService()

    assert service.verify(offer, force=True).error.code == OfferCheckErrorCode.TIMEOUT
    assert service.verify(offer, force=True).error.code == OfferCheckErrorCode.TIMEOUT
    third = service.verify(offer, force=True)

    assert third.error.code == OfferCheckErrorCode.CIRCUIT_OPEN
    assert DummyParser.calls == 2


@pytest.mark.django_db
def test_verification_singleflight_does_not_duplicate_request(offer, monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    service = SourceOfferVerificationService()
    cache.set(service._lock_key(offer), "another-worker", timeout=30)

    result = service.verify(offer, force=True)

    assert result.error.code == OfferCheckErrorCode.IN_PROGRESS
    assert DummyParser.calls == 0


@pytest.mark.django_db
def test_verification_enforces_per_source_rate_limit(offer, settings, monkeypatch):
    settings.SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE = 1
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    service = SourceOfferVerificationService()

    assert service.verify(offer, force=True).is_success is True
    limited = service.verify(offer, force=True)

    assert limited.error.code == OfferCheckErrorCode.RATE_LIMITED
    assert DummyParser.calls == 1


@pytest.mark.django_db
def test_verification_enforces_per_source_concurrency_limit(offer, settings, monkeypatch):
    settings.SOURCE_OFFER_DEFAULT_CONCURRENCY = 1
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    service = SourceOfferVerificationService()
    cache.set("source-offer:slot:v1:zara:0", "another-worker", timeout=30)

    limited = service.verify(offer, force=True)

    assert limited.error.code == OfferCheckErrorCode.RATE_LIMITED
    assert DummyParser.calls == 0


@pytest.mark.django_db
def test_verification_rejects_untrusted_redirect(offer, monkeypatch):
    context = SourceOfferVerificationService._context(offer)
    DummyParser.outcomes = [_success(context, canonical_url="https://evil.example/redirected")]
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer, force=True)

    assert result.error.code == OfferCheckErrorCode.INVALID_SOURCE
    assert DummyParser.calls == 1


@pytest.mark.django_db
def test_verification_persists_trusted_redirect_domain(offer, monkeypatch):
    context = SourceOfferVerificationService._context(offer)
    redirected_url = "https://tr.zara.com/tr/tr/product-p1.html"
    DummyParser.outcomes = [
        _success(context, canonical_url=redirected_url),
        _success(context, canonical_url=redirected_url),
    ]
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    service = SourceOfferVerificationService()

    assert service.verify(offer, force=True).is_success is True
    offer.refresh_from_db()
    assert offer.canonical_url == redirected_url
    assert offer.source_domain == "tr.zara.com"
    assert service.verify(offer, force=True).is_success is True
    assert DummyParser.calls == 2


@pytest.mark.django_db
def test_not_found_blocks_offer_without_counting_transport_failure(offer, monkeypatch):
    DummyParser.outcomes = [OfferNotFound(offer.canonical_url)]
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )

    result = SourceOfferVerificationService().verify(offer, force=True)

    assert result.availability_status == OfferAvailability.OUT_OF_STOCK
    offer.refresh_from_db()
    assert offer.availability_status == ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK
    assert offer.last_error_code == OfferCheckErrorCode.NOT_FOUND
    assert offer.consecutive_failures == 0
