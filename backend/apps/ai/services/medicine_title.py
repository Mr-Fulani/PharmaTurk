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
    # Пилот 18.10.2026: формы, которые модель переводила с браком.
    "dilalti sprey": ("подъязычный спрей", "sublingual spray"),
    "dilalti tablet": ("подъязычные таблетки", "sublingual tablets"),
    "dilalti damla": ("подъязычные капли", "sublingual drops"),
    "agiz ici sprey": ("спрей для полости рта", "oromucosal spray"),
    "agiz spreyi": ("спрей для полости рта", "oromucosal spray"),
    "deri spreyi": ("спрей для наружного применения", "cutaneous spray"),
    "topikal sprey": ("спрей для наружного применения", "cutaneous spray"),
    "topikal cozelti": ("раствор для наружного применения", "cutaneous solution"),
    "iv infuzyon icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инфузий", "powder for solution for infusion"
    ),
    "infuzyon icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инфузий", "powder for solution for infusion"
    ),
    "infuzyonluk cozelti icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инфузий", "powder for solution for infusion"
    ),
    "infuzyonluk cozelti icin toz": (
        "порошок для приготовления раствора для инфузий", "powder for solution for infusion"
    ),
    "enjeksiyonluk cozelti icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "enjeksiyonluk cozelti hazirlamak icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "enjeksiyonluk cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "iv infuzyon icin konsantre cozelti": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "infuzyon icin konsantre cozelti": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "infuzyonluk konsantre cozelti": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "konsantre infuzyon cozeltisi": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "konsantre cozelti": ("концентрат для приготовления раствора", "concentrate for solution"),
    "enjektabl solusyon": ("раствор для инъекций", "solution for injection"),
    "enjeksiyonluk solusyon": ("раствор для инъекций", "solution for injection"),
    "oral solusyon": ("раствор для приёма внутрь", "oral solution"),
    "solusyon": ("раствор", "solution"),
    "sert jelatin kapsul": ("капсулы", "capsules"),
    "yumusak jelatin kapsul": ("мягкие капсулы", "soft capsules"),
    "modifiye salimli kapsul": ("капсулы с модифицированным высвобождением", "modified-release capsules"),
    "kontrollu salimli kapsul": ("капсулы с контролируемым высвобождением", "controlled-release capsules"),
    "vajinal kapsul": ("вагинальные капсулы", "vaginal capsules"),
    "vajinal jel": ("вагинальный гель", "vaginal gel"),
    "rektal krem": ("ректальный крем", "rectal cream"),
    "rektal pomad": ("ректальная мазь", "rectal ointment"),
    "oral toz": ("порошок для приёма внутрь", "oral powder"),
    "kuru surup": ("порошок для приготовления сиропа", "powder for syrup"),
    "inhalasyon icin kuru toz": ("порошок для ингаляций", "inhalation powder"),
    "inhalasyon tozu": ("порошок для ингаляций", "inhalation powder"),
    "inhalasyon suspansiyonu": ("суспензия для ингаляций", "inhalation suspension"),
    "basincli inhalasyon suspansiyonu": ("суспензия для ингаляций под давлением", "pressurised inhalation suspension"),
    "inhalasyon cozeltisi": ("раствор для ингаляций", "inhalation solution"),
    "emme tableti": ("таблетки для рассасывания", "lozenges"),
    "agizda eriyen tablet": ("таблетки, диспергируемые в полости рта", "orodispersible tablets"),
    "kopuk": ("пена", "foam"),
    "macun": ("паста", "paste"),
    "pudra": ("присыпка", "powder"),
    "implant": ("имплантат", "implant"),
    "kartus": ("картридж", "cartridge"),
    # Пилот 20.10.2026 (AIRun 3) и разбор 13 тыс. названий: формы, на которых шаблон сдавался.
    "enjeksiyonluk/infuzyonluk cozelti": ("раствор для инъекций и инфузий", "solution for injection/infusion"),
    "enjeksiyonluk/infuzyonluk cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для инъекций и инфузий", "powder for solution for injection/infusion"
    ),
    "enjeksiyonluk/infuzyonluk cozelti hazirlamak icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инъекций и инфузий", "powder for solution for injection/infusion"
    ),
    "enjeksiyon ve infuzyon icin toz": (
        "порошок для приготовления раствора для инъекций и инфузий", "powder for solution for injection/infusion"
    ),
    "infuzyonluk cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для инфузий", "powder for solution for infusion"
    ),
    "infuzyonluk cozelti hazirlamak icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инфузий", "powder for solution for infusion"
    ),
    "infuzyonluk cozelti hazirlamak icin konsantre": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "infuzyonluk cozelti konsantresi": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "infuzyonluk cozelti hazirlamada kullanilacak konsantre icin toz": (
        "порошок для приготовления концентрата для приготовления раствора для инфузий",
        "powder for concentrate for solution for infusion",
    ),
    "enjeksiyonluk cozelti icin toz": (
        "порошок для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "enjeksiyonluk suspansiyon hazirlamak icin toz": (
        "порошок для приготовления суспензии для инъекций", "powder for suspension for injection"
    ),
    "enjeksiyonluk liyofilize toz": (
        "лиофилизат для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "enjeksiyon icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "enjeksiyonluk toz": ("порошок для приготовления раствора для инъекций", "powder for solution for injection"),
    "enjektabl toz": ("порошок для приготовления раствора для инъекций", "powder for solution for injection"),
    "oral suspansiyon hazirlamak icin kuru toz": (
        "порошок для приготовления суспензии для приёма внутрь", "powder for oral suspension"
    ),
    "oral suspansiyon hazirlamak icin toz": (
        "порошок для приготовления суспензии для приёма внутрь", "powder for oral suspension"
    ),
    "suspansiyon hazirlamak icin kuru toz": ("порошок для приготовления суспензии", "powder for suspension"),
    "oral cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для приёма внутрь", "powder for oral solution"
    ),
    "kullanima hazir inhalasyon tozu": ("порошок для ингаляций", "inhalation powder"),
    "kullanima hazir siringa": ("в предварительно заполненном шприце", "pre-filled syringe"),
    "nebulizasyon icin cozelti": ("раствор для ингаляций через небулайзер", "nebuliser solution"),
    "nebulizasyon icin inhalasyon suspansiyonu": (
        "суспензия для ингаляций через небулайзер", "nebuliser suspension"
    ),
    "rektal merhem": ("ректальная мазь", "rectal ointment"),
    "oftalmik pomat": ("глазная мазь", "eye ointment"),
    "oftalmik pomad": ("глазная мазь", "eye ointment"),
    "oftalmik merhem": ("глазная мазь", "eye ointment"),
    "oftalmik suspansiyon": ("глазная суспензия", "eye suspension"),
    "oftalmik solusyon": ("глазные капли", "eye drops"),
    "oftalmik cozelti": ("глазные капли", "eye drops"),
    "oftalmik jel": ("глазной гель", "eye gel"),
    "aerosol inhalasyon cozeltisi": ("аэрозоль для ингаляций", "pressurised inhalation solution"),
    "deriye uygulanacak sprey": ("спрей для наружного применения", "cutaneous spray"),
    "deriye uygulanacak cozelti": ("раствор для наружного применения", "cutaneous solution"),
    "deriye uygulanacak emulsiyon": ("эмульсия для наружного применения", "cutaneous emulsion"),
    "gastro direncli sert kapsul": ("кишечнорастворимые капсулы", "gastro-resistant capsules"),
    "uzatilmis salimli film kapli tablet": (
        "таблетки пролонгированного высвобождения, покрытые плёночной оболочкой",
        "prolonged-release film-coated tablets",
    ),
    "kontrollu salim tableti": ("таблетки с контролируемым высвобождением", "controlled-release tablets"),
    "degistirilmis salim tablet": ("таблетки с модифицированным высвобождением", "modified-release tablets"),
    "suda dagilabilen tablet": ("диспергируемые таблетки", "dispersible tablets"),
    "mikropellet kapsul": ("капсулы с микропеллетами", "micropellet capsules"),
    "aerosol inhaler": ("аэрозоль для ингаляций", "inhalation aerosol"),
    "sise": ("флакон", "bottle"),
}
# Флакон/ампула как форма, если та же упаковка указана и счётом («ICEREN FLAKON (1 FLAKON)»),
# не повторяется: остаётся «1 флакон».
_CONTAINER_FORMS = {
    "ampul": "ampoule", "flakon": "vial", "sise": "vial", "kartus": "cartridge",
    "kullanima hazir kalem": "pen", "kullanima hazir enjektor": "syringe",
    "kullanima hazir siringa": "syringe", "dolu enjektor": "syringe",
}
# Сокращения и английские слова источника → полная турецкая запись (после fold_tr).
_ABBREVIATIONS = (
    (r"(?:tablets|tabs?|tb)\.?", "tablet"),
    (r"(?:capsules|capsule|caps|cap)\.?", "kapsul"),
    (r"(?:vials?|flk)\.?", "flakon"),
    (r"amp\.", "ampul"),
    (r"enj\.", "enjeksiyon"),
    (r"inf\.", "infuzyon"),
    (r"coz\.", "cozelti"),
    (r"sol\.?", "solusyon"),
    (r"yum\.", "yumusak"),
    (r"ent\.", "enterik"),
    (r"i\.v\.?", "iv"),
    (r"i\.m\.?", "im"),
    (r"s\.c\.?", "sc"),
    (r"gram", "g"),
    (r"powder", "toz"),
    (r"solution", "cozelti"),
    (r"hard", "sert"),
    (r"gastro[\s-]?rezistan", "gastro direncli"),
    (r"pediyatrik", "pediatrik"),
)
# Сокращение с точкой может стоять вплотную к слову: «ENT.TABLET», «YUM.KAPSUL».
_ABBREVIATION_RES = tuple(
    (re.compile(rf"(?<![a-z]){pattern}" + ("" if pattern.endswith(r"\.") else r"(?![a-z])")), f" {full} ")
    for pattern, full in _ABBREVIATIONS
)
# Форма, разорванная фасовкой: «UZATILMIS SALIMLI 30 TABLET» → «30 UZATILMIS SALIMLI TABLET».
_SPLIT_FORM_RE = re.compile(
    r"(uzatilmis salimli|kontrollu salimli|agizda dagilan|enterik kapli|gastro direncli|film kapli|"
    r"efervesan|cigneme|sert|yumusak|mikropellet|suda dagilabilen) (\d+) ((?:film )?(?:tablet|kapsul))\b"
)


