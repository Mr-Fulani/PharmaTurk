from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.db.models.signals import post_save
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    ClothingProduct,
    ClothingVariant,
    ClothingVariantSize,
    PriceHistory,
    Product,
    ProductSourceOffer,
    SupplementProduct,
)
from apps.catalog.services.product_card_source_refresh import (
    ProductCardRefreshError,
    ProductCardSourceRefreshService,
)
from apps.catalog.utils.product_markup import apply_product_markup
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckResult,
    OfferStockPrecision,
)


class DummyZaraParser:
    pass


class DummyAkakceParser:
    def check_offer(self, context):
        raise AssertionError("network adapter must be mocked in this test")


class DummyLcwParser:
    pass


def _fake_registry(value):
    if value == "zara":
        return DummyZaraParser
    if value == "akakce":
        return DummyAkakceParser
    if value == "lcw":
        return DummyLcwParser
    host = (urlparse(str(value or "")).hostname or "").casefold()
    if host == "www.zara.com" or host.endswith(".zara.com"):
        return DummyZaraParser
    if host == "www.akakce.com" or host.endswith(".akakce.com"):
        return DummyAkakceParser
    if host == "www.lcw.com" or host.endswith(".lcw.com"):
        return DummyLcwParser
    return None


@pytest.fixture(autouse=True)
def refresh_settings(settings, monkeypatch):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"product-card-refresh-{uuid4().hex}",
        }
    }
    settings.PRODUCT_CARD_SOURCE_REFRESH_ENABLED = True
    settings.PRODUCT_CARD_SOURCE_REFRESH_SOURCES = ["zara", "akakce", "lcw"]
    settings.PRODUCT_CARD_SOURCE_REFRESH_TIMEOUT_SECONDS = 1
    settings.PRODUCT_CARD_SOURCE_REFRESH_MAX_RETRIES = 0
    settings.PRODUCT_CARD_SOURCE_REFRESH_STATE_TTL_SECONDS = 300
    settings.PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS = 30
    settings.PRODUCT_CARD_SOURCE_REFRESH_LOCK_SECONDS = 150
    settings.PRODUCT_CARD_SOURCE_REFRESH_MIN_PRICE_RATIO = 0.05
    settings.PRODUCT_CARD_SOURCE_REFRESH_MAX_PRICE_RATIO = 20
    settings.SOURCE_OFFER_DEFAULT_CONCURRENCY = 2
    settings.SOURCE_OFFER_SOURCE_CONCURRENCY = {}
    settings.SOURCE_OFFER_DEFAULT_RATE_PER_MINUTE = 100
    settings.SOURCE_OFFER_SOURCE_RATE_PER_MINUTE = {}
    settings.SOURCE_OFFER_CIRCUIT_FAILURE_THRESHOLD = 5
    settings.SOURCE_OFFER_CIRCUIT_RECOVERY_SECONDS = 60
    settings.SOURCE_OFFER_VERIFICATION_ENABLED = True
    settings.SOURCE_OFFER_VERIFICATION_SOURCES = ["akakce"]
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.get_parser",
        _fake_registry,
    )
    monkeypatch.setattr(
        "apps.catalog.services.product_card_source_refresh.get_parser",
        _fake_registry,
    )
    cache.clear()
    yield
    cache.clear()


def _offer(product, *, variant="black", size="S", price="100.00"):
    return ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/test-product-p100.html",
        external_product_id="zara-100",
        external_sku=f"SKU-{variant}-{size}" if size else f"SKU-{variant}",
        variant_key=variant,
        size_key=size,
        selected_options={"color": variant, "size": size},
        source_price=Decimal(price),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )


