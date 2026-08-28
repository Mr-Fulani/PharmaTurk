from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Product, ProductSourceOffer
from apps.orders.cart_source_verification import CartOfferDecision
from apps.orders.models import Cart, CartItem, Order, PromoCode
from apps.orders.views import (
    _cart_item_clone_values,
    _cart_verification_error_response,
)
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckError,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferStockPrecision,
)
from apps.users.models import User


@pytest.fixture(autouse=True)
def source_cart_settings(settings):
    settings.SOURCE_OFFER_CART_ENFORCEMENT_ENABLED = True
    settings.SOURCE_OFFER_CART_REVALIDATE_MAX_ITEMS = 20


@pytest.fixture
def source_cart_product(db):
    product = Product.objects.create(
        name="Cart source API product",
        slug=f"cart-source-api-{uuid4().hex}",
        product_type="clothing",
        price=Decimal("100.00"),
        currency="TRY",
        stock_quantity=None,
    )
    offer = ProductSourceOffer.objects.create(
        product=product,
        parser_key="zara",
        canonical_url="https://www.zara.com/tr/tr/product-p1.html",
        external_product_id="p1",
        source_price=Decimal("100.00"),
        source_currency="TRY",
        availability_status=ProductSourceOffer.AvailabilityStatus.IN_STOCK,
        stock_precision=ProductSourceOffer.StockPrecision.BOOLEAN,
    )
    return product, offer


def _decision(
    offer,
    *,
    availability=OfferAvailability.IN_STOCK,
    precision=OfferStockPrecision.BOOLEAN,
    stock_quantity=None,
    source_price="100.00",
    public_price="100.00",
    status=CartItem.VerificationStatus.VERIFIED,
    issues=(),
    payable=True,
    price_change=CartItem.PriceChangeState.NONE,
    price_acknowledged=False,
):
    result = OfferCheckResult(
        availability_status=availability,
        stock_precision=precision,
        stock_quantity=stock_quantity,
        canonical_url=offer.canonical_url,
        source_price=Decimal(source_price) if source_price is not None else None,
        source_currency="TRY",
    )
    return CartOfferDecision(
        offer=offer,
        result=result,
        verification_status=status,
        issues=tuple(issues),
        payable=payable,
        public_price=Decimal(public_price) if public_price is not None else None,
        public_currency="TRY",
        price_change_state=price_change,
        price_acknowledged=price_acknowledged,
    )


def _client(session_key="source-cart-api-session"):
    client = APIClient()
    client.credentials(HTTP_X_CART_SESSION=session_key, HTTP_X_CURRENCY="TRY")
    return client


@pytest.mark.django_db
def test_add_verifies_before_creating_payable_line(source_cart_product):
    product, offer = source_cart_product
    decision = _decision(offer)

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=decision,
    ) as evaluate:
        response = _client().post(
            reverse("cart-add"),
            {"product_id": product.pk, "quantity": 1},
            format="json",
        )

    assert response.status_code == 200
    item = CartItem.objects.get()
    assert item.source_offer == offer
    assert item.verification_status == CartItem.VerificationStatus.VERIFIED
    assert item.observed_source_price == Decimal("100.00")
    assert item.observed_public_price == Decimal("100.00")
    assert item.verified_quantity == 1
    assert response.json()["has_blocking_issues"] is False
    assert response.json()["payable_items_count"] == 1
    assert evaluate.call_args.kwargs["quantity"] == 1


@pytest.mark.django_db
def test_unavailable_add_returns_issue_without_allocating_anonymous_cart(
    source_cart_product,
):
    product, offer = source_cart_product
    decision = _decision(
        offer,
        availability=OfferAvailability.OUT_OF_STOCK,
        status=CartItem.VerificationStatus.BLOCKED,
        issues=(CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK,),
        payable=False,
        public_price=None,
    )

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=decision,
    ):
        response = _client("new-unavailable-cart").post(
            reverse("cart-add"),
            {"product_id": product.pk, "quantity": 1},
            format="json",
        )

    assert response.status_code == 409
    assert response.json()["code"] == CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK
    assert response.json()["verification"]["available_quantity"] is None
    assert not Cart.objects.filter(session_key="new-unavailable-cart").exists()
    assert CartItem.objects.count() == 0


