from decimal import Decimal
from uuid import uuid4

import pytest

from apps.catalog.models import Product, ProductSourceOffer, ShoeProduct, ShoeVariant
from apps.orders.cart_source_verification import CartSourceOfferPolicy
from apps.orders.models import CartItem
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckError,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferStockPrecision,
)


class FakeVerifier:
    def __init__(self, result, enabled_sources=("zara",)):
        self.result = result
        self.enabled_sources = set(enabled_sources)
        self.calls = []

    def is_enabled_for(self, parser_key):
        return parser_key in self.enabled_sources

    def verify(self, offer, *, force=False):
        self.calls.append((offer.pk, force))
        return self.result


def _result(
    *,
    availability=OfferAvailability.IN_STOCK,
    price="100.00",
    precision=OfferStockPrecision.BOOLEAN,
    quantity=None,
    error=None,
):
    return OfferCheckResult(
        availability_status=availability,
        stock_precision=precision,
        stock_quantity=quantity,
        canonical_url="https://www.zara.com/tr/tr/product-p1.html",
        source_price=Decimal(price) if price is not None else None,
        source_currency="TRY",
        error=error,
    )


def test_cart_policy_explicitly_allows_interactive_web_unlocker():
    policy = CartSourceOfferPolicy()

    assert policy.verifier.allow_web_unlocker is True


