from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.authentication import JWTSafeAuthentication
from apps.catalog.models import (
    Category,
    PriceHistory,
    Product,
    ProductMarketCheck,
    ProductSourceOffer,
    SupplementProduct,
)
from apps.catalog.services.supplement_availability import SupplementAvailabilityService
from apps.catalog.services.supplement_market_check import (
    SupplementMarketCheckError,
    SupplementMarketCheckService,
    TrustedSupplementSource,
)
from apps.catalog.views import SupplementProductViewSet
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def supplement(settings):
    settings.SUPPLEMENT_MARKET_CHECK_ENABLED = True
    settings.SUPPLEMENT_MARKET_CHECK_SOURCES = ["ilacfiyati"]
    settings.SUPPLEMENT_MARKET_CHECK_GLOBAL_RATE_PER_MINUTE = 100
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = []
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = ["ilacfiyati"]
    category = Category.objects.create(
        name="Supplement market test",
        slug="supplement-market-test",
    )
    base = Product.objects.create(
        name="ANEVITA FOLIC ACID",
        slug="anevita-market-check",
        product_type="supplements",
        category=category,
        price=Decimal("49.70"),
        currency="TRY",
        is_available=False,
        stock_quantity=None,
        external_id="anevita-folic-acid",
        external_url=(
            "https://ilacfiyati.com/takviye-edici-gida/" "anevita-folic-acid-tablet-90-tablet"
        ),
        external_data={"source": "ilacfiyati"},
    )
    item = SupplementProduct.objects.get(base_product=base)
    SupplementProduct.objects.filter(pk=item.pk).update(
        external_url=base.external_url,
        external_data={"source": "ilacfiyati"},
        is_available=False,
        stock_quantity=None,
        dosage_form="tablet",
    )
    item.refresh_from_db()
    ScraperConfig.objects.create(
        name="ilacfiyati-supplement-market-test",
        parser_class="ilacfiyati",
        base_url="https://ilacfiyati.com",
        default_category=category,
        status="active",
        is_enabled=True,
        priority=1,
        max_retries=1,
    )
    return item


def _trusted_source():
    return TrustedSupplementSource(
        key="ilacfiyati",
        url=("https://ilacfiyati.com/takviye-edici-gida/" "anevita-folic-acid-tablet-90-tablet"),
        parser_class=IlacFiyatiParser,
        config=ScraperConfig.objects.get(name="ilacfiyati-supplement-market-test"),
    )


@pytest.mark.django_db
def test_market_check_updates_price_without_projecting_fake_stock(supplement, monkeypatch):
    check = ProductMarketCheck.objects.create(
        product=supplement.base_product,
        source="ilacfiyati",
        source_url=supplement.external_url,
        status=ProductMarketCheck.Status.PENDING,
        requested_at=timezone.now(),
    )
    service = SupplementMarketCheckService()
    monkeypatch.setattr(service, "resolve_source", lambda item: _trusted_source())
    monkeypatch.setattr(
        service,
        "_parse_snapshot",
        lambda source: ScrapedProduct(
            name=supplement.name,
            price=Decimal("59.90"),
            currency="TRY",
            url=supplement.external_url,
            source="ilacfiyati",
            is_available=True,
            stock_quantity=3,
        ),
    )
    monkeypatch.setattr(
        "apps.catalog.services.supplement_stock_discovery."
        "SupplementStockDiscoveryService.discover",
        lambda *_args, **_kwargs: pytest.fail(
            "reference-price worker must not run stock discovery"
        ),
    )

    result = service.run(check.pk)

    assert result["status"] == ProductMarketCheck.Status.SUCCEEDED
    supplement.refresh_from_db()
    supplement.base_product.refresh_from_db()
    check.refresh_from_db()
    assert supplement.price == Decimal("59.90")
    assert supplement.old_price == Decimal("49.70")
    assert supplement.is_available is False
    assert supplement.stock_quantity is None
    assert supplement.base_product.is_available is False
    assert supplement.base_product.stock_quantity is None
    assert check.observed_price == Decimal("59.90")
    assert check.analog_count == 0
    assert PriceHistory.objects.filter(
        product=supplement.base_product,
        source="ilacfiyati_supplement_on_demand",
        price=Decimal("59.90"),
    ).exists()


