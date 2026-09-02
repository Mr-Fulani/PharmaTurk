from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.authentication import JWTSafeAuthentication
from api.throttles import TrustedProxyIPRateThrottle
from apps.catalog.models import (
    Category,
    MedicineAnalog,
    MedicineProduct,
    PriceHistory,
    Product,
    ProductMarketCheck,
)
from apps.catalog.services.medicine_market_check import (
    MedicineMarketCheckError,
    MedicineMarketCheckService,
    TrustedMedicineSource,
)
from apps.catalog.throttles import MEDICINE_MARKET_CHECK_THROTTLES
from apps.catalog.views import MedicineProductViewSet
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def medicine(settings):
    settings.MEDICINE_MARKET_CHECK_ENABLED = True
    settings.MEDICINE_MARKET_CHECK_SOURCES = ["ilacfiyati"]
    settings.MEDICINE_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE = 100
    category = Category.objects.create(name="Medicine market test", slug="medicine-market-test")
    base = Product.objects.create(
        name="LASIRIN 20 MG",
        slug="lasirin-market-check",
        product_type="medicines",
        category=category,
        price=Decimal("100.00"),
        currency="TRY",
        is_available=False,
        stock_quantity=0,
        external_id="lasirin-20-mg",
        external_url="https://ilacfiyati.com/ilaclar/lasirin-20-mg",
        external_data={"source": "ilacfiyati"},
    )
    # Product domain-sync already creates the one-to-one MedicineProduct row.
    # Update only medicine-specific metadata so the fixture follows production.
    item = MedicineProduct.objects.get(base_product=base)
    MedicineProduct.objects.filter(pk=item.pk).update(
        active_ingredient="Acetylsalicylic acid",
        dosage_form="tablet",
        volume="20 tablet",
    )
    item.refresh_from_db()
    ScraperConfig.objects.create(
        name="ilacfiyati-market-test",
        parser_class="ilacfiyati",
        base_url="https://ilacfiyati.com",
        default_category=category,
        status="active",
        is_enabled=True,
        priority=1,
        max_retries=1,
    )
    return item


def _trusted_source(medicine):
    return TrustedMedicineSource(
        key="ilacfiyati",
        url="https://ilacfiyati.com/ilaclar/lasirin-20-mg",
        parser_class=IlacFiyatiParser,
        config=ScraperConfig.objects.get(name="ilacfiyati-market-test"),
    )


@pytest.mark.django_db
def test_market_check_updates_only_price_and_equivalents(medicine, monkeypatch):
    original_product_count = Product.objects.count()
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.PENDING,
        requested_at=timezone.now(),
    )
    scraped = ScrapedProduct(
        name=medicine.name,
        price=Decimal("125.45"),
        currency="TRY",
        url=medicine.external_url,
        source="ilacfiyati",
        # These are known legacy synthetic defaults and must never be projected.
        is_available=True,
        stock_quantity=3,
        analogs=[
            {
                "name": "LASIRIN EQUIVALENT",
                "url": "https://ilacfiyati.com/ilaclar/lasirin-equivalent",
                "external_id": "lasirin-equivalent",
                "barcode": "8690000000001",
                "price": Decimal("110.25"),
                "source_tab": "Eşdeğeri",
            }
        ],
    )
    service = MedicineMarketCheckService()
    monkeypatch.setattr(service, "resolve_source", lambda item: _trusted_source(item))
    monkeypatch.setattr(service, "_parse_snapshot", lambda source: scraped)

    result = service.run(check.pk)

    assert result["status"] == ProductMarketCheck.Status.SUCCEEDED
    medicine.refresh_from_db()
    medicine.base_product.refresh_from_db()
    check.refresh_from_db()
    assert medicine.price == Decimal("125.45")
    assert medicine.old_price == Decimal("100.00")
    assert medicine.is_available is False
    assert medicine.stock_quantity == 0
    assert medicine.base_product.is_available is False
    assert medicine.base_product.stock_quantity == 0
    assert Product.objects.count() == original_product_count
    assert PriceHistory.objects.filter(
        product=medicine.base_product,
        price=Decimal("125.45"),
        source="ilacfiyati_on_demand",
    ).exists()
    analog = MedicineAnalog.objects.get(product=medicine, external_id="lasirin-equivalent")
    assert analog.analog_product is None
    assert analog.reference_price == Decimal("110.25")
    assert analog.reference_currency == "TRY"
    assert analog.source_url.endswith("/lasirin-equivalent")
    assert analog.last_observed_at is not None
    assert check.observed_price == Decimal("125.45")
    assert check.analog_count == 1
    assert check.last_success_at is not None


