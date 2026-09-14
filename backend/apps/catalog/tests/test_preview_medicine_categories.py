from io import StringIO
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.management.commands.preview_medicine_categories import Command
from apps.catalog.models import Category, MedicineProduct, Product


def test_preview_has_no_apply_mode_and_rejects_invalid_limits():
    parser = Command().create_parser("manage.py", "preview_medicine_categories")
    with pytest.raises(CommandError):
        parser.parse_args(["--apply"])
    for options in ({"limit": 0}, {"examples": -1}, {"examples": 11}):
        with pytest.raises(CommandError):
            Command().handle(**options)


@pytest.mark.django_db(transaction=True)
def test_preview_cannot_write_and_does_not_require_seeded_targets():
    root, _ = Category.objects.get_or_create(slug="medicines", defaults={"name": "Медицина"})
    # Build exact fixtures without Product.save() synchronising a second
    # MedicineProduct or invoking exchange-rate services.
    shadow = Product.objects.bulk_create([
        Product(name="Keep all fields", slug="keep-all-fields", price=7,
                description="Keep text", category=root),
    ])[0]
    MedicineProduct.objects.bulk_create([
        MedicineProduct(name="Antibiotic", slug="antibiotic", atc_code="J01CA04", category=root, base_product=shadow, price=7),
        MedicineProduct(name="Nervous", slug="nervous", atc_code="N03AX12", price=7),
        MedicineProduct(name="Unknown", slug="unknown", price=7),
        MedicineProduct(name="Stub", slug="stub", atc_code="J01CA04", external_data={"is_stub": True}, price=7),
    ])
    before = list(MedicineProduct.objects.order_by("id").values())
    before_shadow = Product.objects.filter(pk=shadow.pk).values().get()
    before_categories = list(Category.objects.order_by("id").values())
    out = StringIO()
    with CaptureQueriesContext(connection) as queries:
        call_command("preview_medicine_categories", as_json=True, examples=1, stdout=out)
    report = json.loads(out.getvalue())
    assert report["statuses"] == {"proposed": 2, "review": 1, "stub": 1}
    assert report["mode"] == "dry_run" and report["writes"] == 0
    assert list(MedicineProduct.objects.order_by("id").values()) == before
    assert Product.objects.filter(pk=shadow.pk).values().get() == before_shadow
    assert list(Category.objects.order_by("id").values()) == before_categories
    assert not any(q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")) for q in queries)
    if connection.vendor == "postgresql":
        assert report["database_read_only"]
        assert any("READ ONLY" in q["sql"] for q in queries)


@pytest.mark.django_db(transaction=True)
def test_postgresql_rejects_even_an_accidental_write_in_preview(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Database-enforced READ ONLY requires PostgreSQL")
    category = Category.objects.create(slug="readonly-proof", name="Unchanged")

    def accidental_write(self, **kwargs):
        Category.objects.filter(pk=category.pk).update(name="Must not be saved")

    monkeypatch.setattr(Command, "_preview", accidental_write)
    with pytest.raises(DatabaseError, match="read-only transaction"):
        call_command("preview_medicine_categories", stdout=StringIO())
    category.refresh_from_db()
    assert category.name == "Unchanged"
