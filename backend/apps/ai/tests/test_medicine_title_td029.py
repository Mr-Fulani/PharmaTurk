"""TD-029: шаблон названия на всём каталоге; TD-030: бренд абзацев заморожен.

Названия — настоящие строки каталога ilacfiyati. Новые разборы не должны менять
ни бренд абзацев (ключи памяти), ни названия, которые собирались раньше.
"""

import hashlib

import pytest

from apps.ai.services import medicine_title
from apps.ai.services.medicine_title import (
    _LEGACY_FORM_PHRASES, build_medicine_title, paragraph_brand, title_brand,
)
from apps.ai.services.semantic_validator import (
    _medicine_flavour_lost, _medicine_identity_lost, _medicine_ru_title_untranslated,
)


@pytest.mark.parametrize("source, ru, en", [
    # ммоль/л в растворах для диализа
    (
        "BALANCE SAFE LOCK %2,3 GLUKOZ 1,75 MMOL/L KALSIYUM PERITON DIYALIZ SOLUSYONU 5000 ML",
        "BALANCE SAFE LOCK, раствор глюкозы 2,3% и кальция 1,75 ммоль/л для перитонеального диализа, 5000 мл",
        "BALANCE SAFE LOCK, glucose 2.3% and calcium 1.75 mmol/l peritoneal dialysis solution, 5000 ml",
    ),
    (
        "BALANCE %1,5 GLIKOZ 1,25 MMOL / 1 KALSIYUM 2000 ML BIOFIN TORBA",
        "BALANCE, раствор глюкозы 1,5% и кальция 1,25 ммоль/л, пакет, 2000 мл",
        "BALANCE, glucose 1.5% and calcium 1.25 mmol/l solution, bag, 2000 ml",
    ),
    # английские и немецкие названия импортных препаратов
    (
        "CRYSVITA 20 MG SOLUTION FOR INJECTION",
        "CRYSVITA 20 мг, раствор для инъекций", "CRYSVITA 20 mg, solution for injection",
    ),
    (
        "SYLVANT 100 MG POWDER FOR CONCENTRATE FOR SOLUTION FOR INFUSION",
        "SYLVANT 100 мг, порошок для приготовления концентрата для приготовления раствора для инфузий",
        "SYLVANT 100 mg, powder for concentrate for solution for infusion",
    ),
    (
        "ESIDREX 25 MG 100 TABLETTEN",
        "ESIDREX 25 мг, таблетки, 100 шт.", "ESIDREX 25 mg, tablets, 100 pcs",
    ),
    (
        "INTUNIV 2 MG PROLONGED RELEASE 28 TABLETS",
        "INTUNIV 2 мг, таблетки пролонгированного высвобождения, 28 шт.",
        "INTUNIV 2 mg, prolonged-release tablets, 28 pcs",
    ),
    (
        "KRYSTEXXA 8 MG/ML INJECTION",
        "KRYSTEXXA 8 мг/мл, для инъекций", "KRYSTEXXA 8 mg/ml, for injection",
    ),
    # опечатки источника
    ("TEMETEX %01 10 GR KREM", "TEMETEX 0,1%, крем, 10 г", "TEMETEX 0.1%, cream, 10 g"),
    (
        "LAFLEKS %5 DEKSTROZ %09 SODYUM KLORUR COZELTISI 1000 ML (SETSIZ)",
        "LAFLEKS, раствор декстрозы 5% и натрия хлорида 0,9%, без системы, 1000 мл",
        "LAFLEKS, dextrose 5% and sodium chloride 0.9% solution, without set, 1000 ml",
    ),
    (
        "PENBISIN 1000 MG ENJEKSIYONLUK COZELI TOZU (1 FLAKON)",
        "PENBISIN 1000 мг, порошок для приготовления раствора для инъекций, 1 флакон",
        "PENBISIN 1000 mg, powder for solution for injection, 1 vial",
    ),
    (
        "TALZENNA 0,1 MG SERTKAPSUL (30 ADET)",
        "TALZENNA 0,1 мг, капсулы, 30 шт.", "TALZENNA 0.1 mg, capsules, 30 pcs",
    ),
    (
        "ALTUZAN ROCHE 100MG/4ML KONS.INF.COZ.ICEREN 1 FLAKON",
        "ALTUZAN ROCHE 100 мг/4 мл, концентрат для приготовления раствора для инфузий, 1 флакон",
        "ALTUZAN ROCHE 100 mg/4 ml, concentrate for solution for infusion, 1 vial",
    ),
    # вкусы лечебного питания
    (
        "RESOURCE 2.0 VANILYA AROMALI 200 ML",
        "RESOURCE 2.0, со вкусом ванили, 200 мл", "RESOURCE 2.0, vanilla flavour, 200 ml",
    ),
    (
        "PKU LOPHLEX LQ 10 KIRMIZI MEYVELER (60X62,5 ML)",
        "PKU LOPHLEX LQ 10, со вкусом красных фруктов, 60 шт. по 62,5 мл",
        "PKU LOPHLEX LQ 10, red fruits flavour, 60 × 62.5 ml",
    ),
    (
        "VITAL 1,5 KCAL ORMAN MEYVELERI AROMALI 200 ML",
        "VITAL 1,5 ккал, со вкусом лесных ягод, 200 мл", "VITAL 1.5 kcal, forest fruits flavour, 200 ml",
    ),
    (
        "ISOSOURCE ENERGY 500 ML VANILLA",
        "ISOSOURCE ENERGY, со вкусом ванили, 500 мл", "ISOSOURCE ENERGY, vanilla flavour, 500 ml",
    ),
    ("FORTIMEL DRINK CIKOLATA AROMALI", "FORTIMEL DRINK, со вкусом шоколада", "FORTIMEL DRINK, chocolate flavour"),
    # формы, на которых шаблон сдавался чаще всего
    (
        "BEMUSTU 100 MG IV INFUZYONLUK COZELTI HAZIRLAMADA KULLANILACAK KONSANTRE ICIN TOZ",
        "BEMUSTU 100 мг, порошок для приготовления концентрата для приготовления раствора "
        "для внутривенных инфузий",
        "BEMUSTU 100 mg, powder for concentrate for solution for intravenous infusion",
    ),
    (
        "ADACEL 0,5 ML IM ENJ. ICIN SUS. ICEREN FLAKON",
        "ADACEL, суспензия для инъекций, флакон (в/м), 0,5 мл",
        "ADACEL, suspension for injection, vial (IM), 0.5 ml",
    ),
    (
        "OLICLINOMEL N7-1000E INFUZYONLUK ELEKTROLITLI AMINOASIT COZELTISI, GLUKOZ COZELTISI, "
        "LIPID EMULSIYONU (1000 ML)",
        "OLICLINOMEL N7-1000E, раствор аминокислот с электролитами, раствор глюкозы и липидная эмульсия "
        "для инфузий, 1000 мл",
        "OLICLINOMEL N7-1000E, amino acid solution with electrolytes, glucose solution and lipid emulsion "
        "for infusion, 1000 ml",
    ),
    (
        "DROPOETIN 2000 IU/0,2 ML SC/IV ENJEKSIYON ICIN COZELTI ICEREN KULLANIMA HAZIR 6 SIRINGA",
        "DROPOETIN 2000 МЕ/0,2 мл, раствор для инъекций (п/к, в/в), 6 шприцев",
        "DROPOETIN 2000 IU/0.2 ml, solution for injection (SC/IV), 6 syringes",
    ),
])
def test_new_titles(source, ru, en):
    title = build_medicine_title(source)
    assert title == {"ru": ru, "en": en}
    # Шаблонное название проходит те же проверки, что и название модели.
    assert not _medicine_ru_title_untranslated(title["ru"], source)
    assert not _medicine_identity_lost(source, title["ru"])
    assert not _medicine_flavour_lost(title["ru"], source)