def _expand_source(rest: str) -> str:
    for pattern, full in _ABBREVIATION_RES:
        rest = pattern.sub(full, rest)
    rest = re.sub(r"(?<=[a-z])\s*/\s*(?=[a-z])", "/", rest)
    rest = _SPLIT_FORM_RE.sub(r"\2 \1 \3", re.sub(r"\s+", " ", rest).strip())
    return rest


FORM_WORDS = {word for phrase in FORM_PHRASES for word in phrase.split()}
_FORM_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in sorted(FORM_PHRASES, key=len, reverse=True)) + r")\b"
)

# Единица фасовки после числа → ключ medicine_reference._COUNT_UNITS.
_PACK_WORDS = {
    "adet": "piece", "ampul": "ampoule", "flakon": "vial", "sase": "sachet",
    "kalem": "pen", "enjektor": "syringe", "doz": "dose", "puskurtme": "dose",
    "tup": "tube", "sise": "vial", "flaster": "patch", "kutu": "box",
    "blister": "blister", "kartus": "cartridge",
}
# Обозначения линейки после дозировки («200 MG CR») — сохраняются как в источнике.
_SERIES_WORDS = {
    "sr", "xr", "mr", "cr", "xl", "la", "er", "ec", "odt", "retard", "forte", "fort",
    "plus", "mite", "depot", "duo", "junior", "max",
}
# Уточнения после формы → RU/EN.
_MODIFIERS = {
    "setli": ("с системой", "with set"),
    "setsiz": ("без системы", "without set"),
    "pediatrik": ("детский", "paediatric"),
    "cocuk": ("детский", "for children"),
    "bebek": ("для младенцев", "for infants"),
    "yetiskin": ("для взрослых", "adult"),
    "steril": ("стерильный", "sterile"),
    "sekersiz": ("без сахара", "sugar-free"),
    "centikli": ("с риской", "scored"),
    "oftalmik": ("для глаз", "ophthalmic"),
}
# Уточнения из нескольких слов: «TOZ VE COZUCU» — порошок с растворителем.
_PHRASE_MODIFIERS_RE = re.compile(r"ve cozucu(?:su)?\b")
_PHRASE_MODIFIERS = ("с растворителем", "with solvent")
# Слова-связки источника, которые в название не переносятся: «COZELTI ICEREN AMPUL».
_SKIP_WORDS = {"iceren"}
_PACK_RE = re.compile(r"(\d+)\s+(" + "|".join(_PACK_WORDS) + r")\b")