@pytest.mark.django_db
def test_reference_only_supplement_cannot_bypass_cart_with_legacy_stock(settings):
    settings.SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES = ["supplements"]
    settings.SUPPLEMENT_STOCK_ADAPTER_SOURCES = []
    product = Product.objects.create(
        name="Reference-only supplement",
        slug=f"reference-only-supplement-{uuid4().hex}",
        product_type="supplements",
        price=Decimal("49.70"),
        currency="TRY",
        is_available=True,
        stock_quantity=3,
    )

    response = _client("reference-supplement-cart").post(
        reverse("cart-add"),
        {"product_id": product.pk, "quantity": 1},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == CartItem.VerificationIssue.VERIFICATION_UNSUPPORTED
    assert response.json()["verification"]["availability_status"] == "unsupported"
    assert not Cart.objects.filter(session_key="reference-supplement-cart").exists()
    assert not CartItem.objects.filter(product=product).exists()


@pytest.mark.django_db
def test_unavailable_repeated_add_blocks_the_saved_line(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="existing-unavailable-cart", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
    )
    decision = _decision(
        offer,
        availability=OfferAvailability.OUT_OF_STOCK,
        status=CartItem.VerificationStatus.BLOCKED,
        issues=(CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK,),
        payable=False,
        public_price=None,
    )

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=decision,
    ):
        response = _client(cart.session_key).post(
            reverse("cart-add"),
            {"product_id": product.pk, "quantity": 1},
            format="json",
        )

    assert response.status_code == 409
    item.refresh_from_db()
    assert item.quantity == 1
    assert item.verification_status == CartItem.VerificationStatus.BLOCKED
    assert item.verification_issues == [CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK]
    assert item.observed_source_price == Decimal("100.00")


def test_retryable_source_failure_returns_service_unavailable(source_cart_product):
    _product, offer = source_cart_product
    result = OfferCheckResult(
        availability_status=OfferAvailability.SOURCE_UNREACHABLE,
        stock_precision=OfferStockPrecision.UNKNOWN,
        canonical_url=offer.canonical_url,
        error=OfferCheckError(
            code=OfferCheckErrorCode.TIMEOUT,
            message="Supplier request timed out",
            retryable=True,
        ),
    )
    decision = CartOfferDecision(
        offer=offer,
        result=result,
        verification_status=CartItem.VerificationStatus.RETRYABLE_ERROR,
        issues=(CartItem.VerificationIssue.SOURCE_UNREACHABLE,),
        payable=False,
        public_price=None,
        public_currency="TRY",
        price_change_state=CartItem.PriceChangeState.NONE,
        price_acknowledged=False,
    )

    response = _cart_verification_error_response(decision)

    assert response.status_code == 503
    assert response.data["code"] == CartItem.VerificationIssue.SOURCE_UNREACHABLE


@pytest.mark.django_db
def test_price_increase_requires_exact_ack_before_add(source_cart_product):
    product, offer = source_cart_product
    blocked = _decision(
        offer,
        source_price="120.00",
        public_price="120.00",
        status=CartItem.VerificationStatus.BLOCKED,
        issues=(CartItem.VerificationIssue.SOURCE_PRICE_CHANGED,),
        payable=False,
        price_change=CartItem.PriceChangeState.INCREASED,
    )
    accepted = _decision(
        offer,
        source_price="120.00",
        public_price="120.00",
        issues=(CartItem.VerificationIssue.SOURCE_PRICE_CHANGED,),
        price_change=CartItem.PriceChangeState.INCREASED,
        price_acknowledged=True,
    )
    client = _client("price-ack-add-cart")

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        side_effect=[blocked, accepted],
    ) as evaluate:
        first = client.post(
            reverse("cart-add"),
            {"product_id": product.pk, "quantity": 1},
            format="json",
        )
        second = client.post(
            reverse("cart-add"),
            {
                "product_id": product.pk,
                "quantity": 1,
                "acknowledged_price": "120.00",
                "acknowledged_currency": "TRY",
            },
            format="json",
        )

    assert first.status_code == 409
    assert first.json()["verification"]["public_price"] == 120.0
    assert second.status_code == 200
    item = CartItem.objects.get()
    assert item.price == Decimal("120.00")
    assert item.price_acknowledged_value == Decimal("120.00")
    assert item.price_acknowledged_currency == "TRY"
    assert item.price_acknowledged_at is not None
    assert evaluate.call_args_list[1].kwargs["acknowledged_price"] == Decimal("120.00")