@pytest.fixture
def parsed_clothing(db):
    category = Category.objects.create(
        name="Parsed clothing",
        slug=f"parsed-clothing-{uuid4().hex}",
        margin_percent=Decimal("10"),
    )
    domain = ClothingProduct.objects.create(
        name="Curated product name",
        slug=f"curated-zara-product-{uuid4().hex}",
        description="Manually curated description",
        category=category,
        price=Decimal("100.00"),
        currency="TRY",
        old_price=Decimal("160.00"),
        external_id="zara-100",
        external_url="https://www.zara.com/tr/tr/test-product-p100.html",
        external_data={"source": "zara", "editor_note": "keep"},
        is_available=True,
    )
    domain.refresh_from_db()
    product = domain.base_product
    black = ClothingVariant.objects.create(
        product=domain,
        name="Curated black title",
        color="Siyah",
        sku="SKU-black",
        external_id="black",
        price=Decimal("100.00"),
        currency="TRY",
        old_price=Decimal("150.00"),
        is_available=False,
        stock_quantity=0,
    )
    ClothingVariant.objects.filter(pk=black.pk).update(
        main_image="https://manual.example/black.jpg"
    )
    ClothingVariantSize.objects.create(
        variant=black,
        size="S",
        is_available=False,
        stock_quantity=0,
    )
    red = ClothingVariant.objects.create(
        product=domain,
        name="Existing red title",
        color="Kırmızı",
        sku="SKU-red",
        external_id="red",
        price=Decimal("105.00"),
        currency="TRY",
        is_available=True,
        stock_quantity=None,
    )
    ClothingVariantSize.objects.create(
        variant=red,
        size="XL",
        is_available=True,
        stock_quantity=None,
    )
    _offer(product, variant="black", size="S")
    _offer(product, variant="red", size="XL", price="105.00")
    return product, domain, black, red


def _scraped(*, external_id="zara-100"):
    return ScrapedProduct(
        name="Supplier title must not overwrite",
        description="Supplier description must not overwrite",
        price=120,
        currency="TRY",
        url="https://www.zara.com/tr/tr/test-product-p100.html",
        external_id=external_id,
        sku="100",
        source="zara",
        is_available=True,
        attributes={
            "fashion_variants": [
                {
                    "external_id": "black",
                    "display_name": "Supplier black title",
                    "color": "Siyah",
                    "sku": "SKU-black",
                    "price": 120,
                    "currency": "TRY",
                    "external_url": "https://www.zara.com/tr/tr/test-product-p100.html",
                    "images": ["https://supplier.example/new-black.jpg"],
                    "is_available": True,
                    "sizes": [
                        {"size": "S", "is_available": True, "sort_order": 0},
                        {"size": "M", "is_available": False, "sort_order": 1},
                    ],
                },
                {
                    "external_id": "blue",
                    "display_name": "Blue variant",
                    "color": "Mavi",
                    "sku": "SKU-blue",
                    "price": 130,
                    "currency": "TRY",
                    "external_url": "https://www.zara.com/tr/tr/test-product-p100.html",
                    "images": ["https://supplier.example/blue.jpg"],
                    "is_available": True,
                    "sizes": [{"size": "L", "is_available": True, "sort_order": 0}],
                },
            ]
        },
    )


def test_flo_card_fetch_explicitly_requests_web_unlocker(settings, monkeypatch):
    settings.FLO_WEB_UNLOCKER_ENABLED = True
    settings.FLO_WEB_UNLOCKER_TIMEOUT_SECONDS = 19
    captured = {}

    class FloCaptureParser:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def configure_request_identity(self, **_kwargs):
            return None

        def parse_product_detail(self, url, **kwargs):
            captured["detail_kwargs"] = kwargs
            return ScrapedProduct(
                name="FLO product",
                url=url,
                source="flo",
                external_id="flo-10001",
            )

    config = SimpleNamespace(
        base_url="https://www.flo.com.tr",
        use_proxy=True,
        scraper_username="",
        scraper_password="",
        delay_min=0,
        delay_max=0,
        user_agent="",
        headers={},
        cookies={},
    )
    target = SimpleNamespace(
        parser_key="flo",
        parser_class=FloCaptureParser,
        offer=SimpleNamespace(
            canonical_url="https://www.flo.com.tr/urun/model-10001"
        ),
    )
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(service, "_scraper_config", lambda _offer: config)

    result = service._fetch_product(target)

    assert result.source == "flo"
    assert captured["use_proxy"] is True
    assert captured["use_web_unlocker"] is True
    assert captured["timeout"] == 19.0
    assert captured["detail_kwargs"] == {"include_sibling_variants": False}


