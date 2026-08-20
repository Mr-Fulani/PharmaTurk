from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.payments.models import CryptoPaymentStatus
from apps.payments.reconciliation import classify_coinremitter_state


def _payment(*, local_payment="pending", local_order="pending"):
    return SimpleNamespace(
        pk=7,
        invoice_id="provider-long-id",
        invoice_code="short-id",
        status=local_payment,
        order=SimpleNamespace(
            number="ORDER-7",
            currency="USD",
            total_amount=Decimal("12.50"),
            payment_status=local_order,
        ),
    )


def _invoice(status_code, *, paid="0"):
    return {
        "id": "provider-long-id",
        "invoice_id": "short-id",
        "custom_data1": "ORDER-7",
        "status_code": status_code,
        "total_amount": {"USD": "12.50"},
        "paid_amount": {"USD": paid},
    }


@pytest.mark.parametrize("status_code", [1, 3])
def test_remote_paid_local_pending_is_critical_drift(status_code):
    result = classify_coinremitter_state(
        _payment(),
        _invoice(status_code, paid="12.50"),
    )

    assert result.category == "needs_local_confirmation"
    assert result.is_drift
    assert result.is_critical


def test_remote_and_local_paid_are_consistent():
    result = classify_coinremitter_state(
        _payment(local_payment="confirmed", local_order="paid"),
        _invoice(1, paid="12.50"),
    )

    assert result.category == "consistent_paid"
    assert not result.is_drift


def test_local_paid_remote_pending_is_critical_drift():
    result = classify_coinremitter_state(
        _payment(local_payment="confirmed", local_order="paid"),
        _invoice(0),
    )

    assert result.category == "local_paid_provider_nonpaid"
    assert result.is_critical


def test_invalid_remote_binding_is_critical_without_leaking_details():
    invoice = _invoice(0)
    invoice["custom_data1"] = "OTHER-ORDER"

    result = classify_coinremitter_state(_payment(), invoice)

    assert result.category == "invalid_provider_invoice"
    assert result.provider_status_code is None
    assert result.is_critical


def test_stored_short_invoice_id_mismatch_is_critical():
    payment = _payment()
    payment.invoice_code = "different-short-id"

    result = classify_coinremitter_state(payment, _invoice(0))

    assert result.category == "invalid_provider_invoice"
    assert result.is_critical


@patch("apps.payments.management.commands.reconcile_coinremitter.get_invoice")
@patch("apps.payments.management.commands.reconcile_coinremitter.CryptoPayment.objects")
def test_command_is_read_only_and_reports_drift(objects, get_invoice):
    payment = _payment()
    queryset = MagicMock()
    objects.select_related.return_value = queryset
    queryset.filter.return_value.order_by.return_value.__getitem__.return_value = [payment]
    get_invoice.return_value = _invoice(1, paid="12.50")
    stdout = StringIO()

    call_command(
        "reconcile_coinremitter",
        older_than_minutes=0,
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert "category=needs_local_confirmation" in output
    assert "checked=1 drift=1 critical=1 unavailable=0" in output
    assert "READ ONLY" in output
    assert payment.status == CryptoPaymentStatus.PENDING
    get_invoice.assert_called_once_with("short-id")


@patch("apps.payments.management.commands.reconcile_coinremitter.get_invoice")
@patch("apps.payments.management.commands.reconcile_coinremitter.CryptoPayment.objects")
def test_command_can_fail_monitoring_when_provider_is_unavailable(objects, get_invoice):
    payment = _payment()
    queryset = MagicMock()
    objects.select_related.return_value = queryset
    queryset.filter.return_value.order_by.return_value.__getitem__.return_value = [payment]
    get_invoice.return_value = None

    with pytest.raises(CommandError, match="drift or unavailable"):
        call_command(
            "reconcile_coinremitter",
            older_than_minutes=0,
            fail_on_drift=True,
            stdout=StringIO(),
            stderr=StringIO(),
        )
