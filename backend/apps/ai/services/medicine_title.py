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
from functools import lru_cache
from typing import Any, Optional

from apps.ai.services.medicine_reference import _COUNT_UNITS, fold_tr, ru_plural
from apps.ai.services.ownership import SOURCE_NAME_KEY

# Турецкая форма (после fold_tr) → (RU, EN). Сравнение — по самой длинной фразе.
FORM_PHRASES = {
    "uzatilmis salimli film tablet": (
        "таблетки пролонгированного высвобождения, покрытые плёночной оболочкой",
        "prolonged-release film-coated tablets",
    ),
    "uzatilmis salimli tablet": ("таблетки пролонгированного высвобождения", "prolonged-release tablets"),
    "kontrollu salimli tablet": ("таблетки с контролируемым высвобождением", "controlled-release tablets"),
    "kontrollu salimli film tablet": (
        "таблетки с контролируемым высвобождением, покрытые плёночной оболочкой",
        "controlled-release film-coated tablets",
    ),
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
    "enterik kapli pellet tablet": ("кишечнорастворимые таблетки", "gastro-resistant tablets"),
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
    "tek dozluk goz damlasi": ("глазные капли в однодозовых контейнерах", "single-dose eye drops"),
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
    "deri cozeltisi": ("раствор для наружного применения", "cutaneous solution"),
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
    "enjeksiyon/infuzyon icin cozelti": ("раствор для инъекций и инфузий", "solution for injection/infusion"),
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
    "nebulizasyon icin tek dozluk inhalasyon cozeltisi": (
        "раствор для ингаляций через небулайзер в однодозовых контейнерах", "single-dose nebuliser solution"
    ),
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
    "likit jel": ("жидкий гель", "liquid gel"),
    "enjeksiyon cozelti": ("раствор для инъекций", "solution for injection"),  # «ENJ. COZ.»
    "konsantre infuzyonluk cozelti icin toz": (
        "порошок для приготовления концентрата для приготовления раствора для инфузий",
        "powder for concentrate for solution for infusion",
    ),
    "degistirilmis salimli sert kapsul": ("капсулы с модифицированным высвобождением", "modified-release hard capsules"),
    "suspansiyon iceren olculu doz inhaler": (
        "суспензия для ингаляций дозированная", "pressurised inhalation suspension, metered dose"
    ),
    "rahim ici sistem": ("внутриматочная система", "intrauterine system"),
}
# Слова форм до 24.10.2026: по ним считается бренд для метки {BRAND} в памяти абзацев
# (paragraph_brand). Новая форма не должна менять этот бренд — иначе у лекарства меняются
# ключи абзацев, и готовые переводы инструкции не находятся.
_LEGACY_FORM_PHRASES = tuple(FORM_PHRASES)
# Пилот 24.10.2026: растворы для диализа и в/в растворы в пакетах, порошки с растворителем.
FORM_PHRASES.update({
    "periton diyaliz cozeltisi": ("раствор для перитонеального диализа", "peritoneal dialysis solution"),
    "periton diyaliz solusyonu": ("раствор для перитонеального диализа", "peritoneal dialysis solution"),
    "periton diyaliz solusyon": ("раствор для перитонеального диализа", "peritoneal dialysis solution"),
    "periton diyaliz": ("раствор для перитонеального диализа", "peritoneal dialysis solution"),
    "periton dializ cozeltisi": ("раствор для перитонеального диализа", "peritoneal dialysis solution"),
    "periton dializ": ("раствор для перитонеального диализа", "peritoneal dialysis solution"),
    "hemodiyaliz/hemofiltrasyon cozeltisi": (
        "раствор для гемодиализа и гемофильтрации", "haemodialysis and haemofiltration solution"
    ),
    "dengeli elektrolit cozeltisi": ("сбалансированный электролитный раствор", "balanced electrolyte solution"),
    "dengeli elektrolit solusyonu": ("сбалансированный электролитный раствор", "balanced electrolyte solution"),
    "dengeli elektrolit solusyon": ("сбалансированный электролитный раствор", "balanced electrolyte solution"),
    "dengeli elektrolit": ("сбалансированный электролитный раствор", "balanced electrolyte solution"),
    "cozeltisi": ("раствор", "solution"),
    "solusyonu": ("раствор", "solution"),
    "enjeksiyonluk cozelti tozu": (
        "порошок для приготовления раствора для инъекций", "powder for solution for injection"
    ),
    "cozelti tozu": ("порошок для приготовления раствора", "powder for solution"),
    # Пилот 6 (24.10.2026, самые востребованные по Вордстату): формы, на которых шаблон сдавался.
    "tek kullanimlik oral cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для приёма внутрь", "powder for oral solution"
    ),
    "goz merhemi": ("глазная мазь", "eye ointment"),
    "yavas salimli film tablet": (
        "таблетки пролонгированного высвобождения, покрытые плёночной оболочкой",
        "prolonged-release film-coated tablets",
    ),
    "yavas salimli tablet": ("таблетки пролонгированного высвобождения", "prolonged-release tablets"),
    "kapli tablet": ("таблетки, покрытые оболочкой", "coated tablets"),
    # Партия 7 (25.10.2026): формы самых востребованных лекарств, на которых шаблон сдавался.
    "deri merhemi": ("мазь для наружного применения", "ointment for cutaneous use"),
    "infuzyon solusyonu": ("раствор для инфузий", "solution for infusion"),
    "scalp cozelti": ("раствор для кожи головы", "scalp solution"),
    "oral suspansiyon icin kuru toz": (
        "порошок для приготовления суспензии для приёма внутрь", "powder for oral suspension"
    ),
    # Партия 8 (25.10.2026): формы, на которых шаблон сдавался у 81 лекарства.
    "sakiz": ("жевательная резинка", "chewing gum"),
    "kase": ("облатки", "cachets"),
    "doz ayarli burun spreyi": ("дозированный назальный спрей", "metered-dose nasal spray"),
    "oral mukozaya uygulanacak sprey": ("спрей для слизистой оболочки полости рта", "oromucosal spray"),
    "surup hazirlamak icin toz": ("порошок для приготовления сиропа", "powder for syrup"),
    "infuzyon konsantre cozeltisi": (
        "концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"
    ),
    "iv infuzyonluk cozelti hazirlamak icin konsantre": (
        "концентрат для приготовления раствора для внутривенных инфузий",
        "concentrate for solution for intravenous infusion",
    ),
    "enjeksiyon ve infuzyon icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инъекций и инфузий",
        "powder for solution for injection/infusion",
    ),
    "cerrahi kullanim icin irrigasyon cozeltisi": (
        "раствор для ирригации при хирургических вмешательствах", "solution for surgical irrigation"
    ),
    "hemofiltrasyon solusyonu": ("раствор для гемофильтрации", "haemofiltration solution"),
    "hemofiltrasyon cozeltisi": ("раствор для гемофильтрации", "haemofiltration solution"),
    "nebulizasyon icin inhalasyon cozeltisi": ("раствор для ингаляций через небулайзер", "nebuliser solution"),
    "nebulizasyon suspansiyonu": ("суспензия для ингаляций через небулайзер", "nebuliser suspension"),
    "olculu dozlu inhalasyon suspansiyonu": (
        "дозированная суспензия для ингаляций", "metered-dose inhalation suspension"
    ),
    "inhalasyon icin cozelti iceren olculu dozlu aerosol": (
        "дозированный аэрозоль для ингаляций", "metered-dose inhalation aerosol"
    ),
    "aerosol inhalasyonu, suspansiyon": ("аэрозоль для ингаляций, суспензия", "pressurised inhalation suspension"),
    "degistirilmis salimli film kapli tablet": (
        "таблетки с модифицированным высвобождением, покрытые плёночной оболочкой",
        "modified-release film-coated tablets",
    ),
    "kontrollu salimli film kapli tablet": (
        "таблетки с контролируемым высвобождением, покрытые плёночной оболочкой",
        "controlled-release film-coated tablets",
    ),
    "kontrollu salimli film tableti": (
        "таблетки с контролируемым высвобождением, покрытые плёночной оболочкой",
        "controlled-release film-coated tablets",
    ),
    "film kapli vajinal tablet": (
        "вагинальные таблетки, покрытые плёночной оболочкой", "film-coated vaginal tablets"
    ),
    "enterik kapli mikropellet kapsul": (
        "кишечнорастворимые капсулы с микропеллетами", "gastro-resistant micropellet capsules"
    ),
    "enterik kapli mikropellet iceren kapsul": (
        "кишечнорастворимые капсулы с микропеллетами", "gastro-resistant micropellet capsules"
    ),
    "enterik mikropellet kapsul": (
        "кишечнорастворимые капсулы с микропеллетами", "gastro-resistant micropellet capsules"
    ),
    "sac losyonu": ("лосьон для кожи головы", "scalp lotion"),
    # Партия Claude 200 и 1047 (25.10.2026).
    "enterik kapli film tablet": ("кишечнорастворимые таблетки, покрытые плёночной оболочкой", "gastro-resistant film-coated tablets"),
    "agizda cozunebilir tablet": ("таблетки, диспергируемые в полости рта", "orodispersible tablets"),
    "enjeksiyon toz": ("порошок для приготовления раствора для инъекций", "powder for solution for injection"),
    "iv infuzyonluk cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для внутривенных инфузий", "powder for solution for intravenous infusion"
    ),
    # TD-029 (31.10.2026): формы, на которых шаблон сдавался по всему каталогу.
    "injection": ("для инъекций", "for injection"),
    "vajinal yumusak kapsul": ("вагинальные мягкие капсулы", "soft vaginal capsules"),
    "ovul": ("вагинальные суппозитории", "pessaries"),
    "rektal suspansiyon": ("ректальная суспензия", "rectal suspension"),
    "rektal cozelti": ("раствор для ректального введения", "rectal solution"),
    "lavman": ("клизма", "enema"),
    "uzatilmis salimli sert kapsul": ("капсулы пролонгированного высвобождения", "prolonged-release hard capsules"),
    "degistirilmis salimli kapsul": ("капсулы с модифицированным высвобождением", "modified-release capsules"),
    "enterik sert kapsul": ("кишечнорастворимые капсулы", "gastro-resistant capsules"),
    "uzun etkili film tablet": (
        "таблетки пролонгированного действия, покрытые плёночной оболочкой", "prolonged-release film-coated tablets"
    ),
    "uzun etkili tablet": ("таблетки пролонгированного действия", "prolonged-release tablets"),
    "goz ve kulak damlasi": ("глазные и ушные капли", "eye and ear drops"),
    "oral granul": ("гранулы для приёма внутрь", "oral granules"),
    "suspansiyon hazirlamak icin granul": ("гранулы для приготовления суспензии", "granules for suspension"),
    "oral suspansiyon hazirlamak icin granul": (
        "гранулы для приготовления суспензии для приёма внутрь", "granules for oral suspension"
    ),
    "surup hazirlamak icin kuru toz": ("порошок для приготовления сиропа", "powder for syrup"),
    "inhalasyon icin toz iceren blister": ("порошок для ингаляций в блистерах", "inhalation powder in blisters"),
    "aerosol inhalasyonu suspansiyon": ("аэрозоль для ингаляций, суспензия", "pressurised inhalation suspension"),
    "basincli inhalasyon suspansiyon": ("суспензия для ингаляций под давлением", "pressurised inhalation suspension"),
    "inhalasyon icin olculu dozlu aerosol": ("дозированный аэрозоль для ингаляций", "metered-dose inhalation aerosol"),
    "cozelti iceren inhalasyon aerosolu": ("аэрозоль для ингаляций, раствор", "pressurised inhalation solution"),
    "inhalasyon tozu bolunmus dozlu": ("порошок для ингаляций дозированный", "inhalation powder, pre-dispensed"),
    "nebulizasyon cozeltisi": ("раствор для ингаляций через небулайзер", "nebuliser solution"),
    "nebulizasyon icin tek dozluk inhalasyon suspansiyonu": (
        "суспензия для ингаляций через небулайзер в однодозовых контейнерах", "single-dose nebuliser suspension"
    ),
    "topikal jel": ("гель для наружного применения", "cutaneous gel"),
    "deri kremi": ("крем для наружного применения", "cream for cutaneous use"),
    "tirnak cilasi": ("лак для ногтей", "medicated nail lacquer"),
    "tirnak cilasi seti": ("набор лака для ногтей", "medicated nail lacquer set"),
    "agizda dagilabilir tablet": ("таблетки, диспергируемые в полости рта", "orodispersible tablets"),
    "cozunebilir tablet": ("растворимые таблетки", "soluble tablets"),
    "cignenebilir/cozunebilir tablet": ("жевательные растворимые таблетки", "chewable/soluble tablets"),
    "film kapli modifiye salim tablet": (
        "таблетки с модифицированным высвобождением, покрытые плёночной оболочкой",
        "modified-release film-coated tablets",
    ),
    "uzatilmis salim tablet": ("таблетки пролонгированного высвобождения", "prolonged-release tablets"),
    "inhalasyon icin kapsul": ("капсулы с порошком для ингаляций", "inhalation powder, hard capsules"),
    "burun spreyi suspansiyonu": ("назальный спрей, суспензия", "nasal spray, suspension"),
    "burun spreyi, suspansiyon": ("назальный спрей, суспензия", "nasal spray, suspension"),
    "oral liyofilizat": ("лиофилизат для приёма внутрь", "oral lyophilisate"),
    "oral suspansiyon icin granul": (
        "гранулы для приготовления суспензии для приёма внутрь", "granules for oral suspension"
    ),
    "infuzyonluk ve oral cozelti": ("раствор для инфузий и приёма внутрь", "solution for infusion and oral use"),
    "infuzyonluk ve oral cozelti hazirlamak icin toz": (
        "порошок для приготовления раствора для инфузий и приёма внутрь", "powder for solution for infusion and oral use"
    ),
    "infuzyonluk ve oral cozelti hazirlamak icin liyofilize toz": (
        "лиофилизат для приготовления раствора для инфузий и приёма внутрь", "powder for solution for infusion and oral use"
    ),
    "kullanima hazir dolu enjeksiyon kalemi icinde enjeksiyonluk cozelti": (
        "раствор для инъекций в шприц-ручке", "solution for injection in pre-filled pen"
    ),
    "enjeksiyonluk uzatilmis salimli suspansiyon": (
        "суспензия пролонгированного высвобождения для инъекций", "prolonged-release suspension for injection"
    ),
    "enjeksiyon icin uzun salimli suspansiyon": (
        "суспензия пролонгированного высвобождения для инъекций", "prolonged-release suspension for injection"
    ),
    "uzatilmis salimli sc enjeksiyonluk cozelti": (
        "раствор пролонгированного высвобождения для подкожных инъекций", "prolonged-release solution for subcutaneous injection"
    ),
    "elektrolit iv infuzyon icin cozelti": (
        "раствор электролитов для внутривенных инфузий", "electrolyte solution for intravenous infusion"
    ),
    "intratekal infuzyonluk cozelti": ("раствор для интратекальных инфузий", "solution for intrathecal infusion"),
    "intratrakeal suspansiyon": ("суспензия для эндотрахеального введения", "endotracheal suspension"),
    "dental kartus": ("стоматологический картридж", "dental cartridge"),
    "uc bolmeli": (
        "раствор аминокислот, раствор глюкозы и липидная эмульсия для инфузий",
        "amino acid and glucose solutions with lipid emulsion for infusion",
    ),
    "uc bolmeli elektrolitli": (
        "раствор аминокислот с электролитами, раствор глюкозы и липидная эмульсия для инфузий",
        "amino acid solution with electrolytes, glucose solution and lipid emulsion for infusion",
    ),
    "kullanima hazir dolu enjektor": ("в предварительно заполненном шприце", "pre-filled syringe"),
    "kullanima hazir siringada enjeksiyonluk cozelti": (
        "раствор для инъекций в предварительно заполненном шприце", "solution for injection in pre-filled syringe"
    ),
    "enjektor": ("в шприце", "in syringe"),
    "oto enjektor": ("автоинъектор", "auto-injector"),
    "basincli inhalasyon, suspansiyon": ("суспензия для ингаляций под давлением", "pressurised inhalation suspension"),
    "inhalasyon icin": ("для ингаляций", "for inhalation"),
    "iv infuzyon/sc enjeksiyon icin cozelti": (
        "раствор для в/в инфузий и п/к инъекций", "solution for IV infusion/SC injection"
    ),
    "suspansiyon hazirlamak icin toz": ("порошок для приготовления суспензии", "powder for suspension"),
    "suspansiyon icin kuru toz": ("порошок для приготовления суспензии", "powder for suspension"),
    "uzatilmis salimli kapli tablet": (
        "таблетки пролонгированного высвобождения, покрытые оболочкой", "prolonged-release coated tablets"
    ),
    "uzatilmis salimli granul": ("гранулы пролонгированного высвобождения", "prolonged-release granules"),
    "yavas salimli kapsul": ("капсулы пролонгированного высвобождения", "prolonged-release capsules"),
    "goz damlasi suspansiyonu": ("глазные капли, суспензия", "eye drops, suspension"),
    "goz damlasi, suspansiyon": ("глазные капли, суспензия", "eye drops, suspension"),
    "goz damlasi, cozelti": ("глазные капли, раствор", "eye drops, solution"),
    "intravitreal enjeksiyonluk cozelti": ("раствор для интравитреального введения", "solution for intravitreal injection"),
    "intravitreal enjeksiyon icin cozelti": ("раствор для интравитреального введения", "solution for intravitreal injection"),
    "intrakameral enjeksiyonluk cozelti tozu": (
        "порошок для приготовления раствора для внутрикамерного введения", "powder for solution for intracameral injection"
    ),
    "infuzyon konsantresi": ("концентрат для приготовления раствора для инфузий", "concentrate for solution for infusion"),
})
# Форма «для инъекций/инфузий» — турецкие варианты записи одной и той же формы.
_FORM_PURPOSES = {
    "iv infuzyonluk": ("для внутривенных инфузий", "for intravenous infusion"),
    "iv infuzyon icin": ("для внутривенных инфузий", "for intravenous infusion"),
    "iv infuzyon": ("для внутривенных инфузий", "for intravenous infusion"),
    "enjeksiyonluk": ("для инъекций", "for injection"),
    "enjeksiyon icin": ("для инъекций", "for injection"),
    "enjeksiyon": ("для инъекций", "for injection"),
    "enjektabl": ("для инъекций", "for injection"),
    "infuzyonluk": ("для инфузий", "for infusion"),
    "infuzyon icin": ("для инфузий", "for infusion"),
    "infuzyon": ("для инфузий", "for infusion"),
    "perfuzyon icin": ("для инфузий", "for infusion"),
    "enjeksiyonluk/infuzyonluk": ("для инъекций и инфузий", "for injection/infusion"),
    "infuzyonluk/enjeksiyonluk": ("для инъекций и инфузий", "for injection/infusion"),
    "enjeksiyon/infuzyon icin": ("для инъекций и инфузий", "for injection/infusion"),
    "enjeksiyon ve infuzyon icin": ("для инъекций и инфузий", "for injection/infusion"),
    "enjeksiyonluk veya infuzyonluk": ("для инъекций и инфузий", "for injection/infusion"),
}
_FORM_PREPARE = ("icin", "hazirlamak icin", "hazirlamada kullanilacak")
for _purpose, (_ru, _en) in _FORM_PURPOSES.items():
    # «IV INFUZYON COZELTISI» без порошка разбирается как раньше: форма + путь введения.
    _iv = _purpose.startswith("iv ")
    for _word in ("cozelti", "cozeltisi", "solusyon", "solusyonu"):
        if not _iv:
            FORM_PHRASES.setdefault(f"{_purpose} {_word}", (f"раствор {_ru}", f"solution {_en}"))
            FORM_PHRASES.setdefault(f"{_purpose} konsantre {_word}", (
                f"концентрат для приготовления раствора {_ru}", f"concentrate for solution {_en}"
            ))
            FORM_PHRASES.setdefault(f"konsantre {_purpose} {_word}", (
                f"концентрат для приготовления раствора {_ru}", f"concentrate for solution {_en}"
            ))
        FORM_PHRASES.setdefault(f"konsantre {_purpose} {_word} hazirlamak icin liyofilize toz", (
            f"лиофилизат для приготовления концентрата для приготовления раствора {_ru}",
            f"powder for concentrate for solution {_en}",
        ))
        for _prepare in _FORM_PREPARE:
            FORM_PHRASES.setdefault(f"{_purpose} {_word} {_prepare} konsantre", (
                f"концентрат для приготовления раствора {_ru}", f"concentrate for solution {_en}"
            ))
            for _powder in ("toz", "kuru toz"):
                FORM_PHRASES.setdefault(f"{_purpose} {_word} {_prepare} {_powder}", (
                    f"порошок для приготовления раствора {_ru}", f"powder for solution {_en}"
                ))
            FORM_PHRASES.setdefault(f"{_purpose} {_word} {_prepare} liyofilize toz", (
                f"лиофилизат для приготовления раствора {_ru}", f"powder for solution {_en}"
            ))
            FORM_PHRASES.setdefault(f"{_purpose} {_word} {_prepare} konsantre icin toz", (
                f"порошок для приготовления концентрата для приготовления раствора {_ru}",
                f"powder for concentrate for solution {_en}",
            ))
        FORM_PHRASES.setdefault(f"{_purpose} {_word} konsantresi", (
            f"концентрат для приготовления раствора {_ru}", f"concentrate for solution {_en}"
        ))
        FORM_PHRASES.setdefault(f"{_purpose} {_word} konsantresi icin toz", (
            f"порошок для приготовления концентрата для приготовления раствора {_ru}",
            f"powder for concentrate for solution {_en}",
        ))
    for _word in ("suspansiyon", "suspansiyonu"):
        if not _iv:
            FORM_PHRASES.setdefault(f"{_purpose} {_word}", (f"суспензия {_ru}", f"suspension {_en}"))
        for _prepare in _FORM_PREPARE:
            FORM_PHRASES.setdefault(f"{_purpose} {_word} {_prepare} toz", (
                f"порошок для приготовления суспензии {_ru}", f"powder for suspension {_en}"
            ))
            FORM_PHRASES.setdefault(f"{_purpose} {_word} {_prepare} liyofilize toz", (
                f"лиофилизат для приготовления суспензии {_ru}", f"powder for suspension {_en}"
            ))
    FORM_PHRASES.setdefault(f"{_purpose} liyofilize toz", (
        f"лиофилизат для приготовления раствора {_ru}", f"powder for solution {_en}"
    ))
    FORM_PHRASES.setdefault(f"{_purpose} toz", (
        f"порошок для приготовления раствора {_ru}", f"powder for solution {_en}"
    ))
    FORM_PHRASES.setdefault(f"{_purpose} konsantre cozelti icin toz", (
        f"порошок для приготовления концентрата для приготовления раствора {_ru}",
        f"powder for concentrate for solution {_en}",
    ))