def test_flo_card_fetch_maps_clean_page_without_product_to_not_found(
    settings,
    monkeypatch,
):
    settings.FLO_WEB_UNLOCKER_ENABLED = True

    class RemovedFloParser:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return None

        def configure_request_identity(self, **_kwargs):
            return None

        def parse_product_detail(self, _url, **kwargs):
            assert kwargs == {"include_sibling_variants": False}
            return None

    config = SimpleNamespace(
        base_url="https://www.flo.com.tr",
        use_proxy=True,
        scraper_username="",
        scraper_password="",
        delay_min=0,
        delay_max=0,
        user_agent="",
        headers={},
        cookies={},
    )
    target = SimpleNamespace(
        parser_key="flo",
        parser_class=RemovedFloParser,
        offer=SimpleNamespace(
            canonical_url="https://www.flo.com.tr/urun/removed-model-10001"
        ),
    )
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(service, "_scraper_config", lambda _offer: config)

    with pytest.raises(ProductCardRefreshError) as error:
        service._fetch_product(target)

    assert error.value.code == "source_not_found"
    assert error.value.retryable is False


@pytest.mark.django_db
def test_source_not_found_disables_only_variants_on_opened_url(
    parsed_clothing,
    monkeypatch,
):
    product, domain, black, red = parsed_clothing
    black_url = "https://www.zara.com/tr/tr/black-product-p100.html"
    red_url = "https://www.zara.com/tr/tr/red-product-p101.html"
    product.source_offers.filter(variant_key="black").update(
        canonical_url=black_url,
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
        last_error_code="",
    )
    product.source_offers.filter(variant_key="red").update(
        canonical_url=red_url,
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
        last_error_code="",
    )
    ClothingVariant.objects.filter(pk=black.pk).update(
        is_available=True,
        stock_quantity=None,
    )
    ClothingVariantSize.objects.filter(variant=black).update(
        is_available=True,
        stock_quantity=None,
    )

    service = ProductCardSourceRefreshService()

    def removed(_target):
        raise ProductCardRefreshError(
            "source_not_found",
            "Supplier product was not found",
            retryable=False,
        )

    monkeypatch.setattr(service, "_fetch_product", removed)

    result = service.run(product.pk)

    assert result["status"] == "failed"
    assert result["error_code"] == "source_not_found"
    assert result["retryable"] is False
    assert result["changes"] == {
        "offers_updated": 1,
        "variants_updated": 1,
        "sizes_updated": 1,
        "product_updated": 0,
    }
    black.refresh_from_db()
    red.refresh_from_db()
    domain.refresh_from_db()
    assert black.is_available is False
    assert black.stock_quantity == 0
    assert red.is_available is True
    assert domain.is_available is True
    assert set(
        product.source_offers.filter(variant_key="black").values_list(
            "availability_status", "last_error_code"
        )
    ) == {(ProductSourceOffer.AvailabilityStatus.OUT_OF_STOCK, "not_found")}
    assert set(
        product.source_offers.filter(variant_key="red").values_list(
            "availability_status", "last_error_code"
        )
    ) == {(ProductSourceOffer.AvailabilityStatus.IN_STOCK, "")}


@pytest.mark.django_db
def test_manual_product_is_never_enqueued(monkeypatch):
    product = Product.objects.create(
        name="Manual product",
        slug=f"manual-{uuid4().hex}",
        product_type="accessories",
        price=Decimal("50.00"),
        currency="TRY",
    )
    calls = []
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_product_card_source_task.apply_async",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = ProductCardSourceRefreshService().request_refresh(product)

    assert result == {"eligible": False, "status": "not_eligible", "retryable": False}
    assert calls == []