@pytest.mark.django_db
def test_market_check_accepts_supported_eur_source_price(medicine, monkeypatch):
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.PENDING,
        requested_at=timezone.now(),
    )
    scraped = ScrapedProduct(
        name=medicine.name,
        price=Decimal("4200.00"),
        currency="EUR",
        url=medicine.external_url,
        source="ilacfiyati",
        is_available=True,
        stock_quantity=3,
    )
    service = MedicineMarketCheckService()
    monkeypatch.setattr(service, "resolve_source", lambda item: _trusted_source(item))
    monkeypatch.setattr(service, "_parse_snapshot", lambda source: scraped)

    result = service.run(check.pk)

    assert result["status"] == ProductMarketCheck.Status.SUCCEEDED
    medicine.refresh_from_db()
    medicine.base_product.refresh_from_db()
    check.refresh_from_db()
    assert medicine.price == Decimal("4200.00")
    assert medicine.currency == "EUR"
    assert medicine.base_product.price == Decimal("4200.00")
    assert medicine.base_product.currency == "EUR"
    assert medicine.is_available is False
    assert medicine.stock_quantity == 0
    assert check.observed_price == Decimal("4200.00")
    assert check.observed_currency == "EUR"


@pytest.mark.django_db
def test_source_failure_keeps_last_successful_price_and_stock(medicine, monkeypatch):
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.PENDING,
        observed_price=Decimal("100.00"),
        observed_currency="TRY",
        last_success_at=timezone.now(),
        requested_at=timezone.now(),
    )
    service = MedicineMarketCheckService()
    monkeypatch.setattr(service, "resolve_source", lambda item: _trusted_source(item))

    def fail(_source):
        raise httpx.ConnectError("supplier unavailable")

    monkeypatch.setattr(service, "_parse_snapshot", fail)

    service.run(check.pk)

    medicine.refresh_from_db()
    check.refresh_from_db()
    assert medicine.price == Decimal("100.00")
    assert medicine.is_available is False
    assert medicine.stock_quantity == 0
    assert check.status == ProductMarketCheck.Status.SOURCE_UNAVAILABLE
    assert check.observed_price == Decimal("100.00")
    assert check.error_code == "source_unavailable"


@pytest.mark.django_db
def test_invalid_market_price_is_not_persisted(medicine, monkeypatch):
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.PENDING,
        requested_at=timezone.now(),
    )
    service = MedicineMarketCheckService()
    monkeypatch.setattr(service, "resolve_source", lambda item: _trusted_source(item))
    monkeypatch.setattr(
        service,
        "_parse_snapshot",
        lambda source: ScrapedProduct(
            name=medicine.name,
            price=None,
            currency="TRY",
            url=medicine.external_url,
            source="ilacfiyati",
        ),
    )

    service.run(check.pk)

    medicine.refresh_from_db()
    check.refresh_from_db()
    assert medicine.price == Decimal("100.00")
    assert PriceHistory.objects.filter(product=medicine.base_product).count() == 0
    assert check.status == ProductMarketCheck.Status.FAILED
    assert check.error_code == "price_missing"


