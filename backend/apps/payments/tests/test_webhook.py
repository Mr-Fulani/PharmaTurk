"""Тесты для CryptoWebhook — обработка событий от CoinRemitter."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class TestCryptoWebhookView(TestCase):
    """Интеграционные тесты для CryptoWebhookView."""

    def setUp(self):
        from apps.orders.models import Order, OrderItem
        from apps.payments.models import CryptoPayment
        from apps.catalog.models import Product

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Создаём минимальный товар
        self.product = Product.objects.create(
            name="Test Product",
            slug="test-product",
            price=100,
            currency="USD",
        )

        # Создаём заказ в статусе PENDING_PAYMENT
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

        # Создаём CryptoPayment
        self.crypto_payment = CryptoPayment.objects.create(
            order=self.order,
            provider="coinremitter",
            invoice_id="test-invoice-123",
            address="TNdummyRealAddress1234567890ABCDEF",
            amount_crypto=Decimal("1.74"),
            amount_fiat=Decimal("1.74"),
            currency="USD",
            status="pending",
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    def test_webhook_confirmed_updates_order(self, mock_notify):
        """Webhook с status=confirmed → заказ переходит в PAID."""
        import json
        from apps.orders.models import Order as OrderModel
        response = self.client.post(
            "/api/payments/crypto/webhook/",
            data=json.dumps({"id": "test-invoice-123", "status": "confirmed"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        self.order.refresh_from_db()
        assert self.order.payment_status == "paid"
        assert self.order.status == OrderModel.OrderStatus.PAID

        self.crypto_payment.refresh_from_db()
        assert self.crypto_payment.status == "confirmed"

        # Уведомление должно быть вызвано
        mock_notify.assert_called_once_with(self.order.id)

    @patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay")
    def test_webhook_idempotent_already_paid(self, mock_notify):
        """Повторный webhook для уже оплаченного заказа → 200, без повторного notify."""
        import json
        from apps.orders.models import Order as OrderModel
        self.order.payment_status = "paid"
        self.order.status = OrderModel.OrderStatus.PAID
        self.order.save()

        response = self.client.post(
            "/api/payments/crypto/webhook/",
            data=json.dumps({"id": "test-invoice-123", "status": "confirmed"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        mock_notify.assert_not_called()

    @patch("apps.payments.tasks.notify_crypto_payment_expired.delay")
    def test_webhook_expired_updates_status(self, mock_notify):
        """Webhook с status=expired → CryptoPayment помечается expired."""
        import json
        response = self.client.post(
            "/api/payments/crypto/webhook/",
            data=json.dumps({"id": "test-invoice-123", "status": "expired"}),
            content_type="application/json",
        )
        assert response.status_code == 200

        self.crypto_payment.refresh_from_db()
        assert self.crypto_payment.status == "expired"
        mock_notify.assert_called_once_with(self.order.id)

    def test_webhook_unknown_invoice_returns_200(self):
        """Неизвестный invoice_id → 200 OK (не ломаем CoinRemitter)."""
        import json
        response = self.client.post(
            "/api/payments/crypto/webhook/",
            data=json.dumps({"id": "nonexistent-invoice", "status": "confirmed"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_webhook_validation_ping_no_invoice_id(self):
        """POST без invoice_id (validation ping от CoinRemitter) → 200 OK."""
        import json
        response = self.client.post(
            "/api/payments/crypto/webhook/",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_webhook_get_request_returns_ok(self):
        """GET-запрос (проверка доступности URL) → 200 OK."""
        response = self.client.get("/api/payments/crypto/webhook/")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_webhook_paid_status_synonym(self):
        """status=paid (синоним confirmed) → заказ оплачен."""
        import json
        with patch("apps.payments.tasks.notify_crypto_payment_confirmed.delay"):
            response = self.client.post(
                "/api/payments/crypto/webhook/",
                data=json.dumps({"id": "test-invoice-123", "status": "paid"}),
                content_type="application/json",
            )
        assert response.status_code == 200
        self.order.refresh_from_db()
        assert self.order.payment_status == "paid"