@pytest.mark.django_db
def test_success_updates_only_raw_price_inventory_and_observed_options(
    parsed_clothing,
    monkeypatch,
):
    product, domain, black, red = parsed_clothing
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(service, "_fetch_product", lambda target: _scraped())
    original_domain_external_data = dict(domain.external_data)
    product_save_signals = []

    def capture_product_save(sender, instance, **kwargs):
        if instance.pk == product.pk:
            product_save_signals.append(kwargs)

    post_save.connect(
        capture_product_save,
        sender=Product,
        weak=False,
        dispatch_uid="test_product_card_refresh_does_not_emit_product_save",
    )

    try:
        result = service.run(product.pk)
    finally:
        post_save.disconnect(
            sender=Product,
            dispatch_uid="test_product_card_refresh_does_not_emit_product_save",
        )

    assert result["status"] == "succeeded"
    product.refresh_from_db()
    domain.refresh_from_db()
    black.refresh_from_db()
    red.refresh_from_db()
    assert product.price == Decimal("120.00")
    assert domain.price == Decimal("120.00")
    assert product.old_price == domain.old_price == Decimal("160.00")
    assert product.currency == domain.currency == "TRY"
    assert product.description == "Manually curated description"
    assert domain.description == "Manually curated description"
    assert product.external_data["editor_note"] == "keep"
    assert domain.external_data == original_domain_external_data
    assert product_save_signals == []
    assert black.name == "Curated black title"
    assert black.main_image == "https://manual.example/black.jpg"
    assert black.price == Decimal("120.00")
    assert black.old_price == Decimal("150.00")
    assert black.is_available is True
    assert black.stock_quantity is None
    assert black.sizes.get(size="S").is_available is True
    assert black.sizes.get(size="M").is_available is False

    blue = domain.variants.get(external_id="blue")
    assert blue.is_active is True
    assert blue.is_available is True
    assert blue.sizes.get(size="L").is_available is True
    # Missing from one response is not evidence of removal or unavailability.
    assert red.is_active is True
    assert red.is_available is True
    assert product.source_offers.get(variant_key="red", size_key="XL").is_active is True
    assert product.source_offers.get(variant_key="black", size_key="S").availability_status == "in_stock"
    assert product.source_offers.get(variant_key="blue", size_key="L").is_active is True
    assert PriceHistory.objects.filter(
        product=product,
        price=Decimal("120.00"),
        source="product_card_refresh:zara",
    ).exists()
    # The service stores source truth; existing currency + product markup stays public-only.
    assert apply_product_markup(product.price, product) == Decimal("132.00")


@pytest.mark.django_db
def test_identity_error_keeps_card_and_offers_unchanged(parsed_clothing, monkeypatch):
    product, domain, black, red = parsed_clothing
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(
        service,
        "_fetch_product",
        lambda target: _scraped(external_id="zara-different-product"),
    )
    original_offer_values = list(
        product.source_offers.order_by("id").values_list(
            "id", "source_price", "availability_status", "last_checked_at"
        )
    )

    result = service.run(product.pk)

    assert result["status"] == "failed"
    assert result["error_code"] == "identity_mismatch"
    assert result["retryable"] is False
    product.refresh_from_db()
    domain.refresh_from_db()
    black.refresh_from_db()
    red.refresh_from_db()
    assert product.price == domain.price == Decimal("100.00")
    assert black.price == Decimal("100.00")
    assert red.price == Decimal("105.00")
    assert list(
        product.source_offers.order_by("id").values_list(
            "id", "source_price", "availability_status", "last_checked_at"
        )
    ) == original_offer_values
    assert PriceHistory.objects.filter(product=product).count() == 0