@pytest.mark.django_db
def test_unpublished_zero_market_price_is_reported_without_persistence(medicine, monkeypatch):
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.PENDING,
        requested_at=timezone.now(),
    )
    scraped = ScrapedProduct(
        name=medicine.name,
        price=None,
        currency="TRY",
        url=medicine.external_url,
        source="ilacfiyati",
    )
    scraped.price_unpublished = True
    service = MedicineMarketCheckService()
    monkeypatch.setattr(service, "resolve_source", lambda item: _trusted_source(item))
    monkeypatch.setattr(service, "_parse_snapshot", lambda source: scraped)

    service.run(check.pk)

    medicine.refresh_from_db()
    check.refresh_from_db()
    assert medicine.price == Decimal("100.00")
    assert PriceHistory.objects.filter(product=medicine.base_product).count() == 0
    assert check.status == ProductMarketCheck.Status.FAILED
    assert check.error_code == "price_unpublished"
    assert check.error_message == (
        "Первоисточник указывает цену 0,00 — актуальная цена для этого препарата не опубликована."
    )
    payload = service.serialize(medicine, check)
    assert payload["error"] == {
        "code": "price_unpublished",
        "message": check.error_message,
    }


def test_decimal_zero_price_is_classified_as_unpublished():
    with pytest.raises(MedicineMarketCheckError) as error:
        MedicineMarketCheckService._decimal_price(Decimal("0.00"))

    assert error.value.code == "price_unpublished"


@pytest.mark.django_db
def test_source_resolution_rejects_non_medical_or_untrusted_urls(medicine):
    medicine.external_url = "https://evil.example/ilaclar/lasirin"
    medicine.base_product.external_url = "https://ilacfiyati.com/takviye-edici-gida/vitamin-c"
    medicine.external_data = {}
    medicine.base_product.external_data = {}
    MedicineProduct.objects.filter(pk=medicine.pk).update(
        external_url=medicine.external_url,
        external_data={},
    )
    Product.objects.filter(pk=medicine.base_product_id).update(
        external_url=medicine.base_product.external_url,
        external_data={},
    )

    with pytest.raises(MedicineMarketCheckError) as error:
        MedicineMarketCheckService().resolve_source(medicine)

    assert error.value.code == "invalid_source"
    assert (
        MedicineMarketCheckService._canonical_ilacfiyati_medicine_url(
            "https://ilacfiyati.com:444/ilaclar/lasirin"
        )
        is None
    )


@pytest.mark.django_db
def test_market_check_api_is_idempotent_and_ignores_client_source(medicine, monkeypatch):
    calls = []

    def fake_apply_async(args=None, **kwargs):
        calls.append(args)
        return SimpleNamespace(id="market-task-1")

    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_medicine_market_check_task.apply_async",
        fake_apply_async,
    )
    client = APIClient()
    url = reverse("medicine-product-market-check", kwargs={"slug": medicine.slug})

    first = client.post(
        url,
        {"source_url": "https://evil.example/item", "parser": "evil"},
        format="json",
        REMOTE_ADDR="198.51.100.10",
    )
    second = client.post(url, {}, format="json", REMOTE_ADDR="198.51.100.10")
    read = client.get(url, REMOTE_ADDR="198.51.100.10")

    assert first.status_code == 202
    assert second.status_code == 200
    assert read.status_code == 200
    assert len(calls) == 1
    check = ProductMarketCheck.objects.get(product=medicine.base_product)
    assert check.source_url == "https://ilacfiyati.com/ilaclar/lasirin-20-mg"
    assert check.task_id == "market-task-1"
    assert check.request_count == 2
    assert read.data["status"] == "pending"
    assert "source_url" not in read.data


@pytest.mark.django_db
def test_anonymous_market_check_post_is_rate_limited(medicine, monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_medicine_market_check_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="throttle-task"),
    )
    client = APIClient()
    url = reverse("medicine-product-market-check", kwargs={"slug": medicine.slug})

    responses = [client.post(url, {}, format="json", REMOTE_ADDR="198.51.100.16") for _ in range(4)]

    assert [response.status_code for response in responses] == [202, 200, 200, 429]


