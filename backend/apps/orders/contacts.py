"""Контакты клиента для связи менеджера: канал, юзернейм, email.

Общая проверка для заявки из checkout и формы «Найдём товар».
"""

import re

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
