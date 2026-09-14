from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.currency_models import GlobalCurrencySettings
from apps.catalog.models import Category, Product
from apps.catalog.utils.product_markup import apply_product_markup, get_effective_product_markup


def node(margin, parent=None, pk=None):
    return SimpleNamespace(margin_percent=Decimal(str(margin)), parent=parent, pk=pk)


@pytest.fixture
def global_markup(monkeypatch):
    monkeypatch.setattr(GlobalCurrencySettings, "load", lambda: SimpleNamespace(default_margin_percentage=Decimal("15")))


def test_zero_child_inherits_parent_markup(global_markup):
    product = SimpleNamespace(brand=None, category=node(0, node(50)))
    assert get_effective_product_markup(product) == (Decimal("50"), "category")
    assert apply_product_markup(Decimal("100"), product) == Decimal("150.00")


@pytest.mark.parametrize("brand,leaf,middle,root,expected,source", [
    (20, 30, 40, 50, 20, "brand"),
    (0, 30, 40, 50, 30, "category"),
    (0, 0, 40, 50, 40, "category"),
    (0, 0, 0, 50, 50, "category"),
    (0, 0, 0, 0, 15, "global"),
    (0, -1, -1, 50, 50, "category"),
])
def test_nearest_positive_markup_wins_without_stacking(global_markup, brand, leaf, middle, root, expected, source):
    product = SimpleNamespace(brand=node(brand), category=node(leaf, node(middle, node(root))))
    assert get_effective_product_markup(product) == (Decimal(str(expected)), source)


def test_no_category_and_legacy_category_objects_still_work(global_markup):
    assert get_effective_product_markup(SimpleNamespace(brand=None, category=None)) == (Decimal("15"), "global")
    assert get_effective_product_markup(SimpleNamespace(brand=None, category=SimpleNamespace(margin_percent=0))) == (Decimal("15"), "global")


@pytest.mark.parametrize("same_pk", [False, True])
def test_cycles_do_not_hang_and_fall_back_to_global(global_markup, same_pk):
    a, b = node(0, pk=1 if same_pk else None), node(0, pk=1 if same_pk else None)
    a.parent, b.parent = b, a
    assert get_effective_product_markup(SimpleNamespace(brand=None, category=a)) == (Decimal("15"), "global")


def test_cycle_with_usable_ancestor_keeps_nearest_markup(global_markup):
    a, b = node(0), node(40)
    a.parent, b.parent = b, a
    assert get_effective_product_markup(SimpleNamespace(brand=None, category=a)) == (Decimal("40"), "category")


@pytest.mark.django_db
def test_inherited_markup_uses_cached_relations_and_fresh_objects_see_parent_edits():
    root = Category.objects.create(name="Markup root", slug="markup-root", margin_percent=50)
    parent = Category.objects.create(name="Markup parent", slug="markup-parent", parent=root)
    leaf = Category.objects.create(name="Markup leaf", slug="markup-leaf", parent=parent)
    product = Product.objects.bulk_create([Product(name="Markup test", slug="markup-test", category=leaf, price=100)])[0]
    loaded = Product.objects.select_related("brand", "category__parent__parent").get(pk=product.pk)
    before = Product.objects.filter(pk=product.pk).values().get()
    with CaptureQueriesContext(connection) as queries:
        for _ in range(10):
            assert apply_product_markup(100, loaded) == Decimal("150.00")
    assert len(queries) == 0
    assert Product.objects.filter(pk=product.pk).values().get() == before
    Category.objects.filter(pk=root.pk).update(margin_percent=60)
    fresh = Product.objects.select_related("brand", "category__parent__parent").get(pk=product.pk)
    assert apply_product_markup(100, fresh) == Decimal("160.00")


@pytest.mark.django_db
def test_real_category_cycle_is_bounded(global_markup):
    a = Category.objects.create(name="Cycle a", slug="cycle-a")
    b = Category.objects.create(name="Cycle b", slug="cycle-b", parent=a)
    Category.objects.filter(pk=a.pk).update(parent=b)
    product = SimpleNamespace(brand=None, category=Category.objects.get(pk=a.pk))
    with CaptureQueriesContext(connection) as queries:
        assert get_effective_product_markup(product) == (Decimal("15"), "global")
    assert len(queries) <= 2