@pytest.mark.django_db
def test_lcw_group_id_drift_is_allowed_only_for_the_exact_saved_variant(
    parsed_clothing,
    monkeypatch,
):
    product, domain, black, _red = parsed_clothing
    lcw_url = "https://www.lcw.com/test-product-lacivert-o-200"
    black.external_id = "lcw-var-200"
    black.save(update_fields=["external_id"])
    offers = list(product.source_offers.order_by("id"))
    selected_offer = offers[0]
    selected_offer.parser_key = "lcw"
    selected_offer.canonical_url = lcw_url
    selected_offer.external_product_id = "lcw-100"
    selected_offer.variant_key = "lcw-var-200"
    selected_offer.source_domain = ""
    selected_offer.offer_key = ""
    selected_offer.save()
    offers[1].parser_key = "lcw"
    offers[1].canonical_url = "https://www.lcw.com/test-product-red-o-300"
    offers[1].external_product_id = "lcw-100"
    offers[1].source_domain = ""
    offers[1].offer_key = ""
    offers[1].save()

    scraped = ScrapedProduct(
        name="Supplier title",
        price=120,
        currency="TRY",
        url=lcw_url,
        external_id="lcw-200",
        source="lcw",
        is_available=True,
        attributes={
            "fashion_variants": [
                {
                    "external_id": "lcw-var-200",
                    "external_url": lcw_url,
                    "display_name": "Supplier blue title",
                    "color": "Lacivert",
                    "sku": "SKU-black-S",
                    "price": 120,
                    "currency": "TRY",
                    "is_available": True,
                    "sizes": [{"size": "S", "is_available": True}],
                }
            ]
        },
    )
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(service, "_fetch_product", lambda target: scraped)

    result = service.run(product.pk)

    assert result["status"] == "succeeded"
    product.refresh_from_db()
    domain.refresh_from_db()
    black.refresh_from_db()
    selected_offer.refresh_from_db()
    assert product.price == domain.price == black.price == Decimal("120.00")
    assert selected_offer.external_product_id == "lcw-200"
    assert selected_offer.variant_key == "lcw-var-200"
    assert product.source_offers.filter(parser_key="lcw").count() == 2


@pytest.mark.django_db
def test_lcw_group_id_drift_rejects_a_different_variant(parsed_clothing, monkeypatch):
    product, domain, black, _red = parsed_clothing
    lcw_url = "https://www.lcw.com/test-product-lacivert-o-200"
    offer = product.source_offers.order_by("id").first()
    offer.parser_key = "lcw"
    offer.canonical_url = lcw_url
    offer.external_product_id = "lcw-100"
    offer.variant_key = "lcw-var-200"
    offer.source_domain = ""
    offer.offer_key = ""
    offer.save()
    product.source_offers.exclude(pk=offer.pk).update(is_active=False)
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(
        service,
        "_fetch_product",
        lambda target: ScrapedProduct(
            name="Different supplier item",
            price=120,
            currency="TRY",
            url=lcw_url,
            external_id="lcw-999",
            source="lcw",
            is_available=True,
            attributes={
                "fashion_variants": [
                    {
                        "external_id": "lcw-var-999",
                        "external_url": lcw_url,
                        "price": 120,
                        "currency": "TRY",
                        "is_available": True,
                        "sizes": [{"size": "S", "is_available": True}],
                    }
                ]
            },
        ),
    )

    result = service.run(product.pk)

    assert result["status"] == "failed"
    assert result["error_code"] == "identity_mismatch"
    product.refresh_from_db()
    domain.refresh_from_db()
    black.refresh_from_db()
    assert product.price == domain.price == black.price == Decimal("100.00")


@pytest.mark.django_db
def test_lcw_partial_variant_without_sizes_does_not_duplicate_saved_size_offers(
    parsed_clothing,
    monkeypatch,
):
    product, domain, black, _red = parsed_clothing
    lcw_url = "https://www.lcw.com/test-product-lacivert-o-200"
    black.external_id = "lcw-var-200"
    black.save(update_fields=["external_id"])
    offers = list(product.source_offers.order_by("id"))
    selected_offer = offers[0]
    selected_offer.parser_key = "lcw"
    selected_offer.canonical_url = lcw_url
    selected_offer.external_product_id = "lcw-100"
    selected_offer.variant_key = "lcw-var-200"
    selected_offer.source_domain = ""
    selected_offer.offer_key = ""
    selected_offer.save()
    offers[1].is_active = False
    offers[1].save(update_fields=["is_active"])
    service = ProductCardSourceRefreshService()
    monkeypatch.setattr(
        service,
        "_fetch_product",
        lambda target: ScrapedProduct(
            name="Supplier title",
            price=120,
            currency="TRY",
            url=lcw_url,
            external_id="lcw-200",
            source="lcw",
            is_available=True,
            attributes={
                "fashion_variants": [
                    {
                        "external_id": "lcw-var-200",
                        "external_url": lcw_url,
                        "price": 120,
                        "currency": "TRY",
                        "is_available": False,
                        "sizes": [],
                    }
                ]
            },
        ),
    )

    result = service.run(product.pk)

    assert result["status"] == "succeeded"
    assert result["changes"]["offers_observed"] == 1
    product.refresh_from_db()
    domain.refresh_from_db()
    black.refresh_from_db()
    assert product.price == domain.price == black.price == Decimal("120.00")
    assert black.is_available is False
    assert product.source_offers.filter(parser_key="lcw", is_active=True).count() == 1
    assert not product.source_offers.filter(parser_key="lcw", size_key="").exists()


