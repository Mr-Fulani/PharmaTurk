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
# карточки — до 160 знаков, полная фраза вытесняла бы вещество и «инструкцию»; короткая форма «3–14 дней»
# (решение владельца 09.11.2026) той же длины, что прежнее «… 7–14 дней.». Полные сроки — на страницах и в FAQ.
ORDER_SENTENCE = {
    "ru": "Заявка менеджеру, доставка 3–14 дней.",
    "en": "Send a request, delivery in 3–14 days.",
}
# В описаниях для поиска (meta/og/seo description) — короткая форма
SHORT = {"ru": "3–14 дней", "en": "3–14 days"}

# Прежний срок: лекарства — всегда, БАДы — ещё и «7–14 дней» (только срок доставки; «от 5 $» у БАДов не пишем)
_MEDICINE_RANGE = {"ru": r"7[–-]21 рабоч(?:ий|их) д(?:ень|ня|ней)", "en": r"7[–-]21 (?:business|working) days"}
_SUPPLEMENT_RANGE = {"ru": r"7[–-]14 (?:дней|дня)(?:, от 5 \$)?", "en": r"7[–-]14 days(?:, from \$5)?"}
# Полная форма без диапазона впереди: «доставка 7–21 рабочий день» → «доставка: авиа 3–7, …»,
# «посылка идёт 7–21 рабочий день» → «посылка: авиа 3–7, …»; после тире — просто фраза.
_VERBS = {
    "ru": r"занимает|займёт|длится|идёт|идут|приходит|доставляются|находится|будет в пути",
    "en": r"takes|take|arrive|arrives|is in transit for|is",
}
_PREPOSITIONS = {"ru": r"за|в течение", "en": r"in|within"}


def _full(locale: str, range_re: str) -> list[tuple[re.Pattern, str]]:
    terms = TERMS[locale]
    return [
        # «Parcels take 7–21 business days to arrive», «the parcel spends 7–21 working days in transit»
        (re.compile(rf"\s+takes?\s+{range_re}\s+to arrive"), f": {terms}"),
        (re.compile(rf"\bspends\s+{range_re}\s+in transit"), f"is in transit: {terms}"),
        # «Срок доставки — 7–21 рабочий день», «Allow 7–21 working days» — подставить фразу как есть
        (re.compile(rf"(—\s*|\b(?:Allow|allow|закладывайте|Ожидание посылки —)\s*){range_re}"), rf"\g<1>{terms}"),
        (
            re.compile(rf"(?:\s+(?:{_VERBS[locale]}))?(?:\s+(?:{_PREPOSITIONS[locale]}))?\s+{range_re}"),
            f": {terms}",
        ),
    ]


def replace_terms(text: str, *, supplements: bool = False, short: bool = False) -> str:
    """Прежние сроки доставки → новые. ``supplements`` — текст БАДа: ещё и «7–14 дней»;
    ``short`` — описание для поиска: «3–14 дней», чтобы не выйти за 200 знаков; прежнее предложение
    кода «Заявка менеджеру, доставка 7–21 рабочий день.» становится ``ORDER_SENTENCE``."""
    if not text:
        return text
    for locale in ("ru", "en"):
        ranges = [_MEDICINE_RANGE[locale]] + ([_SUPPLEMENT_RANGE[locale]] if supplements else [])
        for range_re in ranges:
            if short:
                text = re.sub(range_re, SHORT[locale], text)
                continue
            for pattern, replacement in _full(locale, range_re):
                text = pattern.sub(replacement, text)
    return text
