"""Кнопки под уведомлением о заявке в Telegram-чате заявок и команда /orders."""

from decimal import Decimal
from itertools import count
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.orders.models import Order, OrderItem, OrderProcessingEvent, SourcingRequest
from apps.orders.sourcing import create_order_for_sourcing_request
from apps.orders.tasks import notify_new_order_telegram, notify_sourcing_request_telegram
from apps.orders.telegram_buttons import STATUS_MARK, order_keyboard
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
    """Подменяет Bot API для вебхука: участник чата заявок — только MEMBER. Возвращает список вызовов."""
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


def _order(**extra):
    data = dict(
        number=f"TB{next(_seq):06d}",
        total_amount=Decimal("1000.00"),
        currency="RUB",
        contact_name="Иван Петров",
        contact_phone="+79990001122",
        contact_channel="whatsapp",
        payment_method="manager",
    )
    data.update(extra)
    return Order.objects.create(**data)


def _texts(keyboard):
    return [button["text"] for row in keyboard["inline_keyboard"] for button in row]


def _data(keyboard, text):
    return next(b["callback_data"] for row in keyboard["inline_keyboard"] for b in row if b["text"] == text)


def _press(data, user_id=MEMBER, message=None):
    message = message or {"message_id": 5, "chat": {"id": int(CHAT)}, "text": "Новая заявка TB1"}
    return process_telegram_webhook({
        "callback_query": {
            "id": "cb1",
            "from": {"id": user_id, "first_name": "Анвар", "username": "anvar"},
            "message": message,
            "data": data,
        }
    })


def _calls(telegram, method):
    return [payload for name, payload in telegram if name == method]


# ─── Клавиатура ───────────────────────────────────────────────────────────────


def test_new_order_keyboard_has_next_steps_and_links():
    order = _order()
    keyboard = order_keyboard(order)

    assert _texts(keyboard) == [
        "🛠 Взять в работу", "💬 Написали клиенту", "💰 Назвали цену", "❌ Не состоялась",
        "🗂 Открыть в админке", "✍️ Написать в WhatsApp",
    ]
    links = {b["text"]: b["url"] for row in keyboard["inline_keyboard"] for b in row if "url" in b}
    assert links["🗂 Открыть в админке"] == f"https://mudaroba.test/admin/orders/order/{order.id}/change/"
    assert links["✍️ Написать в WhatsApp"].startswith("https://wa.me/79990001122?text=")


@pytest.mark.parametrize(
    "status, expected",
    [
        (PS.IN_PROGRESS, ["💬 Написали клиенту", "💰 Назвали цену", "🤝 Клиент согласен", "❌ Не состоялась", "↩️ Вернуть: Новая"]),
        (PS.PRICE_SENT, ["🤝 Клиент согласен", "✅ Оплачено", "❌ Не состоялась", "↩️ Вернуть: Написали клиенту"]),
        (PS.PAID, ["📦 Отправлено", "❌ Не состоялась", "↩️ Вернуть: Клиент согласен"]),
        (PS.SHIPPED, ["🏁 Завершена", "❌ Не состоялась", "↩️ Вернуть: Оплачено"]),
        (PS.DONE, ["↩️ Вернуть: Отправлено"]),
        (PS.CANCELLED, ["↩️ Вернуть в работу"]),
    ],
)
def test_keyboard_follows_status(status, expected):
    keyboard = order_keyboard(_order(processing_status=status, contact_phone="", contact_channel=""))

    assert _texts(keyboard) == [*expected, "🗂 Открыть в админке"]


def test_no_write_button_without_usable_contact():
    assert "Написать" not in " ".join(_texts(order_keyboard(_order(contact_phone="0532", contact_channel="email"))))


def test_callback_data_fits_telegram_limit():
    order = _order(processing_status=PS.WAITING_CLIENT)
    order.id = 99_999_999_999
    for menu in ("main", "fail"):
        for row in order_keyboard(order, menu=menu)["inline_keyboard"]:
            for button in row:
                assert len(button.get("callback_data", "").encode()) <= 64


# ─── Нажатия ──────────────────────────────────────────────────────────────────