@pytest.mark.django_db
def test_update_clamps_to_real_exact_stock_and_keeps_notice(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="exact-stock-update-cart", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
    )
    decision = _decision(
        offer,
        precision=OfferStockPrecision.EXACT,
        stock_quantity=2,
        status=CartItem.VerificationStatus.BLOCKED,
        issues=(CartItem.VerificationIssue.SOURCE_QUANTITY_CHANGED,),
        payable=False,
    )

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=decision,
    ):
        response = _client(cart.session_key).post(
            reverse("cart-update-item", kwargs={"pk": item.pk}),
            {"quantity": 3},
            format="json",
        )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.quantity == 2
    assert item.observed_stock_quantity == 2
    assert item.verification_status == CartItem.VerificationStatus.VERIFIED
    assert item.verification_issues == [CartItem.VerificationIssue.SOURCE_QUANTITY_CHANGED]
    assert response.json()["total_amount"] == 200.0


@pytest.mark.django_db
def test_revalidate_keeps_unavailable_line_visible_but_excludes_payable_total(
    source_cart_product,
):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="revalidate-unavailable-cart", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=2,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
        observed_public_price=Decimal("100.00"),
        observed_public_currency="TRY",
    )
    decision = _decision(
        offer,
        availability=OfferAvailability.OUT_OF_STOCK,
        status=CartItem.VerificationStatus.BLOCKED,
        issues=(CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK,),
        payable=False,
        public_price=None,
    )

    with (
        patch(
            "apps.orders.views.CartSourceOfferPolicy.evaluate",
            return_value=decision,
        ) as evaluate,
        patch(
            "apps.orders.shipping_pricing.calculate_item_shipping_costs_usd"
        ) as calculate_shipping,
    ):
        response = _client(cart.session_key).post(reverse("cart-revalidate"), {})

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.quantity == 2
    assert item.verification_status == CartItem.VerificationStatus.BLOCKED
    payload = response.json()
    assert payload["items_count"] == 2
    assert payload["payable_items_count"] == 0
    assert payload["total_amount"] == 0.0
    assert payload["has_blocking_issues"] is True
    assert payload["items"][0]["issues"][0]["code"] == "source_out_of_stock"
    assert evaluate.call_args.kwargs["force"] is True
    calculate_shipping.assert_not_called()


@pytest.mark.django_db
def test_apply_promo_ignores_blocked_source_lines(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="blocked-promo-cart", currency="RUB")
    CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=10,
        price=Decimal("1000.00"),
        currency="RUB",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.BLOCKED,
        verification_issues=[CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK],
    )
    promo = PromoCode.objects.create(
        code="BLOCKED-LINES-DO-NOT-COUNT",
        discount_value=Decimal("10.00"),
        min_amount=Decimal("1.00"),
    )

    response = _client(cart.session_key).post(
        reverse("cart-apply-promo"),
        {"code": promo.code},
        format="json",
    )

    assert response.status_code == 400
    cart.refresh_from_db()
    assert cart.promo_code is None


