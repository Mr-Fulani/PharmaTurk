"""Сверка перевода абзаца инструкции с турецким исходником без LLM.

Пакетный перевод (десятки абзацев в одном JSON) иногда сдвигает ответы:
ключу «5» достаётся перевод абзаца «6» и так до конца запроса. Проверки
дозировок такое не видят, если в абзацах нет чисел с единицами. В памяти
``medicine_paragraph`` 20.10.2026 так испорчено около 21 % записей
(«Papiller nekroz» → «Храните при температуре ниже 25°C»).

Сравниваются признаки, которые переживают перевод: все числа, медицинские
понятия по словарю TR/RU/EN, длина (модель Гейла–Чёрча), номер заголовка,
частота побочного эффекта, метка {BRAND} и знак в конце абзаца.

- ``item_problems`` — правила для одного абзаца (входят в ``paragraph_problems``);
- ``restore_heading`` — номер «N.» шага или раздела, который модель потеряла, ставится кодом;
- ``request_shift`` — сдвиг внутри одного ответа модели: перевод ближе к
  соседнему исходнику, чем к своему; отбрасывается цепочка таких абзацев;
- ``audit_sequence`` — то же для записей памяти в порядке pk (команда
  ``medicine_paragraph_audit``).

Пороги подобраны по выгрузке памяти 20.10.2026 (270 945 записей) и ручной
разметке 120 случайных записей; цифры — в docs/MEDICINE_PARAGRAPH_SHIFT_2026-10-20.md.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional, Sequence

from apps.ai.services.medicine_fact_check import _normalize_number, fix_ocr_digits

_BRAND = "{BRAND}"  # medicine_memory.BRAND_TOKEN

# ── Числа ─────────────────────────────────────────────────────────────────

_NUMBER_WORDS = {
    "tr": {
        "iki": 2, "ikinci": 2, "üç": 3, "üçüncü": 3, "dört": 4, "dördüncü": 4, "beş": 5, "yedi": 7,
        "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60,
        "yetmiş": 70, "seksen": 80, "doksan": 90, "yüz": 100, "bin": 1000,
        # «3 blisterde onar pastil» — «по 10 пастилок».
        "ikişer": 2, "üçer": 3, "dörder": 4, "beşer": 5, "altışar": 6, "yedişer": 7, "sekizer": 8, "onar": 10,
    },
    "ru": {
        "два": 2, "две": 2, "двух": 2, "двум": 2, "двумя": 2, "дважды": 2,
        "три": 3, "трех": 3, "трёх": 3, "трем": 3, "трём": 3, "тремя": 3, "трижды": 3,
        "четыре": 4, "четырех": 4, "четырёх": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
        "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
        "десять": 10, "десяти": 10, "двенадцать": 12, "двенадцати": 12,
        "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30,
        "второй": 2, "второго": 2, "второму": 2, "вторым": 2, "второе": 2, "вторая": 2, "вторую": 2,
        "третий": 3, "третьего": 3, "третьей": 3, "третье": 3, "третья": 3, "третью": 3,
        "четвертый": 4, "четвёртый": 4, "четвертого": 4, "четвёртого": 4, "четвертой": 4, "четвёртой": 4,
        "четвертая": 4, "четвёртая": 4, "четвертую": 4, "четвёртую": 4,
        "втором": 2, "третьем": 3, "четвертом": 4, "четвёртом": 4,
        "сто": 100, "тысяча": 1000, "тысячи": 1000, "тысяч": 1000,
    },
    "en": {
        "two": 2, "twice": 2, "three": 3, "thrice": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20, "thirty": 30,
        "second": 2, "third": 3, "fourth": 4, "hundred": 100, "thousand": 1000,
    },
}
# «on bin» = 10 000: составные числа частот («10 000 hastanın birinde»);
# «ilk 3 aylık dönem» модель переводит «первый триместр», «2 kat artış» —
# «двукратное увеличение», «trisiklik (Kimyasal yapılarında 3 halka bulunan)» —
# «трициклические», «12 parmak bağırsağı» — «двенадцатиперстная кишка»,
# «24 saatte 4 tablet» — «4 таблетки в сутки».
_NUMBER_PHRASES = {
    "tr": ((r"\bon bin\b", "10000"),),
    "ru": (
        (r"\bдесят[ьи] тысяч\b", "10000"), (r"триместр", "3"), (r"двукратн", "2"), (r"тр[её]хкратн", "3"),
        (r"четыр[её]хкратн", "4"), (r"трицикл", "3"), (r"двенадцатиперстн|дуоден", "12"), (r"\bсут(?:ки|ок)\b", "24"),
    ),
    "en": (
        (r"\bten thousand\b", "10000"), (r"trimester", "3"), (r"twofold", "2"), (r"threefold", "3"), (r"fourfold", "4"),
        (r"tricycl", "3"), (r"duoden", "12"),
    ),
}
# «yetmiş beş» = 75: десятки и единицы словами («Yetmiş beş yaşın üzerinde» → «старше 75 лет»).
_TENS_TR = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
_UNITS_TR = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
# «IV» не переводим: так пишут «внутривенно» (İ.V. → IV).
_ROMAN = {"II": "2", "III": "3", "VI": "6", "VII": "7", "VIII": "8", "IX": "9", "XII": "12"}
# «anjiyotensin IIantagonistleri», «faktör IXartışı» — пробел потерян исходником.
_ROMAN_RE = re.compile(r"\b(?:II|III|VI|VII|VIII|IX|XII)(?![A-ZÇĞİÖŞÜ\d])(?=\b|[a-zçğıöşü])")
_FRACTIONS = str.maketrans({"½": " 1/2 ", "¼": " 1/4 ", "¾": " 3/4 ", "⅓": " 1/3 ", "⅔": " 2/3 "})
# «1 000», «10 000 000» — пробел как разделитель тысяч (так пишет RU).
_SPACED_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![\d.,]?\d)")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# Телефон («0 800 314 00 08», «O 800 314 00 08», «800 314 00 08», «0800 314 00 08») модель
# пишет по-разному — сравнивается одним числом с ведущим нулём.
_PHONE = re.compile(
    r"(?:(?<!\d)0|(?<!\w)O)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"
    r"|(?<![\w.,])\d{3}[\s-]\d{3}[\s-]\d{2}[\s-]\d{2}(?!\d)"
)
# Время: «20.00» в исходнике — «20:00» в переводе; не соотношение «1:50».
_TIME_COLON = re.compile(r"(?<=\b\d{2}):(?=\d{2}(?!\d))")
# Площадь: «39 cm2», «600 cm 2», «1,73 m2» — в переводе «см²», «м²».
_SQUARE = re.compile(r"(\d\s?(?:[cс]?[mм]|mm|мм))\s?[2²](?!\d)")
# Номер в названии препарата, которое модель заменила меткой: «ERTES72'nin» → «{BRAND}».
_CAPS_NUMBER = re.compile(r"(?<=[A-ZÇĞİÖŞÜ]{3})\d+")
# Номер сноски, приклеенный к слову: «6Amoksisilin/klavulanik asit alan…», «2Herhangi bir…»,
# «çırpınma8 (konvülsiyon)», «uzama6», «nefes alma9)», внутри слова — «sür8eyle»,
# в конце после скобки — «(anjiyonörotik ödem) 4»; не «B12», «D3».
_FOOTNOTE = re.compile(
    r"(?<!\S)\d{1,2}(?=[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2})|(?<=[a-zçğıöşü)])\d{1,2}(?=[\s()]|$|[a-zçğıöşü])"
    r"|(?<=\)\s)\d{1,2}$"
)
# «2,3 veya 4 doza», «2,10 veya 20 adet», «FORTE,14,28 ve 56», «0.5,1.0 ve 1.5 mL» —
# перечисление без пробела, в переводе «2, 3 или 4»; «250 500 ve 1000 mL» — без запятой.
_COMMA_LIST = re.compile(r"(?<!\d)(?<!\d[.,])\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)+(?![\d.,]?\d)")


def _lower(text: str, lang: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower() if lang == "tr" else text.lower()


def _number_text(text: str) -> str:
    text = fix_ocr_digits(str(text or "").replace(_BRAND, " ").translate(_FRACTIONS))
    text = _ROMAN_RE.sub(lambda m: _ROMAN[m.group(0)], text)
    text = _PHONE.sub(lambda m: " 0" + re.sub(r"\D", "", m.group(0).replace("O", "0")).lstrip("0") + " ", text)
    return _SQUARE.sub(r"\1", _TIME_COLON.sub(".", text))


def plain_numbers(text: str) -> frozenset[str]:
    """Все числа абзаца цифрами в одной записи: «1.000» = «1 000» = «1,000», «2,50» = «2.5».

    Римские («tip II») и дроби («½») приводятся к цифрам, «l» рядом с цифрами
    («l0'unda») — к единице, телефон — к одной записи. Единица и ноль не
    сравниваются: «bir»/«1 из», «once»/«1 раз» модель пишет то словом, то цифрой.
    """
    text = _SPACED_THOUSANDS.sub(lambda m: re.sub(r"\s", "", m.group(0)), _number_text(text))
    return frozenset({_normalize_number(token) for token in _NUMBER.findall(text)} - {"1", "0"})


def number_lists(text: str) -> dict[str, frozenset[str]]:
    """Перечисления, слитые в одно число: {«2.3»: {«2», «3»}, «250500»: {«250», «500»}}.

    «2,3» — то ли 2,3, то ли перечисление 2 и 3: годится любой вариант.
    """
    text = _number_text(text)
    lists = {}
    for token in _COMMA_LIST.findall(text):
        lists[_normalize_number(token)] = frozenset(_normalize_number(part) for part in token.split(",")) - {"1", "0"}
    for token in _SPACED_THOUSANDS.findall(text):
        lists[re.sub(r"\s", "", token)] = frozenset(token.split()) - {"1", "0"}
    return lists


def number_words(text: str, lang: str) -> frozenset[str]:
    """Числа словами («üç», «три», «three», «twice») — только оправдывают цифру
    в другом тексте: «her iki» — это «оба», а не «2»; аббревиатура «TEN» — не 10."""
    words = _NUMBER_WORDS[lang]
    text = str(text or "")
    found = {value for pattern, value in _NUMBER_PHRASES[lang] if re.search(pattern, _lower(text, lang))}
    tokens = re.findall(r"[^\W\d_]+", text)
    for word in tokens:
        key = _lower(word, lang)
        if key in words and not (word.isupper() and len(word) > 1):
            found.add(str(words[key]))
    if lang == "tr":
        keys = [_lower(word, lang) for word in tokens]
        found.update(str(_TENS_TR[a] + _UNITS_TR[b]) for a, b in zip(keys, keys[1:]) if a in _TENS_TR and b in _UNITS_TR)
        # Слитно: «Ondört yaş» = 14.
        found.update(
            str(value + _UNITS_TR[key[len(tens):]])
            for key in keys for tens, value in _TENS_TR.items()
            if key.startswith(tens) and key[len(tens):] in _UNITS_TR
        )
    return frozenset(found)


# ── Понятия ───────────────────────────────────────────────────────────────

# Понятие: (TR, RU, EN). TR сравнивается после свёртки букв (ı→i, ç→c, ğ→g,
# ö→o, ü→u; ş остаётся: «kaş» — бровь, «kas» — мышца). None — в этом языке
# перевод понятия слишком разнообразен (совпадение < 90 % на верных записях).
_CONCEPTS = {
    "doctor": (r"doktor|hekim", r"врач|доктор", r"doctor|physician"),
    "pharmacist": (r"eczaci", r"фармацевт|провизор|аптек", r"pharmac"),
    "kidney": (r"bobrek", r"почк|почек|почеч|нефр", r"kidney|renal|nephr"),
    "liver": (r"karacig|hepat", r"печен|печён|гепат", r"liver|hepat"),
    "heart": (r"\bkalp|\bkalb|kardi", r"сердц|сердеч|кардио|инфаркт", r"heart|cardi"),
    "child": (r"cocuk|pediatri", r"\bдет|ребен|ребён|педиатр", r"child|pediatr|paediatr|kids"),
    "pregnancy": (r"hamile|\bgebe", r"беремен", r"pregnan"),
    "breastfeeding": (r"emzir|anne sut", r"кормл|кормящ|кормить|молок|лактац|грудью|вскармлив", r"breast|lactat|nursing"),
    "allergy": (r"all?er[jg]i", r"аллерг", r"allerg"),
    "infection": (r"enfeks", r"инфекц|инфицир", r"infect"),
    # «kan basıncı» — давление, а не кровь: и в EN «blood pressure» не считаем;
    # «kan sulandırıcı», «kan pıhtılaşmasını önleyici» — «антикоагулянт».
    "blood": (
        r"\bkan(?:in|i|da|daki|dan|a|am\w*)?\b(?! basinc| sulandir| pihtilasmasini onley)|kan pulcu", None,
        r"blood(?! pressure)|bleed|haem|hemo|platelet",
    ),
    # «derin» — «глубокий» («derin ven trombozu», «derin uyku»), а не «кожа».
    # «saç derisi» — «кожа головы», «scalp»: ни кожа, ни волосы.
    "skin": (r"(?<!sac )\bderi(?!n\b|nl|nd)|\bcilt", r"кож|дерм", r"skin|derm|cutaneous"),
    "intestine": (r"bagirsa|barsak", r"кишеч|кишк|кишок", None),
    # «kusma isteği/hissi» — позыв к рвоте, т. е. тошнота.
    "nausea": (r"bulanti|kusma (?:istegi|hissi)", r"тошнот", r"nause"),
    "vomiting": (r"kusma(?! (?:istegi|hissi))|kusar", r"рвот", r"vomit"),
    "diarrhea": (r"ishal", r"диаре|понос", r"diarr"),
    "constipation": (r"kabiz", r"запор", r"constipat"),
    "itching": (r"ka[sş]int", r"зуд", r"itch|prurit"),
    "rash": (r"dokuntu|kizari|kizarik", r"сып|покраснен|высыпан|эритем", r"\brash|redness|erythem"),  # не «trash»
    "swelling": (r"[sş]i[sş]me|[sş]i[sş]lik|odem", r"отек|отёк|опух|припух|отёч|отеч", r"swell|o?edema"),
    "dizziness": (r"ba[sş] donme|sersem|vertigo", r"головокруж", r"dizz|vertigo|lightheaded"),
    "headache": (r"ba[sş] agri", r"головн\w* бол", r"headache"),
    "fatigue": (r"yorgun|halsiz|bitkin", r"усталост|утомл|слабост|вялост", r"tired|fatigue|weak|letharg"),
    # «uyuşukluk» — и вялость, и онемение («numbness»), поэтому не «сон».
    "sleep": (r"uyku", None, r"sleep|insomn|drows|somnol"),
    "depression": (r"depres", r"депрес", r"depress"),
    "cancer": (r"kanser|tumor|malign|onkolo", r"\bрак|опухол|онко|злокачеств", r"cancer|tumou?r|malignan|oncol"),
    "diabetes": (r"diyabet|[sş]eker hastal", r"диабет", r"diabet"),
    "sugar": (r"[sş]eker|glukoz", r"сахар|глюкоз", None),
    "alcohol": (r"alkol", r"алкогол|спирт", r"alcohol"),
    # Не любая «makine»: «saç kurutma makineleri» — фены.
    "driving": (r"\barac\b|makine kullan", r"транспорт|машин|механизм|автомоб|вожден", r"driv|machin|vehicle"),
    "storage": (r"sakla", r"хран", r"\bstor|\bkeep"),
    "refrigerator": (r"buzdolab", r"холодильн", r"refrigerat|fridge"),
    # Не «dondurma» — мороженое (но «dondurmayınız» — не замораживать).
    "freeze": (r"dondur(?!ma(?:\b|l[ıi]))|donmu[sş]", r"замора|морозил|заморож", r"freez|frozen"),
    "light": (
        r"\bi[sş]i[kg]|gune[sş]",
        r"свет(?!л)|солн",
        r"(?<!-)\blight\b(?![- ](?:pink|yellow|blue|green|brown|orange|red|gr[ae]y|purple|colou?red|beige|cream))"
        r"|\bsun(?:light|screen|burn)?\b",
    ),
    "tablet": (r"tablet", r"таблет", r"tablet"),
    "capsule": (r"kapsul", r"капсул", r"capsul"),
    "injection": (r"enjeks|enjekt", None, r"inject|syringe"),
    "solution": (r"cozelti|solusyon", r"раствор", r"solution"),
    "syrup": (r"[sş]urup", r"сироп", r"syrup"),
    "cream": (r"\bkrem", r"крем", r"cream|sunscreen"),
    "week": (r"hafta", r"недел", r"week"),
    "age": (r"\bya[sş](?:in|ind|indan|indaki|tan|taki|a\b|\b)", r"\bлет\b|возраст|\bгод(?:а|у|ом)?\b", r"\byears?\b|\baged?\b"),
    "elderly": (r"ya[sş]li", r"пожил", r"elderl"),
    "women": (r"kadin", r"женщин", r"\bwom[ae]n|female"),
    # Не «gözbebeği» (зрачок), «tüp bebek» (ЭКО), «bebek bezi» (подгузник).
    "baby": (r"(?<!goz)(?<!goz )(?<!tup )bebe[kg](?! bez)|yenidog", r"\bдет|ребен|ребён|младен|новорожд|недонош|груднич", r"bab(?:y|ies)|infant|newborn|neonat"),
    "adult": (r"yeti[sş]kin|eri[sş]kin", r"взросл", r"adult"),
    # «bronkospazm» → «бронхоспазм»: спазм есть и в исходнике.
    "muscle": (r"\bkas(?:\b|lar|ta\b|lara|larda|larin)|kramp|spazm", r"мышц|мышеч|судорог|спазм", r"muscl|muscul|cramp|spasm"),
    "bone": (r"\bkemik", None, r"\bbones?\b|osteo|skelet"),
    "joint": (r"\beklem", r"сустав", r"joint|arthr"),
    "seizure": (r"nobet|havale|konvulz|epilep", None, r"seizure|convuls|epilep"),
    "hair": (r"\bsac(?:\b|lar|in|i\b)(?! deri)", r"волос", r"\bhair"),
    "throat": (r"bogaz", r"горл", r"throat"),
    "nose": (r"burun|burn[iu]", r"\bнос|назал|ноздр|насморк|ринит", r"\bnos[ei]|nasal|nostril|rhin"),
    "surgery": (r"ameliyat|cerrah", r"операц|хирург", r"surg|operation"),
    "vitamin": (r"vitamin", r"витамин", r"vitamin"),
    "hormone": (r"hormon", r"гормон", r"hormon"),
    "antibiotic": (r"antibiyo", r"антибиот", r"antibiot"),
    "bacteria": (r"bakteri", r"бактер", r"bacter"),
    "fungal": (r"mantar", r"грибк|грибов|микоз", r"fung"),
    "virus": (r"virus|viral", r"вирус|\bвич\b|\bспид\b", r"virus|viral"),
    "asthma": (r"astim", r"астм", r"asthm"),
    "cough": (r"oksur", r"кашл|кашел|кашель", r"cough"),
    "contraception": (r"dogum kontrol|kontrasep", r"контрацеп|противозачат|рождаемост|предохран", r"contracep|birth control"),
    "weight": (r"\bkilo(?!gram)|agirlik|agirli", None, r"weigh"),
    "stroke": (r"\binme\b", r"инсульт", r"stroke"),
    "side_effect": (r"yan etki", r"побочн|нежелательн", r"side effect|adverse"),
    "package": (r"ambalaj|\bkutu|blister", r"упаков|коробк|блистер", r"pack|\bbox|blister|carton"),
    # «son kullanım tarihi», «Son Kull. Ta.» — тоже срок годности.
    "expiry": (r"son kullan|son kull\.|miad", None, r"expir"),
    "white": (r"beyaz", r"\bбел", r"white"),
    "red": (r"kirmizi", r"красн", r"\bred\b|\bredd"),
    "yellow": (r"\bsari\b|\bsarims", r"желт|жёлт", r"yellow"),
    "pink": (r"pembe", r"розов", r"pink"),
    "orange": (r"turuncu", r"оранж", r"orange"),
    "green": (r"ye[sş]il", r"зелен|зелён", r"green"),
    "brown": (r"kahverengi", r"коричн", r"brown"),
    "round": (r"yuvarlak", r"кругл", r"round|circular"),
    "oval": (r"\boval", None, r"oval"),
    "lactose": (r"laktoz", r"лактоз", r"lactose"),
    "sodium": (r"sodyum", r"натри", r"sodium"),
    "potassium": (r"potasyum", r"\bкали[йяюе]", r"potassium"),
    "calcium": (r"kalsiyum", r"кальци", r"calcium"),
    "magnesium": (r"magnezyum", r"магни", r"magnesium"),
    # Не «demirhindi» (тамаринд) и другие растения на «demir».
    "iron": (r"\bdemir(?:\b|i\b|in\b|e\b|den\b|le\b|li\b)", None, r"\biron\b|ferr"),
    "thyroid": (r"tiroid", None, r"thyroid"),
    "immune": (r"bagi[sş]iklik|immun", r"иммун|\bвич\b|\bспид\b", r"immun"),
}
_LANGS = ("tr", "ru", "en")
_CONCEPT_RES = {
    lang: [(name, re.compile(row[index])) for name, row in _CONCEPTS.items() if row[index]]
    for index, lang in enumerate(_LANGS)
}
_CHECKED = {lang: frozenset(name for name, _ in _CONCEPT_RES[lang]) for lang in ("ru", "en")}
_TR_FOLD = str.maketrans("ıçğöüâîû", "icgouaiu")


def concepts(text: str, lang: str) -> frozenset[str]:
    """Медицинские понятия абзаца по словарю (врач, почки, хранение, таблетка…)."""
    text = _lower(str(text or "").replace(_BRAND, " "), lang)
    if lang == "tr":
        # «döndürerek açınız» (поворачивая) после свёртки букв совпало бы с «dondur» (заморозить).
        text = text.replace("döndür", "çevir").translate(_TR_FOLD)
    return frozenset(name for name, pattern in _CONCEPT_RES[lang] if pattern.search(text))


# ── Заголовок, частота, длина ─────────────────────────────────────────────

# «2. X'İ KULLANMADAN ÖNCE…», «3. Kapağı açınız»; не «1. günde», «2. haftada», «2. aydan sonra»,
# «3. ve 4. kürler boyunca».
_SOURCE_HEADING = re.compile(
    r"^\s*(\d{1,2})\.\s+(?!ve(?:ya)?\s+\d)(?!(?:g[üu]n|hafta|ay(?:da|dan|a|ın|ını|lık|lar|ları)?\b|y[ıi]l|doz|kez|saat|basamak|tedavi|"
    r"k[üu]r|seans)\w*)(?=[^\W\d_]|\{BRAND\})",
    re.IGNORECASE,
)
_TRANSLATION_HEADING = re.compile(r"^\s*(\d{1,2})\s*[.)](?!\d)")

# «en az 30 dakika önce», «10 hastanın en az 1'inde», «en az iki kez» — нижняя граница,
# её модель теряла («за 30 минут до еды», «у 1 из 10 пациентов»). Не «mümkün olan en az
# doz», «en az miktarda» — это «наименьшая доза». Перевод может передать границу
# по-разному: «не ранее чем через 3 месяца», «детям от 1 года», «один или несколько».
_AT_LEAST = {
    "tr": re.compile(
        # Не «en az 36 saat geçmeden» (отрицание: «не ранее»/«менее чем через» — верно), не
        # диапазон «en az 1'i ila 10'unda» и не испорченные частоты «en az 1'inden daha az/fazla».
        r"\ben az\s+(?:\d|yarım|bir\b|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on\b|yirmi|otuz|kırk|elli|birkaç)"
        r"(?![^.;]{0,30}geçmeden)(?!\S*\s*'?\s*(?:inden|ından|nden|ndan)\b)(?!\S*\s+ila\b)",
        re.IGNORECASE,
    ),
    "ru": re.compile(
        r"не менее|не меньше|по меньшей мере|по крайней мере|как минимум|минимум|хотя бы|и более|или более|"
        r"или нескольк|≥|не реже|не короче|не ранее|не раньше|старше|\bот\s+(?:\d|одного|двух|трёх|трех)|начиная с|"
        r"минимальн|более чем у|не ближе",
        re.IGNORECASE,
    ),
    "en": re.compile(
        r"at least|or more|one or more|or older|and older|and over|and above|no sooner|no earlier|not earlier|"
        r"minimum|≥|no less|not less|from the age of|older than|more than \d+ in",
        re.IGNORECASE,
    ),
}

# Частота побочного эффекта в начале абзаца («Yaygın olmayan: 100 hastanın…»).
_FREQUENCY_LABEL = re.compile(
    r"^\W*(çok yaygın|yaygın olmayan|yaygın|çok seyrek|seyrek|bilinmiyor)\s*(?:yan etkiler\w*)?\s*[:(]",
    re.IGNORECASE,
)
_FREQUENCY_ANYWHERE = re.compile(r"çok yaygın|yaygın olmayan|yaygın|çok seyrek|seyrek", re.IGNORECASE)
_FREQUENCY_SOURCE = {
    "çok yaygın": "very_common", "yaygın olmayan": "uncommon", "yaygın": "common",
    "çok seyrek": "very_rare", "seyrek": "rare", "bilinmiyor": "unknown",
}
# Числа строки частоты задаёт её название: «Seyrek: 000 hastanın birinden az» (в
# исходнике потеряно «10.») модель переводит «реже 1 из 10 000»; так же частота
# в скобках после симптома — «(Çok seyrek (000 hastanın 1'inden az) görülebilir.)».
_FREQUENCY_NUMBERS = {
    "very_common": frozenset({"10"}), "common": frozenset({"10", "100"}), "uncommon": frozenset({"100", "1000"}),
    "rare": frozenset({"1000", "10000"}), "very_rare": frozenset({"10000"}), "unknown": frozenset(),
}
_FREQUENCY_TRANSLATION = {
    "ru": (
        ("unknown", r"неизвестн|не известн"),
        ("very_common", r"очень (?:част|распростран)"),
        ("uncommon", r"нечаст|не част|необычн|нераспростран"),
        ("common", r"част|распростран"),
        ("very_rare", r"очень редк"),
        ("rare", r"редк"),
    ),
    "en": (
        ("unknown", r"not known|unknown"),
        ("very_common", r"very (?:common|frequent)"),
        ("uncommon", r"uncommon|infrequent|not common"),
        ("common", r"common|frequent"),
        ("very_rare", r"very rare"),
        ("rare", r"rare"),
    ),
}

# Длина перевода ≈ c × длина исходника, дисперсия ∝ длине (Гейл–Чёрч).
_LENGTH_MODEL = {"ru": (1.015, 3.737), "en": (0.983, 3.027)}


def _frequency(text: str, lang: str) -> Optional[str]:
    if lang == "tr":
        label = _FREQUENCY_LABEL.match(_lower(text, lang))
        return _FREQUENCY_SOURCE[label.group(1)] if label else None
    head = text.lower()[:60]
    for name, pattern in _FREQUENCY_TRANSLATION[lang]:
        if re.search(pattern, head):
            return name
    return None


class Features:
    """Признаки одного текста для сравнения исходника и перевода."""

    __slots__ = (
        "lang", "numbers", "words", "lists", "footnotes", "brand_numbers", "garbled_frequency", "concepts", "length",
        "heading", "frequency", "brand", "end", "empty", "fragment", "at_least",
    )

    def __init__(self, text: str, lang: str):
        text = str(text or "").strip()
        self.lang = lang
        self.empty = not text
        self.numbers = plain_numbers(text)
        self.lists = number_lists(text)
        # Номер сноски модель то оставляет («7Желудочно-…»), то убирает — он необязателен;
        # как и «000» без начала числа («fakat 000 hastanın») — его не прочесть.
        self.footnotes = self.brand_numbers = self.garbled_frequency = frozenset()
        if lang == "tr":
            zeros = {number for number in self.numbers if set(number) == {"0"}}
            self.footnotes = frozenset(_FOOTNOTE.findall(text)) - {"1", "0"} | zeros
            self.brand_numbers = frozenset(_CAPS_NUMBER.findall(text)) - {"1", "0"}
            if zeros:
                # «Yaygin», «YAYGİN» — та же «yaygın».
                labels = {_FREQUENCY_SOURCE[_lower(label, lang).replace("i", "ı")] for label in _FREQUENCY_ANYWHERE.findall(text)}
                self.garbled_frequency = frozenset().union(*(_FREQUENCY_NUMBERS[label] for label in labels))
        # Обрывок предложения: начинается с суффикса после бренда или со строчной.
        self.fragment = bool(re.match(r"['’`]|[a-zçğıöşü]", text))
        self.words = number_words(text, lang)
        self.concepts = concepts(text, lang)
        self.length = len(text)
        match = (_SOURCE_HEADING if lang == "tr" else _TRANSLATION_HEADING).match(text)
        self.heading = match.group(1) if match else None
        self.frequency = _frequency(text, lang)
        self.brand = _BRAND in text
        self.end = text[-1] if text and text[-1] in ":?,;" else "."
        self.at_least = bool(_AT_LEAST[lang].search(text))


def pair_score(source: Features, translation: Features) -> float:
    """Насколько translation похож на перевод source: больше — лучше, ≈0 — без признаков."""
    score = 0.0
    if source.numbers or translation.numbers:
        matched = source.numbers & (translation.numbers | translation.words)
        matched |= translation.numbers & (source.numbers | source.words)
        score += 3 * (2 * len(matched) / len(source.numbers | translation.numbers) - 1)
    expected = source.concepts & _CHECKED[translation.lang]
    if expected and translation.concepts:
        score += 3 * len(expected & translation.concepts) / math.sqrt(len(expected) * len(translation.concepts)) - 1
    ratio, variance = _LENGTH_MODEL[translation.lang]
    delta = (translation.length - ratio * source.length) / math.sqrt(variance * source.length + 25)
    score -= min(delta * delta / 2, 12) / 2
    if source.heading:
        score += 2 if translation.heading == source.heading else -2
    elif translation.heading:
        score -= 1
    if source.brand != translation.brand:
        score -= 0.7
    if source.end != translation.end:
        score -= 0.3
    return score


# ── Правила для одного абзаца ─────────────────────────────────────────────

# |ln| отношения длин перевода и исходника: у 98 % верных записей — до 0,34.
# Сглаживание гасит разброс у коротких («Gaz» → «Газообразование»), у пары
# RU/EN оно больше: «Gastritis» против «Воспаление желудка (гастрит)» — норма.
# Короткий перевод короткого цельного абзаца сглаживается сильнее: «İdrar
# söktürücü ilaçlar (diüretikler)» → «Diuretics». Как раньше ловятся длинный
# чужой перевод («Papiller nekroz» → «Храните при температуре ниже 25°C…»),
# потеря части длинного абзаца и обрывок («'in uygulama hızını azaltacak ya da
# size insülin uygulayacaktır.» → «или назначить вам инсулин.»).
LENGTH_LOG_RATIO = 0.7
SHORTER_SMOOTHING = 20
SHORT_SOURCE = 80
RU_EN_LENGTH_LOG_RATIO = 0.6


def _log_ratio(a: Features, b: Features, smoothing: int) -> float:
    return abs(math.log((a.length + smoothing) / (b.length + smoothing)))


def _length_differs(translation: Features, source: Features) -> bool:
    gentle = (
        8 <= translation.length < source.length <= SHORT_SOURCE and not source.fragment
    )
    return _log_ratio(translation, source, SHORTER_SMOOTHING if gentle else 10) > LENGTH_LOG_RATIO


def _numbers_differ(a: Features, b: Features, optional: frozenset = frozenset()) -> bool:
    """Цифра одного текста не встречается в другом ни цифрой, ни словом.

    «2,3» без пробела в одном тексте и «2» и «3» в другом — одно и то же
    перечисление («2,3 veya 4 doza» → «2, 3 или 4 дозы»). ``optional`` — числа,
    которых может не быть в одном из текстов (``_optional_numbers``).
    """
    a_only = set(a.numbers - b.numbers - b.words - optional)
    b_only = set(b.numbers - a.numbers - a.words - optional)
    for x, y, x_only, y_only in ((a, b, a_only, b_only), (b, a, b_only, a_only)):
        for number, parts in x.lists.items():
            if number in x_only and parts <= y.numbers | y.words:
                x_only.discard(number)
                y_only -= parts
    return bool(a_only or b_only)


def _optional_numbers(src: Features, translation: Features) -> frozenset:
    """Числа, которые могут быть только в одном из текстов: сноски исходника, номер
    в названии, которое модель заменила меткой, числа строки частоты с тем же названием."""
    optional = src.footnotes | src.garbled_frequency
    if translation.brand and not src.brand:
        optional |= src.brand_numbers
    if src.frequency and translation.frequency == src.frequency:
        optional |= _FREQUENCY_NUMBERS[src.frequency]
    return optional


def _problems(src: Features, ru: Features, en: Features) -> list[str]:
    problems = []
    if src.heading and (ru.heading != src.heading or en.heading != src.heading):
        problems.append("heading_mismatch")
    if _numbers_differ(src, ru, _optional_numbers(src, ru)) or _numbers_differ(src, en, _optional_numbers(src, en)):
        problems.append("number_mismatch")
    if _length_differs(ru, src) or _length_differs(en, src):
        problems.append("length_mismatch")
    if _numbers_differ(ru, en, src.footnotes) or _log_ratio(ru, en, 20) > RU_EN_LENGTH_LOG_RATIO:
        problems.append("ru_en_mismatch")
    for translation in (ru, en):
        expected = src.concepts & _CHECKED[translation.lang]
        if len(expected) >= 2 and not expected & translation.concepts:
            problems.append("concept_mismatch")
            break
    if src.frequency and (ru.frequency != src.frequency or en.frequency != src.frequency):
        problems.append("frequency_mismatch")
    if src.at_least and not (ru.at_least and en.at_least):
        problems.append("at_least_mismatch")
    return problems


def item_problems(source: str, ru: str, en: str) -> list[str]:
    """Признаки чужого перевода в одном абзаце (пустой список — расхождений нет)."""
    return _problems(Features(source, "tr"), Features(ru, "ru"), Features(en, "en"))


# Тысячи через запятую по-английски («1 из 1,000 пациентов», «100,000 МЕ»): по-русски
# запятая — дробная часть. Только частоты и единицы — «0,375 мг» и «1,500 мг» не трогаем.
_RU_THOUSANDS = re.compile(
    r"(?<![\d.,])[1-9]\d{0,2}(?:,\d{3})+(?![\d,])"
    r"(?=\s*(?:пациент|человек|больн|случа|женщин|мужчин|дет|МЕ|ЕД|единиц))"
    r"|(?<=из )[1-9]\d{0,2}(?:,\d{3})+(?![\d,])"
)


def ru_thousands(text: str) -> str:
    """«1 из 1,000» → «1 из 1000», «10,000» → «10 000» (только частоты и единицы действия)."""
    def number(match: re.Match) -> str:
        digits = match.group(0).replace(",", "")
        return digits if len(digits) <= 4 else f"{int(digits):,}".replace(",", " ")

    return _RU_THOUSANDS.sub(number, str(text or ""))


def restore_heading(source: str, translation: str) -> str:
    """Номер шага или раздела «N.», который модель не перенесла в начало перевода,
    ставится кодом: «3. Kalan suyu … doldurunuz» → «Заполните…» → «3. Заполните…».
    Если перевод начинается с другого числа, это не пропуск, а расхождение."""
    match = _SOURCE_HEADING.match(str(source or ""))
    if (
        match and translation and not re.match(r"\s*\d", translation)
        # «3. Bölüm» → «См. раздел 3»: ссылка на раздел, номер уже в переводе.
        and not re.search(rf"(?:раздел\w*|пункт\w*|section|item)\s+{match.group(1)}(?!\d)", translation, re.IGNORECASE)
    ):
        return f"{match.group(1)}. {translation}"
    return translation


# ── Сдвиг в последовательности абзацев ────────────────────────────────────

# Перевод ближе к соседнему исходнику, чем к своему, на SHIFT_MARGIN (RU и EN
# вместе) или на LOCALE_SHIFT_MARGIN в одном языке — сдвиг; сдвиг бывает только
# в EN (≈2 % записей 20.10). Абзац на месте — ближе к своему на SHIFT_MARGIN и
# сам по себе похож (> SELF_MIN_SCORE): исходник чужого перевода мог не попасть
# в память, и тогда с соседями перевод не совпадает.
SHIFT_MARGIN = 2.0
LOCALE_SHIFT_MARGIN = 3.0
SELF_MIN_SCORE = -2.0
_NEIGHBOURS = (1, 2, -1)


def _evidence(rows: Sequence[tuple[Features, Features, Features]], index: int) -> int:
    """+1 — перевод записи index от соседнего абзаца, −1 — от своего, 0 — не ясно.

    Сосед годится в «хозяева» перевода, только если его собственный перевод
    подходит ему не лучше: два почти одинаковых абзаца подряд («Aksiyal
    spondiloartrit…» и «-Radyografik olmayan aksiyal spondiloartrit…») — не сдвиг.
    """
    source, ru, en = rows[index]
    if ru.empty or en.empty:
        return 0
    own_ru, own_en = pair_score(source, ru), pair_score(source, en)
    own = own_ru + own_en
    neighbours, candidates = [], []
    for j in (index + step for step in _NEIGHBOURS):
        if not 0 <= j < len(rows) or rows[j][0].empty:
            continue
        other, other_ru, other_en = rows[j]
        scores = (pair_score(other, ru), pair_score(other, en))
        neighbours.append(scores)
        if sum(scores) >= pair_score(other, other_ru) + pair_score(other, other_en):
            candidates.append(scores)
    if candidates and (
        max(ru_score + en_score for ru_score, en_score in candidates) - own > SHIFT_MARGIN
        or max(ru_score for ru_score, _ in candidates) - own_ru > LOCALE_SHIFT_MARGIN
        or max(en_score for _, en_score in candidates) - own_en > LOCALE_SHIFT_MARGIN
    ):
        return 1
    if not neighbours:
        return 0
    best = max(ru_score + en_score for ru_score, en_score in neighbours)
    return -1 if own - best > SHIFT_MARGIN and own > SELF_MIN_SCORE else 0


def spread_shift(evidence: Sequence[int], *, back: int = 3, forward: int = 40) -> list[bool]:
    """Сдвиг по цепочке: от каждой записи со сдвигом вперёд до записи «на месте»
    (не дальше ``forward``) и назад на ``back`` записей без признаков."""
    shifted = [value == 1 for value in evidence]
    for index, value in enumerate(evidence):
        if value != 1:
            continue
        j = index + 1
        while j < len(evidence) and j <= index + forward and evidence[j] != -1:
            shifted[j] = True
            j += 1
        j = index - 1
        while j >= 0 and j >= index - back and evidence[j] == 0:
            shifted[j] = True
            j -= 1
    return shifted


def request_shift(sources: Sequence[str], ru: Sequence[str], en: Sequence[str]) -> set[int]:
    """Индексы абзацев одного ответа модели, переводы которых, вероятно, сдвинуты.

    Сдвиг тянется по ответу, пока не встретится абзац, точно стоящий на месте,
    поэтому от каждого признака сдвига отбрасываются соседи в обе стороны до
    такого абзаца.
    """
    rows = [(Features(s, "tr"), Features(r, "ru"), Features(e, "en")) for s, r, e in zip(sources, ru, en)]
    evidence = [_evidence(rows, index) for index in range(len(rows))]
    spread = spread_shift(evidence, back=len(rows), forward=len(rows))
    return {index for index, shifted in enumerate(spread) if shifted}


def audit_sequence(rows: Iterable[tuple[str, str, str]]) -> list[list[str]]:
    """Причины для каждой записи потока (исходник, RU, EN) в порядке вставки в память.

    Записи одного запроса стоят в памяти подряд (pk по порядку абзацев), поэтому
    соседи по pk — соседи по ответу модели. К правилам абзаца добавляется
    «shifted»; в памяти держится только окно из четырёх записей.
    """
    problems: list[list[str]] = []
    evidence: list[int] = []
    window: list[tuple[Features, Features, Features]] = []  # записи i-1, i, i+1, i+2
    current = 0  # позиция записи i в окне (0 — у первой записи нет предыдущей)

    def evaluate() -> None:
        nonlocal current
        evidence.append(_evidence(window, current))
        if current == 0:
            current = 1
        else:
            window.pop(0)

    for source, ru, en in rows:
        features = (Features(source, "tr"), Features(ru, "ru"), Features(en, "en"))
        problems.append(_problems(*features))
        window.append(features)
        if len(window) - current == 3:
            evaluate()
    while current < len(window):
        evaluate()
    for index, shifted in enumerate(spread_shift(evidence)):
        if shifted:
            problems[index].append("shifted")
    return problems