def test_press_changes_status_writes_history_and_updates_message(telegram):
    order = _order()
    message = {
        "message_id": 5,
        "chat": {"id": int(CHAT)},
        "text": "📝 Новая заявка TB1\nИмя: Иван",
        "entities": [
            {"type": "bold", "offset": 3, "length": 12},
            {"type": "phone_number", "offset": 0, "length": 2},
        ],
    }

    assert _press(_data(order_keyboard(order), "💰 Назвали цену"), message=message) is True

    order.refresh_from_db()
    assert order.processing_status == PS.PRICE_SENT
    assert order.status == Order.OrderStatus.NEW  # «Статус для клиента» кнопки не трогают
    event = OrderProcessingEvent.objects.get(order=order)
    assert (event.old_status, event.new_status, event.actor, event.actor_label) == (
        PS.NEW, PS.PRICE_SENT, None, "Анвар (@anvar)",
    )
    edit = _calls(telegram, "editMessageText")[0]
    assert edit["chat_id"] == int(CHAT) and edit["message_id"] == 5
    head, line = edit["text"].split(STATUS_MARK)
    assert head == message["text"]
    assert line.startswith("Назвали цену — ждём решения — Анвар (@anvar), ")
    assert edit["entities"] == [{"type": "bold", "offset": 3, "length": 12}]
    assert "✅ Оплачено" in _texts(edit["reply_markup"])
    assert _calls(telegram, "answerCallbackQuery")[0]["text"] == "Статус: Назвали цену — ждём решения"


def test_second_change_replaces_status_line(telegram):
    order = _order(processing_status=PS.PRICE_SENT)
    text = "Заявка" + STATUS_MARK + "Назвали цену — ждём решения — Кто-то, 26.11.2026 10:00"

    _press(_data(order_keyboard(order), "🤝 Клиент согласен"), message={"message_id": 5, "chat": {"id": 1}, "text": text})

    new_text = _calls(telegram, "editMessageText")[0]["text"]
    assert new_text.count(STATUS_MARK) == 1
    assert new_text.startswith("Заявка" + STATUS_MARK + "Клиент согласен — ждём оплату — Анвар")


def test_receipt_caption_is_edited_as_caption(telegram):
    order = _order()
    message = {"message_id": 7, "chat": {"id": 1}, "caption": "Заявка", "document": {"file_id": "x"}}

    _press(_data(order_keyboard(order), "🛠 Взять в работу"), message=message)

    edit = _calls(telegram, "editMessageCaption")[0]
    assert edit["caption"].startswith("Заявка" + STATUS_MARK + "В работе — ")
    assert not _calls(telegram, "editMessageText")


def test_linked_staff_member_becomes_responsible(telegram):
    staff = User.objects.create_user(
        username="boss", email="boss@example.test", password="x", is_staff=True, telegram_id=str(MEMBER),
    )
    order = _order()

    _press(_data(order_keyboard(order), "🛠 Взять в работу"))

    order.refresh_from_db()
    assert order.assigned_to == staff
    assert OrderProcessingEvent.objects.get(order=order).actor == staff


def test_fail_needs_reason_and_back_returns_steps(telegram):
    order = _order()

    _press(_data(order_keyboard(order), "❌ Не состоялась"))

    order.refresh_from_db()
    assert order.processing_status == PS.NEW  # пока причина не выбрана, отметка прежняя
    reasons = _calls(telegram, "editMessageReplyMarkup")[0]["reply_markup"]
    assert _texts(reasons) == [
        "Клиент не ответил", "Дорого", "Долго", "Нет в наличии", "Не нашли товар", "Не можем доставить",
        "Передумал", "Спам или тест", "↩️ Назад",
    ]

    _press(_data(reasons, "↩️ Назад"))
    assert "🛠 Взять в работу" in _texts(_calls(telegram, "editMessageReplyMarkup")[1]["reply_markup"])
    assert not OrderProcessingEvent.objects.exists()

    _press(_data(reasons, "Дорого"))
    order.refresh_from_db()
    assert (order.processing_status, order.processing_fail_reason) == (PS.CANCELLED, "expensive")
    event = OrderProcessingEvent.objects.get(order=order)
    assert (event.new_status, event.new_reason, event.actor_label) == (PS.CANCELLED, "expensive", "Анвар (@anvar)")
    edit = _calls(telegram, "editMessageText")[0]
    assert STATUS_MARK + "Не состоялась (Дорого) — Анвар (@anvar)" in edit["text"]
    assert _texts(edit["reply_markup"])[0] == "↩️ Вернуть в работу"


def test_stranger_gets_no_access(telegram):
    order = _order()

    assert _press(_data(order_keyboard(order), "🛠 Взять в работу"), user_id=STRANGER) is True

    order.refresh_from_db()
    assert order.processing_status == PS.NEW
    assert not OrderProcessingEvent.objects.exists()
    answer = _calls(telegram, "answerCallbackQuery")[0]
    assert answer["text"].startswith("Нет доступа") and answer["show_alert"] is True
    assert not _calls(telegram, "editMessageText")


