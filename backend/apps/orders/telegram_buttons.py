"""Кнопки под уведомлением о заявке в Telegram-чате заявок и команда /orders (сводка по отметкам).

Кнопки двигают только отметку «Обработка» (Order.processing_status) — тем же путём, что и
админка (processing.change_processing). «Статус для клиента» не меняется, покупателю ничего
не уходит. Нажимать и просить список может любой участник чата заявок.
Описание — docs/ORDER_PROCESSING.md.
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.users.models import User

from .contacts import contact_links, contact_message, order_item_names
from .models import Order
from .processing import change_processing
from .tasks import _admin_url, _orders_chat_id, _tg_html_escape, _tg_length

logger = logging.getLogger(__name__)

PS = Order.ProcessingStatus
# callback_data (предел Telegram — 64 байта): o:<id заявки>:<отметка на кнопках>:<действие>[:<значение>]
CALLBACK_PREFIX = "o:"
# Кнопки сводки /orders: ol:<отметка> — заявки с этой отметкой, ol: — сама сводка
LIST_PREFIX = "ol:"
ORDERS_COMMANDS = ("/orders", "/заявки")
# Каждая заявка списка — отдельное сообщение со своими кнопками
ORDERS_LIST_LIMIT = 20
ITEM_NAME_LIMIT = 80
STATUS_MARK = "\n\n📌 Статус: "
MEMBER_CACHE_SECONDS = 300
MENU_CACHE_SECONDS = 24 * 60 * 60
ORDERS_MENU_COMMAND = {"command": "orders", "description": "Незакрытые заявки по статусам"}
NO_ACCESS = "Нет доступа: кнопки и список — только для участников чата заявок."

# Ход заявки по порядку; «Не состоялась» — в стороне, с причиной
CHAIN = [PS.NEW, PS.IN_PROGRESS, PS.WAITING_CLIENT, PS.PRICE_SENT, PS.AGREED, PS.PAID, PS.SHIPPED, PS.DONE]
BUTTONS = {
    PS.IN_PROGRESS: "🛠 Взять в работу",
    PS.WAITING_CLIENT: "💬 Написали клиенту",
    PS.PRICE_SENT: "💰 Назвали цену",
    PS.AGREED: "🤝 Клиент согласен",
    PS.PAID: "✅ Оплачено",
    PS.SHIPPED: "📦 Отправлено",
    PS.DONE: "🏁 Завершена",
}
# Следующие шаги: не все сразу, только ближайшие
NEXT = {
    PS.NEW: [PS.IN_PROGRESS, PS.WAITING_CLIENT, PS.PRICE_SENT],
    PS.IN_PROGRESS: [PS.WAITING_CLIENT, PS.PRICE_SENT, PS.AGREED],
    PS.WAITING_CLIENT: [PS.PRICE_SENT, PS.AGREED],
    PS.PRICE_SENT: [PS.AGREED, PS.PAID],
    PS.AGREED: [PS.PAID],
    PS.PAID: [PS.SHIPPED],
    PS.SHIPPED: [PS.DONE],
}
# Разметка, которую ставит шаблон уведомления: при правке текста её нужно вернуть Telegram
KEPT_ENTITIES = ("bold", "italic", "code", "pre", "text_link")


def _short(label) -> str:
    """«Назвали цену — ждём решения» → «Назвали цену»; «Не можем доставить (страна…)» → «Не можем доставить»."""
    return str(label).split(" — ")[0].split(" (")[0]


def _rows(buttons: list, per_row: int = 2) -> list:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def _link_buttons(order, item_names=None) -> list:
    """«Открыть в админке» и «Написать клиенту» (если контакт годится для ссылки)."""
    sourcing = order.kind == Order.Kind.SOURCING
    if item_names is None:
        item_names = [] if sourcing else order_item_names(order.items.all(), order.locale)
    hrefs = dict(
        contact_links(
            order.contact_channel, order.contact_username, order.contact_phone, "",
            contact_message(order.contact_name, order.number, item_names, sourcing=sourcing, locale=order.locale), "",
        )
    )
    buttons = [{"text": "🗂 Открыть в админке", "url": _admin_url("admin:orders_order_change", order.id)}]
    buttons += [
        {"text": f"✍️ Написать в {label}", "url": hrefs[key]}
        for key, label in (("telegram", "Telegram"), ("whatsapp", "WhatsApp"))
        if key in hrefs
    ]
    return buttons


def order_keyboard(order, menu: str = "main", item_names=None) -> dict:
    """Клавиатура под уведомлением: шаги от текущей отметки (menu="main") или причины отказа ("fail")."""
    status = order.processing_status
    data = f"{CALLBACK_PREFIX}{order.id}:{status}"
    if menu == "fail":
        rows = _rows([
            {"text": _short(label), "callback_data": f"{data}:r:{value}"}
            for value, label in Order.FailReason.choices
        ])
        rows.append([{"text": "↩️ Назад", "callback_data": f"{data}:b"}])
        return {"inline_keyboard": rows}

    rows = _rows([{"text": BUTTONS[step], "callback_data": f"{data}:s:{step}"} for step in NEXT.get(status, [])])
    extra = []
    if status == PS.CANCELLED:
        extra.append({"text": "↩️ Вернуть в работу", "callback_data": f"{data}:s:{PS.IN_PROGRESS}"})
    else:
        if status != PS.DONE:
            extra.append({"text": "❌ Не состоялась", "callback_data": f"{data}:f"})
        if status != PS.NEW:
            previous = CHAIN[CHAIN.index(status) - 1]
            extra.append({"text": f"↩️ Вернуть: {_short(previous.label)}", "callback_data": f"{data}:s:{previous}"})
    rows.append(extra)
    rows += _rows(_link_buttons(order, item_names))
    return {"inline_keyboard": rows}


def _call(method: str, **payload):
    """Вызов Bot API из вебхука: результат или None. Адрес с токеном в журнал не попадает."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        return None
    try:
        data = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=5).json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Telegram %s failed: %s", method, type(exc).__name__)
        return None
    if not data.get("ok"):
        logger.info("Telegram %s refused: %s", method, data.get("description"))
        return None
    return data.get("result") or True