@pytest.mark.django_db
def test_market_check_api_returns_fresh_success_without_requeue(medicine, monkeypatch):
    ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.SUCCEEDED,
        observed_price=Decimal("101.00"),
        observed_currency="TRY",
        requested_at=timezone.now(),
        finished_at=timezone.now(),
        last_success_at=timezone.now(),
    )
    apply_async = monkeypatch.setattr(
        "apps.catalog.tasks.refresh_medicine_market_check_task.apply_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not queue")),
    )
    client = APIClient()
    url = reverse("medicine-product-market-check", kwargs={"slug": medicine.slug})

    response = client.post(
        url,
        {},
        format="json",
        HTTP_X_CURRENCY="TRY",
        REMOTE_ADDR="198.51.100.11",
    )

    assert response.status_code == 200
    assert response.data["cached"] is True
    assert response.data["price"] == {"amount": "101.00", "currency": "TRY"}
    assert apply_async is None


@pytest.mark.django_db
def test_market_check_api_adds_selected_currency_price_with_effective_margins(
    medicine,
    monkeypatch,
):
    medicine.category.margin_percent = Decimal("50.00")
    medicine.category.save(update_fields=["margin_percent"])
    ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.SUCCEEDED,
        observed_price=Decimal("100.00"),
        observed_currency="TRY",
        requested_at=timezone.now(),
        finished_at=timezone.now(),
        last_success_at=timezone.now(),
    )

    def convert_price(amount, source, target, apply_margin=True):
        assert (amount, source, target, apply_margin) == (
            Decimal("100.00"),
            "TRY",
            "RUB",
            True,
        )
        return amount, Decimal("200.00"), Decimal("220.00")

    monkeypatch.setattr(
        "apps.catalog.services.market_check_pricing.currency_converter.convert_price",
        convert_price,
    )
    monkeypatch.setattr(
        "apps.catalog.services.market_check_pricing.currency_converter.get_margin_rate",
        lambda source, target: Decimal("10.00"),
    )

    response = APIClient().get(
        reverse("medicine-product-market-check", kwargs={"slug": medicine.slug}),
        HTTP_X_CURRENCY="RUB",
        REMOTE_ADDR="198.51.100.18",
    )

    assert response.status_code == 200
    # Source truth stays untouched for API compatibility and price history.
    assert response.data["price"] == {"amount": "100.00", "currency": "TRY"}
    # Public display follows rate -> pair margin -> category/brand/global markup.
    assert response.data["display_price"] == {"amount": "330.00", "currency": "RUB"}
    assert response.data["price_calculation"] == {
        "source_currency": "TRY",
        "target_currency": "RUB",
        "currency_pair_margin_percent": "10.00",
        "product_markup_percent": "50.00",
        "product_markup_source": "category",
    }


@pytest.mark.django_db
def test_stale_running_check_is_safely_requeued(medicine, monkeypatch):
    stale_time = timezone.now() - timedelta(minutes=10)
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.RUNNING,
        requested_at=stale_time,
        started_at=stale_time,
    )
    calls = []
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_medicine_market_check_task.apply_async",
        lambda args=None, **kwargs: calls.append(args) or SimpleNamespace(id="requeued-task"),
    )
    client = APIClient()
    url = reverse("medicine-product-market-check", kwargs={"slug": medicine.slug})

    response = client.post(url, {}, format="json", REMOTE_ADDR="198.51.100.14")

    assert response.status_code == 202
    assert calls == [[check.pk]]
    check.refresh_from_db()
    assert check.status == ProductMarketCheck.Status.PENDING
    assert check.task_id == "requeued-task"


@pytest.mark.django_db
def test_queue_publish_failure_is_terminal_and_safe(medicine, monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_medicine_market_check_task.apply_async",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broker down")),
    )
    client = APIClient()
    url = reverse("medicine-product-market-check", kwargs={"slug": medicine.slug})

    response = client.post(url, {}, format="json", REMOTE_ADDR="198.51.100.15")

    assert response.status_code == 503
    assert response.data["error"]["code"] == "queue_unavailable"
    check = ProductMarketCheck.objects.get(product=medicine.base_product)
    assert check.status == ProductMarketCheck.Status.SOURCE_UNAVAILABLE
    assert check.error_code == "queue_unavailable"


