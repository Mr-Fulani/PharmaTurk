"""Правило «похоже на больничный препарат» и сверка (TD-047, docs/HOSPITAL_MEDICINES.md)."""

import csv
import json
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.hospital_rule import (
    GROUP_ALLERGEN, GROUP_DIAGNOSTIC, GROUP_DIALYSIS, GROUP_INFUSION, GROUP_RADIO,
    hospital_medicine_group, looks_like_hospital_medicine,
)
from apps.catalog.models import Category, MedicineProduct, Product


@pytest.mark.parametrize("name,atc,group", [
    # Названия из отбора 26.10.2026 — кода ATC может не быть.
    ("POLIFLEKS %30 DEKSTROZ 1000 ML SOL. SETLI", "", GROUP_INFUSION),
    ("TURKFLEKS %5 DEKSTROZ %0,45 SODYUM KLORUR SUDAKI COZELTISI 500 ML SETSIZ", "", GROUP_INFUSION),
    ("PRIMEFLEKS %10 DEKSTROZ IV INFUZYONLUK COZELTI (1000 ML, SETSIZ)", "B05BA03", GROUP_INFUSION),
    ("%0,9 İZOTONİK SODYUM KLORÜR İÇEREN İRRİGASYON SOLÜSYONU 500 ML (POLİPROPİLEN ŞİŞE)", "", GROUP_INFUSION),
    ("OLIMEL N9-840 INFUZYONLUK AMINOASIT COZELTISI, GLIKOZ COZELTISI VE LIPID EMULSIYONU (1500 ML)",
     "B05BA10", GROUP_INFUSION),
    ("VOLUVEN %6 INFUZYONLUK COZELTI, 1 TORBA", "B05AA07", GROUP_INFUSION),
    ("CERNEVIT IV/IM ENJEKSIYONLUK/INFUZYONLUK COZELTI HAZIRLAMAK ICIN LIYOFILIZE TOZ (4 FLAKON)",
     "B05XC", GROUP_INFUSION),
    ("SERUM FIZYOLOJIK BIOFARMA % 0,9 10 ML 100 AMPUL", "B05XA03", GROUP_INFUSION),
    ("PHYSIONEAL 40 %2,27 PERITON DIYALIZ COZELTISI (2000 ML CIFTLI TORBA)", "", GROUP_DIALYSIS),
    ("CAPD 17 STAY SAFE PERITON DIALIZ 2500 ML", "", GROUP_DIALYSIS),
    ("MULTIBIC 2 MMOL/L POTASYUMLU 5000 ML HEMOFILTRASYON SOLUSYONU", "", GROUP_DIALYSIS),
    ("REGIOCIT 5,03 G/L+5,29 G/L RENAL REPLASMAN VE BOLGESEL ANTIKOAGULASYON COZELTISI (1 ADET)",
     "B05ZB", GROUP_DIALYSIS),
    ("MON.TEK 99MO/99MTC JENERATOR (50 GBQ)", "", GROUP_RADIO),
    ("MON.IYOT-131 0.37-7400 MBQ (10 ΜCI-200 MCI) ORAL KAPSUL (125 MCI)", "", GROUP_RADIO),
    ("Y-90 CITRATE (THERAPEUTIC) 10 mCİ", "V10AA01", GROUP_RADIO),
    ("APIPRICK DERI PRICK TESTI COZELTISI NEGATIF KONTROL", "", GROUP_ALLERGEN),
    ("SULGEN 30000 TU/ML DILALTI SPREY, COZELTI (BETULA)", "V01AA", GROUP_ALLERGEN),
    ("THYROGEN 0.9 MG 2 VIAL", "V04CJ01", GROUP_DIAGNOSTIC),
])
def test_hospital_medicines_are_recognised(name, atc, group):
    assert hospital_medicine_group(name, atc) == group
    assert looks_like_hospital_medicine(name, atc)


@pytest.mark.parametrize("name,atc", [
    ("PAROL 500 MG 20 TABLET", "N02BE01"),
    ("AUGMENTIN BID 1000 MG 14 FILM TABLET", "J01CR02"),
    # Ампулы и уколы, которые делают дома.
    ("DODEX 1000 MCG/ML 5 AMPUL", "B03BA01"),
    ("VOLTAREN 75 MG/3 ML 10 AMPUL", "M01AB05"),
    ("CLEXANE 4000 ANTI-XA IU/0,4 ML 10 KULLANIMA HAZIR ENJEKTOR", "B01AB05"),
    ("POTASYUM KLORUR %7,5 10 ML 10 AMPUL", ""),  # без кода ATC ампулы не отмечаем
    # «Инфузия» у лекарства с действующим веществом — не раствор для капельницы.
    ("REFLOSEL 40 MG ENJEKSİYONLUK/İNFÜZYONLUK ÇÖZELTİ HAZIRLAMAK İÇİN TOZ (1 ADET)", "A02BC05"),
    ("CEREZYME 200 U INFUZYONLUK KONSANTRE COZELTI ICIN TOZ ICEREN 1 FLAKON", "A16AB02"),
    ("PAROL 10 MG/ML INFUZYONLUK COZELTI 100 ML", "N02BE01"),
    ("PAROL 10 MG/ML INFUZYONLUK COZELTI 100 ML", ""),
    # Лечебное питание и препараты для приёма внутрь с кодом B05.
    ("MCT OIL 500 ML", "B05BA02"),
    ("MONOGEN MAMA 400 G. TOZ", "B05BA02"),
    ("ARGININ VEYRON 5 ML 1X20 ORAL SOLUTION", "B05XB01"),
    ("HUMAN ALBUMIN %20 100 ML IV INFUZYON ICIN COZELTI", "B05AA01"),  # решение владельца не принято
    ("ORALAIR 300 IR 30 DILALTI TABLET", "V01AA02"),
    ("STERIMAR IZOTONIK BURUN SPREYI 100 ML", ""),
    ("COREDEM %5 SODYUM KLORUR TEK DOZLUK HIPERTONIK OFTALMIK COZELTI (20 ADET)", ""),
    ("HYPER-HEP B 1 ML HAZIR ENJEKTOR", ""),
    ("", ""),
    (None, None),
])
def test_ordinary_medicines_are_not_hospital(name, atc):
    assert hospital_medicine_group(name, atc) == ""
    assert not looks_like_hospital_medicine(name, atc)