_UNITS = {
    "mg": ("мг", "mg"), "mcg": ("мкг", "mcg"), "mkg": ("мкг", "mcg"), "µg": ("мкг", "mcg"),
    "g": ("г", "g"), "gr": ("г", "g"), "ml": ("мл", "ml"), "l": ("л", "l"),
    "iu": ("МЕ", "IU"), "ui": ("МЕ", "IU"), "mmol": ("ммоль", "mmol"), "meq": ("мэкв", "mEq"),
    "doz": ("доза", "dose"), "puskurtme": ("доза", "dose"), "saat": ("ч", "h"), "h": ("ч", "h"),
    "tu": ("ТЕ", "TU"), "u": ("ЕД", "U"),
}
_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:mg|mcg|mkg|µg|gr|g|ml|iu|ui|mmol|meq|tu|u)"
_PER = r"(?:mg|mcg|g|ml|doz|puskurtme|saat|h|l)"
_DOSE_RE = re.compile(
    rf"(?:%\s*({_NUM})|({_NUM})\s*%|({_NUM})\s*({_UNIT})(?:\s*/\s*({_NUM})?\s*({_PER}))?)(?![a-z])"
)
_MULTI_RE = re.compile(rf"(\d+)\s*x\s*({_NUM})\s*(ml|g|gr)\b")
# Несколько веществ с одной единицей: «400/57 MG», «100/62,5/25 MCG».
_COMBO_DOSE_RE = re.compile(rf"({_NUM}(?:\s*/\s*{_NUM})+)\s*({_UNIT})(?![a-z])")
# Разделитель перед следующей дозировкой: «1 MG/ML + 50 MG/ML», «200 MG VE 50 MG», «250MG/1MG».
_JOINER_RE = re.compile(r"\s*(\+|/|ve(?=\s+[\d%]))\s*")
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


