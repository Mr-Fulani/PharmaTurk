import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, MedicineProduct, Product


@pytest.fixture
def products(db, monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    category = Category.objects.create(name="Медицина", slug="old-price-cleanup")
    medicine = MedicineProduct.objects.create(
        name="Лекарство", slug="old-price-medicine", category=category, price=100, old_price=120,
        currency="TRY", external_data={"source": "ilacfiyati"},
    )
    manual = Product.objects.create(
        name="Ручной товар", slug="old-price-manual", category=category, product_type="clothing",
        price=100, old_price=150, currency="TRY", external_data={},
    )
    instagram = Product.objects.create(
        name="Instagram", slug="old-price-instagram", category=category, product_type="clothing",
        price=100, old_price=150, currency="RUB", external_data={"source": "instagram"},
    )
    return medicine, manual, instagram


def test_dry_run_reports_without_changes(products):
    medicine, _, _ = products
    out = StringIO()

    call_command("clear_heuristic_old_prices", stdout=out)

    medicine.refresh_from_db()
    assert medicine.old_price == 120
    assert "ilacfiyati: old_price у 1 товаров" in out.getvalue()


def test_apply_requires_backup(products):
    with pytest.raises(CommandError):
        call_command("clear_heuristic_old_prices", "--apply")


def test_apply_clears_parser_products_and_domain_with_backup(products, tmp_path):
    medicine, manual, instagram = products
    backup = tmp_path / "old_price.json"

    call_command("clear_heuristic_old_prices", "--apply", "--backup", str(backup), stdout=StringIO())

    medicine.refresh_from_db()
    medicine.base_product.refresh_from_db()
    manual.refresh_from_db()
    instagram.refresh_from_db()
    assert medicine.old_price is None and medicine.base_product.old_price is None
    assert manual.old_price == 150 and instagram.old_price == 150
    saved = json.loads(backup.read_text())
    assert saved["products"] == [[medicine.base_product_id, "120.00"]]
    assert saved["domain"][0][1:] == [medicine.pk, medicine.base_product_id, "120.00"]