@pytest.mark.parametrize("source, ru", [
    # Названия, которые собирались до TD-029, не меняются.
    ("MICROLAX LAVMAN 10 GR", "MICROLAX LAVMAN 10 г"),
    ("BACLOFEN INJECTION 10MG/5 ML (2MG/ML) 5 AMPUL", "BACLOFEN INJECTION 10 мг/5 мл (2 мг/мл), 5 ампул"),
    ("ACLASTA 5 MG/100 ML IV INFUZYON COZELTISI", "ACLASTA 5 мг/100 мл, раствор для инфузий (в/в)"),
    ("BUDEFIX 400 MCG INHALASYON ICIN TOZ ICEREN 60 KAPSUL", "BUDEFIX 400 мкг, порошок для ингаляций, 60 шт."),
    (
        "NIMENRIX 0,5 MG IM ENJEKSIYON ICIN TOZ ICEREN 1 FLAKON VE COZUCU ICEREN KULLANIMA HAZIR 1 ENJEKTOR",
        "NIMENRIX 0,5 мг, порошок для приготовления раствора для инъекций (в/м), "
        "с растворителем в предварительно заполненном шприце, 1 флакон",
    ),
    ("TANFLEX %0,15 ORAL SPREY, COZELTI", "TANFLEX 0,15%, спрей для полости рта, раствор"),
    ("MCT OIL% MEGEMAX 1000 ML", "MCT OIL% MEGEMAX, 1000 мл"),  # «%» внутри бренда, а не перед числом
])
def test_titles_built_before_stay_the_same(source, ru):
    assert build_medicine_title(source)["ru"] == ru


