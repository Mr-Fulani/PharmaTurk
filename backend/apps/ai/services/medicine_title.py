"""Название лекарства по шаблону кодом: бренд + дозировка + форма + фасовка.

«MAJEZIK 100 MG 15 FILM TABLET» →
«MAJEZIK 100 мг, таблетки, покрытые плёночной оболочкой, 15 шт.» /
«MAJEZIK 100 mg, film-coated tablets, 15 pcs».

Бренд — слова источника до первой дозировки/формы, как в источнике. Если в
названии после бренда есть слово, которого нет в словаре форм и единиц,
шаблон не строится (None) и остаётся название от модели.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from apps.ai.services.medicine_reference import _COUNT_UNITS, fold_tr, ru_plural

# Турецкая форма (после fold_tr) → (RU, EN). Сравнение — по самой длинной фразе.
FORM_PHRASES = {
    "uzatilmis salimli film tablet": (
        "таблетки пролонгированного высвобождения, покрытые плёночной оболочкой",
        "prolonged-release film-coated tablets",
    ),
    "uzatilmis salimli tablet": ("таблетки пролонгированного высвобождения", "prolonged-release tablets"),
    "kontrollu salimli tablet": ("таблетки с контролируемым высвобождением", "controlled-release tablets"),
    "modifiye salimli tablet": ("таблетки с модифицированным высвобождением", "modified-release tablets"),
    "degistirilmis salimli tablet": ("таблетки с модифицированным высвобождением", "modified-release tablets"),
    "film kapli tablet": ("таблетки, покрытые плёночной оболочкой", "film-coated tablets"),
    "film tablet": ("таблетки, покрытые плёночной оболочкой", "film-coated tablets"),
    "efervesan tablet": ("шипучие таблетки", "effervescent tablets"),
    "agizda dagilan tablet": ("таблетки, диспергируемые в полости рта", "orodispersible tablets"),
    "agizda dagilan film tablet": ("таблетки, диспергируемые в полости рта", "orodispersible tablets"),
    "cigneme tableti": ("жевательные таблетки", "chewable tablets"),
    "cigneme tablet": ("жевательные таблетки", "chewable tablets"),
    "enterik kapli tablet": ("кишечнорастворимые таблетки", "gastro-resistant tablets"),
    "enterik tablet": ("кишечнорастворимые таблетки", "gastro-resistant tablets"),
    "gastro direncli tablet": ("кишечнорастворимые таблетки", "gastro-resistant tablets"),
    "dagilabilir tablet": ("диспергируемые таблетки", "dispersible tablets"),
    "suda dagilabilir tablet": ("диспергируемые таблетки", "dispersible tablets"),
    "sublingual tablet": ("подъязычные таблетки", "sublingual tablets"),
    "dil alti tablet": ("подъязычные таблетки", "sublingual tablets"),
    "vajinal tablet": ("вагинальные таблетки", "vaginal tablets"),
    "draje": ("драже", "dragées"),
    "tablet": ("таблетки", "tablets"),
    "uzatilmis salimli kapsul": ("капсулы пролонгированного высвобождения", "prolonged-release capsules"),
    "enterik kapli kapsul": ("кишечнорастворимые капсулы", "gastro-resistant capsules"),
    "enterik kapsul": ("кишечнорастворимые капсулы", "gastro-resistant capsules"),
    "gastro direncli kapsul": ("кишечнорастворимые капсулы", "gastro-resistant capsules"),
    "yumusak kapsul": ("мягкие капсулы", "soft capsules"),
    "sert kapsul": ("капсулы", "capsules"),
    "kapsul": ("капсулы", "capsules"),
    "surup": ("сироп", "syrup"),
    "oral suspansiyon icin toz": (
        "порошок для приготовления суспензии для приёма внутрь", "powder for oral suspension"
    ),
    "suspansiyon icin toz": ("порошок для приготовления суспензии", "powder for suspension"),
    "oral suspansiyon": ("суспензия для приёма внутрь", "oral suspension"),
    "enjeksiyonluk suspansiyon": ("суспензия для инъекций", "suspension for injection"),
    "suspansiyon": ("суспензия", "suspension"),
    "oral cozelti": ("раствор для приёма внутрь", "oral solution"),
    "oral damla": ("капли для приёма внутрь", "oral drops"),
    "goz damlasi": ("глазные капли", "eye drops"),
    "kulak damlasi": ("ушные капли", "ear drops"),
    "burun damlasi": ("назальные капли", "nasal drops"),
    "damla": ("капли", "drops"),
    "goz pomadi": ("глазная мазь", "eye ointment"),
    "pomad": ("мазь", "ointment"),
    "merhem": ("мазь", "ointment"),
    "vajinal krem": ("вагинальный крем", "vaginal cream"),
    "krem": ("крем", "cream"),
    "oral jel": ("гель для полости рта", "oral gel"),
    "goz jeli": ("глазной гель", "eye gel"),
    "jel": ("гель", "gel"),
    "losyon": ("лосьон", "lotion"),
    "sampuan": ("шампунь", "shampoo"),
    "nazal sprey": ("назальный спрей", "nasal spray"),
    "burun spreyi": ("назальный спрей", "nasal spray"),
    "oral sprey": ("спрей для полости рта", "oral spray"),
    "sprey": ("спрей", "spray"),
    "inhalasyon icin toz": ("порошок для ингаляций", "inhalation powder"),
    "inhalasyon icin cozelti": ("раствор для ингаляций", "inhalation solution"),
    "inhalasyon icin suspansiyon": ("суспензия для ингаляций", "inhalation suspension"),
    "inhalasyon aerosolu": ("аэрозоль для ингаляций", "inhalation aerosol"),
    "inhaler": ("ингалятор", "inhaler"),
    "rektal supozituar": ("ректальные суппозитории", "rectal suppositories"),
    "supozituar": ("суппозитории", "suppositories"),
    "fitil": ("суппозитории", "suppositories"),
    "vajinal ovul": ("вагинальные суппозитории", "pessaries"),
    "efervesan granul": ("шипучие гранулы", "effervescent granules"),
    "granul": ("гранулы", "granules"),
    "efervesan toz": ("шипучий порошок", "effervescent powder"),
    "liyofilize toz": ("лиофилизат", "lyophilised powder"),
    "enjeksiyonluk cozelti icin toz": (
        "порошок для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "enjeksiyon icin toz": (
        "порошок для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "toz": ("порошок", "powder"),
    "sase": ("саше", "sachets"),
    "enjektabl cozelti": ("раствор для инъекций", "solution for injection"),
    "enjeksiyonluk cozelti": ("раствор для инъекций", "solution for injection"),
    "enjeksiyon icin cozelti": ("раствор для инъекций", "solution for injection"),
    "iv infuzyon icin cozelti": ("раствор для внутривенных инфузий", "solution for intravenous infusion"),
    "iv infuzyonluk cozelti": ("раствор для внутривенных инфузий", "solution for intravenous infusion"),
    "infuzyonluk cozelti": ("раствор для инфузий", "solution for infusion"),
    "infuzyon icin cozelti": ("раствор для инфузий", "solution for infusion"),
    "infuzyon cozeltisi": ("раствор для инфузий", "solution for infusion"),
    "kullanima hazir enjektor": ("в предварительно заполненном шприце", "pre-filled syringe"),
    "dolu enjektor": ("в предварительно заполненном шприце", "pre-filled syringe"),
    "kullanima hazir kalem": ("шприц-ручка", "pre-filled pen"),
    "cozelti": ("раствор", "solution"),
    "emulsiyon": ("эмульсия", "emulsion"),
    "transdermal flaster": ("трансдермальный пластырь", "transdermal patch"),
    "flaster": ("пластырь", "patch"),
    "pastil": ("пастилки", "lozenges"),
    "gargara": ("раствор для полоскания", "gargle"),
    "ampul": ("ампулы", "ampoules"),
    "flakon": ("флакон", "vial"),
}
FORM_WORDS = {word for phrase in FORM_PHRASES for word in phrase.split()}
_FORM_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in sorted(FORM_PHRASES, key=len, reverse=True)) + r")\b"
)

# Единица фасовки после числа → ключ medicine_reference._COUNT_UNITS.
_PACK_WORDS = {
    "adet": "piece", "ampul": "ampoule", "flakon": "vial", "sase": "sachet",
    "kalem": "pen", "enjektor": "syringe", "doz": "dose", "puskurtme": "dose",
    "tup": "tube", "sise": "vial", "flaster": "patch",
}
_PACK_RE = re.compile(r"(\d+)\s+(" + "|".join(_PACK_WORDS) + r")\b")

_UNITS = {
    "mg": ("мг", "mg"), "mcg": ("мкг", "mcg"), "mkg": ("мкг", "mcg"), "µg": ("мкг", "mcg"),
    "g": ("г", "g"), "gr": ("г", "g"), "ml": ("мл", "ml"), "l": ("л", "l"),
    "iu": ("МЕ", "IU"), "ui": ("МЕ", "IU"), "mmol": ("ммоль", "mmol"), "meq": ("мэкв", "mEq"),
    "doz": ("доза", "dose"), "puskurtme": ("доза", "dose"), "saat": ("ч", "h"), "h": ("ч", "h"),
}
_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:mg|mcg|mkg|µg|gr|g|ml|iu|ui|mmol|meq)"
_PER = r"(?:mg|mcg|g|ml|doz|puskurtme|saat|h|l)"
_DOSE_RE = re.compile(
    rf"(?:%\s*({_NUM})|({_NUM})\s*%|({_NUM})\s*({_UNIT})(?:\s*/\s*({_NUM})?\s*({_PER}))?)(?![a-z])"
)
_MULTI_RE = re.compile(rf"(\d+)\s*x\s*({_NUM})\s*(ml|g|gr)\b")
_ROUTE_ABBR_RE = re.compile(r"(im|iv|sc)(?:\s*/\s*(im|iv|sc))*\b")
_MASS_FORMS = {"cream", "ointment", "gel", "lotion", "powder", "granules", "shampoo"}
_ROUTE_ABBR = {"im": ("в/м", "IM"), "iv": ("в/в", "IV"), "sc": ("п/к", "SC")}


def _num(value: str, locale: str) -> str:
    return value.replace(".", ",") if locale == "ru" else value.replace(",", ".")


def _format_dose(match: re.Match, locale: str) -> tuple[str, str]:
    """(текст, вид): strength — дозировка, volume — объём, grams — масса (по форме)."""
    index = 0 if locale == "ru" else 1
    percent = match.group(1) or match.group(2)
    if percent:
        return f"{_num(percent, locale)}%", "strength"
    number, unit, per_number, per_unit = match.group(3, 4, 5, 6)
    text = f"{_num(number, locale)} {_UNITS[unit][index]}"
    if per_unit:
        per = f"{_num(per_number, locale)} " if per_number else ""
        text += f"/{per}{_UNITS[per_unit][index]}"
        return text, "strength"
    if unit in ("ml", "l"):
        return text, "volume"
    return text, "grams" if unit in ("g", "gr") else "strength"


def _pack(number: str, unit: str, locale: str) -> str:
    ru_forms, en_forms = _COUNT_UNITS[unit]
    if locale == "ru":
        return f"{number} {ru_plural(number, *ru_forms)}"
    return f"{number} {en_forms[0] if number == '1' else en_forms[1]}"


def build_medicine_title(name: Any) -> Optional[dict[str, str]]:
    """RU/EN-название из исходного названия или None, если разобрать нельзя."""
    source = re.sub(r"[()]", " ", str(name or "")).strip()
    tokens = source.split()
    brand: list[str] = []
    for token in tokens:
        folded = fold_tr(token)
        if (
            folded[:1].isdigit()
            or folded.startswith("%")
            or folded in FORM_WORDS
            or _ROUTE_ABBR_RE.fullmatch(folded)
        ):
            break
        brand.append(token)
    if not brand or len(brand) == len(tokens):
        return None
    rest = fold_tr(" ".join(tokens[len(brand):]))

    strengths = {"ru": [], "en": []}
    volumes = {"ru": [], "en": []}
    grams = {"ru": [], "en": []}
    packs = {"ru": [], "en": []}
    form = None
    route = None
    while rest:
        rest = rest.lstrip(" ,+-")
        if not rest:
            break
        multi = _MULTI_RE.match(rest)
        pack = _PACK_RE.match(rest)
        dose = _DOSE_RE.match(rest)
        form_match = _FORM_RE.match(rest)
        counted_form = re.match(r"(\d+)\s+", rest)
        if multi:
            count, size, unit = multi.groups()
            unit = "g" if unit == "gr" else unit
            volumes["ru"].append(f"{count} шт. по {_num(size, 'ru')} {_UNITS[unit][0]}")
            volumes["en"].append(f"{count} × {_num(size, 'en')} {_UNITS[unit][1]}")
            rest = rest[multi.end():]
        elif pack:
            number, word = pack.groups()
            for locale in ("ru", "en"):
                packs[locale].append(_pack(number, _PACK_WORDS[word], locale))
            rest = rest[pack.end():]
        elif dose:
            for locale in ("ru", "en"):
                text, kind = _format_dose(dose, locale)
                {"strength": strengths, "volume": volumes, "grams": grams}[kind][locale].append(text)
            rest = rest[dose.end():]
        elif form_match and form is None:
            form = FORM_PHRASES[form_match.group(0)]
            rest = rest[form_match.end():]
        elif counted_form and _FORM_RE.match(rest[counted_form.end():]) and form is None:
            number = counted_form.group(1)
            form_match = _FORM_RE.match(rest[counted_form.end():])
            form = FORM_PHRASES[form_match.group(0)]
            packs["ru"].append(f"{number} шт.")
            packs["en"].append(f"{number} {'pc' if number == '1' else 'pcs'}")
            rest = rest[counted_form.end() + form_match.end():]
        elif _ROUTE_ABBR_RE.match(rest) and route is None:
            route_match = _ROUTE_ABBR_RE.match(rest)
            codes = re.findall(r"im|iv|sc", route_match.group(0))
            route = (
                ", ".join(_ROUTE_ABBR[c][0] for c in codes),
                "/".join(_ROUTE_ABBR[c][1] for c in codes),
            )
            rest = rest[route_match.end():]
        else:
            return None

    if form is None and not (strengths["ru"] or volumes["ru"] or grams["ru"]):
        return None
    # Граммы у мазей/кремов/гелей/порошков — масса упаковки, у прочих — дозировка.
    grams_are_volume = form is not None and form[1].split()[-1] in _MASS_FORMS
    for locale in ("ru", "en"):
        (volumes if grams_are_volume else strengths)[locale][:0] = grams[locale]
    result = {}
    for index, locale in enumerate(("ru", "en")):
        head = " ".join(brand + strengths[locale])
        parts = [head]
        if form:
            parts.append(form[index] + (f" ({route[index]})" if route else ""))
        elif route:
            parts.append(route[index])
        parts.extend(volumes[locale])
        parts.extend(packs[locale])
        result[locale] = ", ".join(parts)
    return result