def test_membership_is_checked_in_orders_chat_and_cached(telegram):
    order = _order()

    _press(_data(order_keyboard(order), "❌ Не состоялась"))
    _press(_data(order_keyboard(order), "❌ Не состоялась"))

    assert _calls(telegram, "getChatMember") == [{"chat_id": CHAT, "user_id": MEMBER}]


def test_repeated_and_stale_press_changes_nothing(telegram):
    order = _order()
    old_button = _data(order_keyboard(order), "💰 Назвали цену")
    _press(old_button)

    # Повтор той же кнопки и нажатие по старому сообщению: отметка уже другая
    _press(old_button)
    _press(f"o:{order.id}:new:s:in_progress")

    order.refresh_from_db()
    assert order.processing_status == PS.PRICE_SENT
    assert OrderProcessingEvent.objects.filter(order=order).count() == 1
    answers = _calls(telegram, "answerCallbackQuery")
    assert len(answers) == 3
    assert answers[1]["text"] == answers[2]["text"] == (
        "Статус уже изменён: Назвали цену — ждём решения. Кнопки обновлены."
    )
    # Сообщение со старыми кнопками получает нынешние
    assert "✅ Оплачено" in _texts(_calls(telegram, "editMessageText")[-1]["reply_markup"])


def test_broken_or_deleted_order_button_is_answered(telegram):
    for data in ("o:123456789:new:s:in_progress", "o:abc", "o:"):
        assert _press(data) is True
    assert len(_calls(telegram, "answerCallbackQuery")) == 3


def test_callback_is_answered_even_when_handler_fails(telegram):
    order = _order()
    with patch("apps.orders.telegram_buttons.change_processing", side_effect=RuntimeError("boom")):
        assert _press(_data(order_keyboard(order), "🛠 Взять в работу")) is False

    assert _calls(telegram, "answerCallbackQuery")[0]["text"].startswith("Не получилось")


def test_cart_reminder_button_still_goes_to_reminders(telegram):
    with patch("apps.users.telegram_auth._process_cart_reminders_callback", return_value=True) as reminders:
        process_telegram_webhook({"callback_query": {"id": "1", "data": "cart_reminders_off"}})

    reminders.assert_called_once()
    assert not telegram


# ─── Заявка «Найдём товар» ────────────────────────────────────────────────────


def _sourcing_request():
    req = SourcingRequest.objects.create(
        comment="Кроссовки 42", contact_name="Олег", contact_channel="telegram", contact_username="oleg_k", locale="ru",
    )
    return req, create_order_for_sourcing_request(req)


def test_sourcing_notification_carries_buttons_of_its_order():
    req, order = _sourcing_request()

    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(status_code=200, ok=True)) as post:
        notify_sourcing_request_telegram.run(request_id=req.pk)

    keyboard = post.call_args.kwargs["json"]["reply_markup"]
    assert _texts(keyboard) == [
        "🛠 Взять в работу", "💬 Написали клиенту", "💰 Назвали цену", "❌ Не состоялась",
        "🗂 Открыть в админке", "✍️ Написать в Telegram",
    ]
    assert _data(keyboard, "🛠 Взять в работу") == f"o:{order.id}:new:s:in_progress"


def test_sourcing_order_is_closed_with_not_found_reason(telegram):
    _req, order = _sourcing_request()

    _press(f"o:{order.id}:new:r:not_found")

    order.refresh_from_db()
    assert (order.processing_status, order.processing_fail_reason) == (PS.CANCELLED, "not_found")


def test_sourcing_notification_is_sent_without_buttons_if_telegram_rejects_them():
    req, _order_ = _sourcing_request()
    replies = [SimpleNamespace(status_code=400, ok=False), SimpleNamespace(status_code=200, ok=True)]

    with patch("apps.orders.tasks.requests.post", side_effect=replies) as post:
        notify_sourcing_request_telegram.run(request_id=req.pk)

    first, second = (call.kwargs["json"] for call in post.call_args_list)
    assert "reply_markup" in first and "reply_markup" not in second
    assert first["text"] == second["text"]


# ─── Уведомление о заявке из Списка ───────────────────────────────────────────


@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=None)
@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.drug_check.service.order_checks", return_value={})
def test_long_order_notification_has_buttons_only_on_last_message(*_):
    order = _order(comment="слово " * 1500)
    OrderItem.objects.create(order=order, product_name="PAROL", price=1, quantity=1, total=1)

    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(status_code=200, ok=True)) as post:
        notify_new_order_telegram.run(order_id=order.id)

    messages = [call.kwargs["json"] for call in post.call_args_list]
    assert len(messages) > 1
    assert ["reply_markup" in message for message in messages] == [False] * (len(messages) - 1) + [True]
    assert _data(messages[-1]["reply_markup"], "🛠 Взять в работу") == f"o:{order.id}:new:s:in_progress"


