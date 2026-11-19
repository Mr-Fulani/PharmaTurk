"""Команда «что изменится»: считает по текущим правилам и по примеряемой шкале, ничего не пишет."""

import csv
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.currency_models import GlobalCurrencySettings, MarkupScale
from apps.catalog.models import Brand, Category, Product

SCALE = "0:100,5000:50,10000:20"


def run(*args):
    out = StringIO()
    call_command("markup_scale_preview", *args, stdout=out)
    return out.getvalue()


def product(slug, price, product_type="shoes", **extra):
    extra.setdefault("is_active", True)
    return Product(
        name=f"Preview {slug}", slug=f"preview-{slug}", product_type=product_type,
        price=Decimal(price), currency="TRY", **extra,
    )


@pytest.fixture
def catalog(db):
    settings = GlobalCurrencySettings.load()
    settings.default_margin_percentage = Decimal("15")
    settings.save()
    plain = Category.objects.create(name="Preview plain", slug="preview-plain")
    fifty = Category.objects.create(name="Preview fifty", slug="preview-fifty", margin_percent=Decimal("50"))
    brand = Brand.objects.create(name="Preview brand", slug="preview-brand", margin_percent=Decimal("30"))
    # bulk_create: без Product.save() и пересчёта цен в валютах
    Product.objects.bulk_create([
        product("cheap", "100", category=plain),
        product("dear", "20000", category=plain),
        product("branded", "100", category=plain, brand=brand),
        product("medicine", "100", product_type="medicines"),
        product("fifty", "20000", category=fifty),
        product("hidden", "100", category=plain, is_active=False),
    ])
    return plain, fifty


def test_global_preview_counts_changes_by_type_and_writes_nothing(catalog, tmp_path):
    report = tmp_path / "scale.csv"

    output = run("--scale", SCALE, "--csv", str(report))

    assert "Активных товаров с ценой: 5; цена изменится у 2." in output
    # 100 лир: 15 % → 100 %; 20 000 лир: 15 % → 20 %; бренд и раздел с 50 % сильнее шкалы
    assert "shoes | 4 | 2 | 0 | 2 | " in output
    assert "medicines | 1 | 0 | 0 | 1 | — | —" in output
    assert "Товаров на ступенях шкалы: от 0 лир — 1; от 10000 лир — 1" in output
    assert "Ничего не записано" in output

    rows = list(csv.reader(report.open(encoding="utf-8")))
    assert rows[0][:2] == ["id", "тип"]
    assert sorted(row[5:] for row in rows[1:]) == [
        ["15.00", "100.00", "115.00", "200.00", "73.91"],
        ["15.00", "20.00", "23000.00", "24000.00", "4.35"],
    ]
    assert MarkupScale.objects.count() == 0
    assert GlobalCurrencySettings.objects.get(pk=1).markup_scale_id is None
    assert not Category.objects.exclude(markup_scale=None).exists()


def test_category_preview_shows_cheaper_products(catalog):
    output = run("--scale", SCALE, "--category", "preview-fifty")

    # раздел с 50 %: товар за 20 000 лир по шкале получит 20 %
    assert "цена изменится у 1." in output
    assert "shoes | 4 | 0 | 1 | 3 | -20.0 | -20.0 … -20.0" in output
    assert "Сильнее всего подешевеют" in output
    assert "Сильнее всего подорожают" not in output


def test_saved_scale_can_be_previewed_by_number(catalog):
    scale = MarkupScale.objects.create(name="Сохранённая")
    scale.steps.create(price_from=0, percent=100)

    output = run("--scale-id", str(scale.pk))

    assert "Шкала «Сохранённая» глобально" in output
    assert "shoes | 4 | 2 | 0 | 2 | " in output


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--scale", SCALE, "--scale-id", "1"),
        ("--scale", "100:50"),
        ("--scale", "0:900"),
        ("--scale", "нет"),
        ("--scale-id", "999999"),
        ("--scale", SCALE, "--category", "no-such-section"),
    ],
)
def test_wrong_arguments_are_refused(catalog, args):
    with pytest.raises(CommandError):
        run(*args)
