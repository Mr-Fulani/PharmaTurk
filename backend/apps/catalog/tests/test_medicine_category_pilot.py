import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.medicine_category_pilot import (
    PilotConflict, apply_pilot, assert_only_categories_changed, rollback_pilot, take_snapshot,
)
from apps.catalog.models import Category, MedicineProduct, MedicineProductImage, Product


@pytest.fixture
def pilot(db):
    root, _ = Category.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})
    target, _ = Category.objects.update_or_create(slug="antibiotics", defaults={"name": "Antibiotics", "parent": root, "is_active": True})
    rows = []
    for index in range(2):
        product = Product.objects.bulk_create([Product(name=f"Pilot {index}", slug=f"pilot-{index}", product_type="medicines", category=root, price=7, stock_quantity=None)])[0]
        medicine = MedicineProduct.objects.bulk_create([MedicineProduct(name=product.name, slug=product.slug, base_product=product, category=root, atc_code="J01CA04", barcode=f"123456789012{index}", active_ingredient="Keep ingredient", price=7)])[0]
        MedicineProductImage.objects.bulk_create([MedicineProductImage(product=medicine, image_url="https://example.test/keep.jpg")])
        rows.append({"product_id": product.pk, "medicine_id": medicine.pk, "to_slug": "antibiotics", "source_atc": "J01CA04", "source_barcode": medicine.barcode})
    return rows, target


def test_apply_changes_only_two_category_columns_and_can_rollback(pilot):
    rows, target = pilot
    before = take_snapshot(rows, expected_count=2)
    with CaptureQueriesContext(connection) as queries:
        assigned = apply_pilot(rows, before, expected_count=2)
    mutations = [item["sql"] for item in queries if item["sql"].lstrip().startswith(("UPDATE", "INSERT", "DELETE"))]
    assert len(mutations) == 4
    assert all('SET "category_id" =' in sql for sql in mutations)
    assert_only_categories_changed(before, take_snapshot(rows, expected_count=2), assigned)
    rollback_pilot(rows, before, assigned, expected_count=2)
    assert take_snapshot(rows, expected_count=2) == before


@pytest.mark.parametrize("change", ["atc", "category", "barcode", "identity", "stub"])
def test_invalid_or_stale_plan_is_atomic_and_writes_nothing(pilot, change):
    rows, target = pilot
    before = take_snapshot(rows, expected_count=2)
    if change == "atc":
        rows[1]["source_atc"] = "N03AX12"
    elif change == "barcode":
        rows[1]["source_barcode"] = "9999999999999"
    elif change == "identity":
        rows[1]["medicine_id"] = rows[0]["medicine_id"]
    elif change == "category":
        Product.objects.filter(pk=rows[1]["product_id"]).update(category=target)
    else:
        MedicineProduct.objects.filter(pk=rows[1]["medicine_id"]).update(external_data={"is_stub": True})
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(PilotConflict):
            apply_pilot(rows, before, expected_count=2)
    assert not any(item["sql"].lstrip().startswith(("UPDATE", "INSERT", "DELETE")) for item in queries)


def test_pilot_limits_cannot_be_accidentally_expanded(pilot):
    rows, _ = pilot
    with pytest.raises(PilotConflict):
        take_snapshot(rows)
    with pytest.raises(PilotConflict):
        take_snapshot(rows * 51, expected_count=102)


def test_rollback_preserves_new_content_but_refuses_new_manual_category(pilot):
    rows, target = pilot
    before = take_snapshot(rows, expected_count=2)
    assigned = apply_pilot(rows, before, expected_count=2)
    Product.objects.filter(pk=rows[0]["product_id"]).update(description="New manual text")
    rollback_pilot(rows, before, assigned, expected_count=2)
    assert Product.objects.get(pk=rows[0]["product_id"]).description == "New manual text"
    current = take_snapshot(rows, expected_count=2)
    assigned = apply_pilot(rows, current, expected_count=2)
    Product.objects.filter(pk=rows[0]["product_id"]).update(category=None)
    with pytest.raises(PilotConflict):
        rollback_pilot(rows, current, assigned, expected_count=2)
    assert Product.objects.get(pk=rows[0]["product_id"]).category_id is None


@pytest.mark.parametrize("change", ["extra_backup", "missing_backup", "wrong_pair", "duplicate_assignment"])
def test_rollback_rejects_mismatched_artifacts_without_writes(pilot, change):
    rows, _ = pilot
    before = take_snapshot(rows, expected_count=2)
    assigned = apply_pilot(rows, before, expected_count=2)
    if change == "extra_backup":
        before["products"].append({"id": 999999, "category_id": None})
    elif change == "missing_backup":
        before["medicines"].pop()
    elif change == "wrong_pair":
        assigned[0]["medicine_id"], assigned[1]["medicine_id"] = (
            assigned[1]["medicine_id"], assigned[0]["medicine_id"],
        )
    else:
        assigned.append(assigned[0])
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(PilotConflict):
            rollback_pilot(rows, before, assigned, expected_count=2)
    assert not any(item["sql"].lstrip().startswith(("UPDATE", "INSERT", "DELETE")) for item in queries)


@pytest.mark.parametrize("target_margin,allowed", [(0, True), (50, True), (20, False)])
def test_category_move_cannot_silently_change_public_markup(pilot, target_margin, allowed):
    from apps.catalog.currency_models import GlobalCurrencySettings
    rows, target = pilot
    GlobalCurrencySettings.objects.update_or_create(pk=1, defaults={"default_margin_percentage": 15})
    Category.objects.filter(slug="medicines").update(margin_percent=50)
    Category.objects.filter(pk=target.pk).update(margin_percent=target_margin)
    before = take_snapshot(rows, expected_count=2)
    with CaptureQueriesContext(connection) as queries:
        if allowed:
            assigned = apply_pilot(rows, before, expected_count=2)
            assert_only_categories_changed(before, take_snapshot(rows, expected_count=2), assigned)
        else:
            with pytest.raises(PilotConflict, match="public markup"):
                apply_pilot(rows, before, expected_count=2)
    if not allowed:
        assert not any(item["sql"].lstrip().startswith(("UPDATE", "INSERT", "DELETE")) for item in queries)
        assert take_snapshot(rows, expected_count=2) == before