# Флакон/ампула как форма, если та же упаковка указана и счётом («ICEREN FLAKON (1 FLAKON)»),
# не повторяется: остаётся «1 флакон».
_CONTAINER_FORMS = {
    "ampul": "ampoule", "flakon": "vial", "sise": "vial", "kartus": "cartridge",
    "kullanima hazir kalem": "pen", "kullanima hazir enjektor": "syringe",
    "kullanima hazir siringa": "syringe", "dolu enjektor": "syringe",
    "kullanima hazir dolu enjektor": "syringe", "enjektor": "syringe",
}
# Сокращения и английские слова источника → полная турецкая запись (после fold_tr).
_ABBREVIATIONS = (
    (r"(?:tablets|tabs?|tb)\.?", "tablet"),
    (r"(?:capsules|capsule|caps|cap)\.?", "kapsul"),
    (r"(?:vials?|flk)\.?", "flakon"),
    (r"amp\.", "ampul"),
    (r"enj\.", "enjeksiyon"),
    (r"enj(?=/)", "enjeksiyon"),  # «ENJ/INF.»
    (r"inf\.", "infuzyon"),
    (r"coz\.", "cozelti"),
    (r"sol\.?", "solusyon"),
    (r"yum\.", "yumusak"),
    (r"ent\.", "enterik"),
    (r"i\.u\.?", "iu"),
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
# С 24.10.2026, только для названия (см. _LEGACY_FORM_PHRASES): опечатки источника.
_TITLE_ABBREVIATIONS = (
    (r"hazirlmak", "hazirlamak"),
    (r"infizyonluk", "infuzyonluk"),
    (r"vecozucu", "ve cozucu"),
    (r"saattransdermal", "saat transdermal"),
    (r"mikrogram", "mcg"),
    (r"unite", "u"),  # ÜNİTE
    (r"chewable", "cigneme"),
    (r"soft\s*gel", "yumusak"),
    (r"cig\.", "cigneme"),  # «CIG.TABLETI»
    # Партия 8 (25.10.2026)
    (r"sus\.", "suspansiyon"),
    (r"haz\.", "hazirlamak"),
    (r"kons\.", "konsantre"),
    (r"liyo\.", "liyofilize"),
    (r"toz\.", "toz"),
    (r"kont\.", "kontrollu"),
    (r"sal\.", "salimli"),
    (r"mik\.", "mikropellet"),
    (r"kps", "kapsul"),
    (r"капсул[аы]?", "kapsul"),
    (r"инъекция/инфузия", "enjeksiyonluk/infuzyonluk cozelti"),
    (r"oralsuspansiyon", "oral suspansiyon"),
    (r"ivenjeksiyonluk", "iv enjeksiyonluk"),
    (r"infuzyoluk", "infuzyonluk"),
    (r"irrrigasyon", "irrigasyon"),
    (r"salinimli", "salimli"),
    # TD-029 (31.10.2026): опечатки источника и английские/немецкие названия импортных препаратов.
    (r"inj\.", "enjeksiyon"),
    (r"susp\.?", "suspansiyon"),
    (r"oft\.", "oftalmik"),
    (r"kon\.", "konsantre"),
    (r"enjeksiyonlukcozelti", "enjeksiyonluk cozelti"),
    (r"enjekiyonluk", "enjeksiyonluk"),
    (r"ivinfuzyonluk", "iv infuzyonluk"),
    (r"cozeltiiceren", "cozelti iceren"),
    (r"cozeli", "cozelti"),
    (r"sertkapsul", "sert kapsul"),
    (r"kapll", "kapli"),
    (r"cozleti", "cozelti"),
    (r"liy\.", "liyofilize"),
    (r"perf\.", "perfuzyon"),
    (r"kullanilacakkonsantre", "kullanilacak konsantre"),
    (r"enjkesiyonluk", "enjeksiyonluk"),
    (r"cc", "ml"),
    (r"suppozituar", "supozituar"),
    (r"salimlisuspansiyon", "salimli suspansiyon"),
    (r"ft", "film tablet"),
    (r"st\.", "adet"),
    (r"aersolu", "aerosolu"),
    (r"supozituvar", "supozituar"),
    (r"pomat", "pomad"),
    (r"glikoz", "glukoz"),
    (r"capsul", "kapsul"),
    (r"vanilla", "vanilya"),
    (r"film ?tabletten", "film tablet"),
    (r"tabletten", "tablet"),
    (r"hartkapseln", "kapsul"),
    (r"cream", "krem"),
    (r"ointment", "merhem"),
    (r"suspension", "suspansiyon"),
    (r"syrup", "surup"),
    (r"eye drops", "goz damlasi"),
    (r"nasal spray", "nazal sprey"),
    (r"ampoules?|ampules?|ampullen", "ampul"),
    (r"sachettes|sachets?|sacht|packets?", "sase"),
    (r"bottle", "sise"),
)
# Английские названия форм целиком — до разворота отдельных слов.
_ENGLISH_FORMS = (
    (r"powder and (?:solvent|diluent) for solution for injection", "enjeksiyonluk cozelti icin toz ve cozucu"),
    (r"powder and (?:solvent|diluent) for suspension for injection",
     "enjeksiyonluk suspansiyon hazirlamak icin toz ve cozucu"),
    (r"powder for concentrate for solution for infusion", "konsantre infuzyonluk cozelti icin toz"),
    (r"powder for solution for (?:infusion/injection|injection/infusion)",
     "enjeksiyonluk/infuzyonluk cozelti hazirlamak icin toz"),
    (r"powder for solution for infusion", "infuzyonluk cozelti icin toz"),
    (r"powder for solution for injection", "enjeksiyonluk cozelti icin toz"),
    (r"powder for injection", "enjeksiyon icin toz"),
    (r"powder for oral solution", "oral cozelti hazirlamak icin toz"),
    (r"powder for oral suspension", "oral suspansiyon icin toz"),
    (r"powder for suspension", "suspansiyon icin toz"),
    (r"powder for solution", "cozelti tozu"),
    (r"solution for injection in pre-filled syringe", "enjeksiyonluk cozelti kullanima hazir enjektor"),
    (r"solution for (?:injection|enjection)", "enjeksiyonluk cozelti"),
    (r"solution for infusion", "infuzyonluk cozelti"),
    (r"injection/infusion", "enjeksiyonluk/infuzyonluk cozelti"),
    (r"for injection", "injection"),
    (r"prolonged release", "uzatilmis salimli"),
)


# Сокращение с точкой может стоять вплотную к слову: «ENT.TABLET», «YUM.KAPSUL».
def _abbreviation_res(pairs):
    return tuple(
        (re.compile(rf"(?<![a-z]){pattern}" + ("" if pattern.endswith(r"\.") else r"(?![a-z])")), f" {full} ")
        for pattern, full in pairs
    )


_ENGLISH_FORM_RES = tuple((re.compile(rf"(?<![a-z]){en}(?![a-z])"), tr) for en, tr in _ENGLISH_FORMS)
_ABBREVIATION_RES = _abbreviation_res(_ABBREVIATIONS)
_TITLE_ABBREVIATION_RES = _abbreviation_res(_TITLE_ABBREVIATIONS)
# Форма, разорванная фасовкой: «UZATILMIS SALIMLI 30 TABLET» → «30 UZATILMIS SALIMLI TABLET».
_SPLIT_FORM_RE = re.compile(
    r"(uzatilmis salimli|kontrollu salimli|agizda dagilan|enterik kapli|gastro direncli|film kapli|"
    r"efervesan|cigneme|sert|yumusak|mikropellet|suda dagilabilen|yavas salimli|degistirilmis salimli|"
    r"uzun etkili|yumusak jelatin|cozunebilir) (\d+) "
    r"((?:film (?:kapli )?|pellet |sert )?(?:tablet|kapsul))\b"
)


def _expand_source(rest: str, legacy: bool = False) -> str:
    """Сокращения → полные слова; ``legacy`` — как до 24.10.2026, для бренда абзацев."""
    if not legacy:
        # «I.M.ENJEKSIYONLUK» — путь введения вплотную к форме.
        rest = re.sub(r"(?<![a-z])i\.m\.(?=[a-z])", " im ", rest)
        # «KREON KAPSUL 25000 300 MG» — число единиц липазы между формой и дозой.
        rest = re.sub(r"^(kapsul|tablet) (\d{4,6}) (?=\d)", r"\2 u \1 ", rest)
        # «ENTERIK KAPLI 50 MG 20 TABLET» — форма, разорванная дозировкой.
        rest = re.sub(
            r"^(enterik kapli|film kapli) (\d+(?:[.,]\d+)?\s*mg) (\d+) (tablet)\b", r"\2 \3 \1 \4", rest
        )
        for pattern, turkish in _ENGLISH_FORM_RES:
            rest = pattern.sub(turkish, rest)
        # «ENJ. SOL.ICEREN» — сокращение вплотную к слову; «.ENJ.SOL.» — точка перед сокращением.
        rest = re.sub(r"(?<![a-z])sol\.(?=[a-z])", " solusyon ", rest)
        rest = re.sub(r"(?<![a-z\d])\.(?=enj)", " ", rest)
        # «KUL.HAZIR ENJEKTOR», «1 KULL. HAZ. ENJEKTOR», «ICEREN HAZIR KALEM» — до разворота «HAZ.».
        rest = re.sub(r"\bkull?\.\s*haz(?:ir\b|\.)\s*(?:enj\.$)?", lambda m: (
            " kullanima hazir enjektor " if m.group(0).endswith("enj.") else " kullanima hazir "
        ), rest)
        rest = re.sub(r"(?<!kullanima )\bhazir kalem\b", "kullanima hazir kalem", rest)
        # «4.500.000 IU» — разделители тысяч у единиц действия.
        rest = re.sub(r"(\d{1,3})\.(\d{3})\.(\d{3})(?=\s*iu\b)", r"\1\2\3", rest)
        # «30TABLET», «(1FLAKON)» — фасовка вплотную к форме.
        rest = re.sub(r"(\d)(tablet|kapsul|flakon|ampul|adet)\b", r"\1 \2", rest)
        # «1,25 MMOL / 1 KALSIYUM» — единица «л», записанная цифрой.
        rest = re.sub(r"mmol\s*/\s*1\b", "mmol/l", rest)
    for pattern, full in _ABBREVIATION_RES if legacy else _ABBREVIATION_RES + _TITLE_ABBREVIATION_RES:
        rest = pattern.sub(full, rest)
    if not legacy:
        rest = re.sub(r"\s+", " ", rest)
        # «ENJ. 100 ML COZELTI» — объём внутри формы; «1X30 PATCHES», «1X28PCS.» — число в упаковке.
        rest = re.sub(r"\benjeksiyon (\d+(?:[.,]\d+)?\s*ml) cozelti\b", r"\1 enjeksiyon cozelti", rest)
        rest = re.sub(
            r"(?<![\d.,])1\s*[x×]\s*(\d+)\s*(pcs?\b\.?)?(?![\d.,]*\s*(?:ml|mg|gr|g)\b)",
            lambda m: f" {m.group(1)} {'adet' if m.group(2) else ''} ",
            rest,
        )
        # «30 PATCHES», «TRANSDERMAL PATCH» — пластырь; «EXELON PATCH» в бренде остаётся.
        rest = re.sub(r"(\d+\s*|transdermal )patch(?:es|s)?\b\.?", r"\1 flaster", rest)
        # «30 NANELI SAKIZ», «20 CENTIKLI FILM TABLET» — уточнение между фасовкой и формой.
        rest = re.sub(
            r"(\d+) (naneli|meyveli|centikli) (sakiz|pastil|film kapli tablet|film tablet|tablet)\b", r"\1 \3 \2", rest
        )
        # «4000 ANTI-XA IU/0,4 ML» (эноксапарин) — единица анти-Xa; «(100 ML X 12 ADET)» — 12 флаконов по 100 мл.
        rest = re.sub(r"\banti[- ]?xa iu\b", "axa", rest)
        rest = re.sub(r"(\d+(?:[.,]\d+)?)\s*ml\s*x\s*(\d+)\s+(adet|sise)\b", r"\1 ml \2 \3", rest)
        # «KULLANIMA HAZIR 3 KALEM» — число шприц-ручек внутри формы; «60 G/TUP» — масса тубы;
        # «COZELTI ICEREN KASIK (28 KASIK)» — однодозовые ложки; «IV INF. COZELTI ICIN FLAKON» — флакон с раствором.
        rest = re.sub(r"kullanima hazir (\d+) kalem\b", r"kullanima hazir kalem \1 kalem", rest)
        rest = re.sub(
            r"(?<!cozucu iceren )kullanima hazir (\d+) (enjektor|siringa)\b", r"kullanima hazir \2 \1 \2", rest
        )
        # Форма, разбитая словами-связками и запятой с пробелом (TD-029).
        rest = re.sub(r"\s+,", ",", rest)
        rest = re.sub(r"\binfuzyon icin enjeksiyonluk cozelti\b", "infuzyon icin cozelti", rest)
        rest = re.sub(r"\b((?:sc|iv|im|rektal)(?:/(?:sc|iv|im|rektal))*) (?:uygulama|kullanim) icin\b", r"\1", rest)
        rest = re.sub(r"\b(cozelti) icin (kullanima hazir)\b", r"\1 iceren \2", rest)
        rest = re.sub(r"\binhalasyon icin (\d+) kapsul\b", r"inhalasyon icin kapsul \1 adet", rest)
        rest = re.sub(
            r"(?:(?:iv )?(?:infuzyon icin|infuzyonluk) )?(elektrolitli )?amino ?asit cozeltisi, glukoz cozeltisi,? "
            r"(?:ve )?lipid emulsiyonu\b",
            lambda m: "uc bolmeli elektrolitli" if m.group(1) else "uc bolmeli", rest,
        )
        rest = re.sub(r"\bcam sise\b|\bpe sise\b", "sise", rest)
        rest = re.sub(r"\bblister (\d+ doz)\b", r"\1", rest)
        rest = re.sub(r"\bmcg doz\b", "mcg/doz", rest)
        rest = re.sub(r"\bvajinal (\d+) ovul\b", r"\1 vajinal ovul", rest)
        rest = re.sub(r"\bcozunur (\d+) cigneme tableti\b", r"\1 cignenebilir/cozunebilir tablet", rest)
        rest = re.sub(r"\b(\d+) (xr|sr|mr|cr) (tablet|kapsul)\b", r"\2 \1 \3", rest)
        rest = re.sub(r"\bpellet iceren (\d+) kapsul\b", r"\1 kapsul", rest)
        rest = re.sub(r"\btek kullanimlik toz\b", "toz", rest)
        rest = re.sub(r"\biceren toz ve cozucu\b", "ve cozucu", rest)
        rest = re.sub(r"\bdivitab (?=film)", "", rest)
        rest = re.sub(r"\b(\d+) (uzatilmis salimli \1)\b", r"\2", rest)
        rest = re.sub(r"\b(im|iv)((?:/(?:im|iv))*) rektal\b", r"\1\2/rektal", rest)
        rest = re.sub(r"(\d+(?:[.,]\d+)?\s*g)\s*/?\s*tup\b", r"\1", rest)
        rest = re.sub(r"/\s*kutu\b", "", rest)
        rest = re.sub(r"\biceren kasik\b", "", rest)
        rest = re.sub(r"\binfuzyon cozelti icin flakon\b", "infuzyonluk cozelti", rest)
        # «YUMUSAK KAPSUL (100)» — число без единицы после формы — фасовка.
        rest = re.sub(r"\b(kapsul|tablet) (\d+)$", r"\2 \1", rest.strip())
    # «10 ML X 3 AMPUL» — объём одной ампулы и их число; «AMPUL(25)» в конце — 25 ампул.
    rest = re.sub(r"(\d+(?:[.,]\d+)?)\s*ml\s*x\s*(\d+)\s+(ampul|flakon|kartus)\b", r"\1 ml \2 \3", rest)
    rest = re.sub(r"\b(ampul|flakon)\s+(\d+)\s*$", r"\2 \1", rest)
    rest = re.sub(r"(?<=[a-z])\s*/\s*(?=[a-z])", "/", rest)
    rest = _SPLIT_FORM_RE.sub(r"\2 \1 \3", re.sub(r"\s+", " ", rest).strip())
    return rest


# Слова форм, которые бывают и в бренде: «FORANE LIKIT», «KREON FUR KINDER PELLET»,
# «REFRESH TEK DOZLUK» — на них бренд не обрывается.
# «INJECTION», «LAVMAN» после бренда до дозировки остаются в названии, как раньше («MICROLAX LAVMAN 10 GR»).
_BRAND_FORM_WORDS = {"likit", "pellet", "tek", "dozluk", "doz", "injection", "lavman"}  # и «OTRIVINE DOZ AYARLI»
FORM_WORDS = {word for phrase in FORM_PHRASES for word in phrase.split()} - _BRAND_FORM_WORDS
_LEGACY_FORM_WORDS = {word for phrase in _LEGACY_FORM_PHRASES for word in phrase.split()} - _BRAND_FORM_WORDS
_FORM_RE = re.compile(
    r"(?:" + "|".join(re.escape(p) for p in sorted(FORM_PHRASES, key=len, reverse=True)) + r")\b"
)

# Единица фасовки после числа → ключ medicine_reference._COUNT_UNITS.
_PACK_WORDS = {
    "adet": "piece", "ampul": "ampoule", "flakon": "vial", "sase": "sachet",
    "kalem": "pen", "enjektor": "syringe", "doz": "dose", "puskurtme": "dose",
    "tup": "tube", "sise": "vial", "flaster": "patch", "kutu": "box", "siringa": "syringe",
    "blister": "blister", "kartus": "cartridge", "poset": "sachet", "kasik": "dose",
}
# Обозначения линейки после дозировки («200 MG CR») — сохраняются как в источнике.
_SERIES_WORDS = {
    "sr", "xr", "mr", "cr", "xl", "la", "er", "ec", "odt", "retard", "forte", "fort",
    "plus", "mite", "depot", "duo", "junior", "max", "capsair", "discair", "diskus",
}
# Уточнения после формы → RU/EN.
MODIFIERS = {
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
    "naneli": ("со вкусом мяты", "mint flavour"),
    "glukozlu": ("с глюкозой", "with glucose"),
    "dekstrozlu": ("с декстрозой", "with dextrose"),
    "meyveli": ("с фруктовым вкусом", "fruit flavour"),
    "potasyumlu": ("с калием", "with potassium"),
    "mentollu": ("с ментолом", "with menthol"),
}
# Растворитель с упаковкой рядом: «+ 1 COZUCU FLAKON», «VE COZUCU ICEREN AMPUL». Число после
# растворителя («TOZ VE COZUCU (1 FLAKON)») — фасовка, а не его упаковка.
_SOLVENT = r"(?:(?:ve|\+)\s*)?(?:\d+\s+)?cozucu(?:su)?(?:\s+iceren)?\s+"
# Уточнения из нескольких слов: «TOZ VE COZUCU» — порошок с растворителем; «TEKLI TORBA» — пакет.
_PHRASE_MODIFIERS = (
    (re.compile(_SOLVENT + r"kullanima hazir\s+(?:\d+\s+)?(?:enjektor|siringa)\b"), (
        "с растворителем в предварительно заполненном шприце", "with solvent in pre-filled syringe"
    )),
    (re.compile(_SOLVENT + r"ampul\b"), ("с растворителем в ампуле", "with solvent in ampoule")),
    (re.compile(_SOLVENT + r"flakon\b"), ("с растворителем во флаконе", "with solvent in vial")),
    (re.compile(r"ve cozucu(?:su)?\b"), ("с растворителем", "with solvent")),
    (re.compile(r"(?:tekli|tek) torba\b"), ("одинарный пакет", "single bag")),
    (re.compile(r"(?:ciftli|cift) torba\b"), ("двойной пакет", "twin bag")),
    (re.compile(r"mini kapakli\b"), ("с мини-крышкой", "with mini cap")),
    (re.compile(r"(?:pp )?sise-setli\b"), ("флакон с системой", "bottle with set")),
    (re.compile(r"tek dozluk\b"), ("в однодозовых контейнерах", "in single-dose containers")),
    (re.compile(r"(?:1 |(?:pp|pvc|biofin) )?torba\b"), ("пакет", "bag")),
    (re.compile(r"\d+ cozucu\b"), ("с растворителем", "with solvent")),
    (re.compile(r"tedaviye baslama paketi\b"), ("стартовая упаковка", "treatment initiation pack")),
    (re.compile(r"pvc\b"), ("пакет", "bag")),
    (re.compile(r"bal ve limon aromali\b"), ("со вкусом мёда и лимона", "honey and lemon flavour")),
    *(
        (re.compile(rf"{word}(?: aromali)?\b"), (f"со вкусом {ru}", f"{en} flavour"))
        for word, (ru, en) in (
            ("muz", ("банана", "banana")), ("cilek", ("клубники", "strawberry")), ("vanilya", ("ванили", "vanilla")),
            ("cikolata", ("шоколада", "chocolate")), ("kahve", ("кофе", "coffee")),
            ("portakal", ("апельсина", "orange")), ("ahududu", ("малины", "raspberry")),
            ("kayisi", ("абрикоса", "apricot")), ("kakaolu", ("какао", "cocoa")), ("limon", ("лимона", "lemon")),
            ("kirmizi meyveler(?:i)?", ("красных фруктов", "red fruits")),
            ("orman meyveler(?:i)?", ("лесных ягод", "forest fruits")),
        )
    ),
    (re.compile(r"aromasiz\b"), ("без вкуса", "unflavoured")),
)
# Вкус лечебного питания — не бренд: «PEDIASURE CILEK AROMALI 220 ML» → «PEDIASURE, со вкусом
# клубники, 220 мл» (шаблон оставлял «CILEK AROMALI» в бренде; очередь модерации 27.10.2026).
# «PEDIASURE KAKAOLU» — «с какао» (пилот круга 3 27.10.2026: на сайте 4 названия с «KAKAOLU»).
_FLAVOUR_WORDS = frozenset({
    "muz", "cilek", "vanilya", "cikolata", "kahve", "portakal", "ahududu", "kayisi", "kakaolu", "aromasiz",
    "limon", "orman", "kirmizi",
})
# Вещество в/в раствора («%5 DEKSTROZ SUDAKI COZELTISI») → RU в родительном падеже, EN.
_SUBSTANCES = {
    "laktatli ringer": ("Рингер-лактата", "Ringer's lactate"),
    "ringer laktat": ("Рингер-лактата", "Ringer's lactate"),
    "ringer": ("Рингера", "Ringer's"),
    "sodyum klorur": ("натрия хлорида", "sodium chloride"),
    "dekstroz": ("декстрозы", "dextrose"),
    "glukoz": ("глюкозы", "glucose"),
    "mannitol": ("маннитола", "mannitol"),
    # Растворы для диализа с ммоль/л (TD-029): «1,75 MMOL/L KALSIYUM», «1.2 MMOL/L FOSFATLI».
    "kalsiyum": ("кальция", "calcium"),
    "fosfatli": ("фосфата", "phosphate"),
    "amino asit": ("аминокислот", "amino acids"),
}
_SUBSTANCE_RE = re.compile(r"(?:" + "|".join(sorted(_SUBSTANCES, key=len, reverse=True)) + r")\b")
# Перед формой-раствором: «IZOTONIK … SOL.» → «изотонический раствор».
_PREFIX_MODIFIERS = {"izotonik": ("изотонический", "isotonic"), "hipertonik": ("гипертонический", "hypertonic")}
# Слова-связки источника, которые в название не переносятся: «COZELTI ICEREN AMPUL»,
# «DEKSTROZ SUDAKI» (водный), материал пакета «PVC».
_SKIP_WORDS = {"iceren", "aerosol", "sudaki"}  # «AEROSOL … OLCULU DOZ INHALER» — форма названа дальше
_PACK_RE = re.compile(r"(\d+)\s+(" + "|".join(_PACK_WORDS) + r")\b")

_UNITS = {
    "mg": ("мг", "mg"), "mcg": ("мкг", "mcg"), "mkg": ("мкг", "mcg"), "µg": ("мкг", "mcg"),
    "g": ("г", "g"), "gr": ("г", "g"), "ml": ("мл", "ml"), "l": ("л", "l"),
    "iu": ("МЕ", "IU"), "ui": ("МЕ", "IU"), "mmol": ("ммоль", "mmol"), "meq": ("мэкв", "mEq"),
    # «ROVAMYCINE 3 MIU» — 3 млн МЕ; модель писала «3 МЕ» (пилот очереди 27.10.2026).
    "miu": ("млн МЕ", "MIU"),
    "doz": ("доза", "dose"), "puskurtme": ("доза", "dose"), "sprey": ("впрыск", "spray"),
    "saat": ("ч", "h"), "h": ("ч", "h"),
    "tu": ("ТЕ", "TU"), "u": ("ЕД", "U"), "cm2": ("см²", "cm²"),
    "axa": ("анти-Xa МЕ", "anti-Xa IU"),  # эноксапарин: «4000 ANTI-XA IU/0,4 ML»
    "kcal": ("ккал", "kcal"),  # лечебное питание: «VITAL 1,5 KCAL»
    "mgi": ("мг йода", "mg iodine"),  # контраст: «350 MGI/ML»
}
_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:miu|mgi|mg|mcg|mkg|µg|gr|g|ml|iu|ui|mmol|meq|tu|axa|kcal|u)"
_PER = r"(?:mg|mcg|g|ml|doz|puskurtme|sprey|saat|h|l|cm2)"
_DOSE_RE = re.compile(
    rf"(?:%\s*({_NUM})|({_NUM})\s*%|({_NUM})\s*({_UNIT})(?:\s*/\s*({_NUM})?\s*({_PER}))?)(?![a-z])"
)
_MULTI_RE = re.compile(rf"(\d+)\s*x\s*({_NUM})\s*(ml|g|gr)\b")
# Несколько веществ с одной единицей: «400/57 MG», «100/62,5/25 MCG».
_COMBO_DOSE_RE = re.compile(rf"({_NUM}(?:\s*/\s*{_NUM})+)\s*({_UNIT})(?![a-z])")
# Разделитель перед следующей дозировкой: «1 MG/ML + 50 MG/ML», «200 MG VE 50 MG», «250MG/1MG».
_JOINER_RE = re.compile(r"\s*(\+|/|ve(?=\s+[\d%]))\s*")
_ROUTE_ABBR_RE = re.compile(r"(im|iv|sc|ia)(?:\s*[/,]\s*(im|iv|sc|ia|rektal|intratekal))*\b")
_LEGACY_ROUTE_ABBR_RE = re.compile(r"(im|iv|sc)(?:\s*/\s*(im|iv|sc))*\b")
_MASS_FORMS = {"cream", "ointment", "gel", "lotion", "powder", "granules", "shampoo"}
_ROUTE_ABBR = {
    "im": ("в/м", "IM"), "iv": ("в/в", "IV"), "sc": ("п/к", "SC"), "ia": ("в/а", "IA"),
    "rektal": ("ректально", "rectal"), "intratekal": ("интратекально", "intrathecal"),
}


