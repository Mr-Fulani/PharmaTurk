"""Сверка фактов перевода лекарства с турецким исходником.

Проверяются только факты, ошибка в которых опасна и которые можно сравнить
без LLM: дозировки с единицами в клинических разделах и МНН в переводе из
памяти переводов. Раздел с расхождением помечается в
medicine_translation_quality как неполный и уходит в модерацию. Справочные
поля (форма, рецепт, объём…) заполняет код — их сверять не нужно.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

# Единицы TR/RU/EN → каноническое имя.
_UNIT_ALIASES = {
    "mg": "mg", "мг": "mg",
    "mcg": "mcg", "µg": "mcg", "μg": "mcg", "мкг": "mcg",
    "g": "g", "gr": "g", "г": "g",
    "ml": "ml", "мл": "ml",
    # «1000 l.U./gün» — «l» вместо «I» в распознанном PDF.
    "iu": "iu", "ui": "iu", "i.u.": "iu", "i.u": "iu", "l.u.": "iu", "ме": "iu",
    # «1000 U./gün» — «ünite», в переводе «МЕ» (очередь модерации 27.10.2026).
    "u.": "iu",
    "mmol": "mmol", "ммоль": "mmol",
    "kg": "kg", "кг": "kg",
    "%": "%",
}
_UNIT_PATTERN = "|".join(
    sorted((re.escape(unit) for unit in _UNIT_ALIASES if unit != "%"), key=len, reverse=True)
)
# Миллиграммы и микрограммы словом: «1 miligram», «200 микрограммов», «100 mikrog/mL»
# (начало слова — регулярное выражение).
_UNIT_WORDS = (
    ("miligram", "mg"), ("milligram", "mg"), ("миллиграмм", "mg"),
    ("mikrog", "mcg"), ("microg", "mcg"), ("микрограмм", "mcg"),
    # «1-1,25 g» → «1-1,25 грамма»; «менее 1 ммоля», «1,75 ММОЛ/Л».
    ("gram", "g"), ("грамм", "g"), ("ммол", "mmol"),
    # «40 kilonun altındaki çocuklar» → «детей весом менее 40 кг»; не «kilokalori», «kilocalories».
    ("kilo(?![ck]al)", "kg"), ("килограмм", "kg"),
)
_UNIT_WORD_PATTERN = "|".join(stem for stem, _ in _UNIT_WORDS)
# Число: с разделителем тысяч («1.000», «1 000») или десятичное («2,5»).
_NUMBER = r"[1-9]\d{0,2}(?:[ \u00a0.,]\d{3})+|\d+(?:[.,]\d+)?"
# «2,5'mg'dır» — апостроф между числом и единицей, «5-mg tablet» — дефис,
# «28'er mg», «100'er mg» — «по 28 мг»;
# «4.5. mg», «15.4. mmol» — лишняя точка после числа. Перед числом может быть
# знак препинания без пробела («örn.30 mL», «27 ml,70 ml»), но не цифра с
# разделителем («2,5») и не точка после пробела («.5»).
_DOSE_RE = re.compile(
    rf"(?<!\w)(?<![\d\s][.,])({_NUMBER})(?:\.(?=\s))?\s*(?:['’]ş?[ae]r\b|['’-])?\s*"
    rf"((?:{_UNIT_WORD_PATTERN})\w*|(?:{_UNIT_PATTERN})(?![^\W\d_]))",
    re.IGNORECASE,
)
# Буква «l» вместо единицы в исходнике (распознанный PDF): «l.000 hastanın»,
# «1 ila l0'unda», «Bl2», «0 800 3l4 00 08», «l mmol'den», «5/l0 mg»; не литр в квадрате — «mmol2/l2».
_OCR_ONE = re.compile(
    r"(?<![a-zçğıöşü/])l(?=[.,]?\d|\s(?:mmol|mg|mcg|ml)\b)|(?<=/)l(?=[.,]?\d)(?!2(?!\d))|(?<=\d)l(?=\d)"
    r"|(?<=%)l(?![a-zçğıöşü])"  # «Yaygın yan etkiler (%l'den fazla)»
)
# Другие опечатки распознанного PDF (очередь модерации 27.10.2026): «0.,6 ml», «%0.,9» — запятая;
# «10. 000 hastanın» — тысячи; «1 buçuk-3 saatte» — 1,5; «390 C üzeri ateş» — 39 °C (градус прочитан
# нулём); «200 Lig deksmedetomidin» — мкг (µg), «220 mİ», «5 Ll'lik» — мл.
_OCR_FIXES = (
    (re.compile(r"(?<=\d)\.,(?=\d)"), ","),
    (re.compile(r"(?<=\d)\.\s(?=000(?!\d))"), "."),
    (re.compile(r"(?<=\d) buçuk\b", re.IGNORECASE), ",5"),
    (re.compile(r"\b(3[5-9]|4[0-2])0(?=\s?C\b)|\b([1-4]\d)0(?=C\b)"), lambda m: m.group(1) or m.group(2)),
    (re.compile(r"(?<=\d)(\s?)Lig\b"), r"\1mcg"),
    (re.compile(r"(?<=\d)(\s?)(?:mİ|mI|Ll)(?![^\W\d_])"), r"\1ml"),
    # «25-35 m g/kg», «1 mm ol», «Vitamin Bı2», «406, 5 mg» и «12, 42 mg'a» — пробел внутри дроби.
    (re.compile(r"(?<=\d )m g\b"), "mg"),
    (re.compile(r"(?<=\d )mm ol\b"), "mmol"),
    (re.compile(r"(?<=[A-Z])ı(?=\d)"), "1"),
    (re.compile(r"(?<=\d), (?=\d{1,2}\s?(?:mg|mcg|ml|mL|g)\b)"), ","),
)
# «%0,3 mg/ml», «PROFENID %2,5 MG» — знак процента перед дозой с единицей: в переводе пишут
# одно из двух («0,3 мг/мл» или «2,5%»).
_PERCENT_DOSE_RE = re.compile(rf"%\s*({_NUMBER})\s*({_UNIT_PATTERN})(?![^\W\d_])", re.IGNORECASE)
# «на 1 мл», «на 1 кг массы тела», «1 gramında» → «per gram» — знаменатель, а не
# доза: модель дописывает или убирает единицу («her ml'sinde 23 mg» → «23 мг на 1 мл»).
_PER_UNIT_DOSES = {("1", "ml"), ("1", "kg"), ("1", "g")}
# Пробел, потерянный исходником на границе строчного тега: «70 mLve 100 mL»,
# «135 mLsu», «PREDNOL-L20mginek», «VORELBAN15mg'dır». Однобуквенная «g» не
# берётся: «1 gün» — не «1 g ün».
_GLUED_UNIT = re.compile(r"(\d\s?(?:mg|mcg|ml|mL))(?=[a-zçğıöşü])")
# Не после «x»: «2x5 mg», «1x10ml» — множитель, а не слово.
# Только пробел, не перевод строки: «Vitamin B6\nmg\n0.10» — ячейки таблицы PEDIASURE, а не «B 6 mg».
_GLUED_NUMBER = re.compile(r"(?<=[A-WYZÇĞİÖŞÜa-wyzçğıöşü])(?=\d+(?:[.,]\d+)?[ \u00a0]?(?:mg|mcg|ml|mL|mmol)(?![^\W\d_]))")
# Турецкий процент пишется перед числом: «%5», «yüzde 5», «%hacim olarak 11,8»,
# в RU/EN — после: «5%»; диапазон — «%2-5», «%5,75 ila 13,8» и «2-5%», «от 5,75 до 13,8%».
_PERCENT_RE = re.compile(r"(?:%|\byüzde\s)\s*(?:hacim\s+olarak\s+)?(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*%")
_RANGE_SEPARATOR = r"\s*(?:[-–]|\s(?:ila|to|до)\s)\s*"
_PERCENT_RANGE = re.compile(
    rf"%\s*(\d+(?:[.,]\d+)?){_RANGE_SEPARATOR}(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?){_RANGE_SEPARATOR}(\d+(?:[.,]\d+)?)\s*%"
)
_ANY_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

# Соли, ионы и гидраты: в RU/EN другой корень и порядок слов («Sodyum Klorür» →
# «Натрия хлорид»), поэтому при сверке МНН их не сравниваем.
_SALT_WORDS_TR = re.compile(
    r"\b(?:di|tri)?(?:sodyum|potasyum|kalsiyum|magnezyum|lityum|amonyum|demir|cinko|"
    r"klorur|hidroklorur|hidrobromur|bromur|iyodur|florur|maleat|sulfat|fosfat|asetat|"
    r"sitrat|karbonat|bikarbonat|hidrojen|laktat|glukonat|tartarat|fumarat|suksinat|"
    r"mesilat|besilat|tosilat|nitrat|oksit|hidroksit|(?:mono|di|tri|hemi|seski)?hidrat|"
    r"anhidr\w*|asit|tuzu)\b"
)
_SALT_WORDS_RU = re.compile(
    r"\b(?:ди|три)?(?:натри|кали|кальци|магни|лити|аммони|желез|цинк|хлорид|гидрохлорид|"
    r"гидробромид|бромид|иодид|йодид|фторид|малеат|сульфат|фосфат|ацетат|цитрат|карбонат|"
    r"гидрокарбонат|лактат|глюконат|тартрат|фумарат|сукцинат|мезилат|безилат|тозилат|"
    r"нитрат|оксид|гидроксид|(?:моно|ди|три|геми|сескви)?гидрат|безводн|кислот)\w*"
)
_SALT_WORDS_EN = re.compile(
    r"\b(?:di|tri)?(?:sodium|potassium|calcium|magnesium|lithium|ammonium|iron|ferrous|ferric|"
    r"zinc|chloride|hydrochloride|hydrobromide|bromide|iodide|fluoride|maleate|sulfate|"
    r"sulphate|phosphate|acetate|citrate|carbonate|bicarbonate|hydrogen|lactate|gluconate|"
    r"tartrate|fumarate|succinate|mesylate|mesilate|besylate|besilate|tosylate|nitrate|oxide|"
    r"hydroxide|(?:mono|di|tri|hemi|sesqui)?hydrate|anhydrous|acid|salt)\b"
)


# Строки с фирмой и адресом (конец раздела хранения инструкции: «Ruhsat sahibi:
# … İlaç San. ve Tic. A.Ş., … Mah. … Cad. No:4 … İstanbul, Tel: …»). Имена и
# адреса не переводятся и остаются латиницей с турецкими буквами — при проверке
# «перевод не на турецком» такие строки не учитываются.
_PROPER_NAME_LINE = re.compile(
    r"(?:^|\s)(?:ruhsat sahibi|uretim yeri|uretici|imal eden|ithalatci)\b|"
    r"\b(?:a\.\s?s\.?|ltd\.?|sti\.?|tic\.|san\.|gmbh|s\.p\.a\.?|inc\.?|limited|mah\.|mahallesi|"
    r"cad\.|caddesi|cd\.|sok\.|sokak|sk\.|bulvari|blv\.|plaza|osb|organize sanayi|faks|fax|e-?posta|"
    r"posta kodu|ag|srl|llc|corp|pvt|s\.a\.|b\.v\.|n\.v\.|pharma|pharmaceuticals?|laborator\w*)(?=\W|$)|"
    r"\b(?:no|kat|tel)\s*:|"
    # Почтовый индекс адреса фирмы: «(34010) Topkapı - İSTANBUL» (очередь 27.10.2026).
    r"\(\d{5}\)"
)


# Обращение к читателю («bildiriniz», «danışınız») — это текст инструкции, а не реквизиты.
_INSTRUCTION_WORDS = re.compile(r"\w(?:iniz|unuz)\b|\b(?:bildir\w*|kullan\w*|danis\w*|doktor\w*)\b")


def is_proper_name_line(text: Any) -> bool:
    """Строка — название фирмы, адрес или контакты, а не текст инструкции."""
    from apps.ai.services.medicine_reference import fold_tr

    folded = fold_tr(text)
    return (
        len(folded) <= 250
        and not _INSTRUCTION_WORDS.search(folded)
        and bool(_PROPER_NAME_LINE.search(folded))
    )


# Строка — только топоним адреса фирмы: «Bağcılar», «Başakşehir/İstanbul», «Karabağlar - İzmir»;
# одиночная буква или маркер списка источника («ğ», «ç) Пемфигус…»), материал блистера «Alü/Alü»
# (очередь модерации 27.10.2026: 14 разделов «не переведено» из-за таких строк).
_PLACE_LINE = re.compile(r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s*[/-]\s*[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)*\s*[/-]?")
_SOURCE_LIST_MARKER = re.compile(r"^\s*[a-zçğıöşü]\)\s*")
_BLISTER_MATERIAL = re.compile(r"\bAlü\s*/\s*Alü\b|\bAlü\b")


def strip_proper_name_lines(text: Any) -> str:
    """Текст без строк с фирмами/адресами — для проверки языка перевода."""
    lines, previous = [], ""
    for line in str(text or "").splitlines():
        stripped = line.strip()
        # Одно слово без «/» — топоним, только если строкой выше подпись («Место производства:»):
        # иначе это может быть непереведённый пункт списка («Bulantı»).
        place = (
            len(stripped) <= 40
            and _PLACE_LINE.fullmatch(stripped)
            and (re.search(r"[/-]", stripped) or previous.endswith(":"))
        )
        if stripped:
            previous = stripped
        if is_proper_name_line(line) or place or len(re.findall(r"[^\W\d_]", stripped)) <= 1:
            continue
        lines.append(_BLISTER_MATERIAL.sub(" ", _SOURCE_LIST_MARKER.sub("", line)))
    return "\n".join(lines)


def _normalize_number(raw: str) -> str:
    value = re.sub(r"[ \u00a0]", "", raw)
    if re.fullmatch(r"[1-9]\d{0,2}(?:[.,]\d{3})+", value):
        return re.sub(r"[.,]", "", value)
    value = value.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value or "0"


def _unit(raw: str) -> str:
    raw = raw.lower()
    return next((unit for stem, unit in _UNIT_WORDS if re.match(stem, raw)), None) or _UNIT_ALIASES[raw]


def fix_ocr_digits(text: Any) -> str:
    """Опечатки распознанного PDF в числах: «l» вместо «1» рядом с цифрами («l0'unda» → «10'unda»,
    «Bl2» → «B12»), «0.,6», «10. 000», «200 Lig» (``_OCR_FIXES``)."""
    text = _OCR_ONE.sub("1", str(text or ""))
    for pattern, replacement in _OCR_FIXES:
        text = pattern.sub(replacement, text)
    return text


def extract_doses(text: Any) -> set[tuple[str, str]]:
    """Дозировки вида (число, единица) из текста на любом из трёх языков."""
    text = _GLUED_NUMBER.sub(" ", _GLUED_UNIT.sub(r"\1 ", fix_ocr_digits(text)))
    doses = {(_normalize_number(number), _unit(unit)) for number, unit in _DOSE_RE.findall(text)}
    for prefix, suffix in _PERCENT_RE.findall(text):
        doses.add((_normalize_number(prefix or suffix), "%"))
    for match in _PERCENT_RANGE.findall(text):
        doses.update((_normalize_number(number), "%") for number in match if number)
    return doses


def _numbers(text: Any) -> set[str]:
    return {_normalize_number(token) for token in _ANY_NUMBER.findall(fix_ocr_digits(text))}


def _unit_implied(dose: tuple[str, str], doses: set, numbers: set[str]) -> bool:
    """Число есть в другом тексте без единицы, а единица — у его соседней дозы."""
    number, unit = dose
    return number in numbers and any(other_unit == unit for _, other_unit in doses)


def doses_match(source: Any, translation: Any) -> bool:
    """В переводе те же дозировки, что в исходнике: ничего не потеряно и не добавлено.

    Единицу у числа диапазона или перечисления модель дописывает или убирает:
    «günde 750 mg ila 1000» → «от 750 мг до 1000 мг», «200 mg-400 mg» → «200-400 мг»,
    «5 mL biraya veya 2,08 şaraba» → «2,08 мл вина». Это не расхождение, если
    число есть в обоих текстах, а единица — в другой дозе того же текста. То же
    число с другой единицей («500 mcg» → «500 мг») — расхождение всегда.
    """
    source_doses = extract_doses(source) - _PER_UNIT_DOSES
    translated_doses = extract_doses(translation) - _PER_UNIT_DOSES
    missing, extra = source_doses - translated_doses, translated_doses - source_doses
    for number, unit in _PERCENT_DOSE_RE.findall(fix_ocr_digits(source)):
        pair = {(_normalize_number(number), "%"), (_normalize_number(number), _unit(unit))}
        if pair & translated_doses:
            missing -= pair
    if {number for number, _ in missing} & {number for number, _ in extra}:
        return False
    translated_numbers, source_numbers = _numbers(translation), _numbers(source)
    return all(_unit_implied(dose, translated_doses, translated_numbers) for dose in missing) and all(
        _unit_implied(dose, source_doses, source_numbers) for dose in extra
    )


def _latin_letters(value: Any, locale: str) -> str:
    text = str(value or "").lower()
    if locale == "ru":
        try:
            from transliterate import translit

            text = translit(text, "ru", reversed=True)
        except Exception:
            pass
    text = text.translate(str.maketrans("ıçğöşü", "icgosu"))
    return re.sub(r"[^a-z]", "", text)


def inn_matches(source: Any, translation: Any, locale: str) -> bool:
    """МНН в переводе — то же вещество (с поправкой на транслитерацию и соли)."""
    source_text = str(source or "").lower().translate(str.maketrans("ıçğöşü", "icgosu"))
    salt_re = {"ru": _SALT_WORDS_RU, "en": _SALT_WORDS_EN}.get(locale)
    translated_text = str(translation or "").lower()
    if salt_re is not None:
        source_text = _SALT_WORDS_TR.sub(" ", source_text)
        translated_text = salt_re.sub(" ", translated_text)
    source_letters = _latin_letters(source_text, "tr")
    translated_letters = _latin_letters(translated_text, locale)
    if not source_letters or not translated_letters:
        return True
    return SequenceMatcher(None, source_letters, translated_letters).ratio() >= 0.6
