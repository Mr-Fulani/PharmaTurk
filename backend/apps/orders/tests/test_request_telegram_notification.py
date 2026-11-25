"""Telegram-уведомление о заявке: менеджеру нужны контакты и канал связи."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

from django.test import SimpleTestCase, override_settings

from apps.orders.contacts import contact_message
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


def _item(**overrides):
    data = dict(product_name="PAROL", product=None, chosen_size="", price="50.00", quantity=1, total="150.00")
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
        self.assertIn("<code>REQ-9</code>", admin)
        self.assertIn("Итого: 150.00 RUB", admin)
        self.assertEqual(telegram_post.call_args_list[0].kwargs["json"]["parse_mode"], "HTML")

    def test_admin_message_shows_delivery_address(self, select_related, telegram_post, *_):
        order = _order(shipping_address_text="Россия, 101000, Москва,\nул. Тверская 1 <кв. 5> & подъезд 2")
        admin = self._texts(select_related, telegram_post, order)["admin-chat"]

        self.assertIn(
            "📍 <b>Адрес доставки</b>\nРоссия, 101000, Москва, ул. Тверская 1 &lt;кв. 5&gt; &amp; подъезд 2\n\n",
            admin,
        )
        # Адрес идёт сразу за контактами покупателя, до позиций и итога
        self.assertLess(admin.index("Покупатель"), admin.index("Адрес доставки"))
        self.assertLess(admin.index("Адрес доставки"), admin.index("Итого"))

    def test_admin_message_without_address_says_so(self, select_related, telegram_post, *_):
        # У заявок без адреса (в том числе старых) сообщение собирается как обычно
        for order in (_order(), _order(shipping_address_text="  ")):
            telegram_post.reset_mock()
            admin = self._texts(select_related, telegram_post, order)["admin-chat"]

            self.assertIn("📍 <b>Адрес доставки</b>\nне указан\n\n", admin)
            self.assertIn("Итого: 150.00 RUB", admin)

    def test_user_input_cannot_break_html_markup(self, select_related, telegram_post, *_):
        order = _order(contact_name="Ivan <b>& Co</i>", comment='<a href="https://evil.example">жми</a> & _*`[')
        texts = self._texts(select_related, telegram_post, order)

        admin = texts["admin-chat"]
        self.assertIn("Имя: Ivan &lt;b&gt;&amp; Co&lt;/i&gt;", admin)
        self.assertIn('&lt;a href="https://evil.example"&gt;жми&lt;/a&gt; &amp; _*`[', admin)
        self.assertNotIn("<a href=\"https://evil", admin)
        # Ссылки — только из шаблона: заявка в админке и «Написать»; имя покупателя в адресе закодировано
        self.assertEqual(admin.count("<a "), 2)
        self.assertIn(
            '✍️ Написать: <a href="https://wa.me/79990000000?text=' + quote("Здравствуйте, Ivan <b>& Co</i>!", safe=""),
            admin,
        )

    def test_admin_gets_chat_links_with_draft(self, select_related, telegram_post, *_):
        items = [_item(product_name="Кроссовки <Run & Go>"), _item(product_name="PAROL")]
        order = _order(
            contact_name="Иван", contact_channel="telegram", contact_username="Ivan_Petrov",
            items=SimpleNamespace(all=lambda: items),
        )
        texts = self._texts(select_related, telegram_post, order)
        admin = texts["admin-chat"]

        draft = quote(contact_message("Иван", "REQ-9", ["Кроссовки <Run & Go>", "PAROL"]), safe="")
        self.assertIn(
            f'✍️ Написать: <a href="https://t.me/Ivan_Petrov?text={draft}">Telegram</a>'
            f' · <a href="https://wa.me/79990000000?text={draft}">WhatsApp</a>',
            admin,
        )
        # Покупателю ссылки на самого себя не уходят
        self.assertNotIn("Написать", texts["555"])

    def test_draft_is_in_the_language_of_the_request(self, select_related, telegram_post, *_):
        select_related.return_value.get.return_value = _order(contact_name="Ivan")
        telegram_post.return_value = SimpleNamespace(status_code=200, ok=True)
        notify_new_order_telegram.run(order_id=9, locale="en")

        admin = telegram_post.call_args_list[0].kwargs["json"]["text"]
        draft = quote(contact_message("Ivan", "REQ-9", locale="en"), safe="")
        self.assertIn("Hello%20Ivan%21", draft)
        self.assertIn(f'<a href="https://wa.me/79990000000?text={draft}">WhatsApp</a>', admin)
        # Само уведомление менеджеру остаётся русским
        self.assertIn("Новая заявка", admin)

    def test_unclear_contact_gives_no_chat_links(self, select_related, telegram_post, *_):
        order = _order(contact_channel="telegram", contact_username="", contact_phone="0532 123 45 67")
        admin = self._texts(select_related, telegram_post, order)["admin-chat"]

        self.assertNotIn("Написать", admin)
        self.assertIn("Телефон: 0532 123 45 67", admin)

    def test_customer_is_told_manager_will_contact_them(self, select_related, telegram_post, *_):
        texts = self._texts(select_related, telegram_post, _order())

        self.assertIn("менеджер", texts["555"].lower())

    def test_admin_message_contains_telegram_username(self, select_related, telegram_post, *_):
        texts = self._texts(
            select_related, telegram_post, _order(contact_channel="telegram", contact_username="Ivan_Petrov")
        )

        self.assertIn("Telegram: @Ivan_Petrov", texts["admin-chat"])

    def test_whatsapp_phone_is_shown_without_at(self, select_related, telegram_post, *_):
        texts = self._texts(
            select_related, telegram_post, _order(contact_channel="whatsapp", contact_username="+79990001122")
        )

        self.assertIn("WhatsApp: +79990001122", texts["admin-chat"])

    def test_admin_sees_items_with_price_on_request(self, select_related, telegram_post, *_):
        # Больничный препарат / товар без цены: сумму называет менеджер (docs/HOSPITAL_MEDICINES.md)
        items = [_item(product_name="IZOTONIK_500", price=0, total=0), _item(product_name="PAROL", quantity=3)]
        texts = self._texts(select_related, telegram_post, _order(items=SimpleNamespace(all=lambda: items)))

        admin = texts["admin-chat"]
        self.assertIn("1. <b>IZOTONIK_500</b>\n1 шт. · цена по запросу", admin)
        self.assertIn("Цена по запросу (в сумму не вошли): IZOTONIK_500\n", admin)
        self.assertIn("2. <b>PAROL</b>\n3 шт. × 50.00 RUB = 150.00 RUB", admin)

    def test_each_item_is_a_separate_paragraph_with_size(self, select_related, telegram_post, *_):
        items = [_item(product_name="Кроссовки <Run & Go>", chosen_size="42"), _item(product_name="PAROL")]
        texts = self._texts(select_related, telegram_post, _order(items=SimpleNamespace(all=lambda: items)))

        admin = texts["admin-chat"]
        self.assertIn(
            "🛒 <b>Позиции</b>\n\n"
            "1. <b>Кроссовки &lt;Run &amp; Go&gt;</b>\nРазмер: 42\n1 шт. · 50.00 RUB\n\n"
            "2. <b>PAROL</b>\n1 шт. · 50.00 RUB\n\n"
            "💰 <b>Итого: 150.00 RUB</b>",
            admin,
        )
        # У обычного товара ссылок на проверку лекарств нет: только заявка в админке и «Написать»
        self.assertEqual(admin.count("<a "), 2)
        self.assertNotIn("admin", admin.split("🛒")[1])

    def test_broken_items_do_not_hold_the_message(self, select_related, telegram_post, *_):
        texts = self._texts(select_related, telegram_post, _order(items=SimpleNamespace(all=lambda: [object()])))

        self.assertIn("+79990000000", texts["admin-chat"])
        self.assertNotIn("Позиции", texts["admin-chat"])
