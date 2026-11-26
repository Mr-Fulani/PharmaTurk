"""Готовые сообщения клиенту: текст шаблона из админки с данными заявки.

Сообщение отправляет менеджер сам — бот только показывает готовый текст в чате заявок
(apps/orders/telegram_buttons.py). Описание — docs/ORDER_PROCESSING.md.
"""

import re

from django.conf import settings

from .contacts import message_locale, order_item_names
from .models import ClientMessageTemplate, Order

ITEMS_SHOWN = 20
ITEM_NAME_LIMIT = 80
# Подсказка в админке: что можно вставить в текст
PLACEHOLDERS_HELP = (
    "{имя} — имя клиента (если имени нет, «, {имя}» убирается: «Здравствуйте!»); "
    "{номер} — номер заявки; {товары} — блок «Ваш заказ» со строкой на каждый товар "
    "(у заявки «Найти товар» пропускается); {сумма товаров}, {сумма доставки}, {итого} — суммы "
    "из заявки в её валюте (если доставка не посчитана — «[впишите сумму доставки]», а «Итого» "
    "с пометкой «без доставки»); {ссылка на отзывы} — страница отзывов на сайте. "
    "Незнакомая подстановка остаётся в тексте как есть."
)
WORDS = {
    "ru": {
        "items": "Ваш заказ:", "more": "… и ещё {n}", "on_request": " — цена по запросу",
        "fill": "[впишите сумму]", "fill_shipping": "[впишите сумму доставки]",
        "no_shipping": "без доставки", "no_on_request": "без позиций с ценой по запросу",
    },
    "en": {
        "items": "Your order:", "more": "… and {n} more", "on_request": " — price on request",
        "fill": "[enter the amount]", "fill_shipping": "[enter the delivery cost]",
        "no_shipping": "delivery not included", "no_on_request": "items priced on request not included",
    },
}
_PLACEHOLDER_RE = re.compile(r"\{([^{}\n]+)\}")
_NAME_RE = re.compile(r",?[ \t]*\{\s*имя\s*\}", re.IGNORECASE)


def _values(order) -> dict:
    """Значения подстановок. Суммы — поля самой заявки, как в уведомлении и чеке."""
    locale = message_locale(order.locale)
    words = WORDS[locale]
    money = lambda amount: f"{amount} {order.currency}"  # noqa: E731

    items_block, on_request = "", False
    if order.kind != Order.Kind.SOURCING:
        items = list(order.items.all())
        lines = []
        for item, name in zip(items, order_item_names(items, locale)):
            name = " ".join(str(name).split())
            if len(name) > ITEM_NAME_LIMIT:
                name = name[: ITEM_NAME_LIMIT - 1].rstrip() + "…"
            if item.chosen_size:
                name += f" ({item.chosen_size})"
            line = f"• {name} × {item.quantity}"
            if not item.price:
                on_request = True
                line += words["on_request"]
            lines.append(line)
        if len(lines) > ITEMS_SHOWN:
            lines = lines[:ITEMS_SHOWN] + [words["more"].format(n=len(lines) - ITEMS_SHOWN)]
        if lines:
            items_block = "\n".join([words["items"], *lines])

    notes = []
    if not order.shipping_amount:
        notes.append(words["no_shipping"])
    if on_request:
        notes.append(words["no_on_request"])
    total = money(order.total_amount) if order.total_amount else words["fill"]
    if notes and order.total_amount:
        total += f" ({', '.join(notes)})"
    return {
        "имя": " ".join((order.contact_name or "").split()),
        "номер": str(order.number),
        "товары": items_block,
        "сумма_товаров": money(order.subtotal_amount) if order.subtotal_amount else words["fill"],
        "сумма_доставки": money(order.shipping_amount) if order.shipping_amount else words["fill_shipping"],
        "итого": total,
        "ссылка_на_отзывы": f"{settings.SITE_URL}{'/en' if locale == 'en' else ''}/testimonials?action=add",
    }


def render_client_message(key: str, order) -> str:
    """Текст сообщения клиенту по шаблону key; пустая строка, если шаблона нет или он пуст."""
    template = ClientMessageTemplate.objects.filter(key=key).first()
    if template is None:
        return ""
    text = (template.text_en if message_locale(order.locale) == "en" else "") or template.text_ru
    values = _values(order)
    if not values["имя"]:
        text = _NAME_RE.sub("", text)
    text = _PLACEHOLDER_RE.sub(
        lambda match: values.get("_".join(match.group(1).lower().split()), match.group(0)), text,
    )
    # Пропущенный блок товаров не должен оставлять дыру из пустых строк
    return re.sub(r"\n{3,}", "\n\n", text).strip()