@pytest.mark.django_db
def test_stock_discovery_is_queued_even_when_reference_source_fails(
    supplement,
    settings,
    monkeypatch,
):
    settings.SUPPLEMENT_STOCK_DISCOVERY_ENABLED = True
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["akakce"]
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = ["ilacfiyati", "akakce"]
    ScraperConfig.objects.create(
        name="akakce-independent-discovery",
        parser_class="akakce",
        base_url="https://www.akakce.com",
        default_category=supplement.category,
        status="active",
        is_enabled=True,
        use_proxy=True,
        sync_enabled=False,
    )
    calls = []
    monkeypatch.setattr(
        "apps.catalog.tasks.discover_supplement_stock_offer_task.apply_async",
        lambda args=None, **kwargs: calls.append(args) or SimpleNamespace(id="stock-task"),
    )
    service = SupplementMarketCheckService()

    def fail_source(_supplement):
        raise SupplementMarketCheckError("invalid_source", "missing reference source")

    monkeypatch.setattr(service, "resolve_source", fail_source)

    with pytest.raises(SupplementMarketCheckError, match="missing reference source"):
        service.request_check(supplement)

    assert calls == [[supplement.pk]]
    assert not ProductMarketCheck.objects.exists()


@pytest.mark.django_db
def test_source_resolution_accepts_only_trusted_supplement_path(supplement):
    source = SupplementMarketCheckService().resolve_source(supplement)
    assert source.url.endswith("/anevita-folic-acid-tablet-90-tablet")
    assert (
        SupplementMarketCheckService._canonical_ilacfiyati_supplement_url(
            "https://ilacfiyati.com/ilaclar/not-a-supplement"
        )
        is None
    )
    assert (
        SupplementMarketCheckService._canonical_ilacfiyati_supplement_url(
            "https://evil.example/takviye-edici-gida/anevita"
        )
        is None
    )


@pytest.mark.django_db
def test_market_check_api_is_idempotent_and_client_cannot_choose_source(
    supplement,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_supplement_market_check_task.apply_async",
        lambda args=None, **kwargs: calls.append(args) or SimpleNamespace(id="supplement-task"),
    )
    client = APIClient()
    url = reverse("supplement-product-market-check", kwargs={"slug": supplement.slug})

    first = client.post(
        url,
        {"source_url": "https://evil.example/item", "parser": "evil"},
        format="json",
        REMOTE_ADDR="198.51.100.30",
    )
    second = client.post(url, {}, format="json", REMOTE_ADDR="198.51.100.30")
    read = client.get(url, REMOTE_ADDR="198.51.100.30")

    assert first.status_code == 202
    assert second.status_code == 200
    assert read.status_code == 200
    assert calls == [[ProductMarketCheck.objects.get().pk]]
    assert first.data["stock_discovery_status"] == "disabled"
    assert read.data["status"] == "pending"
    assert read.data["availability"]["can_add_to_cart"] is True
    assert read.data["availability"]["status"] == "catalog"
    assert "source_url" not in read.data


@pytest.mark.django_db
def test_market_check_api_is_feature_flagged(supplement, settings):
    settings.SUPPLEMENT_MARKET_CHECK_ENABLED = False
    response = APIClient().post(
        reverse("supplement-product-market-check", kwargs={"slug": supplement.slug}),
        {},
        format="json",
        REMOTE_ADDR="198.51.100.31",
    )

    assert response.status_code == 503
    assert response.data["enabled"] is False
    assert response.data["error"]["code"] == "disabled"
    assert not ProductMarketCheck.objects.exists()