def is_orders_member(user_id) -> bool:
    """Состоит ли человек в чате заявок (getChatMember); «да» помнится 5 минут."""
    chat_id = _orders_chat_id()
    if not user_id or not chat_id:
        return False
    key = f"tg_orders_member:{chat_id}:{user_id}"
    if cache.get(key):
        return True
    member = _call("getChatMember", chat_id=chat_id, user_id=user_id)
    if not isinstance(member, dict):
        return False
    status = member.get("status")
    allowed = status in ("creator", "administrator", "member") or (status == "restricted" and member.get("is_member"))
    if allowed:
        cache.set(key, True, MEMBER_CACHE_SECONDS)
        _show_orders_in_menu(user_id)
    return bool(allowed)


def _show_orders_in_menu(user_id) -> None:
    """Добавляет /orders в меню команд бота в личке этого участника (раз в сутки). Покупатели её не видят.

    Личное меню заменяет общее, поэтому общие команды бота переносятся в него как есть.
    """
    if not cache.add(f"tg_orders_menu:{user_id}", True, MENU_CACHE_SECONDS):
        return
    common = _call("getMyCommands")
    commands = [ORDERS_MENU_COMMAND] + [
        command for command in (common if isinstance(common, list) else [])
        if command.get("command") != ORDERS_MENU_COMMAND["command"]
    ]
    _call("setMyCommands", commands=commands, scope={"type": "chat", "chat_id": user_id})


def _who(tg_user: dict) -> str:
    """Имя и ник нажавшего — в журнал заявки и в строку «Статус»."""
    name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")]))
    nick = f"@{tg_user['username']}" if tg_user.get("username") else ""
    return (f"{name} ({nick})" if name and nick else name or nick or f"id {tg_user.get('id')}")[:150]


def _status_text(order) -> str:
    text = order.get_processing_status_display()
    if order.processing_status == PS.CANCELLED and order.processing_fail_reason:
        text += f" ({_short(order.get_processing_fail_reason_display())})"
    return text


