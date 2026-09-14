"""Bounded category-only canary; never call model.save(), media or parser jobs."""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from .medicine_taxonomy import propose_medicine_category
from .currency_models import GlobalCurrencySettings
from .utils.product_markup import get_category_markup
from .models import (
    Category, MedicineProduct, MedicineProductImage, MedicineProductTranslation,
    Product, ProductImage, ProductTranslation,
)


class PilotConflict(RuntimeError):
    pass


def _canonical(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True))


def _assert_markup_unchanged(product, target):
    """Changing a navigation FK must not silently change the public markup."""
    if product.brand_id and product.brand.margin_percent > 0:
        return  # The same brand overrides both categories.
    old_margin = get_category_markup(product.category)
    new_margin = get_category_markup(target)
    if old_margin == new_margin:
        return
    global_margin = GlobalCurrencySettings.objects.filter(pk=1).values_list(
        "default_margin_percentage", flat=True,
    ).first()
    if global_margin is None:
        raise PilotConflict("Cannot verify public markup without configured global settings")
    old_effective = old_margin if old_margin is not None else global_margin
    new_effective = new_margin if new_margin is not None else global_margin
    if old_effective != new_effective:
        raise PilotConflict("Category change would alter the effective public markup")


def _validate_plan(plan, expected_count):
    if not 1 <= expected_count <= 100 or len(plan) != expected_count:
        raise PilotConflict("Pilot must contain the exact approved count, at most 100")
    for key in ("product_id", "medicine_id"):
        if any(type(row[key]) is not int or row[key] < 1 for row in plan):
            raise PilotConflict("Invalid product identity")
        if len({row[key] for row in plan}) != len(plan):
            raise PilotConflict("Duplicate product identity")


def take_snapshot(plan, *, expected_count=100):
    _validate_plan(plan, expected_count)
    product_ids = [row["product_id"] for row in plan]
    medicine_ids = [row["medicine_id"] for row in plan]
    groups = {
        "products": Product.objects.filter(pk__in=product_ids),
        "medicines": MedicineProduct.objects.filter(pk__in=medicine_ids),
        "product_images": ProductImage.objects.filter(product_id__in=product_ids),
        "medicine_images": MedicineProductImage.objects.filter(product_id__in=medicine_ids),
        "product_translations": ProductTranslation.objects.filter(product_id__in=product_ids),
        "medicine_translations": MedicineProductTranslation.objects.filter(product_id__in=medicine_ids),
    }
    snapshot = {key: list(query.order_by("pk").values()) for key, query in groups.items()}
    if len(snapshot["products"]) != len(plan) or len(snapshot["medicines"]) != len(plan):
        raise PilotConflict("A selected card no longer exists")
    return _canonical(snapshot)


def _lock_cards(plan):
    products = {row.pk: row for row in Product.objects.select_for_update().filter(
        pk__in=[item["product_id"] for item in plan],
    ).order_by("pk")}
    medicines = {row.pk: row for row in MedicineProduct.objects.select_for_update().filter(
        pk__in=[item["medicine_id"] for item in plan],
    ).order_by("pk")}
    if len(products) != len(plan) or len(medicines) != len(plan):
        raise PilotConflict("A selected card disappeared")
    for row in plan:
        if medicines[row["medicine_id"]].base_product_id != row["product_id"]:
            raise PilotConflict("Product/domain identity changed")
    return products, medicines


def assert_only_categories_changed(before, after, assigned):
    expected = _canonical(before)
    for group, key in (("products", "product_id"), ("medicines", "medicine_id")):
        mapping = {row[key]: row["category_id"] for row in assigned}
        for row in expected[group]:
            row["category_id"] = mapping[row["id"]]
    if expected != _canonical(after):
        raise PilotConflict("An unrelated card field, translation or image changed")


def apply_pilot(plan, before, *, expected_count=100):
    """Requires a durable backup of before; CAS-checks every field before writing."""
    _validate_plan(plan, expected_count)
    with transaction.atomic():
        products, medicines = _lock_cards(plan)
        if take_snapshot(plan, expected_count=expected_count) != _canonical(before):
            raise PilotConflict("Cards changed since backup; no writes performed")
        root = Category.objects.get(slug="medicines", parent__isnull=True, is_active=True)
        assigned = []
        for row in plan:
            product, medicine = products[row["product_id"]], medicines[row["medicine_id"]]
            if product.product_type != "medicines" or not product.is_active or not medicine.is_active:
                raise PilotConflict("Selected card is not an active medicine")
            if product.category_id not in (None, root.pk) or medicine.category_id not in (None, root.pk):
                raise PilotConflict("An existing specific category must not be overwritten")
            for obj in (product, medicine):
                data = obj.external_data if isinstance(obj.external_data, dict) else {}
                attrs = data.get("attributes") or {}
                if data.get("is_stub") is True or (isinstance(attrs, dict) and attrs.get("is_stub") is True):
                    raise PilotConflict("Incomplete card cannot enter pilot")
                if data.get("source_variant_id") or data.get("source_variant_slug"):
                    raise PilotConflict("Variant cannot enter pilot")
            if not medicine.barcode or not row.get("source_barcode"):
                raise PilotConflict("A fresh matching barcode is required")
            proposal = propose_medicine_category(
                atc_code=medicine.atc_code, source_atc_code=row["source_atc"],
                barcode=medicine.barcode, source_barcode=row["source_barcode"],
            )
            if proposal.status != "proposed" or proposal.category_slug != row["to_slug"]:
                raise PilotConflict("Fresh source and card do not agree on category")
            target = Category.objects.filter(
                slug=row["to_slug"], parent=root, is_active=True,
            ).first()
            if not target:
                raise PilotConflict("Target category has not been seeded")
            _assert_markup_unchanged(product, target)
            _assert_markup_unchanged(medicine, target)
            assigned.append({**row, "category_id": target.pk})
        for row in assigned:
            if Product.objects.filter(pk=row["product_id"]).update(category_id=row["category_id"]) != 1:
                raise PilotConflict("Product update failed")
            if MedicineProduct.objects.filter(pk=row["medicine_id"]).update(category_id=row["category_id"]) != 1:
                raise PilotConflict("Medicine update failed")
        assert_only_categories_changed(
            before, take_snapshot(plan, expected_count=expected_count), assigned,
        )
        return assigned


def rollback_pilot(plan, before, assigned, *, expected_count=100):
    """Restore only old category IDs; do not overwrite subsequent content edits."""
    _validate_plan(plan, expected_count)
    _validate_plan(assigned, expected_count)
    if {(row["product_id"], row["medicine_id"]) for row in assigned} != {
        (row["product_id"], row["medicine_id"]) for row in plan
    }:
        raise PilotConflict("Rollback plan does not match the pilot")
    for group, key in (("products", "product_id"), ("medicines", "medicine_id")):
        if len(before[group]) != expected_count or {row["id"] for row in before[group]} != {
            row[key] for row in plan
        }:
            raise PilotConflict("Backup identities do not match the pilot")
    with transaction.atomic():
        products, medicines = _lock_cards(plan)
        for row in assigned:
            if (products[row["product_id"]].category_id != row["category_id"]
                    or medicines[row["medicine_id"]].category_id != row["category_id"]):
                raise PilotConflict("A category was changed after the pilot; refusing to overwrite it")
        for group, model in (("products", Product), ("medicines", MedicineProduct)):
            for row in before[group]:
                if model.objects.filter(pk=row["id"]).update(category_id=row["category_id"]) != 1:
                    raise PilotConflict("Rollback update failed")