@pytest.mark.django_db
def test_repeated_open_uses_one_pending_task(parsed_clothing, monkeypatch):
    product, *_ = parsed_clothing
    calls = []
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_product_card_source_task.apply_async",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    service = ProductCardSourceRefreshService()

    first = service.request_refresh(product)
    second = service.request_refresh(product)

    assert first["status"] == second["status"] == "pending"
    assert len(calls) == 1


@pytest.mark.django_db
def test_new_card_open_enqueues_after_previous_refresh_finished(
    parsed_clothing,
    monkeypatch,
):
    product, *_ = parsed_clothing
    calls = []
    monkeypatch.setattr(
        "apps.catalog.tasks.refresh_product_card_source_task.apply_async",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    service = ProductCardSourceRefreshService()
    service._set_state(
        product.pk,
        {"status": "succeeded", "source": "zara", "retryable": False},
    )

    result = service.request_refresh(product)

    assert result["status"] == "pending"
    assert len(calls) == 1


@pytest.mark.django_db
def test_supplement_single_offer_refresh_uses_commercial_adapter(monkeypatch):
    supplement = SupplementProduct.objects.create(
        name="Parsed supplement",
        slug=f"parsed-supplement-{uuid4().hex}",
        price=Decimal("200.00"),
        currency="TRY",
        external_id="reference-catalog-id",
        external_data={"source": "ilacfiyati"},
        is_available=True,
    )
    supplement.refresh_from_db()
    product = supplement.base_product
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="akakce",
        canonical_url="https://www.akakce.com/vitamin-mineral/test-fiyati,123.html",
        external_product_id="akakce-123",
        source_price=Decimal("200.00"),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
        response_metadata={"seller_name": "Trusted seller"},
    )
    monkeypatch.setattr(
        "apps.catalog.services.source_offer_verification.SourceOfferVerificationService.verify",
        lambda self, saved_offer, force=False: OfferCheckResult(
            availability_status=OfferAvailability.IN_STOCK,
            stock_precision=OfferStockPrecision.BOOLEAN,
            canonical_url=saved_offer.canonical_url,
            source_price=Decimal("150.00"),
            source_currency="TRY",
            response_metadata={"seller_name": "Trusted seller"},
        ),
    )

    result = ProductCardSourceRefreshService().run(product.pk)

    assert result["status"] == "succeeded"
    product.refresh_from_db()
    supplement.refresh_from_db()
    offer.refresh_from_db()
    assert product.price == supplement.price == Decimal("150.00")
    assert product.is_available is True
    # Full-card reconcile must not erase seller diagnostics already owned by verifier.
    assert offer.response_metadata == {"seller_name": "Trusted seller"}


@pytest.mark.django_db
def test_source_refresh_api_is_noop_for_manual_product():
    product = Product.objects.create(
        name="Manual API product",
        slug=f"manual-api-{uuid4().hex}",
        product_type="accessories",
        price=Decimal("50.00"),
        currency="TRY",
    )

    response = APIClient().post(f"/api/catalog/products/{product.slug}/source-refresh")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "eligible": False,
        "status": "not_eligible",
        "retryable": False,
    }
