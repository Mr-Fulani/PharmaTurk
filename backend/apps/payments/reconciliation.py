"""Read-only classification of local and authoritative CoinRemitter state."""
from __future__ import annotations

from dataclasses import dataclass

from .models import CryptoPayment, CryptoPaymentStatus
from .views import CoinRemitterVerificationError, _verify_authoritative_invoice


@dataclass(frozen=True)
class ReconciliationResult:
    category: str
    provider_status_code: int | None
    is_drift: bool
    is_critical: bool = False


def classify_coinremitter_state(
    payment: CryptoPayment,
    provider_invoice: dict,
) -> ReconciliationResult:
    """Compare provider state to local state without writing either system."""
    try:
        provider_status = _verify_authoritative_invoice(
            payment,
            provider_invoice,
            webhook_id="",
            webhook_invoice_id="",
        )
    except CoinRemitterVerificationError:
        return ReconciliationResult(
            category="invalid_provider_invoice",
            provider_status_code=None,
            is_drift=True,
            is_critical=True,
        )

    order_paid = payment.order.payment_status == "paid"
    payment_confirmed = payment.status == CryptoPaymentStatus.CONFIRMED
    payment_expired = payment.status == CryptoPaymentStatus.EXPIRED

    if provider_status in {1, 3}:
        if order_paid and payment_confirmed:
            return ReconciliationResult("consistent_paid", provider_status, False)
        return ReconciliationResult(
            "needs_local_confirmation",
            provider_status,
            True,
            is_critical=True,
        )

    if provider_status in {4, 5}:
        if order_paid or payment_confirmed:
            return ReconciliationResult(
                "local_paid_provider_expired",
                provider_status,
                True,
                is_critical=True,
            )
        if payment_expired:
            return ReconciliationResult("consistent_expired", provider_status, False)
        return ReconciliationResult("needs_local_expiration", provider_status, True)

    # Pending (0) and underpaid (2) are non-fulfilling but still active.
    if order_paid or payment_confirmed:
        return ReconciliationResult(
            "local_paid_provider_nonpaid",
            provider_status,
            True,
            is_critical=True,
        )
    if payment_expired:
        return ReconciliationResult(
            "local_expired_provider_active",
            provider_status,
            True,
            is_critical=True,
        )
    return ReconciliationResult("consistent_pending", provider_status, False)