def _status_line(order) -> str:
    """«Отметка — кто, когда» по последней записи журнала (в том числе о правке из админки)."""
    line = _status_text(order)
    event = order.processing_events.select_related("actor").first()
    if event:
        actor = event.actor
        who = event.actor_label or (actor and (actor.get_full_name() or actor.email)) or "—"
        line += f" — {who}, {timezone.localtime(event.created_at):%d.%m.%Y %H:%M}"
    return line


def _refresh_message(message: dict, order) -> None:
    """Дописывает в уведомление строку «Статус» и перестраивает кнопки под текущую отметку.

    Текст берётся из самого сообщения, разметка возвращается его же entities: у текста это
    editMessageText, у чека или фото с подписью — editMessageCaption. Если Telegram правку
    текста не принял (например, с новой строкой он длиннее предела), меняются только кнопки.
    """
    target = {
        "chat_id": (message.get("chat") or {}).get("id"),
        "message_id": message.get("message_id"),
        "reply_markup": order_keyboard(order),
    }
    is_caption = "caption" in message
    text = message.get("caption") if is_caption else message.get("text")
    done = None
    if text:
        head = text.split(STATUS_MARK)[0]
        entities = [
            entity
            for entity in message.get("caption_entities" if is_caption else "entities") or []
            if entity.get("type") in KEPT_ENTITIES and entity["offset"] + entity["length"] <= _tg_length(head)
        ]
        new_text = head + STATUS_MARK + _status_line(order)
        if is_caption:
            done = _call("editMessageCaption", caption=new_text, caption_entities=entities, **target)
        else:
            done = _call(
                "editMessageText", text=new_text, entities=entities,
                link_preview_options=message.get("link_preview_options") or {"is_disabled": True}, **target,
            )
    if not done:
        _call("editMessageReplyMarkup", **target)


def _press(callback: dict) -> tuple[str, bool]:
    """Обрабатывает нажатие; возвращает текст всплывающего ответа и нужно ли показать его окном."""
    tg_user = callback.get("from") or {}
    if not is_orders_member(tg_user.get("id")):
        return NO_ACCESS, True
    parts = (callback.get("data") or "").split(":")
    order = Order.objects.filter(pk=parts[1]).first() if len(parts) >= 4 and parts[1].isdigit() else None
    if order is None:
        return "Заявка не найдена: возможно, её удалили.", True
    shown, action, value = parts[2], parts[3], parts[4] if len(parts) > 4 else ""
    message = callback.get("message") or {}
    target = {"chat_id": (message.get("chat") or {}).get("id"), "message_id": message.get("message_id")}

    if order.processing_status != shown:
        # Кнопки устарели: отметку уже сменили (другой администратор или админка)
        _refresh_message(message, order)
        return f"Статус уже изменён: {_status_text(order)}. Кнопки обновлены.", True
    if action == "f":
        _call("editMessageReplyMarkup", reply_markup=order_keyboard(order, menu="fail"), **target)
        return "Выберите причину", False
    if action == "b":
        _call("editMessageReplyMarkup", reply_markup=order_keyboard(order), **target)
        return "", False
    if action == "s" and value in PS.values and value != PS.CANCELLED:
        status, reason = value, ""
    elif action == "r" and value in Order.FailReason.values:
        status, reason = PS.CANCELLED, value
    else:
        return "Кнопка устарела.", True

    # Сотрудник, привязавший этот Telegram к аккаунту сайта, становится ответственным, как в админке
    actor = User.objects.filter(telegram_id=str(tg_user.get("id")), is_staff=True, is_active=True).first()
    change_processing(
        [order.pk], actor=actor, status=status, reason=reason, actor_label=_who(tg_user),
        take=actor is not None and status == PS.IN_PROGRESS,
    )
    order.refresh_from_db()
    _refresh_message(message, order)
    return f"Статус: {_status_text(order)}", False


