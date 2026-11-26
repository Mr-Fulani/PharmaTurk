"""Готовые сообщения клиенту по кнопке под заявкой в Telegram: тексты, подстановки, меню, админка."""

from decimal import Decimal
from itertools import count
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache

from apps.orders.admin import ClientMessageTemplateAdmin
from apps.orders.client_messages import render_client_message
from apps.orders.models import ClientMessageTemplate, Order, OrderItem, SourcingRequest
from apps.orders.sourcing import create_order_for_sourcing_request
from apps.orders.telegram_buttons import order_keyboard
from apps.users.models import User
from apps.users.telegram_auth import process_telegram_webhook

PS = Order.ProcessingStatus
CHAT = "-100777"
MEMBER, STRANGER = 111, 999
_seq = count(1)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _telegram_settings(settings):
    settings.TELEGRAM_BOT_TOKEN = "test-token"
    settings.TELEGRAM_ORDERS_CHAT_ID = CHAT
    settings.SITE_URL = "https://mudaroba.test"
    cache.clear()


@pytest.fixture
def telegram():
    calls = []

    def post(url, json=None, **kwargs):
        method = url.rsplit("/", 1)[1]
        calls.append((method, json))
        result = True
        if method == "getChatMember":
            result = {"status": "member" if json["user_id"] == MEMBER else "left"}
        return SimpleNamespace(json=lambda: {"ok": True, "result": result})

    with patch("apps.orders.telegram_buttons.requests.post", side_effect=post):
        yield calls


def _order(items=(("PAROL 500 mg", 2, "350.00"),), **extra):
    data = dict(
        number=f"CM{next(_seq):06d}",
        subtotal_amount=Decimal("700.00"),
        shipping_amount=Decimal("50.00"),
        total_amount=Decimal("750.00"),
        currency="RUB",
        contact_name="Иван Петров",
        contact_phone="+79990001122",
        contact_channel="whatsapp",
        payment_method="manager",
    )
    data.update(extra)
    order = Order.objects.create(**data)
    for name, quantity, price in items:
        OrderItem.objects.create(
            order=order, product_name=name, quantity=quantity, price=Decimal(price), total=Decimal(price) * quantity,
        )
    return order


def _press(data, user_id=MEMBER):
    return process_telegram_webhook({
        "callback_query": {
            "id": "cb1", "from": {"id": user_id, "first_name": "Анвар"}, "data": data,
            "message": {"message_id": 5, "chat": {"id": int(CHAT)}, "text": "Заявка"},
        }
    })


def _calls(telegram, method):
    return [payload for name, payload in telegram if name == method]


def _texts(keyboard):
    return [button["text"] for row in keyboard["inline_keyboard"] for button in row]


# ─── Тексты и подстановки ─────────────────────────────────────────────────────


def test_initial_templates_are_created_by_migration():
    assert set(ClientMessageTemplate.objects.values_list("key", flat=True)) == {"air", "ground", "shipped", "review"}


def test_air_delivery_text_has_order_data_and_owner_wording():
    order = _order(items=(("PAROL 500 mg", 2, "350.00"), ("Крем  для рук", 1, "0")))
    text = render_client_message("air", order)

    assert text.startswith(f"Здравствуйте, Иван Петров! Это Mudaroba, по вашей заявке №{order.number}.\n\nВаш заказ:\n")
    assert "• PAROL 500 mg × 2\n• Крем для рук × 1 — цена по запросу\n\nТовары: 700.00 RUB\n" in text
    assert "Доставка из Стамбула (авиа): 50.00 RUB\nИтого: 750.00 RUB (без позиций с ценой по запросу)\n" in text
    assert "Сроки: авиадоставка — от 3 до 14 дней." in text
    assert "Доставку по России вы оплачиваете отдельно при получении" in text
    assert "{" not in text


def test_ground_delivery_differs_by_kind_and_terms():
    text = render_client_message("ground", _order())

    assert "Доставка из Стамбула (наземная): 50.00 RUB" in text
    assert "Сроки: наземная доставка — от 14 до 21 дня." in text


def test_missing_shipping_and_name_are_said_honestly():
    order = _order(contact_name="  ", shipping_amount=Decimal("0"), total_amount=Decimal("700.00"))
    text = render_client_message("air", order)

    assert text.startswith("Здравствуйте! Это Mudaroba")
    assert "Доставка из Стамбула (авиа): [впишите сумму доставки]\nИтого: 700.00 RUB (без доставки)" in text


def test_sourcing_request_skips_items_block():
    req = SourcingRequest.objects.create(comment="Кроссовки 42", contact_name="Олег", contact_channel="telegram", contact_username="oleg_k")
    order = create_order_for_sourcing_request(req)
    text = render_client_message("air", order)

    assert "Ваш заказ" not in text and "Кроссовки" not in text
    assert f"заявке №{order.number}.\n\nТовары: [впишите сумму]\n" in text
    assert "\n\n\n" not in text


def test_shipped_and_review_texts():
    order = _order()

    assert render_client_message("shipped", order) == (
        f"Здравствуйте, Иван Петров! Ваш заказ №{order.number} отправлен из Стамбула. Как только он прибудет в "
        "Россию и уйдёт на ваш адрес, пришлю трек-номер. Доставка по России оплачивается при получении. "
        "Если есть вопросы — пишите."
    )
    review = render_client_message("review", order)
    assert "https://mudaroba.test/testimonials?action=add\n\nСпасибо, что выбрали Mudaroba!" in review