@pytest.mark.parametrize("source", [
    "FLEBOGAMMA% 10 DIF 10 G/100 ML IV INFUZYONLUK COZELTI (1 FLAKON)",
    "VENIDARA% 5 KREM",  # раньше — «VENIDARA%, крем, 5 шт.»: 5% стало фасовкой
    "SODYUM %005 COZELTI",  # 0,05% или 0,5% — не угадываем
])
def test_ambiguous_titles_go_to_the_model(source):
    assert build_medicine_title(source) is None


# --- TD-030: метка {BRAND} в ключах памяти абзацев -------------------------------


def test_legacy_form_dictionary_is_frozen():
    """Новая форма — в FORM_PHRASES.update(...) после _LEGACY_FORM_PHRASES, а не до него."""
    digest = hashlib.sha256("\n".join(sorted(_LEGACY_FORM_PHRASES)).encode()).hexdigest()
    assert digest == "f98d72b6f0d1cec34d298f0981dad2c171666bf20cde2892ac1c371c5507e821"


@pytest.mark.parametrize("source, brand", [
    ("MAJEZIK 100 MG 15 FILM TABLET", "MAJEZIK"),
    ("ABOUND PORTAKAL AROMALI 30 POSET x 24 G", "ABOUND PORTAKAL AROMALI"),
    ("BETNOVATE SAC LOSYONU 30 ML", "BETNOVATE SAC LOSYONU"),
    ("BIOFLEKS RINGER ENJEKTABL SOL 1000 ML SETLI", "BIOFLEKS RINGER"),
    ("CAPD 18 STAY SAFE PERITON DIALIZ 2000 ML", "CAPD"),
    ("MIDAJECT 15 MG/3 ML IM/IV/REKTAL COZELTI ICEREN 5 AMPUL", "MIDAJECT"),
    ("CUVITRU 2 G/10 ML S.C. UYGULAMA ICIN ENJEKSIYONLUK COZELTI", "CUVITRU"),
    ("PKU LOPHLEX LQ 10 KIRMIZI MEYVELER (60X62,5 ML)", "PKU LOPHLEX LQ"),
])
def test_paragraph_brand_ignores_title_dictionary(source, brand):
    assert paragraph_brand(source) == brand


def test_title_brand_is_wider_than_paragraph_brand_and_that_is_fine():
    """Название и абзацы считают бренд по-разному: это сознательное решение TD-030."""
    source = "CAPD 18 STAY SAFE PERITON DIALIZ 2000 ML"
    assert title_brand(source) == "CAPD 18 STAY SAFE"
    assert paragraph_brand(source) == "CAPD"
    assert medicine_title._LEGACY_ROUTE_ABBR_RE.fullmatch("im/iv")
    assert not medicine_title._LEGACY_ROUTE_ABBR_RE.fullmatch("im/iv/rektal")
