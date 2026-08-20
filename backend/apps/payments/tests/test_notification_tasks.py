"""Database-free guards for payment and order Telegram notification settings."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.orders.tasks import notify_new_order_telegram
from apps.payments.tasks import notify_crypto_payment_confirmed


def _order(*, notifications: bool, receipt_url: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        number="ORDER-7",
        user=SimpleNamespace(
            telegram_id="123456",
            telegram_notifications=notifications,
            email="buyer@example.com",
            is_staff=False,
            is_superuser=False,
        ),
        total_amount="42.00",
        currency="USD",
        payment_method="crypto",
        shipping_method="air",
        receipt_url=receipt_url,
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        contact_name="Buyer",
    )


class CryptoNotificationTaskTests(SimpleTestCase):
    @override_settings(
        TELEGRAM_BOT_TOKEN="test-token",
        TELEGRAM_CHAT_ID="",
        COINREMITTER_COIN="BTC",
    )
    @patch("apps.orders.tasks.send_order_receipt_task.delay")
    @patch("apps.payments.tasks.requests.post")
    @patch("apps.payments.tasks.CryptoPayment.objects.get")
    @patch("apps.orders.models.Order.objects.select_related")
    def test_confirmed_payment_uses_real_user_field_and_configured_coin(
        self, select_related, payment_get, telegram_post, _receipt_delay
    ):
        select_related.return_value.get.return_value = _order(notifications=True)
        payment_get.return_value = SimpleNamespace(
            amount_crypto="0.00100000",
            amount_fiat="42.00",
            currency="USD",
        )
        telegram_post.return_value = Mock(ok=True)

        notify_crypto_payment_confirmed.run(order_id=7)

        payload = telegram_post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], "123456")
        self.assertIn("BTC", payload["text"])

    @override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID="")
    @patch("apps.orders.tasks.send_order_receipt_task.delay")
    @patch("apps.payments.tasks.requests.post")
    @patch("apps.payments.tasks.CryptoPayment.objects.get")
    @patch("apps.orders.models.Order.objects.select_related")
    def test_confirmed_payment_respects_disabled_telegram_preference(
        self, select_related, payment_get, telegram_post, _receipt_delay
    ):
        select_related.return_value.get.return_value = _order(notifications=False)
        payment_get.return_value = SimpleNamespace(
            amount_crypto="1.0", amount_fiat="42.00", currency="USD"
        )

        notify_crypto_payment_confirmed.run(order_id=7)

        telegram_post.assert_not_called()


class OrderNotificationTaskTests(SimpleTestCase):
    @override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID="")
    @patch("apps.orders.tasks.requests.post")
    @patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=b"%PDF-test")
    @patch("apps.orders.tasks.Order.objects.select_related")
    def test_new_order_respects_disabled_telegram_preference(
        self, select_related, _load_receipt, telegram_post
    ):
        select_related.return_value.get.return_value = _order(
            notifications=False,
            receipt_url="https://cdn.example/receipt.pdf",
        )
        notify_new_order_telegram.run(order_id=7)

        telegram_post.assert_not_called()
