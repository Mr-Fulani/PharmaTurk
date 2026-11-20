"""Черновик сообщения покупателю и ссылки на чат/письмо с этим черновиком."""

from urllib.parse import parse_qs, unquote, urlsplit

from apps.orders.contacts import (
    MESSAGE_ITEM_NAME_LIMIT,
    contact_links,
    contact_message,
    contact_message_subject,
)

TEXT = contact_message("Иван", "REQ-20261120-0007", ["Парацетамол 500 мг"])


def _links(channel="", username="", phone="", email="", text=TEXT, subject="Тема"):
    return dict(contact_links(channel, username, phone, email, text, subject))


def test_message_text():
    assert TEXT == (
        "Здравствуйте, Иван! Это Mudaroba. Вы оставили заявку №REQ-20261120-0007: Парацетамол 500 мг. "
        "Готовы ответить на вопросы и уточнить детали."
    )


def test_message_without_name_and_items():
    assert contact_message("  ", "REQ-1") == (
        "Здравствуйте! Это Mudaroba. Вы оставили заявку №REQ-1. Готовы ответить на вопросы и уточнить детали."
    )


def test_message_for_sourcing_request():
    assert contact_message("Анна", 15, sourcing=True) == (
        "Здравствуйте, Анна! Это Mudaroba. Вы оставили заявку на поиск товара №15. "
        "Готовы ответить на вопросы и уточнить детали."
    )
    assert contact_message_subject(15, sourcing=True) == "Заявка на поиск товара №15 — Mudaroba"
    assert contact_message_subject("REQ-1") == "Заявка №REQ-1 — Mudaroba"


def test_long_list_is_cut_and_long_names_are_shortened():
    names = [f"Товар {index}" for index in range(1, 8)] + ["  ", ""]
    text = contact_message("Иван", "REQ-1", names)
    assert "Товар 1; Товар 2; Товар 3; Товар 4; Товар 5 и ещё 2." in text
    assert "Товар 6" not in text

    text = contact_message("Иван", "REQ-1", ["Очень длинное\nназвание " * 30])
    listed = text.split("REQ-1: ")[1].split(". Готовы")[0]
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
