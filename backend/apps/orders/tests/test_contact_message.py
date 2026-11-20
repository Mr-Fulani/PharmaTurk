"""Черновик сообщения покупателю и ссылки на чат/письмо с этим черновиком."""

from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from apps.orders.contacts import (
    MESSAGE_ITEM_NAME_LIMIT,
    contact_links,
    contact_message,
    contact_message_subject,
    order_item_names,
)

TEXT = contact_message("Иван", "REQ-20261120-0007", ["Парацетамол 500 мг"])


def _links(channel="", username="", phone="", email="", text=TEXT, subject="Тема"):
    return dict(contact_links(channel, username, phone, email, text, subject))


RU_TAIL = (
    " Пишем, чтобы уточнить детали и рассказать о стоимости, сроках и порядке доставки."
    " Когда вам удобно это обсудить?"
)
EN_TAIL = (
    " We are writing to confirm the details and tell you about the price, delivery time and how delivery works."
    " When would be a good time to talk?"
)


def test_message_text():
    assert TEXT == (
        "Здравствуйте, Иван! Это Mudaroba. Спасибо за заявку №REQ-20261120-0007: Парацетамол 500 мг." + RU_TAIL
    )
    assert contact_message("Ivan", "REQ-20261120-0007", ["Parol 500 mg", "Nurofen"], locale="en") == (
        "Hello Ivan! This is Mudaroba. Thank you for your request No. REQ-20261120-0007: Parol 500 mg; Nurofen."
        + EN_TAIL
    )


def test_message_without_name_and_items():
    assert contact_message("  ", "REQ-1") == "Здравствуйте! Это Mudaroba. Спасибо за заявку №REQ-1." + RU_TAIL
    assert contact_message("", "REQ-1", locale="en") == (
        "Hello! This is Mudaroba. Thank you for your request No. REQ-1." + EN_TAIL
    )


def test_message_for_sourcing_request():
    assert contact_message("Анна", 15, sourcing=True) == (
        "Здравствуйте, Анна! Это Mudaroba. Спасибо за заявку на поиск товара №15." + RU_TAIL
    )
    assert contact_message("Anna", 15, sourcing=True, locale="en") == (
        "Hello Anna! This is Mudaroba. Thank you for your product search request No. 15." + EN_TAIL
    )
    assert contact_message_subject(15, sourcing=True) == "Заявка на поиск товара №15 — Mudaroba"
    assert contact_message_subject("REQ-1") == "Заявка №REQ-1 — Mudaroba"
    assert contact_message_subject(15, sourcing=True, locale="en") == "Your product search request No. 15 — Mudaroba"
    assert contact_message_subject("REQ-1", locale="en") == "Your request No. REQ-1 — Mudaroba"


@pytest.mark.parametrize("locale", ["", None, "ru", "tr", "de-DE", "xx"])
def test_unknown_or_missing_language_falls_back_to_russian(locale):
    assert contact_message("Иван", "REQ-1", locale=locale).startswith("Здравствуйте, Иван!")
    assert contact_message_subject("REQ-1", locale=locale) == "Заявка №REQ-1 — Mudaroba"


@pytest.mark.parametrize("locale", ["en", "EN", "en-US"])
def test_english_language_variants(locale):
    assert contact_message("Ivan", "REQ-1", locale=locale).startswith("Hello Ivan!")


def test_english_item_names_come_from_translations_in_one_query():
    items = [
        SimpleNamespace(product_id=1, product_name="Парол"),
        SimpleNamespace(product_id=2, product_name="Нурофен"),
        SimpleNamespace(product_id=None, product_name="Без товара"),
    ]
    assert order_item_names(items, "ru") == ["Парол", "Нурофен", "Без товара"]
    with patch("apps.catalog.models.ProductTranslation.objects") as objects:
        objects.filter.return_value.exclude.return_value.values_list.return_value = [(1, "Parol")]
        # Перевод есть только у первой позиции: остальные остаются как есть
        assert order_item_names(items, "en") == ["Parol", "Нурофен", "Без товара"]
    objects.filter.assert_called_once_with(product_id__in=[1, 2], locale="en")


def test_long_list_is_cut_and_long_names_are_shortened():
    names = [f"Товар {index}" for index in range(1, 8)] + ["  ", ""]
    text = contact_message("Иван", "REQ-1", names)
    assert "Товар 1; Товар 2; Товар 3; Товар 4; Товар 5 и ещё 2. Пишем" in text
    assert "Товар 6" not in text
    assert "Товар 5 and 2 more. We are" in contact_message("Ivan", "REQ-1", names, locale="en")

    text = contact_message("Иван", "REQ-1", ["Очень длинное\nназвание " * 30])
    listed = text.split("REQ-1: ")[1].split(". Пишем")[0]
    assert len(listed) == MESSAGE_ITEM_NAME_LIMIT and listed.endswith("…") and "\n" not in listed


def test_text_with_special_characters_is_url_encoded():
    text = contact_message("Иван & <Co>", "REQ-1", ['Крем "A&B" 50% #1 + ?x=1'])
    links = _links("telegram", "@ivan_petrov", "+7 (912) 247-68-66", "ivan@example.test", text=text, subject="A&B?")
    for key in ("telegram", "whatsapp"):
        query = urlsplit(links[key]).query
        assert query.startswith("text=") and not set(query[5:]) & set(' &#"<>+?=')
        assert parse_qs(query)["text"] == [text]
    mail = urlsplit(links["email"])
    assert mail.scheme == "mailto" and mail.path == "ivan@example.test"
    # В mailto пробел — %20: «+» почтовые программы показывают как плюс
    assert "+" not in mail.query
    subject, body = (part.split("=", 1)[1] for part in mail.query.split("&"))
    assert unquote(subject) == "A&B?" and unquote(body) == text


def test_telegram_username_is_normalized():
    assert _links("telegram", "@ivan_petrov")["telegram"].startswith("https://t.me/ivan_petrov?text=")
    assert _links("telegram", "https://t.me/ivan_petrov")["telegram"].startswith("https://t.me/ivan_petrov?text=")
    # Ник не из выбранного канала ссылкой Telegram не становится
    assert "telegram" not in _links("whatsapp", "ivan_petrov", "+79122476866")


def test_telegram_by_phone_when_there_is_no_username():
    assert _links("telegram", "", "+7 (912) 247-68-66")["telegram"].startswith("https://t.me/+79122476866?text=")
    # Вместо ника вписан номер: ссылка по номеру, а не на чужой ник из цифр
    assert _links("telegram", "89122476866")["telegram"].startswith("https://t.me/+79122476866?text=")


def test_garbage_contacts_give_no_links():
    assert _links("telegram", "ivan petrov/../x", "0532 123 45 67") == {"phone": "tel:05321234567"}
    assert _links("whatsapp", "<script>", "12345", "not-an-email") == {"phone": "tel:12345"}
    assert _links("telegram", "@ab", "", "a@b@c") == {}


def test_whatsapp_number_is_digits_only():
    assert _links("whatsapp", "+90 532 123 45 67", "05321234567")["whatsapp"].startswith(
        "https://wa.me/905321234567?text="
    )
    assert _links("phone", "", "8 (912) 247-68-66")["whatsapp"].startswith("https://wa.me/79122476866?text=")