def is_form_word(token: Any) -> bool:
    """Слово лекарственной формы или его сокращение («SOL.», «TB», «CAPSULES») — не бренд."""
    folded = fold_tr(token)
    expanded = _expand_source(folded).split()
    return folded in FORM_WORDS or bool(expanded) and all(word in FORM_WORDS for word in expanded)


def _brand_tokens(tokens: list[str]) -> list[str]:
    """Первые слова названия — до дозировки, формы или пути введения."""
    brand: list[str] = []
    for token in tokens:
        folded = fold_tr(token).strip(",;")
        if (
            folded[:1].isdigit()
            or folded.startswith("%")
            or folded in FORM_WORDS
            # «KAYEXALAT POWDER», «RINGER BIOSEL ENJEKTABL SOL.»; «OLFREX EASY TAB» — бренд.
            or (brand and folded != "tab" and is_form_word(folded))
            or _ROUTE_ABBR_RE.fullmatch(folded)
        ):
            break
        brand.append(token)
    return brand


def paragraph_brand(name: Any, active_ingredient: Any = "") -> str:
    """Бренд для метки {BRAND} в абзацах инструкций: первые слова названия до дозировки.

    Пусто, если короче 3 букв или совпадает с МНН: «IBUPROFEN 400 MG» — это
    вещество, и в переводе оно должно стать «ибупрофеном», а не меткой.
    """
    brand = " ".join(_brand_tokens(re.sub(r"[()]", " ", str(name or "")).split()))
    words = set(re.findall(r"[a-z]+", fold_tr(brand)))
    if sum(map(len, words)) < 3:
        return ""
    inn_words = {word for word in re.findall(r"[a-z]+", fold_tr(active_ingredient)) if len(word) >= 4}
    return "" if words & inn_words else brand


