"""Контакты клиента для связи менеджера: канал, юзернейм, email.

Общая проверка для заявки из checkout и формы «Найдём товар».
"""

import re
from urllib.parse import quote

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

# Telegram — 5–32 символа (латиница, цифры, _);
# WhatsApp — юзернейм 3–35 символов (латиница, цифры, . и _) или номер телефона.
USERNAME_PATTERNS = {
    "telegram": (r"[A-Za-z0-9_]{5,32}", _("Укажите ник Telegram: 5–32 символа, латиница, цифры и _.")),
    "whatsapp": (
        r"[A-Za-z0-9._]{3,35}|\+?\d{9,15}",
        _("Укажите юзернейм WhatsApp (3–35 символов: латиница, цифры, . и _) или номер."),
    ),
}


def validate_contact_fields(attrs: dict) -> dict:
    """Нормализует contact_username под канал и требует email для канала «email»."""
    channel = attrs.get("contact_channel") or ""
    username = (attrs.get("contact_username") or "").strip()
    username = username.removeprefix("https://t.me/").removeprefix("t.me/").lstrip("@")
    pattern = USERNAME_PATTERNS.get(channel)
    if not pattern:
        username = ""
    elif username and not re.fullmatch(pattern[0], username):
        raise serializers.ValidationError({"contact_username": pattern[1]})
    attrs["contact_username"] = username
    if channel == "email" and not attrs.get("contact_email"):
        raise serializers.ValidationError({"contact_email": _("Укажите email: вы выбрали связь по email.")})
    return attrs


# ─── Ссылки для связи из админки ──────────────────────────────────────────────

# Сколько последних цифр телефона сравнивать при поиске других заявок клиента:
# так «+7 912…», «8912…» и «912…» — один номер (и турецкие +90 / 0 5xx тоже).
PHONE_MATCH_DIGITS = 10


def whatsapp_number(raw: str) -> str:
    """Номер для wa.me: только цифры с кодом страны; пусто, если код страны неясен.

    «+…» — как есть; 11 цифр с 7 — как есть; 10 цифр с 9 — российский без кода (+7);
    11 цифр с 8 — российский с 8 (8 → 7). Остальное (например «0532…») — неясно.
    """
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and 10 <= len(digits) <= 15:
        return digits
    if len(digits) == 11 and digits[0] == "7":
        return digits
    if len(digits) == 10 and digits[0] == "9":
        return "7" + digits
    if len(digits) == 11 and digits[0] == "8":
        return "7" + digits[1:]
    return ""


def phone_tail(raw: str) -> str:
    """Последние PHONE_MATCH_DIGITS цифр телефона; пусто, если цифр меньше."""
    digits = re.sub(r"\D", "", raw or "")
    return digits[-PHONE_MATCH_DIGITS:] if len(digits) >= PHONE_MATCH_DIGITS else ""


def telegram_username(raw: str) -> str:
    """Ник Telegram без @ и t.me/; пусто, если не похож на ник."""
    username = (raw or "").strip().removeprefix("https://t.me/").removeprefix("t.me/").lstrip("@")
    return username if re.fullmatch(USERNAME_PATTERNS["telegram"][0], username) else ""


# ─── Черновик сообщения покупателю ────────────────────────────────────────────

# В черновик идут первые позиции и короткие названия: длинный адрес ссылки не откроется
# и раздует уведомление в Telegram.
MESSAGE_ITEMS_SHOWN = 5
MESSAGE_ITEM_NAME_LIMIT = 50


def contact_message(name: str, number, item_names=(), sourcing: bool = False) -> str:
    """Текст, который подставляется в чат или письмо покупателю; отправляет менеджер сам.

    Текст утверждает владелец: без обещаний оплаты, наличия и сроков, без склада и поставщика.
    """
    name = " ".join((name or "").split())
    greeting = f"Здравствуйте, {name}!" if name else "Здравствуйте!"
    if sourcing:
        what = f"Вы оставили заявку на поиск товара №{number}."
    else:
        names = [" ".join(str(item).split()) for item in item_names]
        names = [
            item if len(item) <= MESSAGE_ITEM_NAME_LIMIT else item[: MESSAGE_ITEM_NAME_LIMIT - 1].rstrip() + "…"
            for item in names
            if item
        ]
        listed = "; ".join(names[:MESSAGE_ITEMS_SHOWN])
        more = len(names) - MESSAGE_ITEMS_SHOWN
        if more > 0:
            listed += f" и ещё {more}"
        what = f"Вы оставили заявку №{number}" + (f": {listed}." if listed else ".")
    return f"{greeting} Это Mudaroba. {what} Готовы ответить на вопросы и уточнить детали."


def contact_message_subject(number, sourcing: bool = False) -> str:
    return f"Заявка на поиск товара №{number} — Mudaroba" if sourcing else f"Заявка №{number} — Mudaroba"


def contact_links(channel: str, username: str, phone: str, email: str, text: str, subject: str) -> list[tuple[str, str]]:
    """Ссылки для связи с черновиком text: [(канал, адрес)]. Непонятный контакт — без ссылки.

    Telegram — только если клиент выбрал Telegram: по нику, иначе по номеру с понятным кодом
    страны (по номеру Telegram может не подставить текст). WhatsApp — номер из «Юзернейма»,
    если клиент выбрал WhatsApp, иначе из «Телефона».
    """
    username = (username or "").strip()
    phone = (phone or "").strip()
    email = (email or "").strip()
    phone_wa = whatsapp_number(phone)
    tg = ""
    if channel == "telegram":
        tg = telegram_username(username)
        if not tg or tg.isdigit():
            # Вместо ника клиент вписал номер (или ничего): t.me/<цифры> вёл бы к чужому нику
            number = whatsapp_number(username) or phone_wa
            tg = f"+{number}" if number else ""
    wa = (whatsapp_number(username) if channel == "whatsapp" else "") or phone_wa
    digits = re.sub(r"\D", "", phone)
    # Номер с понятным кодом страны — в международном виде, иначе как ввёл клиент
    tel = f"+{phone_wa}" if phone_wa else (("+" if phone.startswith("+") else "") + digits if digits else "")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", email):
        email = ""
    query = quote(text, safe="")
    candidates = (
        ("telegram", tg and f"https://t.me/{tg}?text={query}"),
        ("whatsapp", wa and f"https://wa.me/{wa}?text={query}"),
        ("phone", tel and f"tel:{tel}"),
        ("email", email and f"mailto:{quote(email, safe='@+')}?subject={quote(subject, safe='')}&body={query}"),
    )
    return [(key, href) for key, href in candidates if href]
