"""Durable and duplicate-safe CoinRemitter invoice orchestration tests."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.checks import payment_outbox_configuration_check
from apps.payments.models import (
    CryptoInvoiceRequest,
    CryptoInvoiceRequestStatus,
    CryptoPayment,
)
from apps.payments.tasks import (
    create_coinremitter_invoice_request,
    dispatch_pending_crypto_invoice_requests,
    enqueue_crypto_invoice_request,
    reconcile_coinremitter_state,
)
from apps.users.models import User


def test_outbox_schedule_and_route_use_serviced_queue(settings):
    from config.celery import app

    dispatch = settings.CELERY_BEAT_SCHEDULE["coinremitter-outbox-dispatch"]
    reconciliation = settings.CELERY_BEAT_SCHEDULE["coinremitter-reconciliation"]
    route = app.amqp.router.route(
        {}, "apps.payments.tasks.create_coinremitter_invoice_request"
    )

    assert dispatch["task"] == "apps.payments.tasks.dispatch_pending_crypto_invoice_requests"
    assert dispatch["schedule"] == settings.COINREMITTER_OUTBOX_DISPATCH_INTERVAL_SECONDS
    assert reconciliation["task"] == "apps.payments.tasks.reconcile_coinremitter_state"
    assert reconciliation["schedule"] == settings.COINREMITTER_RECONCILIATION_INTERVAL_SECONDS
    assert route["queue"].name == "celery"


def test_outbox_system_check_rejects_unsafe_batch_size(settings):
    settings.COINREMITTER_RECONCILIATION_BATCH_SIZE = 11

    errors = payment_outbox_configuration_check(None)

    assert [error.id for error in errors] == ["payments.E005"]


def test_outbox_system_check_rejects_short_republish_window(settings):
    settings.COINREMITTER_OUTBOX_REPUBLISH_SECONDS = 59

    errors = payment_outbox_configuration_check(None)

    assert [error.id for error in errors] == ["payments.E007"]


@pytest.fixture
def invoice_request():
    user = User.objects.create_user(
        username="outbox-user",
        email="outbox@example.test",
        password="not-used",
    )
    order = Order.objects.create(
        user=user,
        number="OUTBOX000001",
        status=Order.OrderStatus.PENDING_PAYMENT,
        subtotal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        currency="RUB",
        contact_name="Outbox User",
        contact_phone="+905550000000",
        payment_method="crypto",
    )
    return CryptoInvoiceRequest.objects.create(
        order=order,
        idempotency_key="a" * 64,
        amount_fiat=order.total_amount,
        fiat_currency=order.currency,
        locale="ru",
    )


def _invoice():
    return {
        "invoice_id": "provider-long-id",
        "invoice_code": "TCN001",
        "address": "test-address",
        "amount": Decimal("1.25000000"),
        "amount_usd": Decimal("1.25"),
        "expires_at": timezone.now() + timedelta(minutes=30),
        "qr_code": "",
        "invoice_url": "https://coinremitter.example/invoice/one",
    }


@pytest.mark.django_db(transaction=True)
def test_provider_call_runs_after_claim_transaction_and_is_idempotent(
    settings,
    invoice_request,
):
    settings.COINREMITTER_API_KEY = "configured"
    settings.COINREMITTER_API_PASSWORD = "configured"

    def provider_call(*args, **kwargs):
        assert connection.in_atomic_block is False
        return _invoice(), {"invoice_url": _invoice()["invoice_url"]}

    with patch(
        "apps.orders.views._create_crypto_invoice",
        side_effect=provider_call,
    ) as create_invoice:
        first = create_coinremitter_invoice_request.run(invoice_request.pk)
        second = create_coinremitter_invoice_request.run(invoice_request.pk)

    invoice_request.refresh_from_db()
    payment = CryptoPayment.objects.get(order=invoice_request.order)
    assert first == {"status": "succeeded", "payment_id": payment.pk}
    assert second == {"status": "already_succeeded"}
    assert invoice_request.status == CryptoInvoiceRequestStatus.SUCCEEDED
    assert invoice_request.attempt_count == 1
    assert invoice_request.provider_invoice_id == "provider-long-id"
    assert invoice_request.provider_invoice_code == "TCN001"
    assert payment.amount_fiat == Decimal("100.00")
    assert payment.currency == "RUB"
    create_invoice.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_unavailable_provider_result_is_quarantined_without_retry(
    settings,
    invoice_request,
):
    settings.COINREMITTER_API_KEY = "configured"
    settings.COINREMITTER_API_PASSWORD = "configured"

    with patch(
        "apps.orders.views._create_crypto_invoice",
        return_value=(None, None),
    ) as create_invoice:
        first = create_coinremitter_invoice_request.run(invoice_request.pk)
        second = create_coinremitter_invoice_request.run(invoice_request.pk)

    invoice_request.refresh_from_db()
    assert first == {
        "status": "uncertain",
        "error_code": "provider_result_unavailable",
    }
    assert second == {"status": "uncertain"}
    assert invoice_request.status == CryptoInvoiceRequestStatus.UNCERTAIN
    assert invoice_request.last_error_code == "provider_result_unavailable"
    assert invoice_request.attempt_count == 1
    assert not CryptoPayment.objects.filter(order=invoice_request.order).exists()
    create_invoice.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_incomplete_provider_result_never_creates_payable_row(
    settings,
    invoice_request,
):
    settings.COINREMITTER_API_KEY = "configured"
    settings.COINREMITTER_API_PASSWORD = "configured"
    incomplete = _invoice()
    incomplete["invoice_id"] = ""

    with patch(
        "apps.orders.views._create_crypto_invoice",
        return_value=(incomplete, {}),
    ):
        result = create_coinremitter_invoice_request.run(invoice_request.pk)

    invoice_request.refresh_from_db()
    assert result == {"status": "uncertain", "error_code": "invalid_provider_result"}
    assert invoice_request.status == CryptoInvoiceRequestStatus.UNCERTAIN
    assert not CryptoPayment.objects.filter(order=invoice_request.order).exists()


@pytest.mark.django_db(transaction=True)
def test_non_positive_provider_amount_never_creates_payable_row(
    settings,
    invoice_request,
):
    settings.COINREMITTER_API_KEY = "configured"
    settings.COINREMITTER_API_PASSWORD = "configured"
    incomplete = _invoice()
    incomplete["amount"] = Decimal("0")

    with patch(
        "apps.orders.views._create_crypto_invoice",
        return_value=(incomplete, {}),
    ):
        result = create_coinremitter_invoice_request.run(invoice_request.pk)

    invoice_request.refresh_from_db()
    assert result == {"status": "uncertain", "error_code": "invalid_provider_result"}
    assert invoice_request.status == CryptoInvoiceRequestStatus.UNCERTAIN
    assert not CryptoPayment.objects.filter(order=invoice_request.order).exists()


@pytest.mark.django_db
def test_processing_duplicate_never_calls_provider(settings, invoice_request):
    settings.COINREMITTER_API_KEY = "configured"
    settings.COINREMITTER_API_PASSWORD = "configured"
    CryptoInvoiceRequest.objects.filter(pk=invoice_request.pk).update(
        status=CryptoInvoiceRequestStatus.PROCESSING,
        processing_started_at=timezone.now(),
        attempt_count=1,
    )

    with patch("apps.orders.views._create_crypto_invoice") as create_invoice:
        result = create_coinremitter_invoice_request.run(invoice_request.pk)

    assert result == {"status": "already_processing"}
    create_invoice.assert_not_called()


@pytest.mark.django_db
def test_successful_enqueue_records_publish_time(invoice_request):
    with patch(
        "apps.payments.tasks.create_coinremitter_invoice_request.delay"
    ) as delay:
        published = enqueue_crypto_invoice_request(invoice_request.pk)

    invoice_request.refresh_from_db()
    assert published is True
    assert invoice_request.last_enqueued_at is not None
    delay.assert_called_once_with(invoice_request.pk)


@pytest.mark.django_db
def test_failed_enqueue_leaves_row_eligible_for_dispatch(invoice_request):
    with patch(
        "apps.payments.tasks.create_coinremitter_invoice_request.delay",
        side_effect=RuntimeError("broker unavailable"),
    ):
        published = enqueue_crypto_invoice_request(invoice_request.pk)

    invoice_request.refresh_from_db()
    assert published is False
    assert invoice_request.last_enqueued_at is None


@pytest.mark.django_db
def test_dispatcher_only_publishes_pending_rows(settings, invoice_request):
    settings.COINREMITTER_OUTBOX_DISPATCH_BATCH_SIZE = 100
    settings.COINREMITTER_OUTBOX_REPUBLISH_SECONDS = 300
    second_order = Order.objects.create(
        user=invoice_request.order.user,
        number="OUTBOX000002",
        status=Order.OrderStatus.PENDING_PAYMENT,
        total_amount=Decimal("50.00"),
        currency="RUB",
        contact_name="Outbox User",
        contact_phone="+905550000000",
        payment_method="crypto",
    )
    second = CryptoInvoiceRequest.objects.create(
        order=second_order,
        idempotency_key="b" * 64,
        amount_fiat=second_order.total_amount,
        fiat_currency=second_order.currency,
        status=CryptoInvoiceRequestStatus.UNCERTAIN,
    )

    with patch(
        "apps.payments.tasks.create_coinremitter_invoice_request.delay"
    ) as delay:
        published = dispatch_pending_crypto_invoice_requests.run()

    assert published == 1
    delay.assert_called_once_with(invoice_request.pk)
    second.refresh_from_db()
    assert second.status == CryptoInvoiceRequestStatus.UNCERTAIN


@pytest.mark.django_db
def test_dispatcher_does_not_republish_recent_pending_row(settings, invoice_request):
    settings.COINREMITTER_OUTBOX_DISPATCH_BATCH_SIZE = 100
    settings.COINREMITTER_OUTBOX_REPUBLISH_SECONDS = 300
    CryptoInvoiceRequest.objects.filter(pk=invoice_request.pk).update(
        last_enqueued_at=timezone.now(),
    )

    with patch(
        "apps.payments.tasks.create_coinremitter_invoice_request.delay"
    ) as delay:
        published = dispatch_pending_crypto_invoice_requests.run()

    assert published == 0
    delay.assert_not_called()


@pytest.mark.django_db
def test_reconciliation_quarantines_stale_processing_claim(settings, invoice_request):
    settings.COINREMITTER_OUTBOX_STALE_SECONDS = 180
    settings.COINREMITTER_RECONCILIATION_BATCH_SIZE = 10
    settings.COINREMITTER_RECONCILIATION_MIN_AGE_MINUTES = 10
    CryptoInvoiceRequest.objects.filter(pk=invoice_request.pk).update(
        status=CryptoInvoiceRequestStatus.PROCESSING,
        processing_started_at=timezone.now() - timedelta(minutes=5),
        attempt_count=1,
    )

    summary = reconcile_coinremitter_state.run()

    invoice_request.refresh_from_db()
    assert invoice_request.status == CryptoInvoiceRequestStatus.UNCERTAIN
    assert invoice_request.last_error_code == "stale_processing"
    assert summary["stale_outbox_quarantined"] == 1
    assert summary["outbox"] == {CryptoInvoiceRequestStatus.UNCERTAIN: 1}
    assert summary["checked"] == 0
