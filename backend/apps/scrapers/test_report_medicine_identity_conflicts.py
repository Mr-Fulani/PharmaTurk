import csv
import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, MedicineProduct, Product

COMMAND = "report_medicine_identity_conflicts"
PAGE = "https://ilacfiyati.com/ilaclar/"


def medicine(category, slug, field, source, *, base_source=None, barcode="8699522352692", stub=False, **product):
    item = MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, price=100, currency="TRY",
        active_ingredient=field, barcode=barcode, external_id=slug, external_url=PAGE + slug,
        external_data={"source": "ilacfiyati"},
    )
    item.refresh_from_db()  # base_product создаётся при сохранении
    data = {"source": "ilacfiyati", "is_stub": stub}
    attrs = {"barcode": barcode}
    MedicineProduct.objects.filter(pk=item.pk).update(
        external_data={**data, "attributes": {**attrs, "active_ingredient": source}},
    )
    Product.objects.filter(pk=item.base_product_id).update(
        external_data={**data, "attributes": {
            **attrs, "active_ingredient": source if base_source is None else base_source,
        }},
        **{"external_id": slug, "external_url": PAGE + slug, **product},
    )
    return item


@pytest.fixture
def medicines(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    category = Category.objects.create(name="Медицина", slug="td045-report")
    return {
        "agree": medicine(category, "parol", "Parasetamol", "Parasetamol"),
        "spelling": medicine(category, "largopen", "amoksisilin", "Amoksisilin trihidrat"),
        "different": medicine(category, "augmentin", "amoksisilin", "Amoksisilin + Klavulanik asit"),
        "disputed": medicine(category, "imigran", "sumatriptan", "Naratriptan", base_source="Zolmitriptan"),
        "russian": medicine(category, "brufen", "Ибупрофен", "İbuprofen"),
        "placeholder": medicine(category, "ig-vena", "immunglobulin", "Albumin", barcode="1111111111116"),
        "stub": medicine(category, "aklovir", "amoksisilin", "Asiklovir", stub=True),
        "oil": medicine(category, "phytoil", "", "", product_type="supplements"),
        "old_id": medicine(category, "nexium-2", "", "", external_id="nexium-old"),
    }


def fields(medicines):
    return {key: MedicineProduct.objects.get(pk=item.pk).active_ingredient for key, item in medicines.items()}


def report_rows(tmp_path):
    path = tmp_path / "report.csv"
    out = StringIO()
    call_command(COMMAND, "--csv", str(path), stdout=out)
    with open(path, encoding="utf-8-sig", newline="") as source:
        return {row["название"]: row for row in csv.DictReader(source)}, out.getvalue()


def test_show_counts_every_case_without_changes(medicines, tmp_path):
    before = fields(medicines)

    rows, output = report_rows(tmp_path)

    assert fields(medicines) == before
    assert set(rows) == {"LARGOPEN", "AUGMENTIN", "IMIGRAN", "BRUFEN", "IG-VENA", "PHYTOIL", "NEXIUM-2"}
    assert rows["LARGOPEN"]["подслучай"].startswith("то же вещество")
    assert rows["LARGOPEN"]["что будет при проходе парсера"] == "обновится целиком"
    assert rows["AUGMENTIN"]["подслучай"] == "вещества разные"
    assert rows["AUGMENTIN"]["у нас (поле)"] == "amoksisilin"
    assert rows["AUGMENTIN"]["источник (external_data товара)"] == "Amoksisilin + Klavulanik asit"
    assert "если штрихкод источника тот же" in rows["AUGMENTIN"]["что будет при проходе парсера"]
    assert rows["BRUFEN"]["подслучай"] == "поле записано по-русски"
    assert rows["BRUFEN"]["что будет при проходе парсера"] == "обновится целиком"
    assert rows["IG-VENA"]["что будет при проходе парсера"].startswith("пропуск")
    assert rows["PHYTOIL"]["причина"] == "variant_or_product_type_conflict"
    assert rows["PHYTOIL"]["подслучай"].startswith("а:") and "supplements" in rows["PHYTOIL"]["подслучай"]
    assert rows["PHYTOIL"]["что будет при проходе парсера"] == "цена и наличие обновятся"
    assert rows["NEXIUM-2"]["подслучай"].startswith("б:")
    assert rows["NEXIUM-2"]["у нас (поле)"] == "nexium-old"
    assert "Поле вещества можно починить по источнику: 2" in output
    assert "ничего не изменено" in output


def test_csv_is_not_overwritten(medicines, tmp_path):
    path = tmp_path / "report.csv"
    path.write_text("занято", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command(COMMAND, "--csv", str(path), stdout=StringIO())
    assert path.read_text(encoding="utf-8") == "занято"


def test_apply_requires_backup(medicines):
    with pytest.raises(CommandError):
        call_command(COMMAND, "--apply", stdout=StringIO())
    assert fields(medicines)["different"] == "amoksisilin"


def test_apply_repairs_only_agreed_different_substance_and_restore_reverts(medicines, tmp_path):
    before = fields(medicines)
    backup = tmp_path / "ingredient.json"

    call_command(COMMAND, "--apply", "--backup", str(backup), stdout=StringIO())

    # Спорные ответы источника, русская запись, заглушка и то же вещество не тронуты.
    assert fields(medicines) == {**before, "different": "Amoksisilin + Klavulanik asit", "placeholder": "Albumin"}
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert [(row["before"], row["after"]) for row in saved] == [
        ("amoksisilin", "Amoksisilin + Klavulanik asit"), ("immunglobulin", "Albumin"),
    ]
    with pytest.raises(CommandError):  # прежняя копия не перезаписывается
        call_command(COMMAND, "--apply", "--backup", str(backup), stdout=StringIO())

    call_command(COMMAND, "--restore", str(backup), stdout=StringIO())
    assert fields(medicines) == before


def test_restore_keeps_later_manual_edit(medicines, tmp_path):
    backup = tmp_path / "ingredient.json"
    call_command(COMMAND, "--apply", "--backup", str(backup), stdout=StringIO())
    MedicineProduct.objects.filter(pk=medicines["different"].pk).update(active_ingredient="Ручная правка")
    out = StringIO()

    call_command(COMMAND, "--restore", str(backup), stdout=out)

    assert fields(medicines)["different"] == "Ручная правка"
    assert "Возвращено: 1 из 2" in out.getvalue()