def _num(value: str, locale: str) -> str:
    return value.replace(".", ",") if locale == "ru" else value.replace(",", ".")


def _format_dose(match: re.Match, locale: str) -> tuple[str, str]:
    """(текст, вид): strength — дозировка, volume — объём, grams — масса (по форме)."""
    index = 0 if locale == "ru" else 1
    percent = match.group(1) or match.group(2)
    if percent:
        if re.fullmatch(r"0\d", percent):
            percent = f"0,{percent[1]}"
        return f"{_num(percent, locale)}%", "strength"
    number, unit, per_number, per_unit = match.group(3, 4, 5, 6)
    # «5.000 I.U.» — турецкий разделитель тысяч у единиц действия, не дробь.
    if unit in ("iu", "ui", "tu", "u", "axa") and re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", number):
        number = number.replace(".", "")
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


def is_form_word(token: Any, legacy: bool = False) -> bool:
    """Слово лекарственной формы или его сокращение («SOL.», «TB», «CAPSULES») — не бренд."""
    folded = fold_tr(token)
    words = _LEGACY_FORM_WORDS if legacy else FORM_WORDS
    expanded = _expand_source(folded, legacy).split()
    return folded in words or bool(expanded) and all(word in words for word in expanded)


def _brand_tokens(tokens: list[str], legacy: bool = False) -> list[str]:
    """Первые слова названия — до дозировки, формы или пути введения.

    ``legacy`` — по словарю форм до 24.10.2026: так считается бренд абзацев (paragraph_brand).
    """
    words = _LEGACY_FORM_WORDS if legacy else FORM_WORDS
    # «LAFLEKS IZOTONIK SODYUM KLORUR SOLUSYONU» — вещество и «изотонический» уже не бренд;
    # но «LAKTATLI RINGER PVC», «IZOTONIK SODYUM KLORUR BIOSEL» — с вещества начинается сам бренд.
    folded_name = fold_tr(" ".join(tokens))
    stop_at_substance = not legacy and not (
        _SUBSTANCE_RE.match(folded_name) or folded_name.split(" ", 1)[0] in _PREFIX_MODIFIERS
    )
    brand: list[str] = []
    for index, token in enumerate(tokens):
        folded = fold_tr(token).strip(",;")
        if brand and stop_at_substance and (
            folded in _PREFIX_MODIFIERS or _SUBSTANCE_RE.match(fold_tr(" ".join(tokens[index:])))
        ):
            break
        if brand and not legacy and folded in _FLAVOUR_WORDS:
            break
        if (
            folded[:1].isdigit()
            or folded.startswith("%")
            or folded in words
            # «KAYEXALAT POWDER», «RINGER BIOSEL ENJEKTABL SOL.»; «OLFREX EASY TAB» — бренд.
            or (brand and folded != "tab" and is_form_word(folded, legacy))
            or (_LEGACY_ROUTE_ABBR_RE if legacy else _ROUTE_ABBR_RE).fullmatch(folded)
        ):
            break
        brand.append(token)
    return brand


