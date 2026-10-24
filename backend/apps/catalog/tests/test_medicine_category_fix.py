"""Миграция 0226: из «Антибиотиков» уходят медикаменты с кодом АТХ не J01 (LEVOTIRON)."""

import importlib
from decimal import Decimal

import pytest
from django.apps import apps as django_apps

from apps.catalog.models import Category, MedicineProduct, Product

antibiotics_fix = importlib.import_module("apps.catalog.migrations.0226_fix_non_antibiotics_category")


@pytest.mark.django_db
def test_antibiotics_fix_moves_only_non_j01_medicines_by_atc(monkeypatch):
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    root = Category.objects.update_or_create(slug="medicines", defaults={"name": "Medicine"})[0]
    antibiotics = Category.objects.update_or_create(slug="antibiotics", defaults={"name": "Antibiotics", "parent": root})[0]
    endocrinology = Category.objects.update_or_create(
        slug="endocrinology-diabetes", defaults={"name": "Hormones", "parent": root, "is_active": True},
    )[0]

    def create(slug, name, atc):
        base = Product.objects.create(
            name=name, slug=slug, product_type="medicines", category=antibiotics,
            price=Decimal("10.00"), currency="TRY", is_active=True,
        )
        MedicineProduct.objects.filter(base_product=base).update(atc_code=atc)
        return MedicineProduct.objects.get(base_product=base)

    levotiron = create("levotiron-75", "LEVOTIRON 75 MCG", "H03AA01")
    zimaks = create("zimaks-400", "ZIMAKS 400 MG 10 TABLET", "J01DD08")
    unknown = create("no-atc", "NO ATC 1 MG", "")

    antibiotics_fix.move_non_antibiotics(django_apps, None)

    levotiron.refresh_from_db()
    assert levotiron.category_id == endocrinology.id
    assert Product.objects.get(pk=levotiron.base_product_id).category_id == endocrinology.id
    assert MedicineProduct.objects.get(pk=zimaks.pk).category_id == antibiotics.id
    assert MedicineProduct.objects.get(pk=unknown.pk).category_id == antibiotics.id