@pytest.mark.django_db
def test_market_check_api_is_feature_flagged(medicine, settings):
    settings.MEDICINE_MARKET_CHECK_ENABLED = False
    client = APIClient()
    url = reverse("medicine-product-market-check", kwargs={"slug": medicine.slug})

    response = client.post(url, {}, format="json", REMOTE_ADDR="198.51.100.12")

    assert response.status_code == 503
    assert response.data["enabled"] is False
    assert response.data["error"]["code"] == "disabled"
    assert not ProductMarketCheck.objects.exists()


@pytest.mark.django_db
def test_duplicate_task_delivery_does_not_repeat_running_check(medicine, monkeypatch):
    check = ProductMarketCheck.objects.create(
        product=medicine.base_product,
        source="ilacfiyati",
        source_url=medicine.external_url,
        status=ProductMarketCheck.Status.RUNNING,
        requested_at=timezone.now(),
        started_at=timezone.now(),
    )
    service = MedicineMarketCheckService()
    monkeypatch.setattr(
        service,
        "_parse_snapshot",
        lambda source: (_ for _ in ()).throw(AssertionError("must not parse twice")),
    )

    result = service.run(check.pk)

    assert result == {
        "status": ProductMarketCheck.Status.RUNNING,
        "check_id": check.pk,
    }


@pytest.mark.django_db
def test_market_check_api_returns_404_for_unknown_slug():
    client = APIClient()
    url = reverse(
        "medicine-product-market-check",
        kwargs={"slug": "unknown-medicine"},
    )

    response = client.get(url, REMOTE_ADDR="198.51.100.13")

    assert response.status_code == 404


@pytest.mark.django_db
def test_analog_api_returns_unresolved_source_reference(medicine):
    MedicineAnalog.objects.create(
        product=medicine,
        name="UNRESOLVED EQUIVALENT",
        external_id="unresolved-equivalent",
        source="ilacfiyati",
        source_url="https://ilacfiyati.com/ilaclar/unresolved-equivalent",
        source_tab="Eşdeğeri",
        reference_price=Decimal("88.75"),
        reference_currency="TRY",
        last_observed_at=timezone.now(),
    )
    client = APIClient()
    url = reverse("medicine-product-analogs", kwargs={"slug": medicine.slug})

    response = client.get(url, {"limit": 10, "currency": "TRY"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    result = response.data["results"][0]
    assert result["slug"] is None
    assert result["is_catalog_product"] is False
    assert result["is_available"] is None
    assert result["source_reference_price"] == 88.75
    assert result["source_reference_currency"] == "TRY"


def test_market_check_endpoint_uses_trusted_ip_post_throttles():
    action = MedicineProductViewSet.market_check
    assert action.kwargs["throttle_classes"] == MEDICINE_MARKET_CHECK_THROTTLES
    assert action.kwargs["authentication_classes"] == [JWTSafeAuthentication]
    assert all(
        issubclass(throttle, TrustedProxyIPRateThrottle)
        for throttle in MEDICINE_MARKET_CHECK_THROTTLES
    )


@pytest.mark.django_db
def test_public_market_check_does_not_require_csrf_for_unrelated_django_session(
    medicine,
    monkeypatch,
):
    """An admin/session cookie must not turn an AllowAny intent into HTTP 403."""
    user = get_user_model().objects.create_user(
        email="medicine-session@example.test",
        username="medicine-session",
        password="not-used",
    )
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_medicine_market_check_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="session-csrf-task"),
    )
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(
        reverse("medicine-product-market-check", kwargs={"slug": medicine.slug}),
        {},
        format="json",
        REMOTE_ADDR="198.51.100.17",
    )

    assert response.status_code == 202
    assert response.data["queued"] is True


def test_global_source_rate_limit_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "apps.catalog.services.medicine_market_check.cache.add",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("redis down")),
    )
    assert MedicineMarketCheckService._global_rate_allowed("ilacfiyati") is False