def _known_title_word(word: str) -> bool:
    """Слово названия, которое разбирает шаблон (форма, единица, «GRAM», фасовка…), — не бренд."""
    return any(
        part in FORM_WORDS or part in _UNITS or part in _PACK_WORDS or part in _SERIES_WORDS
        or part in MODIFIERS or part in _SKIP_WORDS or part in _PREFIX_MODIFIERS
        or _SUBSTANCE_RE.fullmatch(part) or _ROUTE_ABBR_RE.fullmatch(part)
        for part in _expand_source(word).split() or [word]
    )


_SUBSTANCE_WORDS = {word for phrase in _SUBSTANCES for word in phrase.split()} | set(_PREFIX_MODIFIERS)


def is_title_descriptor_word(token: Any) -> bool:
    """Слово, которое шаблон названия переводит (форма, вещество в/в раствора, «IZOTONIK», «SETLI»), — не бренд."""
    folded = fold_tr(token).strip(".,;")
    return folded in _SUBSTANCE_WORDS or _known_title_word(folded)


_NUTRITION_PACK_RE = re.compile(rf"{_NUM}\s*(?:g|gr|ml)\b")


def _title_brand_tokens(tokens: list[str]) -> list[str]:
    """Бренд названия: ещё и число без единицы сразу после бренда — часть названия.

    «CAPD 4 STAY SAFE PERITON DIALIZ», «PHYSIONEAL 40 %3.86 GLUKOZLU …», «POLIFLEKS 1/3 POLIDEKS IV …».
    """
    brand = _brand_tokens(tokens)
    extra = tokens[len(brand):]
    # «CALPOL 6 PLUS 250 MG/5 ML» — число и обозначение линейки перед дозировкой — бренд.
    if (
        brand and len(extra) >= 3 and re.fullmatch(r"\d{1,2}", extra[0])
        and fold_tr(extra[1]) in _SERIES_WORDS and re.match(r"[\d%]", extra[2])
    ):
        return brand + extra[:2]
    if brand and len(extra) >= 2 and re.fullmatch(r"\d+(?:[.,/]\d+)?", extra[0]):
        if re.match(r"%\d", fold_tr(extra[1])):  # «PHYSIONEAL 40 %3.86»; «FUCIDIN 2 % KREM» — дозировка
            return brand + extra[:1]
        # Лечебное питание: «RESOURCE 2.0 VANILYA AROMALI 200 ML», «MILUPA GA 1 (500 G)» — число линейки.
        if fold_tr(extra[1]) in _FLAVOUR_WORDS or _NUTRITION_PACK_RE.fullmatch(fold_tr(" ".join(extra[1:]))):
            return brand + extra[:1]
        # «POLIFLEKS IZOLEN-S PH 7.4 ELEKTROLIT…» — кислотность раствора; «IZOMIX 1/3 ENJEKTABL SOL» — название.
        if fold_tr(brand[-1]) == "ph" or (
            re.fullmatch(r"1/\d", extra[0]) and _FORM_RE.match(_expand_source(fold_tr(" ".join(extra[1:]))))
        ):
            return brand + extra[:1]
        count = 1
        while (
            count < min(len(extra), 4)
            and re.fullmatch(r"[a-z]{3,}", fold_tr(extra[count]))
            and not _known_title_word(fold_tr(extra[count]))
            and fold_tr(extra[count]) not in _FLAVOUR_WORDS
        ):
            count += 1
        # Слова после числа — бренд, только если сразу за ними форма, путь введения, вкус или масса
        # лечебного питания: «… 75 MIKROGRAM 28 FILM TABLET», «… 15 KIRMIZI (30X130 ML)» — не бренд.
        following = fold_tr(" ".join(extra[count:]))
        if count > 1 and (
            _FORM_RE.match(_expand_source(following))
            or _ROUTE_ABBR_RE.match(following)
            or following.split(" ", 1)[0] in _FLAVOUR_WORDS
            or _NUTRITION_PACK_RE.match(following)
        ):
            return brand + extra[:count]
    return brand


