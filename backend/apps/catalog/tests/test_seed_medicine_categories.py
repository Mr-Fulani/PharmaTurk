from io import StringIO

import pytest
from django.core.management import call_command

from apps.catalog.constants import MEDICINES_SUBCATEGORIES
from apps.catalog.management.commands.seed_catalog_data import Command, SUBCAT_TO_ROOT
from apps.catalog.medicine_taxonomy import MEDICINE_CATEGORY_SLUGS, RETIRED_MEDICINE_CATEGORY_SLUGS
from apps.catalog.models import Category, CategoryTranslation, MedicineProduct, Product


def category(slug, parent=None):
    item, _ = Category.objects.get_or_create(slug=slug, defaults={"name": slug})
    item.parent = parent
    item.is_active = True
    item.save()
    return item


def test_medicine_seed_uses_same_canonical_tree_and_no_legacy_hierarchy():
    assert {row[2] for row in MEDICINES_SUBCATEGORIES} == MEDICINE_CATEGORY_SLUGS
    assert {slug for slug, root in SUBCAT_TO_ROOT.items() if root == "medicines"} == MEDICINE_CATEGORY_SLUGS
    assert not RETIRED_MEDICINE_CATEGORY_SLUGS.intersection(SUBCAT_TO_ROOT)
    options = vars(Command().create_parser("manage.py", "seed_catalog_data").parse_args(["--medicines-only"]))
    assert options["medicines_only"]


@pytest.mark.django_db
def test_seed_is_idempotent_retires_empty_nodes_but_never_deletes_or_moves_goods():
    root = category("medicines")
    canonical = category("cardio", root)
    old = category("heart-cardiovascular", root)
    nested = category("omega-3-heart", old)
    populated = category("sleep-stress", root)
    product = Product.objects.create(name="Keep category", category=populated, price=1)
    other_root = category("supplements")
    other = category("melatonin", other_root)
    before_product = Product.objects.filter(pk=product.pk).values().get()
    before_other = Category.objects.filter(pk=other.pk).values().get()
    command = Command(stdout=StringIO())
    command._seed_medicines_subcategories()
    first = list(Category.objects.filter(parent=root).order_by("id").values())
    command._seed_medicines_subcategories()
    command._fix_hierarchy()
    assert list(Category.objects.filter(parent=root).order_by("id").values()) == first
    canonical.refresh_from_db()
    old.refresh_from_db()
    nested.refresh_from_db()
    populated.refresh_from_db()
    assert canonical.slug == "cardio" and canonical.name == "Сердечно-сосудистые препараты"
    assert not old.is_active and not nested.is_active
    assert populated.is_active
    assert Product.objects.filter(pk=product.pk).values().get() == before_product
    assert Category.objects.filter(pk=other.pk).values().get() == before_other
    assert CategoryTranslation.objects.get(category=canonical, locale="en").name == "Cardiovascular"


@pytest.mark.django_db
def test_retirement_protects_domain_only_products_and_custom_descendants():
    root = category("medicines")
    parent = category("cold-flu", root)
    child = category("cough-syrups", parent)
    MedicineProduct.objects.bulk_create([MedicineProduct(name="Domain only", category=child, price=1)])
    custom_parent = category("ent", root)
    custom = category("custom-ear-category", custom_parent)
    command = Command(stdout=StringIO())
    command._seed_medicines_subcategories()
    for item in (parent, child, custom_parent, custom):
        item.refresh_from_db()
        assert item.is_active
    assert MedicineProduct.objects.get(name="Domain only").category_id == child.pk


@pytest.mark.django_db
def test_medicines_only_does_not_touch_other_seed_sections(monkeypatch):
    category("medicines")

    def forbidden(*args, **kwargs):
        raise AssertionError("Unrelated seed section called")

    for name in ("_seed_brands", "_seed_root_categories", "_seed_category_types",
                 "_seed_supplements_subcategories", "_seed_attribute_keys", "_fix_hierarchy"):
        monkeypatch.setattr(Command, name, forbidden)
    call_command("seed_catalog_data", medicines_only=True, stdout=StringIO())


@pytest.mark.django_db
@pytest.mark.parametrize("populated", [False, True])
def test_seed_keeps_real_legacy_cardiovascular_name_without_unique_collision(populated):
    root = category("medicines")
    canonical = category("cardio", root)
    old = category("heart-cardiovascular", root)
    old.name = "Сердце и сосуды"
    old.save(update_fields=["name"])
    if populated:
        product = Product.objects.bulk_create([Product(name="Legacy heart medicine", category=old, product_type="medicines", price=1)])[0]
        before = Product.objects.filter(pk=product.pk).values().get()
    command = Command(stdout=StringIO())
    command._seed_medicines_subcategories()
    command._seed_medicines_subcategories()
    canonical.refresh_from_db()
    old.refresh_from_db()
    assert canonical.name == "Сердечно-сосудистые препараты"
    assert old.name == "Сердце и сосуды"
    assert old.is_active is populated
    if populated:
        assert Product.objects.filter(pk=product.pk).values().get() == before