@pytest.mark.django_db
def test_supplement_market_check_adds_selected_currency_public_price(
    supplement,
    monkeypatch,
):
    supplement.category.margin_percent = Decimal("25.00")
    supplement.category.save(update_fields=["margin_percent"])
    ProductMarketCheck.objects.create(
        product=supplement.base_product,
        source="ilacfiyati",
        source_url=supplement.external_url,
        status=ProductMarketCheck.Status.SUCCEEDED,
        observed_price=Decimal("49.70"),
        observed_currency="TRY",
        requested_at=timezone.now(),
        finished_at=timezone.now(),
        last_success_at=timezone.now(),
    )
    monkeypatch.setattr(
        "apps.catalog.services.market_check_pricing.currency_converter.convert_price",
        lambda amount, source, target, apply_margin=True: (
            amount,
            Decimal("10.00"),
            Decimal("11.00"),
        ),
    )
    monkeypatch.setattr(
        "apps.catalog.services.market_check_pricing.currency_converter.get_margin_rate",
        lambda source, target: Decimal("10.00"),
    )

    response = APIClient().get(
        reverse("supplement-product-market-check", kwargs={"slug": supplement.slug}),
        HTTP_X_CURRENCY="USD",
        REMOTE_ADDR="198.51.100.33",
    )

    assert response.status_code == 200
    assert response.data["price"] == {"amount": "49.70", "currency": "TRY"}
    assert response.data["display_price"] == {"amount": "13.75", "currency": "USD"}
    assert response.data["price_calculation"]["product_markup_source"] == "category"
    assert response.data["price_calculation"]["product_markup_percent"] == "25.00"


@pytest.mark.django_db
def test_public_market_check_does_not_require_csrf_for_unrelated_django_session(
    supplement,
    monkeypatch,
):
    user = get_user_model().objects.create_user(
        email="supplement-session@example.test",
        username="supplement-session",
        password="not-used",
    )
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_supplement_market_check_task.apply_async",
        lambda *args, **kwargs: SimpleNamespace(id="supplement-session-csrf-task"),
    )
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.post(
        reverse("supplement-product-market-check", kwargs={"slug": supplement.slug}),
        {},
        format="json",
        REMOTE_ADDR="198.51.100.32",
    )

    assert response.status_code == 202
    assert response.data["queued"] is True


def test_market_check_endpoint_uses_jwt_only_authentication():
    action = SupplementProductViewSet.market_check
    assert action.kwargs["authentication_classes"] == [JWTSafeAuthentication]


@pytest.mark.django_db
def test_supplement_detail_exposes_normal_catalog_sale_when_enforcement_is_off(supplement):
    response = APIClient().get(
        reverse("supplement-product-detail", kwargs={"slug": supplement.slug})
    )

    assert response.status_code == 200
    assert response.data["purchase_mode"] == "catalog_sale"
    assert response.data["can_add_to_cart"] is True
    assert response.data["availability_verification"] == "catalog"


@pytest.mark.django_db
def test_supplement_sale_capability_ignores_reference_price_source(supplement, settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["ilacfiyati"]

    capability = SupplementAvailabilityService().capability(supplement)

    assert capability.can_add_to_cart is True
    assert capability.purchase_mode == "catalog_sale"
    assert capability.availability_verification == "informational"


@pytest.mark.django_db
def test_supplement_sale_capability_requires_enabled_explicit_adapter(
    supplement,
    settings,
):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = ["ikea"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["ikea"]
    ProductSourceOffer.objects.create(
        product=supplement.base_product,
        parser_key="ikea",
        canonical_url="https://www.ikea.com.tr/urun/test-supplement",
        source_price=Decimal("59.90"),
        source_currency="TRY",
    )

    capability = SupplementAvailabilityService().capability(supplement)

    assert capability.can_add_to_cart is True
    assert capability.purchase_mode == "verified_sale"
    assert capability.availability_verification == "live_on_cart"

    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = False
    disabled = SupplementAvailabilityService().capability(supplement)
    assert disabled.can_add_to_cart is True
    assert disabled.purchase_mode == "catalog_sale"


def test_invalid_supplement_price_is_rejected():
    with pytest.raises(SupplementMarketCheckError) as error:
        SupplementMarketCheckService._decimal_price(None)
    assert error.value.code == "price_missing"