def handle_callback(callback: dict) -> bool:
    """Нажатие кнопки под заявкой или в сводке. Telegram получает ответ всегда, иначе на кнопке висят «часики»."""
    text, alert = "Не получилось. Попробуйте ещё раз или откройте заявку в админке.", True
    try:
        if str(callback.get("data") or "").startswith(LIST_PREFIX):
            text, alert = _press_list(callback)
        else:
            text, alert = _press(callback)
    finally:
        _call("answerCallbackQuery", callback_query_id=callback.get("id"), text=text, show_alert=alert)
    return True


def _send_summary(chat_id) -> None:
    """Сводка незакрытых заявок: по кнопке на каждую отметку, на которой есть заявки."""
    counts = {status: 0 for status in CHAIN[:-1]}
    for status in Order.objects.filter(processing_status__in=counts).values_list("processing_status", flat=True):
        counts[status] += 1
    rows = [
        [{"text": f"{status.label} ({count})", "callback_data": f"{LIST_PREFIX}{status}"}]
        for status, count in counts.items()
        if count
    ]
    rows.append([{
        "text": "🗂 Все незакрытые в админке",
        "url": _admin_url("admin:orders_order_changelist") + "?processing=open",
    }])
    total = sum(counts.values())
    text = f"📋 <b>Незакрытые заявки: {total}</b>"
    text += "\nНажмите на строку — покажу эти заявки." if total else "\nВсе заявки закрыты."
    _call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", reply_markup={"inline_keyboard": rows})


def _order_card(order) -> str:
    """Заявка в списке: номер, клиент, что в ней и сумма — и та же строка «Статус», что под уведомлением."""
    h = _tg_html_escape
    kind = "🔎 " if order.kind == Order.Kind.SOURCING else ""
    lines = [f"{kind}<b>№{h(order.number)}</b> · {h(order.contact_name)} · {timezone.localtime(order.created_at):%d.%m.%Y}"]
    for item in order.items.all():
        name = " ".join(item.product_name.split())
        if len(name) > ITEM_NAME_LIMIT:
            name = name[: ITEM_NAME_LIMIT - 1].rstrip() + "…"
        size = f" ({h(item.chosen_size)})" if item.chosen_size else ""
        lines.append(f"• {h(name)}{size} × {item.quantity}")
    lines.append(f"💰 {order.total_amount} {h(order.currency)}")
    return "\n".join(lines) + STATUS_MARK + h(_status_line(order))


def _press_list(callback: dict) -> tuple[str, bool]:
    """Кнопка сводки: присылает заявки выбранной отметки, каждую — со своими кнопками шагов."""
    if not is_orders_member((callback.get("from") or {}).get("id")):
        return NO_ACCESS, True
    chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
    status = str(callback.get("data"))[len(LIST_PREFIX):]
    if status not in PS.values:
        _send_summary(chat_id)
        return "", False
    found = Order.objects.filter(processing_status=status)
    total = found.count()
    orders = list(found.order_by("created_at").prefetch_related("items")[:ORDERS_LIST_LIMIT])
    for order in orders:
        _call(
            "sendMessage", chat_id=chat_id, text=_order_card(order), parse_mode="HTML",
            link_preview_options={"is_disabled": True}, reply_markup=order_keyboard(order),
        )
    label = PS(status).label
    text = f"<b>{_tg_html_escape(label)}</b>: {total}"
    if total > len(orders):
        text += f"\nПоказаны первые {len(orders)}, остальные — в админке."
    _call(
        "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
        reply_markup={"inline_keyboard": [
            [{"text": "🗂 Эти заявки в админке", "url": _admin_url("admin:orders_order_changelist") + f"?processing={status}"}],
            [{"text": "↩️ К сводке", "callback_data": LIST_PREFIX}],
        ]},
    )
    return f"{label}: {total}", False


def handle_orders_command(message: dict) -> bool:
    """Команда /orders в личном чате с ботом: сводка незакрытых заявок с кнопками по отметкам."""
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return False
    if not is_orders_member((message.get("from") or {}).get("id")):
        _call("sendMessage", chat_id=chat.get("id"), text=NO_ACCESS)
        return False
    _send_summary(chat.get("id"))
    return True
