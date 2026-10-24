"""Препараты, которые нельзя продвигать: ввоз в Россию и СНГ запрещён или ограничен.

Временная проверка до справочника контролируемых веществ (TD-024 в docs/TECH_DEBT.md).
Используется там, где сайт сам выбирает, что показать и куда сослаться: страницы
препаратов (/drugs/<slug>) и ссылки на них с карточек. Каталог и карточки такие
товары по-прежнему показывают.

Признаки: действующее вещество из списков наркотических, психотропных,
сильнодействующих веществ и прекурсоров (ПП РФ № 681 и № 964) или турецкий рецепт
строгого учёта (красный, зелёный, оранжевый, фиолетовый, «kontrole tabi»).
Вещество ищется по началу слова на турецком, английском и русском, поэтому
«Psödoefedrin Hidroklorür», «pseudoephedrine» и «псевдоэфедрин» ловятся одинаково.
"""

from __future__ import annotations

import re
from typing import Any

from apps.ai.services.medicine_reference import fold_tr

# Начала слов (после fold_tr: нижний регистр, турецкие буквы → ASCII).
RESTRICTED_SUBSTANCE_STEMS = (
    # опиоиды
    "fentan", "фентан", "kodein", "codein", "кодеин", "dihidrokodein", "morfin", "morphin", "морфин",
    "oksikodon", "oxycodon", "оксикодон", "tramadol", "трамадол", "tapentadol", "тапентадол",
    "metadon", "methadon", "метадон", "buprenorf", "бупренорф", "petidin", "pethidin", "петидин",
    "dekstrometorfan", "dextromethorphan", "декстрометорфан",
    # прекурсоры в средствах от простуды
    "psodoefedrin", "psoydoefedrin", "pseudoefedrin", "pseudoephedrin", "псевдоэфедрин",
    "efedrin", "ephedrin", "эфедрин", "fenilpropanolamin", "phenylpropanolamin", "фенилпропаноламин",
    "ergotamin", "эрготамин",
    # противосудорожные, снотворные, успокоительные
    "pregabalin", "прегабалин", "fenobarbital", "phenobarbital", "фенобарбитал",
    "allobarbital", "аллобарбитал", "barbital", "барбитал",
    "alprazolam", "алпразолам", "diazepam", "диазепам", "lorazepam", "лоразепам",
    "klonazepam", "clonazepam", "клоназепам", "midazolam", "мидазолам", "bromazepam", "бромазепам",
    "zolpidem", "золпидем", "zopiklon", "zopiclon", "зопиклон", "ketamin", "кетамин",
    "tianeptin", "тианептин", "metilfenidat", "methylphenidat", "метилфенидат",
    "sibutramin", "сибутрамин",
    # сильнодействующие: глазные мидриатики, анаболики
    "tropikamid", "tropicamid", "тропикамид", "siklopentolat", "cyclopentolat", "циклопентолат",
    "testosteron", "тестостерон", "nandrolon", "нандролон",
)

# Турецкий рецепт строгого учёта и его перевод (см. medicine_seo.prescription_kind).
_CONTROLLED_PRESCRIPTION = re.compile(
    r"kirmizi|yesil|turuncu|\bmor\b|kontrole tabi|controlled|красн|зелен|зелён|оранж|фиолет|строгого",
)
_SUBSTANCE = re.compile(r"(?<![a-zа-яё])(?:" + "|".join(RESTRICTED_SUBSTANCE_STEMS) + ")")


def is_restricted_medicine(active_ingredient: Any = "", prescription_type: Any = "") -> bool:
    """True — препарат не продвигаем (страницы препаратов, ссылки, тексты)."""
    if _SUBSTANCE.search(fold_tr(active_ingredient)):
        return True
    return bool(_CONTROLLED_PRESCRIPTION.search(fold_tr(prescription_type)))
