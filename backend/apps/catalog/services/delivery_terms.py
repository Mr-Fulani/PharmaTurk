"""Сроки доставки лекарств и БАДов в текстах сайта (решение владельца 09.11.2026).

Владелец: «и бады и лекарства одинаковый срок: авиа 3–7, наземная 7–14, морем 20–45 дней» — как в
блоке «Способы доставки» на /delivery. Прежние сроки: лекарства «7–21 рабочий день», БАДы «7–14 дней»
(28.10.2026). Одежду, обувь, мебель и другие товары это не касается: у них «7–14 дней, от 5 $».

Здесь — фраза для генераторов SEO и правила замены уже записанных текстов (команда
``replace_delivery_terms``). Меняются только известные формулировки сроков; остальной текст как был.
"""

from __future__ import annotations

import re

TERMS = {
    "ru": "авиа 3–7, наземная 7–14, морем 20–45 дней",
    "en": "air 3–7, ground 7–14, sea 20–45 days",
}
# Предложение в SEO-описаниях карточек, которое собирает код (medicine_seo, supplement_content). Описание
# карточки — до 160 знаков, полная фраза вытесняла бы вещество и «инструкцию»; 3–45 дней — от авиа до моря,
# той же длины, что прежнее «Заявка менеджеру, доставка 7–14 дней.». Полные сроки — на страницах и в FAQ.
ORDER_SENTENCE = {
    "ru": "Заявка менеджеру, доставка 3–45 дней.",
    "en": "Send a request, delivery in 3–45 days.",
}
# Внутри фразы вместо прежнего срока: «доставка 7–21 рабочий день» → «доставка 3–45 дней (авиа …)»
_SPAN = {
    "ru": "3–45 дней (авиа 3–7, наземная 7–14, морем 20–45)",
    "en": "3–45 days (air 3–7, ground 7–14, sea 20–45)",
}
# В описаниях для поиска (meta/og/seo description) — без расшифровки
_SPAN_SHORT = {"ru": "3–45 дней", "en": "3–45 days"}

# Предложения, которые прежний код ставил в SEO целиком
_OLD_ORDER_SENTENCES = (
    ("Заявка менеджеру, доставка 7–21 рабочий день.", ORDER_SENTENCE["ru"]),
    ("Send a request, delivery in 7–21 business days.", ORDER_SENTENCE["en"]),
    ("Заявка менеджеру, доставка 7–14 дней.", ORDER_SENTENCE["ru"]),
    ("Send a request, delivery in 7–14 days.", ORDER_SENTENCE["en"]),
)
_MEDICINE_PATTERNS = (
    ("ru", re.compile(r"7[–-]21 рабоч(?:ий|их) д(?:ень|ня|ней)")),
    ("en", re.compile(r"7[–-]21 (?:business|working) days")),
)
# «7–14 дней» у БАДов — только срок доставки (тексты разделов и SEO карточек БАДов); «от 5 $» у БАДов не пишем
_SUPPLEMENT_PATTERNS = (
    ("ru", re.compile(r"7[–-]14 (?:дней|дня)(?:, от 5 \$)?")),
    ("en", re.compile(r"7[–-]14 days(?:, from \$5)?")),
)


def replace_terms(text: str, *, supplements: bool = False, short: bool = False) -> str:
    """Прежние сроки доставки → новые. ``supplements`` — текст БАДа: ещё и «7–14 дней»;
    ``short`` — описание для поиска: «3–45 дней» без расшифровки, чтобы не выйти за 200 знаков."""
    if not text:
        return text
    for old, new in _OLD_ORDER_SENTENCES:
        text = text.replace(old, new)
    spans = _SPAN_SHORT if short else _SPAN
    for locale, pattern in _MEDICINE_PATTERNS + (_SUPPLEMENT_PATTERNS if supplements else ()):
        text = pattern.sub(spans[locale], text)
    return text
