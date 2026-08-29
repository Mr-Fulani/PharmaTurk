import hashlib
import json
import logging
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional, Tuple

from django.conf import settings
from django.http import Http404, HttpResponse
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import JWTSafeAuthentication

from apps.catalog.models import (
    Product,
    ProductSourceOffer,
    ClothingProduct,
    ClothingProductSize,
    ClothingVariant,
    ClothingVariantSize,
    ShoeProduct,
    ShoeProductSize,
    ShoeVariant,
    ShoeVariantSize,
    JewelryProduct,
    JewelryVariant,
    JewelryVariantSize,
)
from apps.catalog.utils.currency_converter import currency_converter
from apps.users.models import UserAddress

from .models import Cart, CartItem, Order, OrderItem, PromoCode

# Crypto payment (lazy to avoid circular import / optional dependency)
def _create_crypto_invoice(number: str, total, cart_currency: str, locale: str = "") -> tuple[dict | None, dict | None]:
    """Создаёт инвойс. Возвращает (invoice_data, payment_data) или (None, None) при ошибке.
    Инвойс создаётся ДО создания заказа, чтобы не терять корзину при ошибке провайдера.
    locale: язык пользователя (ru/en) — для сохранения при редиректе после оплаты.
    """
    from apps.payments.providers.coinremitter import create_invoice
    from apps.payments.providers.dummy import create_invoice_dummy

    site = (getattr(settings, "SITE_URL", None) or "").rstrip("/")
    frontend = (getattr(settings, "FRONTEND_SITE_URL", None) or "").rstrip("/") or site
    notify_url = f"{site}/api/payments/crypto/webhook/" if site else ""
    # next-i18next.config.js uses defaultLocale=ru: Russian has no prefix,
    # while English routes live under /en/.
    loc = (locale or "").strip().lower()
    if loc not in ("ru", "en"):
        loc = "ru"
    path_prefix = "/en" if loc == "en" else ""
    success_path = f"{path_prefix}/checkout-success" if path_prefix else "/checkout-success"
    fail_path = f"{path_prefix}/checkout-crypto" if path_prefix else "/checkout-crypto"
    q = f"number={number}&locale={loc}"
    success_url = f"{frontend}{success_path}?{q}" if frontend else ""
    fail_url = f"{frontend}{fail_path}?{q}" if frontend else ""
    fiat_currency = (cart_currency or "USD").upper()[:3]

    invoice_data = create_invoice(
        amount_fiat=Decimal(str(total)),
        fiat_currency=fiat_currency,
        order_number=number,
        notify_url=notify_url,
        success_url=success_url,
        fail_url=fail_url,
        expiry_minutes=30,
        description=f"Order {number}",
    )

    # Dummy-режим ТОЛЬКО при явном CRYPTO_DUMMY_MODE=1 (не просто DEBUG).
    # Это позволяет тестировать через реальный CoinRemitter (TCN/USDTTRC20) даже в dev.
    if not invoice_data and getattr(settings, "CRYPTO_DUMMY_MODE", False):
        logger.warning(
            "CoinRemitter create_invoice failed, using DUMMY (CRYPTO_DUMMY_MODE=1). "
            "API key set: %s. Check COINREMITTER_API_KEY / COINREMITTER_API_PASSWORD.",
            bool(getattr(settings, "COINREMITTER_API_KEY", "")),
        )
        invoice_data = create_invoice_dummy(
            amount_fiat=float(total),
            fiat_currency=fiat_currency,
            order_number=number,
            notify_url=notify_url,
            success_url=success_url,
            fail_url=fail_url,
            expiry_minutes=30,
            description=f"Order {number}",
        )
    elif not invoice_data:
        logger.error(
            "CoinRemitter create_invoice failed and CRYPTO_DUMMY_MODE is off. "
            "API key set: %s. Returning 503 to client.",
            bool(getattr(settings, "COINREMITTER_API_KEY", "")),
        )
    if not invoice_data:
        return None, None

    expires_at = invoice_data.get("expires_at") or (timezone.now() + timezone.timedelta(minutes=30))
    payment_data = {
        "address": invoice_data["address"],
        "qr_code": invoice_data.get("qr_code") or "",
        "amount": str(invoice_data["amount"]),
        "amount_usd": str(invoice_data["amount_usd"]),
        "currency": fiat_currency,
        "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
        "invoice_url": invoice_data.get("invoice_url") or "",
    }
    return invoice_data, payment_data


def _save_crypto_payment(order, invoice_data: dict, cart_currency: str):
    """Сохраняет CryptoPayment после создания заказа."""
    from apps.payments.models import CryptoPayment

    fiat_currency = (cart_currency or "USD").upper()[:3]
    expires_at = invoice_data.get("expires_at") or (timezone.now() + timezone.timedelta(minutes=30))
    provider = "dummy" if invoice_data.get("invoice_id", "").startswith("dummy-") else "coinremitter"

    CryptoPayment.objects.create(
        order=order,
        provider=provider,
        invoice_id=invoice_data["invoice_id"],
        invoice_code=invoice_data.get("invoice_code") or "",
        address=invoice_data["address"],
        amount_crypto=invoice_data["amount"],
        # Persist exactly what the customer was charged. amount_usd is only a
        # display/conversion field returned by CoinRemitter and may not match
        # the order currency.
        amount_fiat=order.total_amount,
        currency=(order.currency or fiat_currency).upper()[:3],
        status="pending",
        qr_code_url=invoice_data.get("qr_code") or "",
        invoice_url=invoice_data.get("invoice_url") or "",
        expires_at=expires_at,
    )
from .serializers import (
    AcknowledgeCartPriceSerializer,
    AddToCartSerializer,
    ApplyPromoCodeSerializer,
    CartItemSerializer,
    CartSerializer,
    CreateOrderSerializer,
    OrderReceiptSerializer,
    OrderSerializer,
    PromoCodeSerializer,
    UpdateCartItemSerializer,
)
from .cart_source_verification import CartOfferDecision, CartSourceOfferPolicy
from .services import build_order_receipt_payload, render_receipt_html, get_order_customer_email
from .tasks import send_order_receipt_task, notify_new_order_telegram
from .throttles import (
    CART_MUTATION_THROTTLES,
    CHECKOUT_THROTTLES,
    RECEIPT_EMAIL_THROTTLES,
)

logger = logging.getLogger(__name__)

CART_ITEM_VERIFICATION_FIELDS = (
    'source_offer_id',
    'verification_status',
    'source_checked_at',
    'source_availability_status',
    'observed_source_price',
    'observed_source_currency',
    'observed_public_price',
    'observed_public_currency',
    'observed_stock_precision',
    'observed_stock_quantity',
    'verified_quantity',
    'verification_issues',
    'price_change_state',
    'price_acknowledged_at',
    'price_acknowledged_value',
    'price_acknowledged_currency',
)


def _cart_item_verification_values(
    decision: CartOfferDecision,
    *,
    quantity: int,
    existing_item: CartItem | None = None,
) -> dict:
    values = decision.cart_item_values(verified_quantity=quantity)
    if decision.price_change_state == CartItem.PriceChangeState.INCREASED:
        if decision.price_acknowledged and decision.public_price is not None:
            values.update(
                {
                    'price_acknowledged_at': decision.result.checked_at,
                    'price_acknowledged_value': decision.public_price,
                    'price_acknowledged_currency': decision.public_currency,
                }
            )
        else:
            values.update(
                {
                    'price_acknowledged_at': None,
                    'price_acknowledged_value': None,
                    'price_acknowledged_currency': '',
                }
            )
    elif decision.price_change_state == CartItem.PriceChangeState.DECREASED:
        values.update(
            {
                'price_acknowledged_at': None,
                'price_acknowledged_value': None,
                'price_acknowledged_currency': '',
            }
        )
    elif existing_item is not None:
        values.update(
            {
                'price_acknowledged_at': existing_item.price_acknowledged_at,
                'price_acknowledged_value': existing_item.price_acknowledged_value,
                'price_acknowledged_currency': existing_item.price_acknowledged_currency,
            }
        )
    return values


