import json
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import (
    Category,
    ClothingProduct,
    ClothingVariant,
    IslamicClothingProduct,
    IslamicClothingVariant,
    Product,
)


def _colours(variant_model, domain, colours):
    for index, (price, old_price, available) in enumerate(colours):
        variant_model.objects.create(
            product=domain,
            name=f"Цвет {index}",
            slug=f"{domain.slug}-c{index}",
            color=f"color-{index}",
            price=Decimal(price),
            old_price=Decimal(old_price),
            currency="TRY",
            is_available=available,
            sort_order=index,
        )


@pytest.fixture
def products(db, monkeypatch):
    """Nautica K35052T до релиза: цена серого (распродан) при зачёркнутой синего."""
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    category = Category.objects.create(name="Поло", slug="recalc-colour-prices")
    nautica = ClothingProduct.objects.create(
        name="Nautica polo", slug="recalc-nautica", category=category,
        price=Decimal("749.70"), old_price=Decimal("1249.50"), currency="TRY",
        external_data={"source": "superstep"},
    )
    _colours(ClothingVariant, nautica, [("749.70", "899.00", False), ("999.60", "1249.50", True)])
    manual = IslamicClothingProduct.objects.create(
        name="Instagram abaya", slug="recalc-instagram", category=category,
        price=Decimal("500.00"), currency="TRY", external_data={"source": "instagram"},
    )
    _colours(IslamicClothingVariant, manual, [("400.00", "450.00", False), ("600.00", "700.00", True)])
    # Состояние «до» — без пересчётов сигналами при создании цветов.
    for domain, price, old_price, source in (
        (nautica, "749.70", "1249.50", "superstep"),
        (manual, "500.00", None, "instagram"),
    ):
        values = {"price": Decimal(price), "old_price": old_price and Decimal(old_price)}
        type(domain).objects.filter(pk=domain.pk).update(**values)
        Product.objects.filter(pk=domain.base_product_id).update(**values, external_data={"source": source})
        domain.refresh_from_db()
    return nautica, manual


def _base(domain):
    return Product.objects.get(pk=domain.base_product_id)


def test_dry_run_reports_without_changes(products):
    nautica, _ = products
    out = StringIO()

    call_command("recalc_colour_prices", stdout=out)

    assert _base(nautica).price == Decimal("749.70")
    assert "superstep: изменится 1 товаров, из них цена — 1" in out.getvalue()
    assert "price 749.70 → 999.60" in out.getvalue()


def test_apply_requires_backup(products):
    with pytest.raises(CommandError):
        call_command("recalc_colour_prices", "--apply", stdout=StringIO())


def test_apply_takes_pair_of_one_colour_in_stock_and_keeps_manual_sources(products, tmp_path):
    nautica, manual = products
    backup = tmp_path / "colour_prices.json"

    call_command("recalc_colour_prices", "--apply", "--backup", str(backup), "--batch-size", "1", stdout=StringIO())

    product = _base(nautica)
    nautica.refresh_from_db()
    pair = (Decimal("999.60"), Decimal("1249.50"))
    assert (product.price, product.old_price, product.is_available) == (*pair, True)
    assert (nautica.price, nautica.old_price) == pair
    assert _base(manual).price == Decimal("500.00")  # цену Instagram ведут вручную
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert [row["product_id"] for row in saved] == [nautica.base_product_id]
    assert saved[0]["before"]["price"] == "749.70"

    out = StringIO()
    call_command("recalc_colour_prices", stdout=out)
    assert "изменится: 0" in out.getvalue()