def paragraph_brand(name: Any, active_ingredient: Any = "") -> str:
    """Бренд для метки {BRAND} в абзацах инструкций: первые слова названия до дозировки.

    Пусто, если короче 3 букв или совпадает с МНН: «IBUPROFEN 400 MG» — это
    вещество, и в переводе оно должно стать «ибупрофеном», а не меткой.
    """
    brand = " ".join(_brand_tokens(re.sub(r"[()]", " ", str(name or "")).split(), legacy=True))
    words = set(re.findall(r"[a-z]+", fold_tr(brand)))
    if sum(map(len, words)) < 3:
        return ""
    inn_words = {word for word in re.findall(r"[a-z]+", fold_tr(active_ingredient)) if len(word) >= 4}
    return "" if words & inn_words else brand


def build_medicine_title(name: Any) -> Optional[dict[str, str]]:
    """RU/EN-название из исходного названия или None, если разобрать нельзя."""
    title = _title_and_brand(str(name or ""))[0]
    return dict(title) if title else None


@lru_cache(maxsize=4096)
def _title_and_brand(name: str) -> tuple[Optional[dict[str, str]], tuple[str, ...]]:
    """Название и бренд, с которым оно собрано.

    Сначала бренд по расширенному словарю (24.10.2026: обрывается и на веществе в/в
    раствора, бывает с числом). Если так не разобрать, то по прежнему словарю: прежние
    названия не теряются («PRIMEFLEKS RINGER 0,86 G+0,03 G…», «IZOLEKS DENGELI ELEKTROLIT BIOSEL SOL»).
    """
    # «D-COLEFOR-1000-IU-YUMUSAK-KAPSUL» — слова через дефис после бренда.
    hyphenated = re.search(r"-(\d+-(?:IU|MG|MCG)-\S*)", name, re.IGNORECASE)
    if hyphenated:
        name = name[:hyphenated.start()] + " " + hyphenated.group(1).replace("-", " ") + name[hyphenated.end():]
    tokens = [token for token in re.sub(r"[()]", " ", name).strip().split() if token != ","]
    for brand in (_title_brand_tokens(tokens), _brand_tokens(tokens, legacy=True)):
        title = _build_title(tokens, brand)
        if title:
            return title, tuple(brand)
    return None, tuple(_title_brand_tokens(tokens))


