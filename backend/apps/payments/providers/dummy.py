"""Заглушка платёжного провайдера для разработки без реальных оплат."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from django.utils import timezone


def create_invoice_dummy(
    amount_fiat: float | Decimal,
    fiat_currency: str,
    order_number: str,
    notify_url: str,
    success_url: str = "",
    fail_url: str = "",
    expiry_minutes: int = 30,
    description: str = "",
) -> dict[str, Any]:
    """Заглушка для создания крипто-инвойса в разработке (когда CoinRemitter не настроен)."""
    amount = Decimal(str(amount_fiat))
    expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
    return {
        "invoice_id": f"dummy-{order_number[:8]}",
        "address": "TDevWallet123456789012345678901",
        "qr_code": "",
        "amount": amount,
        "amount_usd": amount,
        "currency": (fiat_currency or "USD").upper()[:3],
        "expires_at": expires_at,
        "invoice_url": "",
    }


@dataclass
class PaymentInitResult:
    """Результат инициализации платежа."""

    payment_id: str
    redirect_url: str | None
    extra: dict


class PaymentProvider(Protocol):
    """Контракт платёжного провайдера."""

    def create_payment(self, *, amount_minor: int, currency: str, description: str, metadata: dict) -> PaymentInitResult:  # noqa: E501
        """Инициализирует платёж и возвращает данные для редиректа/виджета."""

    def capture_payment(self, payment_id: str) -> bool:
        """Подтверждает платёж (если требуется двухстадийная оплата)."""

    def refund_payment(self, payment_id: str, *, amount_minor: int | None = None) -> bool:
        """Возвращает средства полностью/частично."""


class DummyProvider:
    """Заглушка провайдера для разработки без реальных оплат."""

    def create_payment(self, *, amount_minor: int, currency: str, description: str, metadata: dict) -> PaymentInitResult:  # noqa: E501
        return PaymentInitResult(payment_id="dummy-123", redirect_url=None, extra={"status": "created"})

    def capture_payment(self, payment_id: str) -> bool:
        return True

    def refund_payment(self, payment_id: str, *, amount_minor: int | None = None) -> bool:
        return True
