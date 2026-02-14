"""Публичные представления для платежей (заглушки и крипто webhook)."""
import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import CryptoPayment
from .providers import DummyProvider

logger = logging.getLogger(__name__)


class PaymentInitView(APIView):
    """Инициализация платежа через провайдера-заглушку."""

    @extend_schema(summary="Инициализация платежа (заглушка)", responses={200: dict})
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
    client = request.META.get("REMOTE_ADDR") or ""
    return client in allowed_ips


@method_decorator(csrf_exempt, name="dispatch")
class CryptoWebhookView(APIView):
    """Webhook для уведомлений от CoinRemitter о статусе криптоплатежа."""

    permission_classes = []  # AllowAny
    authentication_classes = []

    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        """Для проверки доступности URL (CoinRemitter и др. могут валидировать)."""
        return Response({"ok": True}, status=200)

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        if not _verify_webhook_request(request):
            logger.warning("Crypto webhook: rejected IP %s", request.META.get("REMOTE_ADDR"))
            return Response(status=403)
        data = _parse_webhook_payload(request)
        invoice_id = (data.get("id") or data.get("invoice_id") or "").strip()
        status = (data.get("status") or "").strip().lower()
        if not invoice_id:
            # CoinRemitter отправляет тестовый POST при валидации URL — возвращаем 200
            logger.info("Crypto webhook: validation ping (no invoice_id)")
            return Response({"ok": True}, status=200)
        try:
            cp = CryptoPayment.objects.get(invoice_id=invoice_id)
        except CryptoPayment.DoesNotExist:
            logger.warning("Crypto webhook: unknown invoice_id=%s", invoice_id)
            return Response({"ok": True}, status=200)
        order = cp.order
        if status in ("confirm", "confirmed", "paid", "1"):
            if order.payment_status == "paid":
                return Response({"ok": True}, status=200)
            from django.db import transaction
            from apps.orders.models import Order
            from apps.orders.views import _decrement_stock_for_cart_item
            with transaction.atomic():
                for item in order.items.select_related("product").all():
                    _decrement_stock_for_cart_item(item.product, item.chosen_size, item.quantity)
                order.status = Order.OrderStatus.PAID
                order.payment_status = "paid"
                order.save(update_fields=["status", "payment_status"])
                cp.status = "confirmed"
                cp.save(update_fields=["status"])
            logger.info("Crypto payment confirmed: order=%s invoice_id=%s", order.number, invoice_id)
        elif status in ("expire", "expired", "0"):
            cp.status = "expired"
            cp.save(update_fields=["status"])
        return Response({"ok": True}, status=200)