def _cart_item_update_values(
    decision: CartOfferDecision,
    *,
    item: CartItem,
    requested_quantity: int,
) -> dict:
    """Build an optimistic CartItem update, clamping only a real exact quantity."""
    final_quantity = (
        requested_quantity
        if decision.payable or decision.allow_cart
        else item.quantity
    )
    values = _cart_item_verification_values(
        decision,
        quantity=final_quantity,
        existing_item=item,
    )
    if (
        CartItem.VerificationIssue.SOURCE_QUANTITY_CHANGED in decision.issues
        and decision.observed_stock_quantity is not None
        and decision.observed_stock_quantity > 0
    ):
        final_quantity = min(requested_quantity, decision.observed_stock_quantity)
        values['verified_quantity'] = final_quantity
        price_still_blocking = (
            decision.price_change_state == CartItem.PriceChangeState.INCREASED
            and not decision.price_acknowledged
        )
        if not price_still_blocking:
            values['verification_status'] = CartItem.VerificationStatus.VERIFIED
    values['quantity'] = final_quantity
    if (
        values['verification_status'] == CartItem.VerificationStatus.VERIFIED
        and decision.public_price is not None
    ):
        values['price'] = decision.public_price
        values['currency'] = decision.public_currency
    values['updated_at'] = timezone.now()
    return values


def _checkout_cart_fingerprint(cart: Cart, items: list[CartItem]) -> str:
    """Return a stable fingerprint for every value consumed by checkout.

    The source offer identity is included for audit safety, while observed supplier
    price/stock remain owned by CartItem. Datetimes and Decimals are serialized as
    strings so the digest is deterministic across the preflight/locked reads.
    """

    item_payload = []
    for item in sorted(items, key=lambda candidate: candidate.pk):
        offer = item.source_offer if item.source_offer_id else None
        item_payload.append(
            {
                'id': item.pk,
                'product_id': item.product_id,
                'chosen_size': item.chosen_size,
                'quantity': item.quantity,
                'price': str(item.price),
                'currency': item.currency,
                'source_offer_id': item.source_offer_id,
                'verification_status': item.verification_status,
                'source_checked_at': (
                    item.source_checked_at.isoformat() if item.source_checked_at else None
                ),
                'source_availability_status': item.source_availability_status,
                'observed_source_price': (
                    str(item.observed_source_price)
                    if item.observed_source_price is not None
                    else None
                ),
                'observed_source_currency': item.observed_source_currency,
                'observed_public_price': (
                    str(item.observed_public_price)
                    if item.observed_public_price is not None
                    else None
                ),
                'observed_public_currency': item.observed_public_currency,
                'observed_stock_precision': item.observed_stock_precision,
                'observed_stock_quantity': item.observed_stock_quantity,
                'verified_quantity': item.verified_quantity,
                'verification_issues': item.verification_issues,
                'price_change_state': item.price_change_state,
                'price_acknowledged_at': (
                    item.price_acknowledged_at.isoformat()
                    if item.price_acknowledged_at
                    else None
                ),
                'price_acknowledged_value': (
                    str(item.price_acknowledged_value)
                    if item.price_acknowledged_value is not None
                    else None
                ),
                'price_acknowledged_currency': item.price_acknowledged_currency,
                'updated_at': item.updated_at.isoformat(),
                'offer_identity': (
                    {
                        'parser_key': offer.parser_key,
                        'canonical_url': offer.canonical_url,
                        'external_product_id': offer.external_product_id,
                        'external_sku': offer.external_sku,
                        'variant_key': offer.variant_key,
                        'size_key': offer.size_key,
                        'selected_options': offer.selected_options,
                        'updated_at': offer.updated_at.isoformat(),
                    }
                    if offer is not None
                    else None
                ),
            }
        )
    payload = {
        'cart_id': cart.pk,
        'currency': cart.currency,
        'promo_code_id': cart.promo_code_id,
        'updated_at': cart.updated_at.isoformat(),
        'items': item_payload,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _checkout_issue_response(
    request,
    cart: Cart,
    decision: CartOfferDecision | None = None,
) -> Response:
    """Return the refreshed cart when checkout must stop for user review."""

    cart = _get_cart_with_prefetch(cart)
    payload = CartSerializer(cart, context={'request': request}).data
    issue_codes = (
        list(decision.issues)
        if decision is not None and decision.issues
        else [CartItem.VerificationIssue.CART_CHANGED]
    )
    labels = dict(CartItem.VerificationIssue.choices)
    payload.update(
        {
            'detail': str(labels.get(issue_codes[0], issue_codes[0])),
            'code': issue_codes[0],
            'operation_issues': [
                {
                    'code': code,
                    'message': str(labels.get(code, code)),
                    'blocking': True,
                }
                for code in issue_codes
            ],
        }
    )
    response_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if decision is not None
        and decision.verification_status == CartItem.VerificationStatus.RETRYABLE_ERROR
        else status.HTTP_409_CONFLICT
    )
    return Response(payload, status=response_status)


def _checkout_source_preflight(request, cart: Cart) -> tuple[str | None, Response | None]:
    """Live-check supplier offers without a transaction or database row locks."""

    items = list(
        cart.items.select_related('product', 'source_offer').order_by('pk')
    )
    if not items:
        return None, Response({'detail': _('Корзина пуста')}, status=400)

    policy = CartSourceOfferPolicy()
    review_decision = None
    changed = False
    for item in items:
        decision = policy.evaluate(
            product=item.product,
            chosen_size=item.chosen_size,
            quantity=item.quantity,
            target_currency=item.currency or cart.currency,
            baseline_public_price=item.price,
            acknowledged_price=item.price_acknowledged_value,
            acknowledged_currency=item.price_acknowledged_currency,
            force=True,
        )
        if decision is None:
            continue
        values = _cart_item_update_values(
            decision,
            item=item,
            requested_quantity=item.quantity,
        )
        updated = CartItem.objects.filter(
            pk=item.pk,
            cart_id=cart.pk,
            quantity=item.quantity,
            updated_at=item.updated_at,
        ).update(**values)
        if not updated:
            return None, _cart_changed_response(request, cart)
        changed = True
        if review_decision is None and (decision.issues or not decision.payable):
            review_decision = decision

    if changed:
        _touch_cart(cart)

    refreshed_cart = Cart.objects.select_related('promo_code').get(pk=cart.pk)
    refreshed_items = list(
        refreshed_cart.items.select_related('product', 'source_offer').order_by('pk')
    )
    if review_decision is not None:
        return None, _checkout_issue_response(request, refreshed_cart, review_decision)
    if any(not item.is_payable for item in refreshed_items):
        return None, _checkout_issue_response(request, refreshed_cart)
    return _checkout_cart_fingerprint(refreshed_cart, refreshed_items), None


def _order_item_source_snapshot(item: CartItem) -> dict:
    """Copy server-owned supplier identity and the last live observation to an order."""

    offer = item.source_offer if item.source_offer_id else None
    if offer is None:
        return {
            # Supplements remain payable without a stock adapter by explicit
            # business policy. Keep that fulfilment exception visible to admins
            # even when no supplier offer could be attached to the cart line.
            'supplier_confirmation_required': (
                CartSourceOfferPolicy.availability_is_informational(item.product)
            ),
        }
    selected_options = dict(offer.selected_options or {})
    if offer.parser_key == "akakce" and isinstance(offer.response_metadata, dict):
        metadata = offer.response_metadata
        seller_name = str(metadata.get("seller_name") or "").strip()
        seller_url = str(metadata.get("seller_url") or "").strip()
        if seller_name and seller_url:
            # Reuse the existing immutable JSON snapshot to retain the exact
            # procurement seller selected by the live checkout observation.
            selected_options["procurement_offer"] = {
                "seller_name": seller_name[:200],
                "seller_url": seller_url[:2000],
                "market_product_name": str(
                    metadata.get("market_product_name") or ""
                )[:500],
                "market_product_id": str(metadata.get("market_product_id") or "")[:100],
            }
    reservation_capable = {
        str(source).strip().casefold()
        for source in getattr(settings, 'SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES', [])
        if str(source).strip()
    }
    return {
        'source_parser': offer.parser_key,
        'source_domain': offer.source_domain,
        'source_url': offer.canonical_url,
        'source_external_product_id': offer.external_product_id,
        'source_external_sku': offer.external_sku,
        'source_variant_key': offer.variant_key,
        'source_size_key': offer.size_key,
        'source_selected_options': selected_options,
        'source_price': (
            item.observed_source_price
            if item.observed_source_price is not None
            else offer.source_price
        ),
        'source_currency': item.observed_source_currency or offer.source_currency,
        'source_availability_status': (
            item.source_availability_status or offer.availability_status
        ),
        'source_stock_precision': item.observed_stock_precision or offer.stock_precision,
        'source_stock_quantity': item.observed_stock_quantity,
        'source_checked_at': item.source_checked_at,
        'supplier_confirmation_required': (
            CartSourceOfferPolicy.availability_is_informational(item.product)
            or offer.parser_key not in reservation_capable
        ),
    }


