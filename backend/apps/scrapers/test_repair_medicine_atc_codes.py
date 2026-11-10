import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, MedicineProduct, Product


def medicine(category, slug, field, *, own, base, stub=False):
    item = MedicineProduct.objects.create(
        name=slug.upper(), slug=slug, category=category, price=100, currency="TRY", atc_code=field,
        external_data={"source": "ilacfiyati"},
    )
    item.refresh_from_db()  # base_product создаётся при сохранении
    data = {"source": "ilacfiyati", "is_stub": stub}
    MedicineProduct.objects.filter(pk=item.pk).update(
        external_data={**data, "attributes": {"atc_code": own} if own else {}},
    )
    Product.objects.filter(pk=item.base_product_id).update(
        external_data={**data, "attributes": {"atc_code": base} if base else {}},
    )
    return item


@pytest.fixture
def medicines(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    category = Category.objects.create(name="Медицина", slug="atc-repair")
    return {
        "wrong": medicine(category, "brufen", "M02AA13", own="M01AE01", base="M01AE01"),
        "right": medicine(category, "junifen", "M01AE01", own="m01ae01", base="M01AE01"),
        "disputed": medicine(category, "imigran", "P03AC03", own="N02CC01", base="N02CC02"),
        "one_copy": medicine(category, "elocon", "R01AD09", own="D07AC13", base=""),
        "empty": medicine(category, "maxidex", "", own="S01BA01", base="S01BA01"),
        "stub": medicine(category, "aklovir", "D06BB03", own="J05AB01", base="J05AB01", stub=True),
    }


def codes(medicines):
    return {key: MedicineProduct.objects.get(pk=item.pk).atc_code for key, item in medicines.items()}


def test_show_reports_without_changes(medicines):
    before = codes(medicines)
    out = StringIO()

    call_command("repair_medicine_atc_codes", stdout=out)

    assert codes(medicines) == before
    assert "чужим кодом АТХ в поле: 1" in out.getvalue()
    assert "M02AA13 → M01AE01" in out.getvalue()


def test_apply_requires_backup(medicines):
    with pytest.raises(CommandError):
        call_command("repair_medicine_atc_codes", "--apply", stdout=StringIO())
    assert codes(medicines)["wrong"] == "M02AA13"


def test_apply_fixes_only_field_confirmed_by_both_copies(medicines, tmp_path):
    wrong = medicines["wrong"]
    before = MedicineProduct.objects.filter(pk=wrong.pk).values().get()
    before_base = Product.objects.filter(pk=wrong.base_product_id).values().get()
    backup = tmp_path / "atc.json"

    call_command("repair_medicine_atc_codes", "--apply", "--backup", str(backup), stdout=StringIO())

    assert codes(medicines) == {
        "wrong": "M01AE01", "right": "M01AE01", "disputed": "P03AC03",
        "one_copy": "R01AD09", "empty": "", "stub": "D06BB03",
    }
    after = MedicineProduct.objects.filter(pk=wrong.pk).values().get()
    assert {key for key in before if before[key] != after[key]} == {"atc_code"}
    assert Product.objects.filter(pk=wrong.base_product_id).values().get() == before_base
    assert json.loads(backup.read_text()) == [{
        "medicine_id": wrong.pk, "product_id": wrong.base_product_id, "name": "BRUFEN",
        "atc_code_before": "M02AA13", "atc_code_after": "M01AE01",
    }]


def test_restore_returns_previous_codes_unless_changed_later(medicines, tmp_path):
    before = codes(medicines)
    backup = tmp_path / "atc.json"
    call_command("repair_medicine_atc_codes", "--apply", "--backup", str(backup), stdout=StringIO())
    with pytest.raises(CommandError):
        call_command("repair_medicine_atc_codes", "--apply", "--backup", str(backup), stdout=StringIO())

    call_command("repair_medicine_atc_codes", "--restore", str(backup), stdout=StringIO())
    assert codes(medicines) == before

    call_command("repair_medicine_atc_codes", "--apply", "--backup", str(tmp_path / "2.json"), stdout=StringIO())
    MedicineProduct.objects.filter(pk=medicines["wrong"].pk).update(atc_code="M01AE51")
    call_command("repair_medicine_atc_codes", "--restore", str(tmp_path / "2.json"), stdout=StringIO())
    assert codes(medicines)["wrong"] == "M01AE51"
