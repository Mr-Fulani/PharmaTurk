"""Публичные представления для платежей (заглушки и крипто webhook)."""
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.throttles import get_trusted_client_ip

from .models import CryptoPayment
from .providers import DummyProvider
from .providers.coinremitter import get_invoice
from .throttles import CRYPTO_WEBHOOK_THROTTLES

logger = logging.getLogger(__name__)


class CoinRemitterWebhookSerializer(serializers.Serializer):
    """Строгая валидация входящих данных от CoinRemitter Webhook."""
    id = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=128)
    invoice_id = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=128)
    # Accepted for provider compatibility, but deliberately never trusted.
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=32)


class PaymentInitResponseSerializer(serializers.Serializer):
    payment_id = serializers.CharField()
    redirect_url = serializers.URLField(allow_null=True)
    extra = serializers.JSONField()


class PaymentInitView(APIView):
    """Инициализация платежа через провайдера-заглушку."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Инициализация платежа (заглушка)",
        request=None,
        responses={200: PaymentInitResponseSerializer},
    )
    def post(self, request: Request) -> Response:  # type: ignore[override]
        provider = DummyProvider()
        result = provider.create_payment(
            amount_minor=100,
            currency="RUB",
            description="Тестовый платёж",
            metadata={},
        )
        return Response({
            "payment_id": result.payment_id,
            "redirect_url": result.redirect_url,
            "extra": result.extra,
        })


def _parse_webhook_payload(request: Request) -> dict:
    """Parse JSON or form body; return dict with id/invoice_id, status."""
    try:
        data = request.data
        if hasattr(data, "dict"):
            data = data.dict()
        elif not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    return data


def _verify_webhook_request(request: Request) -> bool:
    """Optional: IP whitelist. CoinRemitter does not always document IPs; skip if not configured."""
    allowed_ips = getattr(settings, "COINREMITTER_WEBHOOK_IP_WHITELIST", None)
    if not allowed_ips:
        return True
    client = get_trusted_client_ip(request) or ""
    return client in allowed_ips


class CoinRemitterVerificationError(ValueError):
    """The authenticated provider response does not match the local payment."""


def _parse_status_code(value: object) -> int:
    """Return a documented CoinRemitter invoice status code, fail closed otherwise."""
    if isinstance(value, bool):
        raise CoinRemitterVerificationError("invalid status_code")
    if isinstance(value, int):
        status_code = value
    elif isinstance(value, str) and value.strip() in {"0", "1", "2", "3", "4", "5"}:
        status_code = int(value.strip())
    else:
        raise CoinRemitterVerificationError("invalid status_code")
    if status_code not in {0, 1, 2, 3, 4, 5}:
        raise CoinRemitterVerificationError("unsupported status_code")
    return status_code


def _amount_in_currency(value: object, currency: str) -> Decimal | None:
    """Read a non-negative Decimal from a CoinRemitter amount mapping."""
    if not isinstance(value, dict):
        return None
    normalized = {str(key).upper(): item for key, item in value.items()}
    raw_amount = normalized.get(currency.upper())
    if raw_amount is None or isinstance(raw_amount, bool):
        return None
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def _verify_authoritative_invoice(
    payment: CryptoPayment,
    provider_invoice: dict,
    webhook_id: str,
    webhook_invoice_id: str,
) -> int:
    """Validate provider identity, order binding, amounts and authoritative status."""
    remote_id = str(provider_invoice.get("id") or "").strip()
    remote_invoice_id = str(provider_invoice.get("invoice_id") or "").strip()
    remote_ids = {value for value in (remote_id, remote_invoice_id) if value}
    local_invoice_code = str(getattr(payment, "invoice_code", "") or "").strip()

    local_ids = {
        value
        for value in (
            str(payment.invoice_id or "").strip(),
            local_invoice_code,
        )
        if value
    }
    if not remote_ids or not local_ids.intersection(remote_ids):
        raise CoinRemitterVerificationError("provider invoice identity mismatch")
    if local_invoice_code and local_invoice_code != remote_invoice_id:
        raise CoinRemitterVerificationError("stored invoice_id mismatch")
    if webhook_id and webhook_id != remote_id:
        raise CoinRemitterVerificationError("webhook id mismatch")
    if webhook_invoice_id and webhook_invoice_id != remote_invoice_id:
        raise CoinRemitterVerificationError("webhook invoice_id mismatch")
    if str(provider_invoice.get("custom_data1") or "").strip() != payment.order.number:
        raise CoinRemitterVerificationError("order binding mismatch")

    currency = str(payment.order.currency or payment.currency or "").upper()
    expected_total = Decimal(payment.order.total_amount)
    provider_total = _amount_in_currency(provider_invoice.get("total_amount"), currency)
    if provider_total is None or provider_total != expected_total:
        raise CoinRemitterVerificationError("invoice total mismatch")

    status_code = _parse_status_code(provider_invoice.get("status_code"))
    if status_code in {1, 2, 3}:
        paid_amount = _amount_in_currency(provider_invoice.get("paid_amount"), currency)
        if paid_amount is None:
            raise CoinRemitterVerificationError("paid amount is missing")
        if status_code in {1, 3} and paid_amount < provider_total:
            raise CoinRemitterVerificationError("paid amount is insufficient")
        if status_code == 2 and paid_amount >= provider_total:
            raise CoinRemitterVerificationError("underpaid status conflicts with paid amount")
    return status_code


def _apply_authoritative_invoice(
    payment_id: int,
    provider_invoice: dict,
    webhook_id: str,
    webhook_invoice_id: str,
) -> str:
    """Apply an authenticated provider state exactly once under row locks."""
    from apps.orders.models import Order
    from apps.orders.views import _decrement_stock_for_cart_item

    with transaction.atomic():
        payment = CryptoPayment.objects.select_for_update().get(pk=payment_id)
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        payment.order = order
        status_code = _verify_authoritative_invoice(
            payment,
            provider_invoice,
            webhook_id,
            webhook_invoice_id,
        )
        remote_invoice_code = str(provider_invoice.get("invoice_id") or "").strip()
        if remote_invoice_code and not payment.invoice_code:
            # Backfill historical rows that only stored CoinRemitter's long id.
            payment.invoice_code = remote_invoice_code
            payment.save(update_fields=["invoice_code"])

        if status_code in {1, 3}:  # Paid / Over Paid
            if order.payment_status == "paid" or payment.status == "confirmed":
                # Heal the two local status fields without replaying stock or notifications.
                if payment.status != "confirmed":
                    payment.status = "confirmed"
                    payment.save(update_fields=["status"])
                if order.payment_status != "paid":
                    order.payment_status = "paid"
                    if order.status == Order.OrderStatus.PENDING_PAYMENT:
                        order.status = Order.OrderStatus.PAID
                        order.save(update_fields=["status", "payment_status"])
                    else:
                        order.save(update_fields=["payment_status"])
                return "duplicate"

            for item in order.items.select_related("product").all():
                _decrement_stock_for_cart_item(item.product, item.chosen_size, item.quantity)
            order.status = Order.OrderStatus.PAID
            order.payment_status = "paid"
            order.save(update_fields=["status", "payment_status"])
            payment.status = "confirmed"
            payment.save(update_fields=["status"])

            from .tasks import notify_crypto_payment_confirmed

            transaction.on_commit(
                lambda order_id=order.id: notify_crypto_payment_confirmed.delay(order_id)
            )
            return "confirmed"

        if status_code in {4, 5}:  # Expired / Cancelled
            # A late expiration must never downgrade an already recognized payment.
            if order.payment_status == "paid" or payment.status == "confirmed":
                return "paid_unchanged"
            if payment.status == "expired":
                return "duplicate"
            payment.status = "expired"
            payment.save(update_fields=["status"])

            from .tasks import notify_crypto_payment_expired

            transaction.on_commit(
                lambda order_id=order.id: notify_crypto_payment_expired.delay(order_id)
            )
            return "expired"

        # Pending and Under Paid are deliberately non-fulfilling states.
        return "unchanged"


@method_decorator(csrf_exempt, name="dispatch")
class CryptoWebhookView(APIView):
    """Webhook для уведомлений от CoinRemitter о статусе криптоплатежа."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = CRYPTO_WEBHOOK_THROTTLES

    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        """Для проверки доступности URL (CoinRemitter и др. могут валидировать)."""
        return Response({"ok": True}, status=200)

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        if not _verify_webhook_request(request):
            logger.warning("Crypto webhook: rejected IP %s", get_trusted_client_ip(request))
            return Response(status=403)
            
        data = _parse_webhook_payload(request)
        serializer = CoinRemitterWebhookSerializer(data=data)
        if not serializer.is_valid():
            logger.warning("Crypto webhook: invalid payload %s", serializer.errors)
            return Response({"ok": False, "errors": serializer.errors}, status=400)
            
        validated_data = serializer.validated_data
        webhook_id = (validated_data.get("id") or "").strip()
        webhook_invoice_id = (validated_data.get("invoice_id") or "").strip()
        candidate_ids = list(dict.fromkeys(value for value in (webhook_id, webhook_invoice_id) if value))
        
        if not candidate_ids:
            # CoinRemitter отправляет тестовый POST при валидации URL — возвращаем 200
            logger.info("Crypto webhook: validation ping (no invoice_id)")
            return Response({"ok": True}, status=200)

        payments = list(
            CryptoPayment.objects.filter(
                Q(invoice_id__in=candidate_ids) | Q(invoice_code__in=candidate_ids),
                provider="coinremitter",
            ).select_related("order")[:2]
        )
        if len(payments) != 1:
            logger.warning("Crypto webhook: unknown or ambiguous invoice identifier")
            return Response({"ok": True}, status=200)

        payment = payments[0]
        # The public webhook body is only a lookup hint. The authenticated API
        # response below is the sole source of payment status and amounts.
        lookup_id = webhook_invoice_id or payment.invoice_code or payment.invoice_id
        provider_invoice = get_invoice(lookup_id)
        if provider_invoice is None:
            logger.error("Crypto webhook: authoritative invoice lookup failed")
            return Response({"ok": False, "detail": "provider_unavailable"}, status=503)

        try:
            result = _apply_authoritative_invoice(
                payment.id,
                provider_invoice,
                webhook_id,
                webhook_invoice_id,
            )
        except CoinRemitterVerificationError as exc:
            logger.warning("Crypto webhook verification failed: %s", exc)
            return Response({"ok": False, "detail": "verification_failed"}, status=403)

        logger.info(
            "Crypto webhook reconciled: order=%s result=%s",
            payment.order.number,
            result,
        )
        return Response({"ok": True}, status=200)