def _cart_verification_error_response(decision: CartOfferDecision) -> Response:
    code = decision.issues[0] if decision.issues else CartItem.VerificationIssue.CART_CHANGED
    labels = dict(CartItem.VerificationIssue.choices)
    response_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if decision.verification_status == CartItem.VerificationStatus.RETRYABLE_ERROR
        else status.HTTP_409_CONFLICT
    )
    return Response(
        {
            'detail': str(labels.get(code, code)),
            'code': code,
            'issues': [
                {'code': issue, 'message': str(labels.get(issue, issue)), 'blocking': True}
                for issue in decision.issues
            ],
            'verification': {
                'status': decision.verification_status,
                'availability_status': decision.result.availability_status.value,
                'stock_precision': decision.result.stock_precision.value,
                'available_quantity': decision.result.stock_quantity,
                'source_price': decision.result.source_price,
                'source_currency': decision.result.source_currency,
                'public_price': decision.public_price,
                'public_currency': decision.public_currency,
                'checked_at': decision.result.checked_at,
            },
        },
        status=response_status,
    )


def _cart_changed_response(request, cart: Cart) -> Response:
    cart = _get_cart_with_prefetch(cart)
    payload = CartSerializer(cart, context={'request': request}).data
    payload['operation_issues'] = [
        {
            'code': CartItem.VerificationIssue.CART_CHANGED,
            'message': str(CartItem.VerificationIssue.CART_CHANGED.label),
            'blocking': True,
        }
    ]
    return Response(payload, status=status.HTTP_409_CONFLICT)


def _get_preferred_currency(request, fallback: str = 'RUB') -> str:
    if not request:
        return fallback
    preferred_currency = request.headers.get('X-Currency')
    if preferred_currency:
        return preferred_currency.upper()
    preferred_currency = request.query_params.get('currency')
    if preferred_currency:
        return preferred_currency.upper()
    if getattr(request, 'user', None) and request.user.is_authenticated:
        user_currency = getattr(request.user, 'currency', None)
        if user_currency:
            return user_currency.upper()
    return fallback


def _get_product_price_for_currency(product, currency: str):
    from apps.catalog.utils.product_markup import apply_product_markup

    currency = (currency or 'RUB').upper()
    base_price = getattr(product, "price", None)
    base_currency = (getattr(product, "currency", None) or "RUB").upper()

    # Для shadow-варианта сохранённый ProductPrice содержит фактическую
    # базовую цену выбранного варианта. Целевую цену из snapshot не берём:
    # она может ещё не успеть обновиться после изменения маржи.
    try:
        prices = product.get_all_prices() or {}
        for code, data in prices.items():
            if data.get("is_base_price"):
                base_price = data.get("original_price")
                if base_price is None:
                    base_price = data.get("converted_price")
                base_currency = code.upper()
                break
    except Exception:
        pass

    if base_price is not None:
        try:
            _, _, price_with_margin = currency_converter.convert_price(
                Decimal(str(base_price)),
                base_currency,
                currency,
                apply_margin=True,
            )
            return apply_product_markup(price_with_margin, product)
        except Exception:
            return apply_product_markup(base_price, product)
    try:
        return apply_product_markup(0, product)
    except Exception:
        return Decimal('0')


