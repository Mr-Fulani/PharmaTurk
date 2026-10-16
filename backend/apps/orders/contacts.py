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