@pytest.fixture
def medicines(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    category = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})[0]

    def make(slug, source_name, atc, *, is_hospital=False, is_active=True, **external):
        base = Product.objects.create(
            name=slug, slug=slug, category=category, product_type="medicines", price=Decimal("100"),
            currency="TRY", is_active=is_active,
            external_data={"source": "ilacfiyati", "source_name": source_name, **external},
        )
        medicine = MedicineProduct.objects.filter(base_product=base).first()
        if medicine is None:
            medicine = MedicineProduct.objects.create(
                base_product=base, name=slug, slug=f"medicine-{slug}", category=category,
            )
        MedicineProduct.objects.filter(pk=medicine.pk).update(
            atc_code=atc, is_hospital=is_hospital, is_active=is_active, price=Decimal("100"),
        )
        return medicine

    return {
        "infusion": make("polifleks", "POLIFLEKS %5 DEKSTROZ 500 ML SOL. SETLI", "B05BA03"),
        "dialysis": make("capd", "CAPD 2 STAY SAFE PERITON DIALIZ 2000 ML", ""),
        "marked": make("turkfleks", "TURKFLEKS %0,9 IZOTONIK SODYUM KLORUR 1000 ML SETSIZ", "B05BB01", is_hospital=True),
        "manual": make("aprokam", "APROKAM 50 MG ENJEKSIYONLUK COZELTI ICIN TOZ", "S01AA27", is_hospital=True),
        "tablet": make("parol", "PAROL 500 MG 20 TABLET", "N02BE01"),
        "hidden": make("hidden", "NEOFLEKS %5 DEKSTROZ 250 ML SETSIZ", "B05BA03", is_active=False),
        "stub": make("stub", "BIOFLEKS %5 DEKSTROZ 100 ML SETLI", "", is_stub=True),
    }


def _flags(medicines):
    return {key: MedicineProduct.objects.get(pk=medicine.pk).is_hospital for key, medicine in medicines.items()}


def test_check_command_shows_both_differences_and_changes_nothing(medicines, tmp_path, capsys):
    before = _flags(medicines)
    path = tmp_path / "hospital.csv"

    call_command("check_hospital_medicines", csv=str(path))

    assert _flags(medicines) == before
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = {int(row["medicine_id"]): row for row in csv.DictReader(fh)}
    assert set(rows) == {medicines["infusion"].pk, medicines["dialysis"].pk, medicines["manual"].pk}
    assert rows[medicines["infusion"].pk]["расхождение"] == "подходит под правило, не отмечен"
    assert rows[medicines["infusion"].pk]["группа"] == GROUP_INFUSION
    assert rows[medicines["dialysis"].pk]["группа"] == GROUP_DIALYSIS
    assert rows[medicines["manual"].pk]["расхождение"] == "отмечен, под правило не подходит"
    assert "ничего не изменено" in capsys.readouterr().out


def test_check_command_apply_marks_unmarked_and_never_unmarks(medicines, tmp_path):
    backup = tmp_path / "backup.json"
    with pytest.raises(CommandError):
        call_command("check_hospital_medicines", apply=True)

    call_command("check_hospital_medicines", apply=True, backup=str(backup), group=["диализ"])
    assert _flags(medicines) == {
        "infusion": False, "dialysis": True, "marked": True, "manual": True,
        "tablet": False, "hidden": False, "stub": False,
    }
    assert [row["id"] for row in json.loads(backup.read_text(encoding="utf-8"))] == [medicines["dialysis"].pk]

    with pytest.raises(CommandError):  # бэкап не перезаписывается
        call_command("check_hospital_medicines", apply=True, backup=str(backup))
    call_command("check_hospital_medicines", apply=True, backup=str(tmp_path / "backup2.json"))
    flags = _flags(medicines)
    assert flags["infusion"] and flags["manual"] and not flags["tablet"] and not flags["hidden"] and not flags["stub"]
    medicine = MedicineProduct.objects.get(pk=medicines["infusion"].pk)
    assert medicine.price == Decimal("100") and medicine.is_active
