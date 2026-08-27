from decimal import Decimal
from uuid import uuid4

import pytest

from apps.catalog.models import Product, ProductSourceOffer
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
