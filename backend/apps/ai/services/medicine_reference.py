"""Справочные поля лекарств: перевод RU/EN кодом, без LLM.

Значения полей MedicineProduct (лекарственная форма, путь введения, тип
рецепта, условия хранения, SGK, происхождение, срок годности, объём) — это
небольшие справочники ilacfiyati. Их переводит словарь; модель эти поля не
генерирует и сверка фактов их не проверяет. Неизвестное значение не
переводится (на сайте остаётся исходник) и попадает в отчёт
``medicine_reference_coverage``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

# Поля, которые заполняет только код (модель их не возвращает).
CODE_FIELDS = (
    "dosage_form",
    "administration_route",
    "prescription_type",
    "storage_conditions",
    "sgk_status",
    "origin_country",
    "shelf_life",
    "volume",
)

_TR_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i", "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})


def fold_tr(value: Any) -> str:
    """Турецкий текст → нижний регистр ASCII с одинарными пробелами."""
    text = unicodedata.normalize("NFC", str(value or "")).translate(_TR_FOLD).lower()
    text = text.replace("̇", "")
    return re.sub(r"\s+", " ", text).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", fold_tr(value))


def ru_plural(number: Any, one: str, few: str, many: str) -> str:
    text = str(number).replace(",", ".")
    if not re.fullmatch(r"\d+", text):
        return few  # дробное: «2,5 таблетки»
    n = int(text)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


# ── Лекарственная форма: код MedicineProduct.dosage_form → подпись ≤ 20 символов.
DOSAGE_FORM_LABELS = {
    "tablet": ("Таблетки", "Tablets"),
    "capsule": ("Капсулы", "Capsules"),
    "syrup": ("Сироп", "Syrup"),
    "drops": ("Капли", "Drops"),
    "ointment": ("Мазь", "Ointment"),
    "cream": ("Крем", "Cream"),
    "gel": ("Гель", "Gel"),
    "injection": ("Инъекции", "Injection"),
    "powder": ("Порошок", "Powder"),
    "spray": ("Спрей", "Spray"),
    "suppository": ("Суппозитории", "Suppositories"),
}


def dosage_form_labels(locale: str) -> set[str]:
    index = 0 if locale == "ru" else 1
    return {labels[index] for labels in DOSAGE_FORM_LABELS.values()}


# ── Тип рецепта. Цвет турецкого бланка («белый рецепт») покупателю из России
# ничего не говорит: белый — обычный рецептурный препарат; красный, зелёный,
# оранжевый, фиолетовый — препараты строгого учёта. Формулировки нейтральные:
# на сайте лекарства не продаются.
_RX_CONTROLLED = ("рецептурный препарат строгого учёта", "controlled prescription medicine")
PRESCRIPTION_TYPES = {
    "beyazrecete": ("рецептурный препарат", "prescription medicine"),
    "normalrecete": ("рецептурный препарат", "prescription medicine"),
    "kisitlanmisbeyazrecete": (
        "рецептурный препарат с ограничением назначения", "restricted prescription medicine"
    ),
    "yesilrecete": _RX_CONTROLLED,
    "morrecete": _RX_CONTROLLED,
    "turuncurecete": _RX_CONTROLLED,
    "kirmizirecete": _RX_CONTROLLED,
    "kontroletabirecete": _RX_CONTROLLED,
    "recetesiz": ("безрецептурный препарат", "over-the-counter medicine"),
}
# Цвет рецепта в тексте модели («отпускается по белому рецепту») — убирается кодом.
_RX_COLOR_RE = re.compile(
    r"\b(?:(?:обычн|бел|красн|зел[её]н|оранжев|фиолетов)(?:ый|ого|ому|ым|ом|ая|ой|ую|ые|ых|ыми)"
    r"\s+(рецепт)|(?:white|red|green|orange|purple|normal|regular)\s+(prescription))",
    re.IGNORECASE,
)


def neutral_prescription_text(text: Any) -> Any:
    """«по белому рецепту» → «по рецепту», «a white prescription» → «a prescription»."""
    if not isinstance(text, str):
        return text

    def drop_color(match: re.Match) -> str:
        word = match.group(1) or match.group(2)
        return word[:1].upper() + word[1:] if match.group(0)[0].isupper() else word.lower()

    return _RX_COLOR_RE.sub(drop_color, text)


# Справочные поля, которые в описании карточки — шум для покупателя (Haiku 25.10.2026 писал их
# в 44 описаниях из 46): страховка SGK, срок годности, страна и производство, импорт.
_BOILERPLATE_SENTENCE_RE = re.compile(
    r"SGK|страхов|insurance|reimburs|covered by|срок\w* годност|shelf[ -]life|"
    r"произвед[её]н|производ\w*|manufactur|produced in|made in|импортн|imported|"
    r"страна происхождения|country of origin|Турци[яи]|Turkey|Turkish",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r",\s+(?![^()]*\))")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ0-9«\"(])")


def without_card_boilerplate(text: Any) -> Any:
    """Описание карточки без SGK, срока годности, страны и производства.

    Убирается часть предложения между запятыми, где они упомянуты («…, производства X (Турция).»),
    а если в предложении ничего не осталось — всё предложение. Если убирать нечего или
    после этого пусто — текст как есть.
    """
    if not isinstance(text, str) or not _BOILERPLATE_SENTENCE_RE.search(text):
        return text
    kept = []
    for sentence in _SENTENCE_SPLIT_RE.split(text.strip()):
        if not _BOILERPLATE_SENTENCE_RE.search(sentence):
            kept.append(sentence)
            continue
        end = sentence[-1] if sentence[-1:] in ".!?" else ""
        clauses = [c for c in _CLAUSE_SPLIT_RE.split(sentence.rstrip(".!? ")) if not _BOILERPLATE_SENTENCE_RE.search(c)]
        if clauses:
            joined = ", ".join(clauses)
            joined = joined[:1].upper() + joined[1:]  # убрано начало предложения
            kept.append(joined + ("" if joined[-1:] in ".!?" else end))
    return " ".join(kept) if kept else text


# ── Особые сведения: бейджи «ÖZEL BİLGİLER» ilacfiyati. У части бейджей на
# самом сайте нет предмета: с чем «не применять совместно», в чём «осторожность»,
# чего «не использовать, пока не известна чувствительность» (это про транспорт).
# В карточку такие фразы не переводятся.
_CONTEXT_FREE_NOTES = frozenset({
    "birlikte kullanilmamalidir",
    "dikkatli olunmalidir",
    "hastalar duyarliliklari belli oluncaya kadar kullanmamalidir",
})
_NOTE_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*(?:\([^)]*\))?")


def meaningful_special_notes(value: Any) -> str:
    """Особые сведения источника без фраз, в которых не сказано, о чём речь."""
    sentences = [s.strip() for s in _NOTE_SENTENCE_RE.findall(str(value or "")) if s.strip()]
    return " ".join(
        sentence
        for sentence in sentences
        if re.sub(r"[^a-z ]", "", fold_tr(sentence)).strip() not in _CONTEXT_FREE_NOTES
    )


# Бейджи ilacfiyati — конечный набор фраз (логи 24–26.10.2026: 45 разных предложений, частые —
# ниже). Переводятся кодом: модель оставляла турецкий текст рядом с переводом («Ek izlemeye
# tabi ilaç! — Препарат подлежит…», «(Alternatif Geri Ödeme Kapsamındadır)») — 46 логов в
# модерации 26.10.2026. Ключ — fold_tr без знаков; {n} — число, {unit} — срок, {gen} — срок
# после «не менее» (_NOTE_UNITS: винительный, родительный единственного и множественного).
_NOTE_UNITS = {
    "saat": (("час", "часа", "часов"), ("часа", "часов"), ("hour", "hours")),
    "gun": (("день", "дня", "дней"), ("дня", "дней"), ("day", "days")),
    "hafta": (("неделю", "недели", "недель"), ("недели", "недель"), ("week", "weeks")),
    "ay": (("месяц", "месяца", "месяцев"), ("месяца", "месяцев"), ("month", "months")),
}
_N, _U = r"(?P<n>\d+)", r"(?P<unit>saat|gun|hafta|ay)"
SPECIAL_NOTE_PHRASES = (
    (r"tedavi suresince emzirmemesi onerilir kullanilmamalidir",
     "Кормить грудью во время лечения не рекомендуется.", "Breastfeeding is not recommended during treatment."),
    (r"ek izlemeye tabi ilac", "Препарат подлежит дополнительному мониторингу.",
     "This medicine is subject to additional monitoring."),
    (r"dikkatli kullanilmalidir", "Применять с осторожностью.", "Use with caution."),
    (r"yuksek riskli ilac", "Препарат высокого риска.", "High-risk medicine."),
    (r"laktasyon doneminde kullanilmamalidir", "Не применять в период грудного вскармливания.",
     "Do not use while breastfeeding."),
    (r"arac ve makine kullanilmamalidir", "Не управлять транспортными средствами и механизмами.",
     "Do not drive or operate machinery."),
    (r"laktasyon doneminde kullanim bilgisi icin kub e bakiniz",
     "О применении в период грудного вскармливания — в общей характеристике препарата.",
     "For use while breastfeeding, see the Summary of Product Characteristics."),
    (r"kullanilmadan once doktora danisilmasi gerekmektedir",
     "Перед применением необходимо проконсультироваться с врачом.", "Consult a doctor before use."),
    (r"zorunlu olmadikca kullanilmamalidir", "Не применять без крайней необходимости.",
     "Do not use unless clearly necessary."),
    (r"arac veya makine kullanilmadan once gorme bulanikligi duzelinceye kadar beklenmelidir",
     "Перед управлением транспортом и механизмами дождитесь, пока пройдёт нечёткость зрения.",
     "Wait until blurred vision clears before driving or operating machinery."),
    (r"kullanmadan once calkalayiniz", "Перед применением взболтать.", "Shake before use."),
    (r"alternatif geri odeme kapsamindadir", "Входит в альтернативную схему возмещения SGK.",
     "Covered by the SGK alternative reimbursement scheme."),
    (r"hastanelerce temini zorunlu kemoterapi ilaci",
     "Химиотерапевтический препарат, поставляется только через больницы.",
     "Chemotherapy medicine supplied only through hospitals."),
    (r"bu mustahzar kontrollu dagitim kapsamindadir", "Препарат отпускается в рамках контролируемого распространения.",
     "This medicine is subject to controlled distribution."),
    (r"vucuttan atilmasina kadar gecen 2 3 gun emzirmeye ara verilmelidir",
     "Прервать грудное вскармливание на 2–3 дня, пока препарат не выведется из организма.",
     "Stop breastfeeding for 2–3 days until the medicine is eliminated from the body."),
    (rf"uygulamadan sonra {_N} {_U} sureyle emzirilmemelidir",
     "Не кормить грудью {n} {unit} после введения.", "Do not breastfeed for {n} {unit} after administration."),
    (rf"tedavi suresince ve son dozdan sonraki {_N} {_U} suresince emzirmemelidir",
     "Не кормить грудью во время лечения и {n} {unit} после последней дозы.",
     "Do not breastfeed during treatment and for {n} {unit} after the last dose."),
    (rf"tedavi sirasinda ve tedaviden sonraki en az {_N} {_U} boyunca emzirilmemelidir",
     "Не кормить грудью во время лечения и не менее {n} {gen} после него.",
     "Do not breastfeed during treatment and for at least {n} {unit} afterwards."),
    (rf"tedavi sirasinda ve tedaviden sonraki {_N} {_U} (?:boyunca|suresince) emzirilmemelidir",
     "Не кормить грудью во время лечения и {n} {unit} после него.",
     "Do not breastfeed during treatment and for {n} {unit} afterwards."),
    (rf"tedavi sirasinda ve tedavinin bitmesinden sonraki {_N} {_U} boyunca emzirilmemelidir",
     "Не кормить грудью во время лечения и {n} {unit} после его окончания.",
     "Do not breastfeed during treatment and for {n} {unit} after it ends."),
    (rf"ilac kullanirken ve ilac kesildikten sonra en az {_N} {_U} boyunca alkol alinmamalidir",
     "Не употреблять алкоголь во время лечения и не менее {n} {gen} после отмены препарата.",
     "Do not drink alcohol during treatment and for at least {n} {unit} after stopping it."),
    (rf"ilac aldiktan sonra en az {_N} {_U} gecmeden emzirilmemelidir",
     "Не кормить грудью не менее {n} {gen} после приёма.",
     "Do not breastfeed for at least {n} {unit} after taking the medicine."),
)
_SPECIAL_NOTE_RES = tuple((re.compile(pattern + r"\b\s*"), ru, en) for pattern, ru, en in SPECIAL_NOTE_PHRASES)


def translate_special_notes(value: Any) -> Optional[tuple[str, str]]:
    """(RU, EN) особых сведений по словарю бейджей или None, если есть незнакомая фраза."""
    text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", fold_tr(meaningful_special_notes(value)))).strip()
    ru: list[str] = []
    en: list[str] = []
    while text:
        for pattern, note_ru, note_en in _SPECIAL_NOTE_RES:
            match = pattern.match(text)
            if match:
                break
        else:
            return None
        values = match.groupdict()
        if values.get("n"):
            number = values["n"]
            ru_forms, gen_forms, en_forms = _NOTE_UNITS[values["unit"]]
            single = ru_plural(number, "one", "few", "many") == "one"
            note_ru = note_ru.format(
                n=number, unit=ru_plural(number, *ru_forms), gen=gen_forms[0] if single else gen_forms[1]
            )
            note_en = note_en.format(n=number, unit=en_forms[0] if number == "1" else en_forms[1])
        ru.append(note_ru)
        en.append(note_en)
        text = text[match.end():]
    return (" ".join(ru), " ".join(en)) if ru else None


SGK_STATUSES = {
    "bedeliodenir": ("оплачивается SGK", "covered by SGK"),
    "bedeliodenmez": ("не оплачивается SGK", "not covered by SGK"),
}

ORIGINS = {
    "imal": ("произведено в Турции", "manufactured in Turkey"),
    "yerli": ("произведено в Турции", "manufactured in Turkey"),
    "ithal": ("импортный", "imported"),
}

# ── Путь введения: отдельные термины; составные значения делятся по «,», «/», «ve».
ROUTES = {
    "oral": ("перорально", "oral"),
    "agizdan": ("перорально", "oral"),
    "intravenoz": ("внутривенно", "intravenous"),
    "iv": ("внутривенно", "intravenous"),
    "intravenozinfuzyon": ("внутривенно капельно", "intravenous infusion"),
    "infuzyon": ("инфузионно", "infusion"),
    "perfuzyon": ("инфузионно", "infusion"),
    "intramuskuler": ("внутримышечно", "intramuscular"),
    "im": ("внутримышечно", "intramuscular"),
    "subkutan": ("подкожно", "subcutaneous"),
    "subkutanoz": ("подкожно", "subcutaneous"),
    "sc": ("подкожно", "subcutaneous"),
    "derialti": ("подкожно", "subcutaneous"),
    "intradermal": ("внутрикожно", "intradermal"),
    "topikal": ("местно", "topical"),
    "lokal": ("местно", "local"),
    "haricen": ("наружно", "external use"),
    "harici": ("наружно", "external use"),
    "dermal": ("на кожу", "cutaneous"),
    "kutan": ("на кожу", "cutaneous"),
    "kutanoz": ("на кожу", "cutaneous"),
    "deriuzerine": ("на кожу", "cutaneous"),
    "transdermal": ("трансдермально", "transdermal"),
    "perkutan": ("чрескожно", "percutaneous"),
    "rektal": ("ректально", "rectal"),
    "vajinal": ("вагинально", "vaginal"),
    "oftalmik": ("в глаза", "ophthalmic"),
    "okuler": ("в глаза", "ocular"),
    "goze": ("в глаза", "ophthalmic"),
    "goz": ("в глаза", "ophthalmic"),
    "nazal": ("интраназально", "nasal"),
    "burundan": ("интраназально", "nasal"),
    "burunici": ("интраназально", "nasal"),
    "inhalasyon": ("ингаляционно", "inhalation"),
    "inhaler": ("ингаляционно", "inhalation"),
    "solunumyoluyla": ("ингаляционно", "inhalation"),
    "pulmoner": ("ингаляционно", "pulmonary"),
    "sublingual": ("сублингвально", "sublingual"),
    "dilalti": ("сублингвально", "sublingual"),
    "bukkal": ("буккально", "buccal"),
    "oromukozal": ("на слизистую полости рта", "oromucosal"),
    "agizici": ("на слизистую полости рта", "oromucosal"),
    "agizboslugu": ("на слизистую полости рта", "oromucosal"),
    "mukozal": ("на слизистые", "mucosal"),
    "dental": ("стоматологически", "dental"),
    "gingival": ("на дёсны", "gingival"),
    "periodontal": ("пародонтально", "periodontal"),
    "otik": ("в ухо", "otic"),
    "kulaga": ("в ухо", "otic"),
    "kulak": ("в ухо", "otic"),
    "aurikuler": ("в ухо", "auricular"),
    "intravitreal": ("интравитреально", "intravitreal"),
    "intraokuler": ("внутриглазно", "intraocular"),
    "intrakameral": ("внутрикамерно", "intracameral"),
    "subkonjonktival": ("субконъюнктивально", "subconjunctival"),
    "retrobulber": ("ретробульбарно", "retrobulbar"),
    "intraartikuler": ("внутрисуставно", "intra-articular"),
    "periartikuler": ("периартикулярно", "periarticular"),
    "intrasinovyal": ("внутрисуставно", "intrasynovial"),
    "intrabursal": ("внутрисумочно", "intrabursal"),
    "intratekal": ("интратекально", "intrathecal"),
    "epidural": ("эпидурально", "epidural"),
    "intravezikal": ("внутрипузырно", "intravesical"),
    "intrakaviter": ("внутриполостно", "intracavitary"),
    "intralezyonel": ("внутриочагово", "intralesional"),
    "intralezyonal": ("внутриочагово", "intralesional"),
    "perinoral": ("периневрально", "perineural"),
    "infiltrasyon": ("инфильтрационно", "infiltration"),
    "intrakardiyak": ("внутрисердечно", "intracardiac"),
    "intraarteriyel": ("внутриартериально", "intra-arterial"),
    "intraarteryel": ("внутриартериально", "intra-arterial"),
    "intraarteriel": ("внутриартериально", "intra-arterial"),
    "intrakoroner": ("интракоронарно", "intracoronary"),
    "intraperitoneal": ("внутрибрюшинно", "intraperitoneal"),
    "intraplevral": ("внутриплеврально", "intrapleural"),
    "intraosseoz": ("внутрикостно", "intraosseous"),
    "intrauterin": ("внутриматочно", "intrauterine"),
    "intrakavernoz": ("интракавернозно", "intracavernous"),
    "intraventrikuler": ("интравентрикулярно", "intraventricular"),
    "intratumoral": ("внутриопухолево", "intratumoral"),
    "intralenfatik": ("внутрилимфатически", "intralymphatic"),
    "endotrakeal": ("эндотрахеально", "endotracheal"),
    "endotrakeopulmoner": ("эндотрахеально", "endotracheopulmonary"),
    "uretral": ("уретрально", "urethral"),
    "parenteral": ("парентерально", "parenteral"),
    "enteral": ("энтерально", "enteral"),
    "nazogastrik": ("через назогастральный зонд", "nasogastric"),
    "hemodiyaliz": ("при гемодиализе", "haemodialysis"),
    "ekstrakorporeal": ("экстракорпорально", "extracorporeal"),
    "enjeksiyon": ("инъекционно", "injection"),
    "sistemik": ("системно", "systemic"),
}

# ── Срок годности: «24 Ay» → «24 месяца».
_PERIODS = {
    "ay": (("месяц", "месяца", "месяцев"), ("month", "months")),
    "yil": (("год", "года", "лет"), ("year", "years")),
    "gun": (("день", "дня", "дней"), ("day", "days")),
    "hafta": (("неделя", "недели", "недель"), ("week", "weeks")),
}

# ── Условия хранения: признаки в тексте → фразы RU/EN.
_PROTECT_FROM = (
    (r"isik", "света", "light"),
    (r"nem", "влаги", "moisture"),
)
_STORAGE_RULES = (
    (r"buzdolab|\b2\s*-\s*8\b|\+2\s*-\s*\+8", "хранить в холодильнике (2–8 °C)", "store in a refrigerator (2–8 °C)"),
    (r"soguk zincir", "соблюдать холодовую цепь", "keep the cold chain"),
    (r"dondurucu", "хранить в морозильной камере", "store in a freezer"),
    (r"dondurulma|dondurmay", "не замораживать", "do not freeze"),
    (r"oda sicakl", "хранить при комнатной температуре", "store at room temperature"),
)
_STORAGE_TEMP_BELOW = re.compile(r"(\d+)\s*(?:°\s*c|derece|c)?\s*(?:['’]?\s*n?[iu]n)?\s*alt\w*")
# Служебные слова: после разбора значение должно состоять только из них.
_STORAGE_FILLER = re.compile(
    r"\b(?:koru\w*|gerek\w*|sakla\w*|ortam\w*|yer\w*|alt\w*|derece\w*|sicakl\w*|"
    r"isik\w*|nem\w*|buzdolab\w*|dondur\w*|soguk|zincir\w*|oda|ve|ile|veya|arasi\w*|c)\b"
)


def _lookup(table: dict, value: Any) -> Optional[tuple[str, str]]:
    return table.get(_key(value))


def _translate_parts(table: dict, value: Any) -> Optional[tuple[str, str]]:
    """Целое значение по словарю, иначе — по частям через «,», «/», «;», «+», «ve»."""
    found = _lookup(table, value)
    if found:
        return found
    text = re.sub(r"\(([^)]*)\)", r" \1 ", str(value or ""))
    parts = [p for p in re.split(r"[,/;+&]|\s(?:ve|veya|and)\s", text, flags=re.IGNORECASE) if p.strip()]
    if len(parts) < 2:
        return None
    ru: list[str] = []
    en: list[str] = []
    for part in parts:
        found = _lookup(table, part)
        if not found:
            return None
        if found[0] not in ru:
            ru.append(found[0])
            en.append(found[1])
    return ", ".join(ru), ", ".join(en)


def translate_shelf_life(value: Any) -> Optional[tuple[str, str]]:
    match = re.fullmatch(r"(\d+)\s*(ay|yil|gun|hafta)", fold_tr(value))
    if not match:
        return None
    number, unit = match.groups()
    ru_forms, en_forms = _PERIODS[unit]
    en_word = en_forms[0] if number == "1" else en_forms[1]
    return f"{number} {ru_plural(number, *ru_forms)}", f"{number} {en_word}"


def translate_storage(value: Any) -> Optional[tuple[str, str]]:
    text = fold_tr(value)
    if not text:
        return None
    ru: list[str] = []
    en: list[str] = []
    protect = [(ru_word, en_word) for pattern, ru_word, en_word in _PROTECT_FROM if re.search(pattern, text)]
    if protect:
        ru.append("хранить в защищённом от " + " и ".join(p[0] for p in protect) + " месте")
        en.append("protect from " + " and ".join(p[1] for p in protect))
    for pattern, ru_phrase, en_phrase in _STORAGE_RULES:
        if re.search(pattern, text):
            ru.append(ru_phrase)
            en.append(en_phrase)
    rest = text
    below = _STORAGE_TEMP_BELOW.search(text)
    if below:
        ru.append(f"хранить при температуре ниже {below.group(1)} °C")
        en.append(f"store below {below.group(1)} °C")
        rest = rest.replace(below.group(0), " ")
    rest = re.sub(r"\b2\s*-\s*8\b|\+2\s*-\s*\+8|[°'’.,;:()+\-]", " ", rest)
    rest = _STORAGE_FILLER.sub(" ", rest).strip()
    if not ru or rest:
        return None
    return _capitalize("; ".join(ru)), _capitalize("; ".join(en))


# ── Объём / фасовка.
_COUNT_UNITS = {
    # ключ → (RU-формы, EN ед./мн.)
    "tablet": (("таблетка", "таблетки", "таблеток"), ("tablet", "tablets")),
    "capsule": (("капсула", "капсулы", "капсул"), ("capsule", "capsules")),
    "suppository": (("суппозиторий", "суппозитория", "суппозиториев"), ("suppository", "suppositories")),
    "ampoule": (("ампула", "ампулы", "ампул"), ("ampoule", "ampoules")),
    "vial": (("флакон", "флакона", "флаконов"), ("vial", "vials")),
    "sachet": (("саше", "саше", "саше"), ("sachet", "sachets")),
    "dose": (("доза", "дозы", "доз"), ("dose", "doses")),
    "tube": (("туба", "тубы", "туб"), ("tube", "tubes")),
    "syringe": (("шприц", "шприца", "шприцев"), ("syringe", "syringes")),
    "pen": (("шприц-ручка", "шприц-ручки", "шприц-ручек"), ("pen", "pens")),
    "patch": (("пластырь", "пластыря", "пластырей"), ("patch", "patches")),
    "lozenge": (("пастилка", "пастилки", "пастилок"), ("lozenge", "lozenges")),
    "box": (("упаковка", "упаковки", "упаковок"), ("box", "boxes")),
    "blister": (("блистер", "блистера", "блистеров"), ("blister", "blisters")),
    "cartridge": (("картридж", "картриджа", "картриджей"), ("cartridge", "cartridges")),
    "piece": (("шт.", "шт.", "шт."), ("pc", "pcs")),
    "ml": (("мл", "мл", "мл"), ("ml", "ml")),
    "g": (("г", "г", "г"), ("g", "g")),
}
# Турецкие единицы фасовки (после fold_tr) → ключ _COUNT_UNITS.
_UNIT_WORDS = {
    "tablet": "tablet", "tableti": "tablet", "tb": "tablet", "tab": "tablet",
    "kapsul": "capsule", "kap": "capsule",
    "supozituar": "suppository", "fitil": "suppository", "ovul": "suppository",
    "ampul": "ampoule", "flakon": "vial", "sise": "vial",
    "sase": "sachet", "poset": "sachet", "doz": "dose", "puskurtme": "dose",
    "tup": "tube", "enjektor": "syringe", "kalem": "pen", "flaster": "patch", "bant": "patch",
    "pastil": "lozenge", "adet": "piece",
    "ml": "ml", "g": "g", "gr": "g", "gram": "g",
}
_FORM_COUNT_UNIT = {"tablet": "tablet", "capsule": "capsule", "suppository": "suppository"}


def _format_count(number: str, unit: str) -> tuple[str, str]:
    ru_forms, en_forms = _COUNT_UNITS[unit]
    number_ru = number.replace(".", ",")
    number_en = number.replace(",", ".")
    en_word = en_forms[0] if number_en == "1" else en_forms[1]
    return f"{number_ru} {ru_plural(number_en, *ru_forms)}", f"{number_en} {en_word}"


_STRENGTH_WORDS = {"mg", "mcg", "mkg", "iu", "ui", "mmol", "meq", "u"}


def _unit_from_name(number: str, name: Any) -> Optional[str]:
    """Единица фасовки из названия: «15 FILM TABLET», «10 AMPUL», «150 ML».

    «20 MG …» — дозировка, а не фасовка; штучная единица важнее мл/г
    («1 G IM/IV 1 FLAKON» с фасовкой 1 → флакон).
    """
    num = re.escape(number)
    volume_unit = None
    for match in re.finditer(
        rf"(?<![\d.,]){num}(?![\d.,])\s*([a-z]+(?:\s+[a-z]+){{0,2}})", fold_tr(name)
    ):
        words = match.group(1).split()
        if words[0] in _STRENGTH_WORDS:
            continue
        for word in words:
            unit = _UNIT_WORDS.get(word)
            if unit in ("ml", "g"):
                if word == words[0]:
                    volume_unit = volume_unit or unit
                break
            if unit:
                return unit
    return volume_unit


def translate_volume(
    volume: Any,
    *,
    dosage_form: Any = None,
    name: Any = None,
) -> Optional[tuple[str, str]]:
    """Число из источника + единица по названию или лекарственной форме."""
    text = fold_tr(volume)
    if not text:
        return None
    multi = re.fullmatch(r"(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(ml|g|gr)", text)
    if multi:
        count, size, unit = multi.groups()
        size_ru, size_en = _format_count(size, _UNIT_WORDS[unit])
        return f"{count} шт. по {size_ru}", f"{count} × {size_en}"
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([a-z]+)?\.?", text)
    if not match:
        return None
    number, unit_word = match.groups()
    if unit_word:
        unit = _UNIT_WORDS.get(unit_word)
        if unit is None:
            return None
    else:
        named = re.search(rf"(?<!\d){re.escape(number)}\s*x\s*(\d+(?:[.,]\d+)?)\s*(ml|g|gr)\b", fold_tr(name))
        if named:
            return translate_volume(f"{number}x{named.group(1)} {named.group(2)}")
        unit = (
            _unit_from_name(number, name)
            or _FORM_COUNT_UNIT.get(str(dosage_form or ""))
            or "piece"
        )
    return _format_count(number, unit)


def translate_reference_field(field: str, value: Any, input_data: Optional[dict] = None) -> Optional[tuple[str, str]]:
    """(RU, EN) для справочного поля или None, если значение неизвестно."""
    if value in (None, "") or not str(value).strip() or str(value).strip() == "-":
        return None
    input_data = input_data or {}
    if field == "dosage_form":
        return DOSAGE_FORM_LABELS.get(str(value).strip().lower())
    if field == "administration_route":
        found = _translate_parts(ROUTES, value)
        return (_capitalize(found[0]), _capitalize(found[1])) if found else None
    if field == "prescription_type":
        found = _translate_parts(PRESCRIPTION_TYPES, value)
        return (_capitalize(found[0]), _capitalize(found[1])) if found else None
    if field == "sgk_status":
        found = _lookup(SGK_STATUSES, value)
        return (_capitalize(found[0]), _capitalize(found[1])) if found else None
    if field == "origin_country":
        found = _lookup(ORIGINS, value)
        return (_capitalize(found[0]), _capitalize(found[1])) if found else None
    if field == "shelf_life":
        return translate_shelf_life(value)
    if field == "storage_conditions":
        return translate_storage(value)
    if field == "volume":
        return translate_volume(
            value,
            dosage_form=input_data.get("dosage_form"),
            name=input_data.get("name"),
        )
    return None


def build_reference_translations(input_data: dict) -> tuple[dict, dict, dict]:
    """Переводы всех справочных полей товара: (ru, en, неизвестные значения)."""
    ru: dict[str, str] = {}
    en: dict[str, str] = {}
    unknown: dict[str, str] = {}
    for field in CODE_FIELDS:
        value = input_data.get(field)
        if value in (None, "") or str(value).strip() in ("", "-"):
            continue
        if field == "dosage_form" and str(value).strip().lower() == "other":
            continue
        found = translate_reference_field(field, value, input_data)
        if found:
            ru[field], en[field] = found
        else:
            unknown[field] = str(value)
    # Особые сведения модель тоже переводит; известные бейджи кодом заменяют её перевод.
    notes = translate_special_notes(input_data.get("special_notes"))
    if notes:
        ru["special_notes"], en["special_notes"] = notes
    return ru, en, unknown