def _build_title(tokens: list[str], brand: list[str]) -> Optional[dict[str, str]]:
    # «FLEBOGAMMA% 10 DIF»: знак «%» в бренде RU-название не проходит проверку — название даст модель.
    if not brand or len(brand) == len(tokens) or any(token.endswith("%") for token in brand):
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
    substances: list[tuple[str, str]] = []
    prefix = None
    route = None
    joiner = None
    while rest:
        joiner_match = _JOINER_RE.match(rest)
        if joiner_match:
            joiner = joiner_match.group(1)
            rest = rest[joiner_match.end():]
        rest = rest.lstrip(" ,+-.")  # «2000 ML. TEKLI TORBA»
        if not rest:
            break
        multi = _MULTI_RE.match(rest)
        pack = _PACK_RE.match(rest)
        combo = _COMBO_DOSE_RE.match(rest)
        dose = _DOSE_RE.match(rest)
        form_match = _FORM_RE.match(rest)
        counted = re.match(r"(\d+)\s+", rest)
        counted_form = _FORM_RE.match(rest[counted.end():]) if counted else None
        phrase_modifier = next(
            ((match, text) for regex, text in _PHRASE_MODIFIERS if (match := regex.match(rest))), None
        )
        substance = _SUBSTANCE_RE.match(rest)
        word = re.match(r"[a-z]+\b", rest)
        # «KLAMOKS BID FORT 400/57 SUSPANSIYON …» — дозировки веществ без единицы перед суспензией,
        # порошком или сиропом (у таблеток «75/100» бывает и фасовкой — не угадываем).
        bare_ratio = re.match(rf"({_NUM}/{_NUM})\s+(?=(?:oral )?(?:suspansiyon|surup|kuru toz|toz)\b)", rest)
        if bare_ratio and not strengths["ru"]:
            for locale in ("ru", "en"):
                strengths[locale].append("/".join(_num(part, locale) for part in bare_ratio.group(1).split("/")))
            strength_joiners.append(joiner)
            rest = rest[bare_ratio.end():]
        elif multi:
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
            # «%09 SODYUM KLORUR», «TEMETEX %01» — в источнике потеряна запятая. Ведущий ноль бывает
            # только у дроби: 0,9%; «%005» (0,05% или 0,5%) — не угадываем.
            percent = dose.group(1) or dose.group(2) or ""
            if re.fullmatch(r"0\d{2,}", percent):
                return None
            # «500 MG + 30 MG + 2 MG / 20 G» — дозировка на пакетик 20 г.
            per_pack = joiner == "/" and bool(strengths["ru"]) and _format_dose(dose, "ru")[1] == "grams"
            for locale in ("ru", "en"):
                text, kind = _format_dose(dose, locale)
                if per_pack:
                    strengths[locale][-1] += f"/{text}"
                else:
                    {"strength": strengths, "volume": volumes, "grams": grams}[kind][locale].append(text)
            if kind == "strength" and not per_pack:
                strength_joiners.append(joiner)
            elif kind == "grams" and not per_pack:
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
            codes = re.findall(r"im|iv|sc|ia|rektal|intratekal", route_match.group(0))
            route = (
                ", ".join(_ROUTE_ABBR[c][0] for c in codes),
                "/".join(_ROUTE_ABBR[c][1] for c in codes),
            )
            rest = rest[route_match.end():]
        elif phrase_modifier:
            modifiers.append(phrase_modifier[1])
            rest = rest[phrase_modifier[0].end():]
        elif substance:
            substances.append(_SUBSTANCES[substance.group(0)])
            rest = rest[substance.end():]
        elif word and word.group(0) in _PREFIX_MODIFIERS and prefix is None:
            prefix = _PREFIX_MODIFIERS[word.group(0)]
            rest = rest[word.end():]
        elif word and word.group(0) in _SERIES_WORDS:
            series.append(word.group(0).upper())
            rest = rest[word.end():]
        elif word and word.group(0) in MODIFIERS:
            modifiers.append(MODIFIERS[word.group(0)])
            rest = rest[word.end():]
        elif word and word.group(0) in _SKIP_WORDS:
            rest = rest[word.end():]
        else:
            return None
        joiner = None

    forms = [
        form for key, form in zip(form_keys, forms) if _CONTAINER_FORMS.get(key) not in pack_units
    ]
    # «EXELON PATCH … TRANSDERMAL FLASTER»: «пластырь» внутри «трансдермальный пластырь» не повторяем.
    forms = [form for form in forms if not any(other[0].endswith(" " + form[0]) for other in forms)]
    # «DENGELI ELEKTROLIT I.V. INFUZYONLUK COZELTI» → «сбалансированный электролитный раствор для в/в инфузий».
    if len(forms) == 2 and forms[0][0].endswith("раствор") and forms[1][0].startswith("раствор "):
        forms = [(forms[0][0] + forms[1][0][7:], forms[0][1] + forms[1][1][8:])]
    # Повтор уточнения («SETSIZ … SETSIZ»); общее «с растворителем» рядом с уточнённым — лишнее.
    modifiers = list(dict.fromkeys(modifiers))
    if any(text[0].startswith("с растворителем ") for text in modifiers):
        modifiers = [text for text in modifiers if text != ("с растворителем", "with solvent")]
    if substances and grams["ru"]:
        return None
    # «SERUM FIZYOLOJIK IZOTONIK %0,9 10 ML», «LAKTATLI RINGER … 500 ML» — раствор без слова «раствор».
    if (substances or prefix) and not forms:
        forms = [("раствор", "solution")]
    if (substances or prefix) and not forms[0][0].startswith("раствор"):
        return None
    # Вещества в/в раствора: одно — «раствор декстрозы»; по дозировке на каждое —
    # «раствор декстрозы 5% и натрия хлорида 0,2%». Иначе не сопоставить — название даст модель.
    by_substance = len(substances) > 1 or (substances and len(strengths["ru"]) > 1)
    if by_substance and len(substances) != len(strengths["ru"]):
        return None
    if not forms and not (strengths["ru"] or volumes["ru"] or grams["ru"] or modifiers or pack_units):
        return None
    # «I.M./ORAL COZELTI» — путь введения и «для приёма внутрь» вместе не записать.
    if route and any(key.startswith("oral") for key in form_keys):
        return None
    # Граммы у мазей/кремов/гелей/порошков — масса упаковки, у прочих — дозировка.
    # «ointment for cutaneous use» — мазь, хотя последнее слово не форма; порошки — по последнему слову.
    form_words = forms[0][1].split() if forms else []
    grams_are_volume = bool(forms) and (
        form_words[-1] in _MASS_FORMS or form_words[0] in {"ointment", "cream", "gel", "lotion"}
    )
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
        if by_substance:
            pairs = list(zip(substances, values))
            strength = []
        head = " ".join(brand + strength + list(dict.fromkeys(series)))
        parts = [head]
        if forms:
            first = forms[0][index]
            if substances:
                names = (
                    [f"{substance[index]} {value}" for substance, value in pairs] if by_substance
                    else [substances[0][index]]
                )
                joined = (" и " if locale == "ru" else " and ").join(names)
                # RU: «раствор маннитола для инъекций»; EN: «mannitol solution for injection».
                first = first.replace("раствор", f"раствор {joined}", 1) if locale == "ru" else f"{joined} {first}"
            if prefix:
                first = f"{prefix[index]} {first}"
            form_texts = [first] + [form[index] for form in forms[1:]]
            parts.append(", ".join(form_texts) + (f" ({route[index]})" if route else ""))
        elif route:
            parts.append(route[index])
        parts.extend(modifier[index] for modifier in modifiers)
        parts.extend(volumes[locale])
        parts.extend(packs[locale])
        result[locale] = ", ".join(parts)
    return result