def test_english_order_gets_english_text_and_falls_back_to_russian():
    order = _order(locale="en")

    text = render_client_message("air", order)
    assert text.startswith(f"Hello, Иван Петров! This is Mudaroba, regarding your request No. {order.number}.")
    assert "Your order:\n• PAROL 500 mg × 2" in text and "air delivery takes 3 to 14 days" in text
    assert "https://mudaroba.test/en/testimonials?action=add" in render_client_message("review", order)

    ClientMessageTemplate.objects.filter(key="shipped").update(text_en="")
    assert render_client_message("shipped", order).startswith("Здравствуйте, Иван Петров!")


def test_edited_template_is_used_and_unknown_placeholder_survives():
    ClientMessageTemplate.objects.filter(key="shipped").update(
        text_ru="{Имя}, заказ {номер} в пути. {трек} {сумма  доставки} {итого}"
    )
    order = _order()

    assert render_client_message("shipped", order) == (
        f"Иван Петров, заказ {order.number} в пути. {{трек}} 50.00 RUB 750.00 RUB"
    )


def test_admin_explains_placeholders_and_forbids_add_and_delete(rf):
    model_admin = ClientMessageTemplateAdmin(ClientMessageTemplate, AdminSite())
    request = rf.get("/")
    request.user = User(is_superuser=True, is_staff=True, is_active=True)

    description = str(model_admin.get_fieldsets(request)[0][1]["description"])
    assert "{имя}" in description and "{сумма доставки}" in description and "бот клиенту ничего не отправляет" in description.lower()
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_delete_permission(request) is False
    assert "key" in model_admin.readonly_fields


# ─── Кнопки в Telegram ────────────────────────────────────────────────────────


def test_message_button_opens_menu_of_templates(telegram):
    order = _order()

    _press(f"o:{order.id}:new:m")

    menu = _calls(telegram, "editMessageReplyMarkup")[0]["reply_markup"]
    assert _texts(menu) == [
        "Как проходит доставка — авиа", "Как проходит доставка — наземная", "Заказ отправлен", "Просьба об отзыве",
        "↩️ Назад",
    ]
    assert menu["inline_keyboard"][2][0]["callback_data"] == f"o:{order.id}:new:t:shipped"
    assert not _calls(telegram, "sendMessage")


def test_short_template_is_sent_to_same_chat_with_prefilled_chat_link(telegram):
    order = _order()

    assert _press(f"o:{order.id}:new:t:shipped") is True

    sent = _calls(telegram, "sendMessage")[0]
    text = render_client_message("shipped", order)
    assert sent["chat_id"] == int(CHAT) and sent["parse_mode"] == "HTML"
    assert sent["reply_parameters"]["message_id"] == 5
    assert f"<b>Заказ отправлен</b> · заявка №{order.number}" in sent["text"]
    assert sent["text"].endswith(f"<pre>{text}</pre>")
    button = sent["reply_markup"]["inline_keyboard"][0][0]
    assert button["text"] == "💬 Открыть чат в WhatsApp"
    assert button["url"].startswith("https://wa.me/79990001122?text=%D0%97")
    assert _calls(telegram, "answerCallbackQuery")[0]["text"] == "Текст готов — он ниже."
    order.refresh_from_db()
    assert order.processing_status == PS.NEW  # сообщение отметку не меняет


def test_long_template_opens_plain_chat_and_escapes_text(telegram):
    order = _order(items=(("Товар <A&B>", 1, "10"),))

    _press(f"o:{order.id}:new:t:air")

    sent = _calls(telegram, "sendMessage")[0]
    assert "• Товар &lt;A&amp;B&gt; × 1" in sent["text"]
    assert sent["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://wa.me/79990001122"


def test_message_without_usable_contact_has_no_chat_buttons(telegram):
    order = _order(contact_phone="0532", contact_channel="email")

    _press(f"o:{order.id}:new:t:shipped")

    assert "reply_markup" not in _calls(telegram, "sendMessage")[0]


def test_message_is_available_from_old_notification(telegram):
    order = _order(processing_status=PS.SHIPPED)

    _press(f"o:{order.id}:new:t:shipped")  # кнопки показаны при «Новой», заявка уже отправлена

    assert len(_calls(telegram, "sendMessage")) == 1
    assert not _calls(telegram, "editMessageText")


def test_hint_buttons_after_shipped_and_done_lead_to_templates():
    shipped = order_keyboard(_order(processing_status=PS.SHIPPED))
    done = order_keyboard(_order(processing_status=PS.DONE))

    hint = next(b for row in shipped["inline_keyboard"] for b in row if b["text"] == "✉️ Сообщение: заказ отправлен")
    assert hint["callback_data"].endswith(":shipped:t:shipped")
    hint = next(b for row in done["inline_keyboard"] for b in row if b["text"] == "⭐ Попросить отзыв")
    assert hint["callback_data"].endswith(":done:t:review")


def test_stranger_gets_no_text(telegram):
    order = _order()

    _press(f"o:{order.id}:new:t:shipped", user_id=STRANGER)
    _press(f"o:{order.id}:new:m", user_id=STRANGER)

    assert not _calls(telegram, "sendMessage") and not _calls(telegram, "editMessageReplyMarkup")
    assert all(answer["text"].startswith("Нет доступа") for answer in _calls(telegram, "answerCallbackQuery"))


def test_deleted_or_unknown_template_is_answered_not_crashed(telegram):
    order = _order()
    ClientMessageTemplate.objects.filter(key="review").delete()

    assert _press(f"o:{order.id}:new:t:review") is True
    assert _press(f"o:{order.id}:new:t:nope") is True

    assert not _calls(telegram, "sendMessage")
    assert all("не найден" in answer["text"] for answer in _calls(telegram, "answerCallbackQuery"))