@pytest.fixture(autouse=True)
def cart_enforcement(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True


@pytest.fixture
def offer_product(db):
    source_product = Product.objects.create(
        name="Source product",
        slug=f"source-product-{uuid4().hex}",
        product_type="clothing",
    )
    shadow = Product.objects.create(
        name="Shadow variant",
        slug=f"shadow-product-{uuid4().hex}",
        product_type="clothing",
        external_data={
            "source_offer_product_id": source_product.pk,
            "source_offer_variant_key": "black",
            "source_parser": "zara",
        },
    )
    matching = ProductSourceOffer.objects.create(
        product=source_product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/product-p1.html",
        external_product_id="p1",
        external_sku="p1-black-m",
        variant_key="black",
        size_key="M",
        priority=10,
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )
    ProductSourceOffer.objects.create(
        product=source_product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/product-p1.html",
        external_product_id="p1",
        external_sku="p1-red-m",
        variant_key="red",
        size_key="M",
        priority=1,
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )
    return shadow, matching


@pytest.mark.django_db
def test_policy_selects_exact_server_owned_variant_and_size(offer_product):
    shadow, matching = offer_product
    verifier = FakeVerifier(_result())

    selected = CartSourceOfferPolicy(verifier).select_offer(
        product=shadow,
        chosen_size="m",
    )

    assert selected == matching


@pytest.mark.django_db
def test_policy_resolves_legacy_variant_shadow_through_parent_base_product():
    source_product = Product.objects.create(
        name="Legacy FLO source product",
        slug=f"legacy-flo-source-{uuid4().hex}",
        product_type="shoes",
    )
    domain_product = ShoeProduct.objects.get(base_product=source_product)
    variant = ShoeVariant.objects.create(
        product=domain_product,
        name="Black",
        slug=f"legacy-flo-variant-{uuid4().hex}",
        external_id="flo-variant-10001",
        price=Decimal("100.00"),
        currency="TRY",
    )
    shadow = Product.objects.create(
        name="Legacy FLO shadow",
        slug=f"legacy-flo-shadow-{uuid4().hex}",
        product_type="shoes",
        external_data={"source_variant_id": variant.pk},
    )
    matching = ProductSourceOffer.objects.create(
        product=source_product,
        parser_key="flo",
        canonical_url="https://www.flo.com.tr/urun/model-10001",
        external_product_id="flo-10001",
        external_sku="10001",
        variant_key=variant.external_id,
        size_key="40",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )
    ProductSourceOffer.objects.create(
        product=source_product,
        parser_key="flo",
        canonical_url="https://www.flo.com.tr/urun/other-20002",
        external_product_id="flo-20002",
        external_sku="20002",
        variant_key="flo-variant-20002",
        size_key="40",
        priority=1,
    )

    selected = CartSourceOfferPolicy(
        FakeVerifier(_result(), enabled_sources=("flo",))
    ).select_offer(product=shadow, chosen_size="40")

    assert selected == matching


@pytest.mark.django_db
def test_policy_fails_closed_for_stale_legacy_variant_identity():
    shadow = Product.objects.create(
        name="Stale variant shadow",
        slug=f"stale-variant-shadow-{uuid4().hex}",
        product_type="shoes",
        external_data={"source_variant_id": 999_999_999},
    )
    ProductSourceOffer.objects.create(
        product=shadow,
        parser_key="flo",
        canonical_url="https://www.flo.com.tr/urun/wrong-fallback-10001",
        external_product_id="flo-10001",
        external_sku="10001",
        variant_key="flo-variant-10001",
        size_key="40",
    )

    selected = CartSourceOfferPolicy(
        FakeVerifier(_result(), enabled_sources=("flo",))
    ).select_offer(product=shadow, chosen_size="40")

    assert selected is None


@pytest.mark.django_db
def test_policy_flag_off_avoids_offer_query_and_verifier(
    offer_product, settings, django_assert_num_queries
):
    shadow, _matching = offer_product
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = False
    verifier = FakeVerifier(_result())

    with django_assert_num_queries(0):
        decision = CartSourceOfferPolicy(verifier).evaluate(
            product=shadow,
            chosen_size="M",
            quantity=1,
            target_currency="TRY",
            baseline_public_price=Decimal("100.00"),
        )

    assert decision is None
    assert verifier.calls == []


@pytest.mark.django_db
def test_supplement_without_dedicated_adapter_is_payable_on_catalog_price(settings):
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = []
    product = Product.objects.create(
        name="Reference-only supplement",
        slug=f"reference-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("49.70"),
        currency="TRY",
        is_available=True,
        stock_quantity=3,
    )
    verifier = FakeVerifier(_result(), enabled_sources=("ilacfiyati",))

    decision = CartSourceOfferPolicy(verifier).evaluate(
        product=product,
        chosen_size="",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("57.16"),
    )

    assert decision is not None
    assert decision.offer is None
    assert decision.payable is True
    assert decision.public_price == Decimal("57.16")
    assert decision.verification_status == CartItem.VerificationStatus.VERIFIED
    assert decision.issues == ()
    assert decision.allow_cart is True
    assert decision.result.response_metadata["reason"] == "trusted_stock_adapter_missing"
    assert verifier.calls == []


@pytest.mark.django_db
def test_reference_price_source_cannot_be_configured_as_supplement_stock_adapter(
    settings,
):
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["ilacfiyati"]
    product = Product.objects.create(
        name="Misconfigured reference supplement",
        slug=f"misconfigured-reference-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("49.70"),
        currency="TRY",
    )
    ProductSourceOffer.objects.create(
        product=product,
        parser_key="ilacfiyati",
        canonical_url=(
            "https://ilacfiyati.com/takviye-edici-gida/" "misconfigured-reference-supplement"
        ),
        source_price=Decimal("49.70"),
        source_currency="TRY",
    )
    verifier = FakeVerifier(_result(), enabled_sources=("ilacfiyati",))

    decision = CartSourceOfferPolicy(verifier).evaluate(
        product=product,
        chosen_size="",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("57.16"),
    )

    assert decision is not None
    assert decision.offer is None
    assert decision.payable is True
    assert decision.public_price == Decimal("57.16")
    assert decision.issues == ()
    assert decision.allow_cart is True
    assert verifier.calls == []


@pytest.mark.django_db
def test_supplement_stock_adapter_out_of_stock_remains_payable(settings, monkeypatch):
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["akakce"]
    product = Product.objects.create(
        name="Availability-optional supplement",
        slug=f"availability-optional-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("100.00"),
        currency="TRY",
        stock_quantity=0,
    )
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="akakce",
        canonical_url="https://www.akakce.com/vitamin/urun,123.html",
        source_price=Decimal("100.00"),
        source_currency="TRY",
    )
    verifier = FakeVerifier(
        _result(availability=OfferAvailability.OUT_OF_STOCK),
        enabled_sources=("akakce",),
    )
    monkeypatch.setattr(
        CartSourceOfferPolicy,
        "_public_price_from_source",
        lambda _self, **kwargs: Decimal("100.00"),
    )

    decision = CartSourceOfferPolicy(verifier).evaluate(
        product=product,
        chosen_size="",
        quantity=5,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
    )

    assert decision.offer == offer
    assert decision.result.availability_status == OfferAvailability.OUT_OF_STOCK
    assert decision.verification_status == CartItem.VerificationStatus.VERIFIED
    assert decision.payable is True
    assert decision.issues == ()
    assert verifier.calls == [(offer.pk, False)]


@pytest.mark.django_db
def test_supplement_uses_only_explicit_stock_adapter(settings, monkeypatch):
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = ["supplier_api"]
    product = Product.objects.create(
        name="Supplier supplement",
        slug=f"supplier-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("100.00"),
        currency="TRY",
        external_data={"source_parser": "ilacfiyati"},
    )
    ProductSourceOffer.objects.create(
        product=product,
        parser_key="ilacfiyati",
        canonical_url="https://ilacfiyati.com/takviye-edici-gida/supplier-supplement",
        source_price=Decimal("90.00"),
        source_currency="TRY",
    )
    supplier_offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="supplier_api",
        canonical_url="https://supplier.example/products/supplier-supplement",
        source_price=Decimal("90.00"),
        source_currency="TRY",
    )
    result = OfferCheckResult(
        availability_status=OfferAvailability.IN_STOCK,
        stock_precision=OfferStockPrecision.BOOLEAN,
        canonical_url=supplier_offer.canonical_url,
        source_price=Decimal("100.00"),
        source_currency="TRY",
    )
    verifier = FakeVerifier(result, enabled_sources=("ilacfiyati", "supplier_api"))
    monkeypatch.setattr(
        CartSourceOfferPolicy,
        "_public_price_from_source",
        lambda _self, **kwargs: Decimal("100.00"),
    )

    decision = CartSourceOfferPolicy(verifier).evaluate(
        product=product,
        chosen_size="",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
    )

    assert decision is not None
    assert decision.offer == supplier_offer
    assert decision.payable is True
    assert verifier.calls == [(supplier_offer.pk, False)]