# Название, обрезанное прежней обработкой на десятичном разделителе:
# «MOUNJARO 7» (7,5 MG), «DIFFERIN 0» (%0,1), «Аугментин 200 мг/28», «Кенакорт %0».
# «% 0,1» и «%5» — турецкая запись процента, а не обрезка.
TRUNCATED_TITLE_RE = re.compile(r"(?:(?<![\w%.,-])(?<!%\s)\d+(?:[.,/]\d+)*|%\s*0)\s*$")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Штрихкод во вкладке аналогов ilacfiyati: «BARKOD 8699…», «Barkod: 8699…» или число строкой ниже.
_BARCODE_LINE_RE = re.compile(r"barkod\s*:?\s*(\d*)$", re.IGNORECASE)


def looks_like_source_name(name: Any) -> bool:
    """Название похоже на турецкий оригинал: без кириллицы и не обрезано прежней обработкой."""
    text = str(name or "").strip()
    return bool(text) and not CYRILLIC_RE.search(text) and not TRUNCATED_TITLE_RE.search(text)


def equivalents_source_name(external_data: Any) -> str:
    """Название товара из сохранённой вкладки аналогов ilacfiyati или ''.

    Источник перечисляет среди аналогов и сам препарат: его название — строка
    перед «BARKOD» с тем же штрихкодом, что attributes.barcode.
    """
    attrs = external_data.get("attributes") if isinstance(external_data, dict) else None
    if not isinstance(attrs, dict):
        return ""
    barcode = str(attrs.get("barcode") or "").strip()
    tabs = attrs.get("source_tabs")
    tab = tabs.get("equivalents") if isinstance(tabs, dict) else None
    text = tab.get("text") if isinstance(tab, dict) else tab
    if not barcode or not text:
        return ""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    for index in range(1, len(lines)):
        match = _BARCODE_LINE_RE.match(lines[index])
        if not match:
            continue
        code = match.group(1) or (lines[index + 1] if index + 1 < len(lines) else "")
        if code == barcode:
            return lines[index - 1]
    return ""


