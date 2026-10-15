"""Telegram-уведомление о заявке: менеджеру нужны контакты и канал связи."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.orders.tasks import notify_new_order_telegram


def _order(**overrides):
    data = dict(
        id=9,
        number="REQ-9",
        user=SimpleNamespace(telegram_id="555", telegram_notifications=True),
        total_amount="150.00",
        currency="RUB",
        payment_method="manager",
        shipping_method="air",
        contact_name="Ivan_Petrov *VIP*",
        contact_phone="+79990000000",
        contact_email="ivan@example.com",
        contact_channel="whatsapp",
        contact_username="",
        comment="",
        created_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_CHAT_ID="admin-chat")
@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=None)
@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.orders.tasks.requests.post")
@patch("apps.orders.models.Order.objects.select_related")
class RequestTelegramNotificationTests(SimpleTestCase):
    def _texts(self, select_related, telegram_post, order):
        select_related.return_value.get.return_value = order
        telegram_post.return_value = SimpleNamespace(status_code=200, ok=True)
        notify_new_order_telegram.run(order_id=order.id)
        return {
            call.kwargs["json"]["chat_id"]: call.kwargs["json"]["text"]
            for call in telegram_post.call_args_list
        }

    def test_admin_message_contains_contacts_and_channel(self, select_related, telegram_post, *_):
        texts = self._texts(select_related, telegram_post, _order())

        admin = texts["admin-chat"]
        self.assertIn("Новая заявка", admin)
        self.assertIn("+79990000000", admin)
        self.assertIn("ivan@example.com", admin)
        self.assertIn("WhatsApp", admin)
        self.assertIn("Согласуется с менеджером", admin)
        # Пользовательский ввод экранирован для parse_mode=Markdown
        self.assertIn("Ivan\\_Petrov \\*VIP\\*", admin)

    def test_customer_is_told_manager_will_contact_them(self, select_related, telegram_post, *_):
        texts = self._texts(select_related, telegram_post, _order())

        self.assertIn("менеджер", texts["555"].lower())

    def test_admin_message_contains_telegram_username(self, select_related, telegram_post, *_):
        texts = self._texts(
            select_related, telegram_post, _order(contact_channel="telegram", contact_username="Ivan_Petrov")
        )

        self.assertIn("Telegram: @Ivan\\_Petrov", texts["admin-chat"])