@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.drug_check.service.order_checks", return_value={})
@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=b"%PDF")
def test_receipt_document_carries_buttons_as_json_string(*_):
    order = _order()

    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(status_code=200, ok=True)) as post:
        notify_new_order_telegram.run(order_id=order.id)

    data = post.call_args.kwargs["data"]
    assert post.call_args.args[0].endswith("/sendDocument")
    assert f"o:{order.id}:new:s:in_progress" in data["reply_markup"]


# ─── Команда /orders ──────────────────────────────────────────────────────────


def _command(text, user_id=MEMBER, chat_type="private"):
    return process_telegram_webhook({
        "message": {"text": text, "from": {"id": user_id}, "chat": {"id": user_id, "type": chat_type}}
    })


def test_orders_command_shows_summary_with_status_buttons(telegram):
    _order(processing_status=PS.PAID)
    _order(processing_status=PS.PAID)
    _order()
    _order(processing_status=PS.DONE)
    _order(processing_status=PS.CANCELLED)

    assert _command("/orders") is True

    sent = _calls(telegram, "sendMessage")[0]
    assert sent["chat_id"] == MEMBER and "Незакрытые заявки: 3" in sent["text"]
    rows = sent["reply_markup"]["inline_keyboard"]
    assert [(row[0]["text"], row[0].get("callback_data")) for row in rows[:-1]] == [
        ("Новая (1)", "ol:new"), ("Оплачено — закупаем (2)", "ol:paid"),
    ]
    assert rows[-1][0]["url"].endswith("/admin/orders/order/?processing=open")


def _press_summary(data, user_id=MEMBER):
    return process_telegram_webhook({
        "callback_query": {
            "id": "cb2", "from": {"id": user_id}, "data": data,
            "message": {"message_id": 1, "chat": {"id": user_id, "type": "private"}},
        }
    })


def test_status_button_lists_only_these_orders_with_items_and_step_buttons(telegram):
    paid = _order(processing_status=PS.PAID, contact_name="Мария <b>")
    OrderItem.objects.create(order=paid, product_name="PAROL 500 mg", chosen_size="20 таб", price=5, quantity=3, total=15)
    other = _order(processing_status=PS.PRICE_SENT)

    assert _press_summary("ol:paid") is True

    card, footer = _calls(telegram, "sendMessage")
    assert card["chat_id"] == MEMBER
    assert f"<b>№{paid.number}</b> · Мария &lt;b&gt;" in card["text"]
    assert "• PAROL 500 mg (20 таб) × 3" in card["text"]
    assert "1000.00 RUB" in card["text"]
    assert STATUS_MARK + "Оплачено — закупаем" in card["text"]
    assert _data(card["reply_markup"], "📦 Отправлено") == f"o:{paid.id}:paid:s:shipped"
    assert other.number not in card["text"]
    assert "Оплачено — закупаем</b>: 1" in footer["text"]
    buttons = [button for row in footer["reply_markup"]["inline_keyboard"] for button in row]
    assert buttons[0]["url"].endswith("?processing=paid") and buttons[1]["callback_data"] == "ol:"
    assert _calls(telegram, "answerCallbackQuery")[0]["text"] == "Оплачено — закупаем: 1"

    # Кнопка шага в списке работает так же, как под уведомлением
    _press(_data(card["reply_markup"], "📦 Отправлено"), message={"message_id": 9, "chat": {"id": MEMBER}, "text": "x"})
    paid.refresh_from_db()
    assert paid.processing_status == PS.SHIPPED


def test_back_to_summary_and_stranger_denied(telegram):
    order = _order()

    _press_summary("ol:")
    assert "Незакрытые заявки: 1" in _calls(telegram, "sendMessage")[0]["text"]

    _press_summary("ol:new", user_id=STRANGER)
    assert len(_calls(telegram, "sendMessage")) == 1
    answer = _calls(telegram, "answerCallbackQuery")[-1]
    assert answer["text"].startswith("Нет доступа") and order.number not in answer["text"]


def test_orders_command_denied_to_stranger(telegram):
    order = _order()

    assert _command("/orders", user_id=STRANGER) is False

    texts = [payload["text"] for payload in _calls(telegram, "sendMessage")]
    assert len(texts) == 1 and texts[0].startswith("Нет доступа")
    assert order.number not in texts[0]


def test_orders_command_is_silent_outside_private_chat(telegram):
    assert _command("/orders", chat_type="supergroup") is False
    assert not telegram