@pytest.mark.django_db
def test_policy_blocks_exact_quantity_drift(offer_product, monkeypatch):
    shadow, matching = offer_product
    verifier = FakeVerifier(_result(precision=OfferStockPrecision.EXACT, quantity=2))
    monkeypatch.setattr(
        CartSourceOfferPolicy,
        "_public_price_from_source",
        lambda _self, **kwargs: Decimal("100.00"),
    )

    decision = CartSourceOfferPolicy(verifier).evaluate(
        product=shadow,
        chosen_size="M",
        quantity=3,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
    )

    assert decision.offer == matching
    assert decision.payable is False
    assert decision.observed_stock_quantity == 2
    assert decision.verification_status == CartItem.VerificationStatus.BLOCKED
    assert decision.issues == (CartItem.VerificationIssue.SOURCE_QUANTITY_CHANGED,)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("result", "expected_status", "expected_issue"),
    [
        (
            _result(availability=OfferAvailability.OUT_OF_STOCK),
            CartItem.VerificationStatus.BLOCKED,
            CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK,
        ),
        (
            _result(
                availability=OfferAvailability.SOURCE_UNREACHABLE,
                price=None,
                error=OfferCheckError(
                    code=OfferCheckErrorCode.TIMEOUT,
                    message="timeout",
                    retryable=True,
                ),
            ),
            CartItem.VerificationStatus.RETRYABLE_ERROR,
            CartItem.VerificationIssue.SOURCE_UNREACHABLE,
        ),
        (
            _result(
                availability=OfferAvailability.UNSUPPORTED,
                price=None,
                error=OfferCheckError(
                    code=OfferCheckErrorCode.UNSUPPORTED,
                    message="unsupported",
                    retryable=False,
                ),
            ),
            CartItem.VerificationStatus.UNSUPPORTED,
            CartItem.VerificationIssue.VERIFICATION_UNSUPPORTED,
        ),
    ],
)
def test_policy_distinguishes_unavailable_transport_and_unsupported(
    offer_product, result, expected_status, expected_issue
):
    shadow, _matching = offer_product

    decision = CartSourceOfferPolicy(FakeVerifier(result)).evaluate(
        product=shadow,
        chosen_size="M",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
    )

    assert decision.payable is False
    assert decision.verification_status == expected_status
    assert decision.issues == (expected_issue,)


@pytest.mark.django_db
def test_price_increase_requires_ack_bound_to_current_value(offer_product, monkeypatch):
    shadow, _matching = offer_product
    verifier = FakeVerifier(_result(price="120.00"))
    monkeypatch.setattr(
        CartSourceOfferPolicy,
        "_public_price_from_source",
        lambda _self, **kwargs: Decimal("120.00"),
    )
    policy = CartSourceOfferPolicy(verifier)

    blocked = policy.evaluate(
        product=shadow,
        chosen_size="M",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
        acknowledged_price=Decimal("110.00"),
        acknowledged_currency="TRY",
    )
    accepted = policy.evaluate(
        product=shadow,
        chosen_size="M",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
        acknowledged_price=Decimal("120.00"),
        acknowledged_currency="try",
    )

    assert blocked.payable is False
    assert blocked.price_change_state == CartItem.PriceChangeState.INCREASED
    assert accepted.payable is True
    assert accepted.price_acknowledged is True
    assert accepted.issues == (CartItem.VerificationIssue.SOURCE_PRICE_CHANGED,)


@pytest.mark.django_db
def test_price_decrease_is_applied_with_non_blocking_notice(offer_product, monkeypatch):
    shadow, _matching = offer_product
    monkeypatch.setattr(
        CartSourceOfferPolicy,
        "_public_price_from_source",
        lambda _self, **kwargs: Decimal("80.00"),
    )

    decision = CartSourceOfferPolicy(FakeVerifier(_result(price="80.00"))).evaluate(
        product=shadow,
        chosen_size="M",
        quantity=1,
        target_currency="TRY",
        baseline_public_price=Decimal("100.00"),
    )

    assert decision.payable is True
    assert decision.public_price == Decimal("80.00")
    assert decision.price_change_state == CartItem.PriceChangeState.DECREASED
    assert decision.issues == (CartItem.VerificationIssue.SOURCE_PRICE_CHANGED,)