def medicine_source_name(name: Any, external_data: Any) -> tuple[str, str]:
    """Турецкое название лекарства для шаблона и проверок и откуда оно взято.

    Применение AI пишет в name RU-название, а прежние обработки оставили в name
    переводы («DISAVER 50 MG ФИЛЬМ-КАПЛИ ТАБЛЕТКИ») и обрезки («MOUNJARO 7»).
    Порядок: external_data["source_name"] → name, если он похож на оригинал, →
    строка аналогов с тем же штрихкодом → name как есть.
    """
    stored = external_data.get(SOURCE_NAME_KEY) if isinstance(external_data, dict) else None
    if str(stored or "").strip():
        return str(stored).strip(), "source_name"
    current = str(name or "").strip()
    if looks_like_source_name(current):
        return current, "name"
    equivalent = equivalents_source_name(external_data)
    if equivalent:
        return equivalent, "equivalents"
    return current, "name"


# Соль и гидрат в конце МНН в названии не пишутся: ищут «тамсулозин», а не «тамсулозин гидрохлорид».
_SALT_WORDS = {
    "гидрохлорид", "дигидрохлорид", "гидробромид", "натрия", "натрий", "калия", "калий", "кальция", "кальций",
    "магния", "магний", "ацетат", "сульфат", "бромид", "фосфат", "малеат", "мезилат", "хлорид", "тартрат",
    "цитрат", "нитрат", "дигидрат", "моногидрат", "тригидрат", "гемигидрат", "сесквигидрат", "карбонат",
    "пропионат", "глюконат", "фумарат", "сукцинат", "безилат", "бесилат", "тозилат", "лактат", "стеарат",
    "hydrochloride", "dihydrochloride", "hydrobromide", "sodium", "potassium", "calcium", "magnesium", "acetate",
    "sulfate", "sulphate", "bromide", "phosphate", "maleate", "mesylate", "mesilate", "chloride", "tartrate",
    "citrate", "nitrate", "dihydrate", "monohydrate", "trihydrate", "hemihydrate", "sesquihydrate", "carbonate",
    "propionate", "gluconate", "fumarate", "succinate", "besylate", "besilate", "tosylate", "lactate", "stearate",
    "hcl",
    # Эфиры кортикостероидов и гормонов: ищут «бетаметазон», «мометазон», а не «… дипропионат».
    "ацетонид", "дипропионат", "валерат", "бутират", "фуроат", "ацепонат", "пивалат", "энантат", "деканоат",
    "ундеканоат", "битартрат", "гидротартрат", "малат", "acetonide", "dipropionate", "valerate", "butyrate",
    "furoate", "aceponate", "pivalate", "enanthate", "decanoate", "undecanoate", "bitartrate", "malate",
}
# Катион соли стоит после вещества в родительном падеже («диклофенак натрия»), а при анионе и
# гидрате в родительном падеже стоит само вещество («отилония бромид», «амоксициллина тригидрат»).
_CATION_WORDS = {
    "натрия", "натрий", "калия", "калий", "кальция", "кальций", "магния", "магний",
    "sodium", "potassium", "calcium", "magnesium",
}
_HYDRATE_WORDS = {
    "дигидрат", "моногидрат", "тригидрат", "гемигидрат", "сесквигидрат",
    "dihydrate", "monohydrate", "trihydrate", "hemihydrate", "sesquihydrate",
}
_INN_TITLE_MAX = 45


# «Дорназа альфа», «эпоэтин бета» — МНН из двух слов в именительном падеже.
_GREEK_WORDS = {"альфа", "бета", "гамма", "дельта", "омега"}


def _nominative(word: str) -> str:
    """«отилония» → «отилоний», «амиодарона» → «амиодарон»: вещество перед анионом соли."""
    if word.lower().endswith("аза"):  # ферменты: «дорназа», «алтеплаза»
        return word
    if re.search(r"[а-яё]ия$", word):
        return word[:-1] + "й"
    if word.endswith("ля"):  # «пиридоксаля фосфат» → «пиридоксаль»
        return word[:-1] + "ь"
    if re.search(r"[бвгдзклмнпрстфхцчшщ]ы$", word):  # «глюкозы моногидрат» → «глюкоза»
        return word[:-1] + "а"
    if re.search(r"[бвгдзклмнпрстфхцчшщ]а$", word):
        return word[:-1]
    return word


def title_inn(value: str) -> str:
    """МНН в скобках названия: без соли и гидрата, в именительном падеже, со строчной."""
    parts = []
    for part in re.split(r"\s*\+\s*", value.strip()):
        words = part.split()
        stripped = []
        while len(words) > 1 and words[-1].lower() in _SALT_WORDS:
            stripped.append(words.pop().lower())
        cation = set(stripped) & _CATION_WORDS
        anion = set(stripped) - cation - _HYDRATE_WORDS
        # Соль целиком и есть вещество: «Карбонат кальция», «Кромогликат натрия», «Цинк, магний»,
        # «Дигидроксиалюминия натрия карбонат».
        if (
            "," in part
            or words[0].lower() in _SALT_WORDS
            or (cation and (anion or re.search(r"(?:ат|ид|ит)$", words[-1].lower())))
        ):
            words = part.split()
        elif stripped and not cation:
            # «Полимиксина B сульфат» → «полимиксин B»: буква — часть МНН, в падеже слово перед ней.
            last = len(words) - 2 if len(words) > 1 and re.fullmatch(r"[A-Z]", words[-1]) else len(words) - 1
            words[last] = _nominative(words[last])
        elif len(words) == 2 and re.fullmatch(r"[а-яё-]+", words[1]) and words[1] not in _GREEK_WORDS:
            # Эфир или вторая часть МНН: «Кандесартана цилексетил» → «кандесартан цилексетил».
            words[0] = _nominative(words[0])
        if not words:
            return ""
        first = words[0]
        # «Эзомепразол» → «эзомепразол»; аббревиатуры («ДНК», «D3») как есть.
        if len(first) > 1 and first[1:2].islower():
            words[0] = first[0].lower() + first[1:]
        parts.append(" ".join(words))
    return " + ".join(parts)


# Единица латиницей в RU-названии от модели («CLUSTOID 10000 TU/ML», «VERQUVO 5 MG»): по-русски
# «ТЕ/мл», «мг». «ME» латиницей — те же «МЕ» (очередь модерации 26.10.2026: ≈ 60 названий).
_RU_TITLE_UNITS = {
    "MIU": "млн МЕ", "MG": "мг", "MCG": "мкг", "ML": "мл", "IU": "МЕ", "I.U.": "МЕ", "UI": "МЕ",
    "ME": "МЕ", "TU": "ТЕ", "GR": "г", "G": "г", "MCI": "мКи",  # «Y-90 CITRATE 50 mCi» — милликюри
}
_RU_TITLE_UNIT_RE = re.compile(
    r"(?:(?<=\d)|(?<=\d )|(?<=/))(MIU|MCG|MCI|MG|ML|I\.U\.|IU|UI|ME|TU|GR|G)(?![A-Za-zА-Яа-яЁё.])", re.IGNORECASE
)


def ru_title_units(title: Any, source_name: Any = "") -> str:
    """RU-название лекарства с единицами по-русски: «10000 TU/ML» → «10000 ТЕ/мл».

    «MIU» источника модель пишет «МЕ»/«МЕД» (FILGRASTIM «48 MIU» → «48 МЕД», пилот 27.10.2026) —
    у того же числа единица становится «млн МЕ».
    """
    text = _RU_TITLE_UNIT_RE.sub(lambda m: _RU_TITLE_UNITS[m.group(1).upper()], str(title or ""))
    for number in re.findall(r"(\d+(?:[.,]\d+)?)\s*M\.?I\.?U\b", str(source_name or ""), re.IGNORECASE):
        variants = "|".join(re.escape(v) for v in {number, number.replace(".", ","), number.replace(",", ".")})
        text = re.sub(rf"(?<![\d.,])({variants})\s*(?:МЕД|МЕ|ЕД)(?![А-Яа-яЁё])", r"\1 млн МЕ", text)
    return text


def title_brand(name: Any) -> str:
    """Бренд в начале названия кодом («MAJEZIK», «THERMO FUZO», «IBUPROFEN», «CAPD 4 STAY SAFE»)."""
    return " ".join(_title_and_brand(str(name or ""))[1])


def title_with_inn(title: dict[str, str], name: Any, inn: tuple[str, str], active_ingredient: Any = "") -> dict[str, str]:
    """«NEXIUM 40 мг, …» → «NEXIUM (эзомепразол) 40 мг, …»: по бренду и по веществу ищут на каждом языке.

    Не добавляется, если вещество уже в бренде («PARACETAMOL ATABAY»), веществ больше
    трёх или МНН в названии вышло бы длиннее _INN_TITLE_MAX.
    """
    brand = title_brand(name)
    brand_words = set(re.findall(r"[a-z]+", fold_tr(brand)))
    inn_words = {word for word in re.findall(r"[a-z]+", fold_tr(active_ingredient)) if len(word) >= 4}
    if not brand or brand_words & inn_words or len(re.split(r"\s*\+\s*", inn[0])) > 3:
        return title
    result = {}
    for locale, value in zip(("ru", "en"), inn):
        text = title_inn(value)
        # «Otag (Ml)» — обрывок названия из источника вместо вещества.
        if not text or "(" in text or len(text) > _INN_TITLE_MAX or not title[locale].startswith(brand):
            return title
        # «TURKFLEKS 10%, раствор декстрозы» — вещество уже в названии, в скобках не повторяем.
        if any(word[:6].lower() in title[locale].lower() for word in re.findall(r"[^\W\d_]{5,}", text)):
            return title
        result[locale] = f"{brand} ({text}){title[locale][len(brand):]}"
    return result
