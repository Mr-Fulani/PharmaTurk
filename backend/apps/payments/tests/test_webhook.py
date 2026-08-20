"""Tests for authenticated and idempotent CoinRemitter webhook reconciliation."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient


User = get_user_model()
WEBHOOK_URL = "/api/payments/crypto/webhook/"
PROVIDER_ID = "provider-object-123"
INVOICE_CODE = "invoice-code-123"


def provider_invoice(
    *,
    status_code: int | str = 1,
    provider_id: str = PROVIDER_ID,
    invoice_code: str = INVOICE_CODE,
    order_number: str = "TESTORDER001",
    total: str = "100.00",
    paid: str | None = "100.00",
) -> dict:
    result = {
        "id": provider_id,
        "invoice_id": invoice_code,
        "custom_data1": order_number,
        "status_code": status_code,
        "total_amount": {"USD": total},
        "paid_amount": {},
    }
    if paid is not None:
        result["paid_amount"] = {"USD": paid}
    return result


def webhook_payload(*, status: str = "forged-status") -> dict:
    return {"id": PROVIDER_ID, "invoice_id": INVOICE_CODE, "status": status}


class TestAuthoritativeInvoiceValidation(SimpleTestCase):
    """Database-free unit tests for the provider response contract."""

    def payment(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            invoice_id=PROVIDER_ID,
            currency="USD",
            order=SimpleNamespace(
                number="TESTORDER001",
                currency="USD",
                total_amount=Decimal("100.00"),
            ),
        )

    def test_all_documented_status_codes_are_accepted(self):
        from apps.payments.views import _verify_authoritative_invoice

        cases = {
            0: None,
            1: "100.00",
            2: "50.00",
            3: "101.00",
            4: None,
            5: None,
        }
        for status_code, paid in cases.items():
            with self.subTest(status_code=status_code):
                remote = provider_invoice(status_code=str(status_code), paid=paid)
                assert _verify_authoritative_invoice(
                    self.payment(), remote, PROVIDER_ID, INVOICE_CODE
                ) == status_code

    def test_unknown_status_code_fails_closed(self):
        from apps.payments.views import (
            CoinRemitterVerificationError,
            _verify_authoritative_invoice,
        )

        with self.assertRaises(CoinRemitterVerificationError):
            _verify_authoritative_invoice(
                self.payment(),
                provider_invoice(status_code=99),
                PROVIDER_ID,
                INVOICE_CODE,
            )

    def test_identity_order_amount_and_paid_amount_are_mandatory(self):
        from apps.payments.views import (
            CoinRemitterVerificationError,
            _verify_authoritative_invoice,
        )

        invalid_responses = [
            provider_invoice(provider_id="different-id"),
            provider_invoice(invoice_code="different-code"),
            provider_invoice(order_number="OTHERORDER"),
            provider_invoice(total="99.99", paid="99.99"),
            provider_invoice(paid="99.99"),
        ]
        for remote in invalid_responses:
            with self.subTest(remote=remote):
                with self.assertRaises(CoinRemitterVerificationError):
                    _verify_authoritative_invoice(
                        self.payment(), remote, PROVIDER_ID, INVOICE_CODE
                    )


class CryptoPaymentFixtureMixin:
    def create_payment_fixture(self) -> None:
        from apps.catalog.models import Product
        from apps.orders.models import Order, OrderItem
        from apps.payments.models import CryptoPayment

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            price=100,
            currency="USD",
            stock_quantity=5,
        )
        self.order = Order.objects.create(
            user=self.user,
            number="TESTORDER001",
            subtotal_amount=Decimal("100.00"),
            shipping_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            currency="USD",
            payment_method="crypto",
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_status="pending",
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            price=Decimal("100.00"),
            quantity=1,
            total=Decimal("100.00"),
        )
        self.crypto_payment = CryptoPayment.objects.create(
            order=self.order,
            provider="coinremitter",
            # Existing rows store CoinRemitter's long `id`; the webhook also
            # carries the short `invoice_id` used by invoice/get.
            invoice_id=PROVIDER_ID,
            address="TNdummyRealAddress1234567890ABCDEF",
            amount_crypto=Decimal("1.74"),
            amount_fiat=Decimal("100.00"),
            currency="USD",
            status="pending",
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )


class TestCryptoWebhookView(CryptoPaymentFixtureMixin, TestCase):
    """Integration tests for the webhook HTTP contract."""

    def setUp(self):
        self.create_payment_fixture()

    def post_webhook(self, payload: dict):
        return self.client.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    @patch("apps.payments.views.get_invoice")
    def test_authenticated_paid_updates_order_and_ignores_payload_status(
        self, mock_get_invoice, mock_notify
    ):
        mock_get_invoice.return_value = provider_invoice(status_code="1")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload(status="expired"))

        assert response.status_code == 200
        mock_get_invoice.assert_called_once_with(INVOICE_CODE)
        self.order.refresh_from_db()
        self.crypto_payment.refresh_from_db()
        self.product.refresh_from_db()
        assert self.order.payment_status == "paid"
        assert self.order.status == self.order.OrderStatus.PAID
        assert self.crypto_payment.status == "confirmed"
        assert self.crypto_payment.invoice_code == INVOICE_CODE
        assert self.product.stock_quantity == 4
        mock_notify.assert_called_once_with(self.order.id)

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    @patch("apps.payments.views.get_invoice")
    def test_forged_paid_payload_cannot_override_provider_pending(
        self, mock_get_invoice, mock_notify
    ):
        mock_get_invoice.return_value = provider_invoice(status_code=0, paid=None)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload(status="paid"))

        assert response.status_code == 200
        self.order.refresh_from_db()
        self.crypto_payment.refresh_from_db()
        self.product.refresh_from_db()
        assert self.order.payment_status == "pending"
        assert self.crypto_payment.status == "pending"
        assert self.product.stock_quantity == 5
        mock_notify.assert_not_called()

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    @patch("apps.payments.views.get_invoice")
    def test_duplicate_paid_webhooks_decrement_and_notify_once(
        self, mock_get_invoice, mock_notify
    ):
        mock_get_invoice.return_value = provider_invoice(status_code=1)

        with self.captureOnCommitCallbacks(execute=True):
            first = self.post_webhook(webhook_payload())
            second = self.post_webhook(webhook_payload())

        assert first.status_code == second.status_code == 200
        self.product.refresh_from_db()
        assert self.product.stock_quantity == 4
        mock_notify.assert_called_once_with(self.order.id)

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    @patch("apps.payments.views.get_invoice")
    def test_overpaid_is_fulfilled_after_amount_verification(
        self, mock_get_invoice, mock_notify
    ):
        mock_get_invoice.return_value = provider_invoice(status_code=3, paid="101.00")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload())

        assert response.status_code == 200
        self.order.refresh_from_db()
        assert self.order.payment_status == "paid"
        mock_notify.assert_called_once_with(self.order.id)

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    @patch("apps.payments.views.get_invoice")
    def test_underpaid_does_not_fulfill(self, mock_get_invoice, mock_notify):
        mock_get_invoice.return_value = provider_invoice(status_code=2, paid="50.00")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload(status="paid"))

        assert response.status_code == 200
        self.order.refresh_from_db()
        assert self.order.payment_status == "pending"
        mock_notify.assert_not_called()

    @patch("apps.payments.tasks.notify_crypto_payment_expired.delay")
    @patch("apps.payments.views.get_invoice")
    def test_expired_updates_pending_payment(self, mock_get_invoice, mock_notify):
        mock_get_invoice.return_value = provider_invoice(status_code=4, paid=None)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload(status="paid"))

        assert response.status_code == 200
        self.crypto_payment.refresh_from_db()
        assert self.crypto_payment.status == "expired"
        mock_notify.assert_called_once_with(self.order.id)

    @patch("apps.payments.tasks.notify_crypto_payment_expired.delay")
    @patch("apps.payments.views.get_invoice")
    def test_cancelled_maps_to_expired(self, mock_get_invoice, mock_notify):
        mock_get_invoice.return_value = provider_invoice(status_code=5, paid=None)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload())

        assert response.status_code == 200
        self.crypto_payment.refresh_from_db()
        assert self.crypto_payment.status == "expired"
        mock_notify.assert_called_once_with(self.order.id)

    @patch("apps.payments.tasks.notify_crypto_payment_expired.delay")
    @patch("apps.payments.views.get_invoice")
    def test_expired_never_downgrades_paid(self, mock_get_invoice, mock_notify):
        self.order.payment_status = "paid"
        self.order.status = self.order.OrderStatus.PAID
        self.order.save(update_fields=["payment_status", "status"])
        self.crypto_payment.status = "confirmed"
        self.crypto_payment.save(update_fields=["status"])
        mock_get_invoice.return_value = provider_invoice(status_code=4, paid=None)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_webhook(webhook_payload(status="expired"))

        assert response.status_code == 200
        self.crypto_payment.refresh_from_db()
        assert self.crypto_payment.status == "confirmed"
        mock_notify.assert_not_called()

    @patch("apps.payments.views.get_invoice", return_value=None)
    def test_provider_failure_returns_503_without_mutation(self, mock_get_invoice):
        response = self.post_webhook(webhook_payload(status="paid"))

        assert response.status_code == 503
        self.order.refresh_from_db()
        self.crypto_payment.refresh_from_db()
        assert self.order.payment_status == "pending"
        assert self.crypto_payment.status == "pending"

    @patch("apps.payments.views.get_invoice")
    def test_identity_binding_and_amount_mismatches_fail_closed(self, mock_get_invoice):
        invalid_responses = [
            provider_invoice(provider_id="different-id"),
            provider_invoice(invoice_code="different-code"),
            provider_invoice(order_number="OTHERORDER"),
            provider_invoice(total="99.99", paid="99.99"),
            provider_invoice(status_code=6),
            provider_invoice(status_code=1, paid="99.99"),
        ]

        for remote in invalid_responses:
            with self.subTest(remote=remote):
                mock_get_invoice.return_value = remote
                response = self.post_webhook(webhook_payload(status="paid"))
                assert response.status_code == 403
                self.order.refresh_from_db()
                self.crypto_payment.refresh_from_db()
                assert self.order.payment_status == "pending"
                assert self.crypto_payment.status == "pending"

    @patch("apps.payments.views.get_invoice")
    def test_unknown_invoice_returns_200_without_provider_call(self, mock_get_invoice):
        response = self.post_webhook(
            {"id": "unknown-provider-id", "invoice_id": "unknown-code", "status": "paid"}
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_get_invoice.assert_not_called()

    def test_validation_ping_without_invoice_id_returns_200(self):
        response = self.post_webhook({})
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_get_request_returns_ok(self):
        response = self.client.get(WEBHOOK_URL)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_oversized_identifier_is_rejected_before_lookup(self):
        response = self.post_webhook({"id": "x" * 129})
        assert response.status_code == 400

    def test_new_crypto_payment_persists_requested_order_amount_and_currency(self):
        from apps.orders.models import Order
        from apps.orders.views import _save_crypto_payment

        order = Order.objects.create(
            user=self.user,
            number="TRYORDER001",
            total_amount=Decimal("321.45"),
            currency="TRY",
            payment_method="crypto",
            payment_status="pending",
        )
        _save_crypto_payment(
            order,
            {
                "invoice_id": "other-provider-id",
                "invoice_code": "other-short-id",
                "address": "TAddress",
                "amount": Decimal("8.0"),
                "amount_usd": Decimal("9.99"),
                "currency": "USD",
                "expires_at": timezone.now() + timezone.timedelta(minutes=30),
            },
            "TRY",
        )

        payment = order.crypto_payment
        assert payment.amount_fiat == Decimal("321.45")
        assert payment.currency == "TRY"
        assert payment.invoice_code == "other-short-id"


@skipUnless(connection.vendor == "postgresql", "row-lock concurrency test requires PostgreSQL")
class TestConcurrentCryptoWebhooks(CryptoPaymentFixtureMixin, TransactionTestCase):
    """PostgreSQL integration test for duplicate webhook races."""

    reset_sequences = True

    def setUp(self):
        self.create_payment_fixture()

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    def test_concurrent_paid_webhooks_apply_once(self, mock_notify):
        barrier = threading.Barrier(2)

        def authoritative_lookup(_invoice_id):
            barrier.wait(timeout=5)
            return provider_invoice(status_code=1)

        def post_from_separate_connection():
            close_old_connections()
            try:
                return APIClient().post(WEBHOOK_URL, webhook_payload(), format="json").status_code
            finally:
                close_old_connections()

        with patch("apps.payments.views.get_invoice", side_effect=authoritative_lookup):
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(lambda _: post_from_separate_connection(), range(2)))

        assert statuses == [200, 200]
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        self.crypto_payment.refresh_from_db()
        assert self.product.stock_quantity == 4
        assert self.order.payment_status == "paid"
        assert self.crypto_payment.status == "confirmed"
        mock_notify.assert_called_once_with(self.order.id)