@pytest.mark.django_db
def test_get_cart_never_invokes_source_policy(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="read-only-source-cart", currency="TRY")
    CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
    )

    with patch("apps.orders.views.CartSourceOfferPolicy.evaluate") as evaluate:
        response = _client(cart.session_key).get(reverse("cart-list"))

    assert response.status_code == 200
    evaluate.assert_not_called()


@pytest.mark.django_db
def test_acknowledge_price_updates_blocked_line_atomically(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="acknowledge-existing-cart", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.BLOCKED,
        verification_issues=[CartItem.VerificationIssue.SOURCE_PRICE_CHANGED],
        observed_public_price=Decimal("120.00"),
        observed_public_currency="TRY",
        price_change_state=CartItem.PriceChangeState.INCREASED,
    )
    accepted = _decision(
        offer,
        source_price="120.00",
        public_price="120.00",
        issues=(CartItem.VerificationIssue.SOURCE_PRICE_CHANGED,),
        price_change=CartItem.PriceChangeState.INCREASED,
        price_acknowledged=True,
    )

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        return_value=accepted,
    ):
        response = _client(cart.session_key).post(
            reverse("cart-acknowledge-price", kwargs={"pk": item.pk}),
            {"acknowledged_price": "120.00", "acknowledged_currency": "TRY"},
            format="json",
        )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.price == Decimal("120.00")
    assert item.verification_status == CartItem.VerificationStatus.VERIFIED
    assert item.price_acknowledged_value == Decimal("120.00")


@pytest.mark.django_db
def test_concurrent_item_change_returns_cart_changed_conflict(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="optimistic-source-cart", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
    )
    decision = _decision(offer)

    def concurrent_change(**kwargs):
        CartItem.objects.filter(pk=item.pk).update(quantity=2, updated_at=timezone.now())
        return decision

    with patch(
        "apps.orders.views.CartSourceOfferPolicy.evaluate",
        side_effect=concurrent_change,
    ):
        response = _client(cart.session_key).post(
            reverse("cart-update-item", kwargs={"pk": item.pk}),
            {"quantity": 3},
            format="json",
        )

    assert response.status_code == 409
    assert response.json()["operation_issues"][0]["code"] == "cart_changed"
    item.refresh_from_db()
    assert item.quantity == 2


@pytest.mark.django_db
def test_checkout_rejects_saved_blocking_source_issue(source_cart_product):
    product, offer = source_cart_product
    user = User.objects.create_user(
        username="blocked-checkout-user",
        email="blocked-checkout@example.test",
        password="not-used",
    )
    cart = Cart.objects.create(user=user, session_key="", currency="TRY")
    CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.BLOCKED,
        verification_issues=[CartItem.VerificationIssue.SOURCE_OUT_OF_STOCK],
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        reverse("orders-create-from-cart"),
        {"contact_name": "Test", "contact_phone": "+900000000"},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cart_changed"
    assert Order.objects.count() == 0
    assert CartItem.objects.filter(cart=cart).exists()


@pytest.mark.django_db
def test_anonymous_user_merge_preserves_verification_snapshot(source_cart_product):
    product, offer = source_cart_product
    cart = Cart.objects.create(session_key="snapshot-clone-cart", currency="TRY")
    item = CartItem.objects.create(
        cart=cart,
        product=product,
        quantity=1,
        price=Decimal("100.00"),
        currency="TRY",
        source_offer=offer,
        verification_status=CartItem.VerificationStatus.VERIFIED,
        source_checked_at=timezone.now(),
        observed_source_price=Decimal("90.00"),
        observed_source_currency="TRY",
        observed_public_price=Decimal("100.00"),
        observed_public_currency="TRY",
        observed_stock_precision=CartItem.StockPrecision.BOOLEAN,
        verified_quantity=1,
    )

    values = _cart_item_clone_values(item)

    assert values["source_offer_id"] == offer.pk
    assert values["verification_status"] == CartItem.VerificationStatus.VERIFIED
    assert values["observed_source_price"] == Decimal("90.00")
    assert values["observed_public_price"] == Decimal("100.00")