def build_medicine_title(name: Any) -> Optional[dict[str, str]]:
    """RU/EN-название из исходного названия или None, если разобрать нельзя."""
    source = re.sub(r"[()]", " ", str(name or "")).strip()
    tokens = source.split()
    brand = _brand_tokens(tokens)
    if not brand or len(brand) == len(tokens):
        return None
    rest = _expand_source(fold_tr(" ".join(tokens[len(brand):])))

    strengths = {"ru": [], "en": []}
    volumes = {"ru": [], "en": []}
    grams = {"ru": [], "en": []}
    packs = {"ru": [], "en": []}
    # Разделитель перед каждой дозировкой («+», «/», «ve») — как в источнике.
    strength_joiners: list[Optional[str]] = []
    gram_joiners: list[Optional[str]] = []
    pack_units: list[str] = []
    series: list[str] = []
    forms: list[tuple[str, str]] = []
    form_keys: list[str] = []
    modifiers: list[tuple[str, str]] = []
    route = None
    joiner = None
    while rest:
        joiner_match = _JOINER_RE.match(rest)
        if joiner_match:
            joiner = joiner_match.group(1)
            rest = rest[joiner_match.end():]
        rest = rest.lstrip(" ,+-")
        if not rest:
            break
        multi = _MULTI_RE.match(rest)
        pack = _PACK_RE.match(rest)
        combo = _COMBO_DOSE_RE.match(rest)
        dose = _DOSE_RE.match(rest)
        form_match = _FORM_RE.match(rest)
        counted = re.match(r"(\d+)\s+", rest)
        counted_form = _FORM_RE.match(rest[counted.end():]) if counted else None
        phrase_modifier = _PHRASE_MODIFIERS_RE.match(rest)
        word = re.match(r"[a-z]+\b", rest)
        if multi:
            count, size, unit = multi.groups()
            unit = "g" if unit == "gr" else unit
            volumes["ru"].append(f"{count} шт. по {_num(size, 'ru')} {_UNITS[unit][0]}")
            volumes["en"].append(f"{count} × {_num(size, 'en')} {_UNITS[unit][1]}")
            rest = rest[multi.end():]
        elif pack:
            number, pack_word = pack.groups()
            for locale in ("ru", "en"):
                packs[locale].append(_pack(number, _PACK_WORDS[pack_word], locale))
            pack_units.append(_PACK_WORDS[pack_word])
            rest = rest[pack.end():]
        elif combo:
            numbers, unit = combo.groups()
            for index, locale in enumerate(("ru", "en")):
                values = "/".join(_num(number.strip(), locale) for number in numbers.split("/"))
                strengths[locale].append(f"{values} {_UNITS[unit][index]}")
            strength_joiners.append(joiner)
            rest = rest[combo.end():]
        elif dose:
            for locale in ("ru", "en"):
                text, kind = _format_dose(dose, locale)
                {"strength": strengths, "volume": volumes, "grams": grams}[kind][locale].append(text)
            if kind == "strength":
                strength_joiners.append(joiner)
            elif kind == "grams":
                gram_joiners.append(joiner)
            rest = rest[dose.end():]
        elif form_match:
            if FORM_PHRASES[form_match.group(0)] not in forms:
                forms.append(FORM_PHRASES[form_match.group(0)])
                form_keys.append(form_match.group(0))
            rest = rest[form_match.end():]
        elif counted_form:
            # «15 FILM TABLET», «(80 TABLET)»: число перед формой — фасовка.
            # Повтор «24 FILM TABLET (24 TABLET)» не дублируется; другое число
            # («KLACID MR 500 … TABLET (20 TABLET)» — 500 мг без единицы) — не разобрать.
            number = counted.group(1)
            if packs["ru"] and f"{number} шт." not in packs["ru"]:
                return None
            if not forms:
                forms.append(FORM_PHRASES[counted_form.group(0)])
                form_keys.append(counted_form.group(0))
            if f"{number} шт." not in packs["ru"]:
                packs["ru"].append(f"{number} шт.")
                packs["en"].append(f"{number} {'pc' if number == '1' else 'pcs'}")
            rest = rest[counted.end() + counted_form.end():]
        elif _ROUTE_ABBR_RE.match(rest) and route is None:
            route_match = _ROUTE_ABBR_RE.match(rest)
            codes = re.findall(r"im|iv|sc", route_match.group(0))
            route = (
                ", ".join(_ROUTE_ABBR[c][0] for c in codes),
                "/".join(_ROUTE_ABBR[c][1] for c in codes),
            )
            rest = rest[route_match.end():]
        elif phrase_modifier:
            modifiers.append(_PHRASE_MODIFIERS)
            rest = rest[phrase_modifier.end():]
        elif word and word.group(0) in _SERIES_WORDS:
            series.append(word.group(0).upper())
            rest = rest[word.end():]
        elif word and word.group(0) in _MODIFIERS:
            modifiers.append(_MODIFIERS[word.group(0)])
            rest = rest[word.end():]
        elif word and word.group(0) in _SKIP_WORDS:
            rest = rest[word.end():]
        else:
            return None
        joiner = None

    forms = [
        form for key, form in zip(form_keys, forms) if _CONTAINER_FORMS.get(key) not in pack_units
    ]
    if not forms and not (strengths["ru"] or volumes["ru"] or grams["ru"]):
        return None
    # Граммы у мазей/кремов/гелей/порошков — масса упаковки, у прочих — дозировка.
    grams_are_volume = bool(forms) and forms[0][1].split()[-1] in _MASS_FORMS
    for locale in ("ru", "en"):
        (volumes if grams_are_volume else strengths)[locale][:0] = grams[locale]
    if not grams_are_volume:
        strength_joiners[:0] = gram_joiners
    result = {}
    for index, locale in enumerate(("ru", "en")):
        values = strengths[locale]
        strength = values[:1]
        for value, value_joiner in zip(values[1:], strength_joiners[1:]):
            if value_joiner == "/":
                strength[-1] += f"/{value}"
            elif value_joiner:  # «+» и «ve» — несколько веществ
                strength[-1] += f" + {value}"
            elif "/" in value and "/" in values[0]:
                # «12MG/1.2ML (10MG/ML)»: вторая концентрация — в скобках, как в источнике.
                strength.append(f"({value})")
            else:
                strength.append(value)
        head = " ".join(brand + strength + series)
        parts = [head]
        if forms:
            parts.append(", ".join(form[index] for form in forms) + (f" ({route[index]})" if route else ""))
        elif route:
            parts.append(route[index])
        parts.extend(modifier[index] for modifier in modifiers)
        parts.extend(volumes[locale])
        parts.extend(packs[locale])
        result[locale] = ", ".join(parts)
    return result