def _get_stock_for_cart_product(product: Product, chosen_size: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Возвращает доступный остаток (или None, если лимита нет) и человеко-читаемый источник.

    Приоритет:
    1) Размер варианта одежды/обуви (если есть source_variant_id и задан chosen_size)
    2) Вариант одежды/обуви (если есть source_variant_id)
    3) Базовый Product.stock_quantity

    None означает "не ограничено".
    """
    external = getattr(product, "external_data", None) or {}
    source_variant_id = external.get("source_variant_id")
    jewelry_variant_id = external.get("jewelry_variant_id")
    source_type = (external.get("source_type") or "").lower()
    source_id = external.get("source_id")

    normalized_type = (getattr(product, "product_type", None) or "").lower()
    size_value = (chosen_size or "").strip()

    # Imported supplements can carry a legacy zero/unknown catalogue stock even
    # though the commercial supplier has not been checked yet. For enforced
    # source products the live adapter (or the pending-confirmation state) is the
    # authority, so legacy catalogue stock must not reject the cart beforehand.
    if CartSourceOfferPolicy.requires_verified_offer(product):
        return None, "source_offer"

    if source_variant_id and normalized_type in {"clothing", "shoes"}:
        if normalized_type == "clothing":
            variant = ClothingVariant.objects.filter(id=source_variant_id, is_active=True).first()
            if not variant:
                return product.stock_quantity, "product"
            if size_value:
                size_obj = ClothingVariantSize.objects.filter(variant=variant, size=size_value).first()
                if size_obj and size_obj.stock_quantity is not None:
                    return size_obj.stock_quantity, "variant_size"
            if variant.stock_quantity is not None:
                return variant.stock_quantity, "variant"
        if normalized_type == "shoes":
            variant = ShoeVariant.objects.filter(id=source_variant_id, is_active=True).first()
            if not variant:
                return product.stock_quantity, "product"
            if size_value:
                size_obj = ShoeVariantSize.objects.filter(variant=variant, size=size_value).first()
                if size_obj and size_obj.stock_quantity is not None:
                    return size_obj.stock_quantity, "variant_size"
            if variant.stock_quantity is not None:
                return variant.stock_quantity, "variant"

    if jewelry_variant_id and normalized_type == "jewelry":
        variant = JewelryVariant.objects.filter(id=jewelry_variant_id, is_active=True).first()
        if not variant:
            return product.stock_quantity, "product"
        if size_value:
            size_obj = JewelryVariantSize.objects.filter(variant=variant, size_display=size_value).first()
            if not size_obj:
                size_obj = JewelryVariantSize.objects.filter(variant=variant, size_value=size_value).first()
            if size_obj and size_obj.stock_quantity is not None:
                return size_obj.stock_quantity, "variant_size"
        if variant.stock_quantity is not None:
            return variant.stock_quantity, "variant"

    if source_type == "base_clothing":
        base_obj = ClothingProduct.objects.filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ClothingProductSize.objects.filter(product=base_obj, size=size_value).first()
            if size_obj and size_obj.stock_quantity is not None:
                return size_obj.stock_quantity, "product_size"

    if source_type == "base_shoes":
        base_obj = ShoeProduct.objects.filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ShoeProductSize.objects.filter(product=base_obj, size=size_value).first()
            if size_obj and size_obj.stock_quantity is not None:
                return size_obj.stock_quantity, "product_size"

    return product.stock_quantity, "product"


def _decrement_stock_for_cart_item(product: Product, chosen_size: Optional[str], quantity: int) -> None:
    """Атомарно списывает остаток (если он ограничен).

    Должно вызываться внутри transaction.atomic().
    """
    if quantity <= 0:
        return

    # Supplement catalogue stock is informational and often contains legacy
    # zero/synthetic values. The order is intentionally accepted and fulfilled
    # manually when a supplier cannot confirm availability, so no local stock
    # row may reject or mutate this order here.
    if CartSourceOfferPolicy.availability_is_informational(product):
        return

    external = getattr(product, "external_data", None) or {}
    source_variant_id = external.get("source_variant_id")
    jewelry_variant_id = external.get("jewelry_variant_id")
    source_type = (external.get("source_type") or "").lower()
    source_id = external.get("source_id")
    normalized_type = (getattr(product, "product_type", None) or "").lower()
    size_value = (chosen_size or "").strip()

    if source_variant_id and normalized_type in {"clothing", "shoes"}:
        if normalized_type == "clothing":
            variant = ClothingVariant.objects.select_for_update().filter(id=source_variant_id, is_active=True).first()
            if not variant:
                source_variant_id = None
            else:
                if size_value:
                    size_obj = ClothingVariantSize.objects.select_for_update().filter(variant=variant, size=size_value).first()
                    if size_obj and size_obj.stock_quantity is not None:
                        if size_obj.stock_quantity < quantity:
                            raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                        size_obj.stock_quantity = size_obj.stock_quantity - quantity
                        if size_obj.stock_quantity == 0:
                            size_obj.is_available = False
                        size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                        return
                if variant.stock_quantity is not None:
                    if variant.stock_quantity < quantity:
                        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                    variant.stock_quantity = variant.stock_quantity - quantity
                    if variant.stock_quantity == 0:
                        variant.is_available = False
                    variant.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                    return

        if normalized_type == "shoes":
            variant = ShoeVariant.objects.select_for_update().filter(id=source_variant_id, is_active=True).first()
            if not variant:
                source_variant_id = None
            else:
                if size_value:
                    size_obj = ShoeVariantSize.objects.select_for_update().filter(variant=variant, size=size_value).first()
                    if size_obj and size_obj.stock_quantity is not None:
                        if size_obj.stock_quantity < quantity:
                            raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                        size_obj.stock_quantity = size_obj.stock_quantity - quantity
                        if size_obj.stock_quantity == 0:
                            size_obj.is_available = False
                        size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                        return
                if variant.stock_quantity is not None:
                    if variant.stock_quantity < quantity:
                        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                    variant.stock_quantity = variant.stock_quantity - quantity
                    if variant.stock_quantity == 0:
                        variant.is_available = False
                    variant.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                    return

    if jewelry_variant_id and normalized_type == "jewelry":
        variant = JewelryVariant.objects.select_for_update().filter(id=jewelry_variant_id, is_active=True).first()
        if variant:
            if size_value:
                size_obj = JewelryVariantSize.objects.select_for_update().filter(
                    variant=variant, size_display=size_value
                ).first()
                if not size_obj:
                    size_obj = JewelryVariantSize.objects.select_for_update().filter(
                        variant=variant, size_value=size_value
                    ).first()
                if size_obj and size_obj.stock_quantity is not None:
                    if size_obj.stock_quantity < quantity:
                        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                    size_obj.stock_quantity = size_obj.stock_quantity - quantity
                    if size_obj.stock_quantity == 0:
                        size_obj.is_available = False
                    size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                    return
            if variant.stock_quantity is not None:
                if variant.stock_quantity < quantity:
                    raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                variant.stock_quantity = variant.stock_quantity - quantity
                if variant.stock_quantity == 0:
                    variant.is_available = False
                variant.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                return

    if source_type == "base_clothing":
        base_obj = ClothingProduct.objects.select_for_update().filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ClothingProductSize.objects.select_for_update().filter(
                product=base_obj, size=size_value
            ).first()
            if size_obj and size_obj.stock_quantity is not None:
                if size_obj.stock_quantity < quantity:
                    raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                size_obj.stock_quantity = size_obj.stock_quantity - quantity
                if size_obj.stock_quantity == 0:
                    size_obj.is_available = False
                size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                return

    if source_type == "base_shoes":
        base_obj = ShoeProduct.objects.select_for_update().filter(id=source_id, is_active=True).first()
        if base_obj and size_value:
            size_obj = ShoeProductSize.objects.select_for_update().filter(
                product=base_obj, size=size_value
            ).first()
            if size_obj and size_obj.stock_quantity is not None:
                if size_obj.stock_quantity < quantity:
                    raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
                size_obj.stock_quantity = size_obj.stock_quantity - quantity
                if size_obj.stock_quantity == 0:
                    size_obj.is_available = False
                size_obj.save(update_fields=["stock_quantity", "is_available", "updated_at"])
                return

    # fallback: Product
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    if locked_product.stock_quantity is None:
        return
    if locked_product.stock_quantity < quantity:
        raise serializers.ValidationError({"detail": _("Недостаточно товара в наличии")})
    locked_product.stock_quantity = locked_product.stock_quantity - quantity
    if locked_product.stock_quantity == 0:
        locked_product.is_available = False
    locked_product.save(update_fields=["stock_quantity", "is_available", "updated_at"])


def _get_cart_with_prefetch(cart: Cart):
    """Корзина с prefetch для позиций, товаров и изображений (в т.ч. domain_item)."""
    from django.db.models import Prefetch
    from apps.catalog.models import ProductImage

    item_queryset = CartItem.objects.select_related(
        'product',
        'source_offer',
        'product__category',
        'product__brand',
        'product__price_info',
    )
    return Cart.objects.filter(pk=cart.pk).prefetch_related(
        Prefetch('items', queryset=item_queryset),
        'items__product__translations',
        Prefetch(
            'items__product__images',
            queryset=ProductImage.objects.all().order_by('sort_order', 'created_at'),
        ),
        'items__product__medicine_item__gallery_images',
        'items__product__medicine_item__translations',
        'items__product__supplement_item__gallery_images',
        'items__product__supplement_item__translations',
        'items__product__medical_equipment_item__gallery_images',
        'items__product__medical_equipment_item__translations',
        'items__product__tableware_item__gallery_images',
        'items__product__tableware_item__translations',
        'items__product__accessory_item__gallery_images',
        'items__product__accessory_item__translations',
        'items__product__incense_item__gallery_images',
        'items__product__incense_item__translations',
    ).get()


def _normalise_cart_session_key(value) -> str | None:
    """Return a bounded session bearer token suitable for the Cart column."""
    if value is None:
        return None
    try:
        value = str(value).strip()
    except (TypeError, ValueError):
        return None
    if not value or len(value) > Cart._meta.get_field('session_key').max_length:
        return None
    return value


def _anonymous_cart_session_candidates(request) -> list[str]:
    """Resolve existing anonymous identifiers without creating a Django session."""
    header_session = request.META.get('HTTP_X_CART_SESSION')
    if not header_session:
        header_session = getattr(request, 'headers', {}).get('X-Cart-Session')
    cookie_session = getattr(request, 'COOKIES', {}).get('cart_session')

    django_session = None
    stored_cart_session = None
    session = getattr(request, 'session', None)
    if session is not None:
        django_session = getattr(session, 'session_key', None)
        stored_cart_session = session.get('cart_session_key')

    candidates: list[str] = []
    for raw_value in (
        header_session,
        cookie_session,
        django_session,
        stored_cart_session,
    ):
        value = _normalise_cart_session_key(raw_value)
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def _get_existing_cart_for_read(request) -> Cart | None:
    """Look up an anonymous cart without allocating a session or database row."""
    for session_key in _anonymous_cart_session_candidates(request):
        cart = Cart.objects.filter(user=None, session_key=session_key).first()
        if cart is not None:
            return cart
    return None


def _get_existing_cart_for_mutation(request) -> Cart | None:
    """Resolve a current cart for a no-op-capable mutation without creating one."""
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    if user:
        cart = Cart.objects.filter(user=user).first()
        if cart is not None:
            return cart
    return _get_existing_cart_for_read(request)


class _EmptyCartItems(tuple):
    """Tiny relation-like value accepted by CartSerializer and its method fields."""

    def all(self):
        return self


def _empty_cart_payload(request) -> dict:
    """Serialize a non-persistent empty cart with the regular response schema."""
    empty_cart = SimpleNamespace(
        id=0,
        user=None,
        session_key='',
        currency='RUB',
        items=_EmptyCartItems(),
        items_count=0,
        promo_code=None,
        created_at=None,
        updated_at=None,
    )
    return CartSerializer(empty_cart, context={'request': request}).data


def _get_or_create_cart_record(*, user, session_key: str, defaults: dict) -> tuple[Cart, bool]:
    """Create one identity cart and recover cleanly from a concurrent winner."""
    lookup = {
        'user': user,
        'session_key': session_key,
    }
    try:
        # The savepoint keeps a uniqueness failure from poisoning an outer
        # checkout transaction before we fetch the row created by the winner.
        with transaction.atomic():
            return Cart.objects.get_or_create(**lookup, defaults=defaults)
    except IntegrityError:
        identity_lookup = lookup if user is None else {'user': user}
        return Cart.objects.get(**identity_lookup), False


def _touch_cart(cart: Cart) -> None:
    """Record write activity used by anonymous-cart TTL cleanup."""
    touched_at = timezone.now()
    Cart.objects.filter(pk=cart.pk).update(updated_at=touched_at)
    cart.updated_at = touched_at


def _cart_item_clone_values(item: CartItem) -> dict:
    """Preserve source verification identity/snapshot during anonymous → user merge."""
    values = {
        'product': item.product,
        'quantity': item.quantity,
        'price': item.price,
        'currency': item.currency,
        'chosen_size': item.chosen_size,
    }
    values.update({field: getattr(item, field) for field in CART_ITEM_VERIFICATION_FIELDS})
    return values


def _get_or_create_cart(request) -> Cart:
    """Получить или создать корзину для пользователя или сессии.
    Для анонимных клиентов поддерживаем пользовательский ключ из заголовка X-Cart-Session
    и из cookie cart_session (fallback для случаев, когда заголовок не передан).
    """
    user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None

    # 1) Ключ из заголовка (для фронтенда) или cookie (fallback)
    header_session = request.META.get('HTTP_X_CART_SESSION') or getattr(request, 'headers', {}).get('X-Cart-Session')
    cookie_session = getattr(request, 'COOKIES', {}).get('cart_session')
    custom_session = _normalise_cart_session_key(header_session or cookie_session)

    # 2) Стандартная сессия Django
    django_session = None
    if not user and hasattr(request, 'session'):
        django_session = request.session.session_key
        if not custom_session and not django_session:
            # Гарантируем наличие session_key, если потребуется
            request.session.save()
            django_session = request.session.session_key

    session_key = None
    if not user:
        session_key = custom_session or django_session
        if not session_key:
            session_key = str(uuid.uuid4())
            if hasattr(request, 'session'):
                request.session['cart_session_key'] = session_key

    # Если пользователь авторизован, сначала ищем его корзину
    if user:
        cart = Cart.objects.filter(user=user).first()
        
        # Если у пользователя есть корзина, но она пустая, проверяем анонимную корзину для переноса
        if cart and not cart.items.exists() and custom_session:
            anonymous_cart = Cart.objects.filter(session_key=custom_session, user=None).first()
            if anonymous_cart and anonymous_cart.items.exists():
                # Копируем товары из анонимной корзины в существующую корзину пользователя
                for item in anonymous_cart.items.all():
                    CartItem.objects.create(
                        cart=cart,
                        **_cart_item_clone_values(item),
                    )
                # Удаляем анонимную корзину
                anonymous_cart.delete()
                return cart
        
        if cart:
            # Если нашли корзину пользователя, возвращаем её
            return cart
        
        # Если у пользователя нет корзины, но есть анонимная корзина с session_key,
        # то переносим товары из анонимной корзины в корзину пользователя
        if custom_session:
            anonymous_cart = Cart.objects.filter(session_key=custom_session, user=None).first()
            if anonymous_cart and anonymous_cart.items.exists():
                # Создаем новую корзину для пользователя
                cart, _created = _get_or_create_cart_record(
                    user=user,
                    session_key='',
                    defaults={'currency': anonymous_cart.currency},
                )
                # Копируем товары из анонимной корзины
                for item in anonymous_cart.items.all():
                    CartItem.objects.create(
                        cart=cart,
                        **_cart_item_clone_values(item),
                    )
                # Удаляем анонимную корзину
                anonymous_cart.delete()
                return cart

    # Создаем новую корзину
    cart, created = _get_or_create_cart_record(
        user=user if user else None,
        session_key='' if user else session_key,
        defaults={'currency': 'RUB'},
    )
    logger.debug(
        "cart.resolve user_id=%s anonymous=%s created=%s",
        getattr(user, 'id', None),
        not bool(user),
        created,
    )
    return cart


class CartViewSet(viewsets.ViewSet):
    """Управление корзиной."""
    serializer_class = CartSerializer
    queryset = CartItem.objects.none()
    permission_classes = [AllowAny]
    # Исключаем SessionAuthentication: она применяет CSRF к POST/DELETE даже при AllowAny
    authentication_classes = [JWTSafeAuthentication]

    @extend_schema(
        description=(
            "Получить текущую корзину. Для анонимного клиента без существующей "
            "cart-session возвращает пустую корзину (id=0), не создавая сессию или строку Cart."
        ),
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Пример корзины',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [
                        {
                            "id": 10,
                            "product": 1,
                            "product_name": "Test Product",
                            "product_slug": "test-product",
                            "quantity": 2,
                            "price": "10.00",
                            "currency": "USD"
                        }
                    ],
                    "items_count": 2,
                    "total_amount": "20.00"
                },
                response_only=True
            )
        ]
    )
    def list(self, request):
        user = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
        if user:
            cart = _get_or_create_cart(request)
        else:
            cart = _get_existing_cart_for_read(request)
            if cart is None:
                return Response(_empty_cart_payload(request))
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description=(
            "Добавить товар в текущую корзину (анонимно по X-Cart-Session/cookie). "
            "Для базовых товаров передавайте product_id. Для вариантов одежды/обуви "
            "передавайте product_type + product_slug (slug варианта)."
        ),
        request=AddToCartSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1, "quantity": 1},
                request_only=True
            ),
            OpenApiExample(
                'Запрос (вариант обуви)',
                value={"product_type": "shoes", "product_slug": "nike-air-force-white-42", "quantity": 1},
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [
                        {
                            "id": 11,
                            "product": 1,
                            "product_name": "Test Product",
                            "product_slug": "test-product",
                            "quantity": 1,
                            "price": "10.00",
                            "currency": "USD"
                        }
                    ],
                    "items_count": 1,
                    "total_amount": "10.00"
                },
                response_only=True
            )
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path=r'add/?',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    @extend_schema(
        description="Добавить товар в корзину (для вариантов обуви/одежды требуется размер).",
        request=AddToCartSerializer,
        responses=CartSerializer,
    )
    def add(self, request):
        serializer = AddToCartSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as exc:
            submitted_fields = sorted(
                set(request.data.keys()) & set(serializer.fields.keys())
            )
            logger.warning(
                "cart.add validation failed",
                extra={
                    "submitted_fields": submitted_fields,
                    "error_codes": (
                        exc.get_codes()
                        if hasattr(exc, "get_codes")
                        else "validation_error"
                    ),
                },
            )
            raise
        product = serializer.validated_data['product']
        quantity = serializer.validated_data['quantity']
        chosen_size = serializer.validated_data.get('chosen_size', '')
        existing_cart = _get_existing_cart_for_mutation(request)
        preferred_currency = _get_preferred_currency(
            request,
            fallback=(
                existing_cart.currency
                if existing_cart is not None and existing_cart.currency
                else 'RUB'
            ),
        )
        item_price = _get_product_price_for_currency(product, preferred_currency)

        # Validate stock before allocating an anonymous session/Cart row.
        existing = None
        if existing_cart is not None:
            existing = CartItem.objects.filter(
                cart=existing_cart,
                product=product,
                chosen_size=chosen_size,
            ).first()
        new_total_qty = quantity + (existing.quantity if existing else 0)
        available_stock, _source = _get_stock_for_cart_product(product, chosen_size)
        if available_stock is not None and new_total_qty > available_stock:
            raise serializers.ValidationError({
                "detail": _("Недостаточно товара в наличии"),
                "available": available_stock,
            })

        decision = CartSourceOfferPolicy().evaluate(
            product=product,
            chosen_size=chosen_size,
            quantity=new_total_qty,
            target_currency=preferred_currency,
            baseline_public_price=(existing.price if existing else item_price),
            acknowledged_price=serializer.validated_data.get('acknowledged_price'),
            acknowledged_currency=serializer.validated_data.get('acknowledged_currency', ''),
        )
        if decision is not None and not decision.payable and not decision.allow_cart:
            if existing is not None:
                original_quantity = existing.quantity
                original_updated_at = existing.updated_at
                values = _cart_item_update_values(
                    decision,
                    item=existing,
                    requested_quantity=new_total_qty,
                )
                updated = CartItem.objects.filter(
                    pk=existing.pk,
                    quantity=original_quantity,
                    updated_at=original_updated_at,
                ).update(**values)
                if not updated:
                    return _cart_changed_response(request, existing_cart)
                _touch_cart(existing_cart)
            return _cart_verification_error_response(decision)

        verification_defaults = {}
        if decision is not None:
            verification_defaults = _cart_item_verification_values(
                decision,
                quantity=new_total_qty,
                existing_item=existing,
            )
            if decision.public_price is not None:
                item_price = decision.public_price

        cart = _get_or_create_cart(request)
        _touch_cart(cart)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            chosen_size=chosen_size,
            defaults={
                'quantity': quantity,
                'price': item_price,
                'currency': preferred_currency,
                'chosen_size': chosen_size,
                **verification_defaults,
            }
        )
        if not created:
            # Если уже есть, обновляем цену/валюту по актуальному товару
            updated = False
            if item.price != item_price:
                item.price = item_price
                updated = True
            if item.currency != preferred_currency:
                item.currency = preferred_currency
                updated = True
            item.quantity += quantity
            if decision is not None:
                for field_name, value in verification_defaults.items():
                    setattr(item, field_name, value)
                item.save(
                    update_fields=[
                        'price', 'currency', 'quantity',
                        *verification_defaults.keys(), 'updated_at',
                    ]
                )
            elif updated:
                item.save(update_fields=['price', 'currency', 'quantity', 'updated_at'])
            else:
                item.save(update_fields=['quantity', 'updated_at'])

        # Синхронизируем валюту корзины под валюту последнего товара (простая модель)
        if cart.currency != preferred_currency:
            cart.currency = preferred_currency
            cart.save(update_fields=['currency', 'updated_at'])
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description="Изменить количество позиции корзины",
        request=UpdateCartItemSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample('Запрос', value={"quantity": 3}, request_only=True),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [
                        {
                            "id": 11,
                            "product": 1,
                            "product_name": "Test Product",
                            "product_slug": "test-product",
                            "quantity": 3,
                            "price": "10.00",
                            "currency": "USD"
                        }
                    ],
                    "items_count": 3,
                    "total_amount": "30.00"
                },
                response_only=True
            ),
        ]
    )
    @action(
        detail=True,
        methods=['post'],
        url_path='update',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def update_item(self, request, pk: int | None = None):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response({"detail": _("Корзина не найдена")}, status=404)
        _touch_cart(cart)
        try:
            item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            return Response({"detail": _("Позиция не найдена")}, status=404)

        desired_qty = serializer.validated_data['quantity']
        available_stock, _source = _get_stock_for_cart_product(item.product, item.chosen_size)
        if available_stock is not None and desired_qty > available_stock:
            raise serializers.ValidationError({
                "detail": _("Недостаточно товара в наличии"),
                "available": available_stock,
            })

        should_verify = (
            desired_qty > item.quantity
            or item.verification_status != CartItem.VerificationStatus.VERIFIED
        )
        decision = None
        if should_verify:
            decision = CartSourceOfferPolicy().evaluate(
                product=item.product,
                chosen_size=item.chosen_size,
                quantity=desired_qty,
                target_currency=item.currency or cart.currency,
                baseline_public_price=item.price,
                acknowledged_price=serializer.validated_data.get('acknowledged_price'),
                acknowledged_currency=serializer.validated_data.get(
                    'acknowledged_currency', ''
                ),
            )

        if decision is not None:
            original_quantity = item.quantity
            original_updated_at = item.updated_at
            values = _cart_item_update_values(
                decision,
                item=item,
                requested_quantity=desired_qty,
            )
            updated = CartItem.objects.filter(
                pk=item.pk,
                quantity=original_quantity,
                updated_at=original_updated_at,
            ).update(**values)
            if not updated:
                return _cart_changed_response(request, cart)
            _touch_cart(cart)
            cart = _get_cart_with_prefetch(cart)
            return Response(CartSerializer(cart, context={'request': request}).data)

        item.quantity = desired_qty
        item.save()
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description="Подтвердить актуальную повышенную цену позиции корзины",
        request=AcknowledgeCartPriceSerializer,
        responses=CartSerializer,
    )
    @action(
        detail=True,
        methods=['post'],
        url_path='acknowledge-price',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def acknowledge_price(self, request, pk: int | None = None):
        serializer = AcknowledgeCartPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response({"detail": _("Корзина не найдена")}, status=404)
        try:
            item = cart.items.select_related('product', 'source_offer').get(pk=pk)
        except CartItem.DoesNotExist:
            return Response({"detail": _("Позиция не найдена")}, status=404)

        decision = CartSourceOfferPolicy().evaluate(
            product=item.product,
            chosen_size=item.chosen_size,
            quantity=item.quantity,
            target_currency=item.currency or cart.currency,
            baseline_public_price=item.price,
            acknowledged_price=serializer.validated_data['acknowledged_price'],
            acknowledged_currency=serializer.validated_data['acknowledged_currency'],
        )
        if decision is None:
            return Response(
                {
                    "detail": str(CartItem.VerificationIssue.VERIFICATION_UNSUPPORTED.label),
                    "code": CartItem.VerificationIssue.VERIFICATION_UNSUPPORTED,
                },
                status=status.HTTP_409_CONFLICT,
            )

        values = _cart_item_update_values(
            decision,
            item=item,
            requested_quantity=item.quantity,
        )
        updated = CartItem.objects.filter(
            pk=item.pk,
            quantity=item.quantity,
            updated_at=item.updated_at,
        ).update(**values)
        if not updated:
            return _cart_changed_response(request, cart)
        _touch_cart(cart)
        if not decision.payable:
            return _cart_verification_error_response(decision)
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description=(
            "Повторно проверить сохранённые source offers корзины. GET корзины "
            "никогда не выполняет внешнюю проверку."
        ),
        request=None,
        responses=CartSerializer,
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='revalidate',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def revalidate(self, request):
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response(_empty_cart_payload(request))

        max_items = max(
            1,
            min(
                int(getattr(settings, 'SOURCE_OFFER_CART_REVALIDATE_MAX_ITEMS', 20)),
                100,
            ),
        )
        items = list(
            cart.items.select_related('product', 'source_offer').order_by('pk')[:max_items]
        )
        policy = CartSourceOfferPolicy()
        changed = False
        for item in items:
            decision = policy.evaluate(
                product=item.product,
                chosen_size=item.chosen_size,
                quantity=item.quantity,
                target_currency=item.currency or cart.currency,
                baseline_public_price=item.price,
                acknowledged_price=item.price_acknowledged_value,
                acknowledged_currency=item.price_acknowledged_currency,
                force=True,
            )
            if decision is None:
                continue
            values = _cart_item_update_values(
                decision,
                item=item,
                requested_quantity=item.quantity,
            )
            updated = CartItem.objects.filter(
                pk=item.pk,
                quantity=item.quantity,
                updated_at=item.updated_at,
            ).update(**values)
            if not updated:
                return _cart_changed_response(request, cart)
            changed = True
        if changed:
            _touch_cart(cart)
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description="Удалить позицию из корзины",
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "0.00"
                },
                response_only=True
            )
        ]
    )
    @action(
        detail=True,
        methods=['delete'],
        url_path='remove',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def remove_item(self, request, pk=None):
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response({"detail": _("Корзина не найдена")}, status=404)
        _touch_cart(cart)
        try:
            item = cart.items.get(pk=pk)
        except CartItem.DoesNotExist:
            return Response({"detail": _("Позиция не найдена")}, status=404)
        item.delete()
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description="Очистить корзину",
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "0.00"
                },
                response_only=True
            )
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='clear',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def clear(self, request):
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response(_empty_cart_payload(request))
        _touch_cart(cart)
        cart.items.all().delete()
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description="Применить промокод к корзине",
        request=ApplyPromoCodeSerializer,
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={"code": "SUMMER2024"},
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "100.00",
                    "discount_amount": "10.00",
                    "final_amount": "90.00",
                    "promo_code": {
                        "id": 1,
                        "code": "SUMMER2024",
                        "discount_type": "percent",
                        "discount_value": "10.00"
                    }
                },
                response_only=True
            )
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='apply-promo',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def apply_promo(self, request):
        """Применить промокод к корзине."""
        serializer = ApplyPromoCodeSerializer(data=request.data)
        if not serializer.is_valid():
            err_msg = serializer.errors.get("code", [serializer.errors])[0]
            if isinstance(err_msg, list):
                err_msg = err_msg[0] if err_msg else _("Неверные данные")
            logger.warning("apply_promo: validation failed: %s", serializer.errors)
            return Response({"detail": str(err_msg)}, status=400)

        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response({"detail": _("Корзина не найдена")}, status=404)
        _touch_cart(cart)

        code = serializer.validated_data['code']
        try:
            promo_code = PromoCode.objects.get(code__iexact=code)
        except PromoCode.DoesNotExist:
            return Response({"detail": _("Промокод не найден")}, status=404)
        
        # Для валидности промокода используем те же числа, что и при create_from_cart:
        # сумму по сохранённым CartItem.price (цена на момент добавления).
        cart_total = float(
            sum((i.price * i.quantity for i in cart.items.all() if i.is_payable))
        )
        cart_currency = cart.currency

        # Проверка валидности промокода
        is_valid, error = promo_code.is_valid(
            user=request.user if request.user.is_authenticated else None,
            cart_total=cart_total,
            cart_currency=cart_currency,
        )
        if not is_valid:
            logger.info("apply_promo: promo %s invalid: %s (cart_total=%s, currency=%s)", code, error, cart_total, cart_currency)
            return Response({"detail": error}, status=400)
        
        # Применяем промокод
        cart.promo_code = promo_code
        cart.save(update_fields=['promo_code', 'updated_at'])
        
        # Возвращаем обновленную корзину
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        description="Удалить промокод из корзины",
        responses=CartSerializer,
        examples=[
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "user": None,
                    "session_key": "abc123",
                    "currency": "USD",
                    "items": [],
                    "items_count": 0,
                    "total_amount": "100.00",
                    "discount_amount": "0.00",
                    "final_amount": "100.00",
                    "promo_code": None
                },
                response_only=True
            )
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='remove-promo',
        throttle_classes=CART_MUTATION_THROTTLES,
    )
    def remove_promo(self, request):
        """Удалить промокод из корзины."""
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response(_empty_cart_payload(request))
        _touch_cart(cart)
        cart.promo_code = None
        cart.save(update_fields=['promo_code', 'updated_at'])
        
        # Возвращаем обновленную корзину
        cart = _get_cart_with_prefetch(cart)
        return Response(CartSerializer(cart, context={'request': request}).data)


class OrderViewSet(viewsets.ViewSet):
    """Управление заказами."""
    serializer_class = OrderSerializer
    queryset = Order.objects.none()
    permission_classes = [IsAuthenticated]
    # SessionAuthentication вызывает CSRF-ошибки для POST — используем только JWT
    authentication_classes = [JWTSafeAuthentication]

    def _get_order_for_user(self, user, number: str) -> Order:
        try:
            return (
                Order.objects.filter(user=user, number=number)
                .select_related('user', 'shipping_address', 'promo_code')
                .prefetch_related('items')
                .get()
            )
        except Order.DoesNotExist:
            raise Http404(_("Заказ не найден"))

    @extend_schema(
        description="Список заказов текущего пользователя",
        responses=OrderSerializer(many=True),
        examples=[
            OpenApiExample(
                'Пример списка заказов',
                value=[
                    {
                        "id": 100,
                        "number": "ABC123456789",
                        "status": "new",
                        "subtotal_amount": "30.00",
                        "shipping_amount": "0.00",
                        "discount_amount": "0.00",
                        "total_amount": "30.00",
                        "currency": "USD",
                        "items": [
                            {"id": 1, "product": 1, "product_name": "Test Product", "price": "10.00", "quantity": 3, "total": "30.00"}
                        ]
                    }
                ],
                response_only=True
            )
        ]
    )
    def list(self, request):
        from django.db.models import Prefetch
        from apps.catalog.models import ProductImage
        
        orders = (
            Order.objects
            .filter(user=request.user)
            .select_related('promo_code')
            .prefetch_related(
                Prefetch(
                    'items__product__images',
                    queryset=ProductImage.objects.all().order_by('is_main', 'sort_order')
                ),
                'items__product__translations'
            )
            .order_by('-created_at')
        )
        return Response(OrderSerializer(orders, many=True, context={'request': request}).data)

    def retrieve(self, request, pk: int | None = None):
        order = Order.objects.filter(user=request.user, pk=pk).prefetch_related('items', 'items__product__translations').first()
        if not order:
            raise Http404(_("Заказ не найден"))
        return Response(OrderSerializer(order, context={'request': request}).data)

    @extend_schema(description="Получить заказ по номеру", responses=OrderSerializer)
    @action(detail=False, methods=['get'], url_path=r'by-number/(?P<number>[^/]+)')
    def by_number(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        data = OrderSerializer(order, context={'request': request}).data
        if order.payment_method == 'crypto' and order.status == Order.OrderStatus.PENDING_PAYMENT:
            try:
                from apps.payments.models import CryptoPayment
                cp = CryptoPayment.objects.get(order=order)
                if cp.status == 'pending':
                    data['payment_data'] = {
                        'address': cp.address,
                        'qr_code': cp.qr_code_url,
                        'amount': str(cp.amount_crypto),
                        'amount_usd': str(cp.amount_fiat),
                        'currency': cp.currency,
                        'expires_at': cp.expires_at.isoformat() if cp.expires_at else '',
                        'invoice_url': cp.invoice_url or '',
                    }
            except Exception:
                pass
        return Response(data)

    @extend_schema(description="Получить подготовленный чек по заказу", responses=OrderReceiptSerializer)
    @action(detail=False, methods=['get'], url_path=r'receipt/(?P<number>[^/]+)')
    def receipt(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        receipt = build_order_receipt_payload(order)
        if request.query_params.get('format') == 'html':
            locale = request.META.get('HTTP_ACCEPT_LANGUAGE', 'ru').split(',')[0].split('-')[0]
            if locale not in ('ru', 'en'):
                locale = 'ru'
            html = render_receipt_html(order, receipt, locale=locale)
            return HttpResponse(html)
        serializer = OrderReceiptSerializer(receipt)
        return Response(serializer.data)

    @extend_schema(description="Отправить чек по email", request=None, responses=None)
    @action(
        detail=False,
        methods=['post'],
        url_path=r'send-receipt/(?P<number>[^/]+)',
        throttle_classes=RECEIPT_EMAIL_THROTTLES,
    )
    def send_receipt(self, request, number: str):
        order = self._get_order_for_user(request.user, number)
        # Не превращаем endpoint в авторизованный email relay: получатель всегда
        # берётся из принадлежащего пользователю заказа/профиля.
        email = get_order_customer_email(order)
        if not email:
            return Response({"detail": _("Не указан email для отправки чека")}, status=400)
        try:
            email = serializers.EmailField().to_internal_value(email)
        except serializers.ValidationError:
            return Response({"detail": _("Укажите корректный email")}, status=400)
        locale = (request.data.get('locale') or request.META.get('HTTP_ACCEPT_LANGUAGE', 'ru').split(',')[0].split('-')[0] or 'ru').strip()
        if locale not in ('ru', 'en'):
            locale = 'ru'
        send_order_receipt_task.delay(order.id, email, locale=locale)
        return Response({"detail": _("Чек будет отправлен на %(email)s") % {"email": email}})

    @extend_schema(
        description="Создать заказ из корзины",
        request=CreateOrderSerializer,
        responses=OrderSerializer,
        examples=[
            OpenApiExample(
                'Запрос',
                value={
                    "contact_name": "Иван Иванов",
                    "contact_phone": "+79990000000",
                    "contact_email": "ivan@example.com",
                    "shipping_address_text": "Москва, ул. Пушкина д.1",
                    "payment_method": "card",
                    "comment": "Позвонить курьеру"
                },
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 101,
                    "number": "ZXC987654321",
                    "status": "new",
                    "subtotal_amount": "30.00",
                    "shipping_amount": "0.00",
                    "discount_amount": "0.00",
                    "total_amount": "30.00",
                    "currency": "USD",
                    "items": [
                        {"id": 1, "product": 1, "product_name": "Test Product", "price": "10.00", "quantity": 3, "total": "30.00"}
                    ]
                },
                response_only=True
            )
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='create-from-cart',
        throttle_classes=CHECKOUT_THROTTLES,
    )
    def create_from_cart(self, request):
        """Создание заказа из текущей корзины.
        Требует аутентификацию. Примеры запросов в Swagger.
        """
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = _get_existing_cart_for_mutation(request)
        if cart is None:
            return Response({"detail": _("Корзина пуста")}, status=400)
        expected_fingerprint, preflight_response = _checkout_source_preflight(
            request,
            cart,
        )
        if preflight_response is not None:
            return preflight_response
        return self._create_from_cart_locked(
            request,
            cart_id=cart.pk,
            expected_fingerprint=expected_fingerprint,
            checkout_data=serializer.validated_data,
        )

    @transaction.atomic
    def _create_from_cart_locked(
        self,
        request,
        *,
        cart_id: int,
        expected_fingerprint: str,
        checkout_data: dict,
    ):
        """Create one order after re-checking the preflight snapshot under row locks."""

        # Serialize checkout attempts for one cart. A concurrent retry waits for
        # this transaction and then observes the emptied cart instead of
        # creating a second order/invoice from the same items.
        try:
            cart = Cart.objects.select_for_update().get(pk=cart_id)
        except Cart.DoesNotExist:
            return Response({"detail": _("Корзина пуста")}, status=400)
        locked_items = list(
            cart.items.select_for_update()
            .select_related('product')
            .order_by('pk')
        )
        if not locked_items:
            return Response({"detail": _("Корзина пуста")}, status=400)
        source_offers = ProductSourceOffer.objects.in_bulk(
            {
                item.source_offer_id
                for item in locked_items
                if item.source_offer_id is not None
            }
        )
        for item in locked_items:
            if item.source_offer_id in source_offers:
                item.source_offer = source_offers[item.source_offer_id]
        if _checkout_cart_fingerprint(cart, locked_items) != expected_fingerprint:
            return _cart_changed_response(request, cart)
        if any(not item.is_payable for item in locked_items):
            cart_payload = CartSerializer(
                _get_cart_with_prefetch(cart),
                context={'request': request},
            ).data
            cart_payload.update(
                {
                    'detail': _("Корзина содержит позиции, требующие проверки"),
                    'code': CartItem.VerificationIssue.CART_CHANGED,
                }
            )
            return Response(cart_payload, status=status.HTTP_409_CONFLICT)
        serializer = SimpleNamespace(validated_data=checkout_data)

        for item in locked_items:
            product = item.product
            if not product:
                continue
            if product.product_type == 'jewelry':
                ext = product.external_data or {}
                variant_id = ext.get('jewelry_variant_id') or ext.get('source_variant_id')
                if variant_id:
                    variant = JewelryVariant.objects.filter(id=variant_id, is_active=True).prefetch_related('sizes').first()
                    if variant and variant.sizes.exists():
                        if not item.chosen_size:
                            return Response({"detail": _("Укажите размер для товара в корзине")}, status=400)
                        size_obj = variant.sizes.filter(size_display=item.chosen_size).first()
                        if not size_obj:
                            size_obj = variant.sizes.filter(size_value=item.chosen_size).first()
                        if not size_obj:
                            return Response({"detail": _("Размер не найден для товара в корзине")}, status=400)
                        if not size_obj.is_available:
                            return Response({"detail": _("Размер недоступен для покупки")}, status=400)
                else:
                    base_obj = JewelryProduct.objects.filter(slug=product.slug, is_active=True).first()
                    if base_obj:
                        has_sizes = JewelryVariantSize.objects.filter(variant__product=base_obj).exists()
                        if has_sizes and not item.chosen_size:
                            return Response({"detail": _("Укажите размер для товара в корзине")}, status=400)

        # Расчет сумм и конвертация валют
        # Используем логику из CartSerializer для правильной конвертации валют
        cart_serializer = CartSerializer(cart, context={'request': request})
        
        order_currency = cart_serializer.get_currency(cart)
        subtotal = cart_serializer.get_total_amount(cart)
        shipping_options = cart_serializer.get_shipping_options(cart)
        
        # Получаем конвертированные цены для позиций заказа
        serialized_items = cart_serializer.data.get('items', [])
        converted_prices = {item['id']: item['price'] for item in serialized_items}
        
        shipping_method = (serializer.validated_data.get('shipping_method') or '').lower()
        if 'air' in shipping_method or 'авиа' in shipping_method:
            shipping = shipping_options.get('air', 0)
        elif 'sea' in shipping_method or 'мор' in shipping_method:
            shipping = shipping_options.get('sea', 0)
        else:
            # По умолчанию используем наземную доставку
            shipping = shipping_options.get('ground', 0)

        
        discount = 0
        promo_code = None
        consume_promo = False

        # Проверка и применение промокода из корзины или из запроса
        promo_code_value = serializer.validated_data.get('promo_code') or (cart.promo_code.code if cart.promo_code else None)
        if promo_code_value:
            try:
                promo_code = PromoCode.objects.select_for_update().get(
                    code__iexact=promo_code_value
                )
                # Проверка валидности промокода
                is_valid, error = promo_code.is_valid(user=request.user, cart_total=float(subtotal), cart_currency=order_currency)
                if is_valid:
                    discount = promo_code.calculate_discount(float(subtotal), currency=order_currency)
                    consume_promo = True
                else:
                    promo_code = None
            except PromoCode.DoesNotExist:
                pass

        total = Decimal(str(subtotal)) + Decimal(str(shipping)) - Decimal(str(discount))

        # Генерация номера заказа
        number = uuid.uuid4().hex[:12].upper()
        payment_method = (serializer.validated_data.get('payment_method') or '').strip().lower()
        is_crypto = payment_method == 'crypto'

        # Крипто: создаём инвойс ДО заказа, чтобы не терять корзину при ошибке провайдера
        locale = (serializer.validated_data.get("locale") or "").strip() or request.META.get("HTTP_ACCEPT_LANGUAGE", "").split(",")[0].split("-")[0] or "ru"
        if locale not in ("ru", "en"):
            locale = "ru"

        if is_crypto:
            invoice_data, payment_data = _create_crypto_invoice(number, total, order_currency, locale=locale)
            if not invoice_data:
                return Response(
                    {"detail": _("Не удалось создать платёжную ссылку. Попробуйте позже или выберите другой способ оплаты.")},
                    status=503,
                )

        # Consume the locked promo only after the external invoice (if any)
        # succeeded. Any later DB error rolls this update back with the order.
        if promo_code is not None and consume_promo:
            promo_code.used_count += 1
            promo_code.save(update_fields=['used_count'])

        order = Order.objects.create(
            user=request.user,
            number=number,
            subtotal_amount=subtotal,
            shipping_amount=shipping,
            discount_amount=discount,
            total_amount=total,
            currency=order_currency,
            promo_code=promo_code,
            contact_name=serializer.validated_data.get('contact_name'),
            contact_phone=serializer.validated_data.get('contact_phone'),
            contact_email=serializer.validated_data.get('contact_email') or '',
            shipping_method=serializer.validated_data.get('shipping_method') or '',
            payment_method=serializer.validated_data.get('payment_method') or '',
            comment=serializer.validated_data.get('comment') or '',
            status=Order.OrderStatus.PENDING_PAYMENT if is_crypto else Order.OrderStatus.NEW,
        )

        # Адрес доставки
        shipping_address_text = (serializer.validated_data.get('shipping_address_text') or '').strip()
        shipping_address_id = serializer.validated_data.get('shipping_address')
        if shipping_address_id:
            try:
                addr = UserAddress.objects.get(id=shipping_address_id, user=request.user)
                order.shipping_address = addr
                if not shipping_address_text:
                    address_parts = [addr.country, addr.city, f"{addr.street} {addr.house}"]
                    if addr.region:
                        address_parts.insert(1, addr.region)
                    if addr.postal_code:
                        address_parts.append(addr.postal_code)
                    if addr.apartment:
                        address_parts.append(f"кв. {addr.apartment}")
                    if addr.entrance:
                        address_parts.append(f"подъезд {addr.entrance}")
                    if addr.floor:
                        address_parts.append(f"этаж {addr.floor}")
                    shipping_address_text = ", ".join(filter(None, address_parts))
                order.save()
            except UserAddress.DoesNotExist:
                pass
        elif not shipping_address_text and request.user and request.user.is_authenticated:
            default_addr = (
                UserAddress.objects.filter(user=request.user, is_default=True, is_active=True).first()
                or UserAddress.objects.filter(user=request.user, is_active=True).order_by("-created_at").first()
            )
            if default_addr:
                order.shipping_address = default_addr
                address_parts = [default_addr.country, default_addr.city, f"{default_addr.street} {default_addr.house}"]
                if default_addr.region:
                    address_parts.insert(1, default_addr.region)
                if default_addr.postal_code:
                    address_parts.append(default_addr.postal_code)
                if default_addr.apartment:
                    address_parts.append(f"кв. {default_addr.apartment}")
                if default_addr.entrance:
                    address_parts.append(f"подъезд {default_addr.entrance}")
                if default_addr.floor:
                    address_parts.append(f"этаж {default_addr.floor}")
                shipping_address_text = ", ".join(filter(None, address_parts))
                order.save()
        if shipping_address_text:
            order.shipping_address_text = shipping_address_text
            order.save(update_fields=['shipping_address_text'])

        if is_crypto:
            # Крипто: сохраняем CryptoPayment, позиции заказа без списания остатка
            _save_crypto_payment(order, invoice_data, order_currency)
            for item in locked_items:
                item_price = converted_prices.get(item.id, item.price)
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    chosen_size=item.chosen_size,
                    price=item_price,
                    quantity=item.quantity,
                    total=Decimal(str(item_price)) * item.quantity,
                    **_order_item_source_snapshot(item),
                )
            CartItem.objects.filter(pk__in=[item.pk for item in locked_items]).delete()
            response_data = OrderSerializer(order).data
            response_data["payment_data"] = payment_data
            return Response(response_data, status=201)
        else:
            # Позиции заказа + атомарное списание остатка
            for item in locked_items:
                _decrement_stock_for_cart_item(item.product, item.chosen_size, item.quantity)
                item_price = converted_prices.get(item.id, item.price)
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    chosen_size=item.chosen_size,
                    price=item_price,
                    quantity=item.quantity,
                    total=Decimal(str(item_price)) * item.quantity,
                    **_order_item_source_snapshot(item),
                )
            CartItem.objects.filter(pk__in=[item.pk for item in locked_items]).delete()

            from django.db import transaction

            # Отправляем задачи только после успешного коммита транзакции,
            # чтобы избежать race condition, когда Celery ищет еще не созданный заказ.
            # Берём email покупателя и не отправляем на админские адреса
            receipt_email = get_order_customer_email(order)
            if receipt_email:
                transaction.on_commit(
                    lambda: send_order_receipt_task.delay(order.id, receipt_email, locale=locale)
                )
            
            transaction.on_commit(
                lambda: notify_new_order_telegram.delay(order_id=order.id, locale=locale)
            )

            return Response(OrderSerializer(order).data, status=201)
