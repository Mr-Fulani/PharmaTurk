"""Одежда из «Спорттоваров» — в раздел одежды: смена типа без потери фото и переводов (без сети)."""

import json
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import (
    Category,
    ClothingProduct,
    Product,
    ProductTranslation,
    SportsProduct,
    SportsProductImage,
    SportsProductTranslation,
)
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService

COMMAND = "move_clothing_out_of_sports"


def _cat(slug, parent=None, **extra):
    return Category.objects.create(slug=slug, name=slug, parent=parent, **extra)


@pytest.fixture
def catalog(db):
    sports = _cat("sports")
    sportswear = _cat("sportswear-footwear", sports)
    clothing = _cat("clothing")
    return {
        "sports": sports,
        "tracksuits": _cat("tracksuits", sportswear),
        "balls": _cat("basketball-balls", sports),
        "suits": _cat("suits", clothing),
        "shorts": _cat("shorts", clothing),
    }


def _colour(code, colour, sizes, **extra):
    return {
        "external_id": f"superstep-variant-{code}", "sku": code, "color": colour, "price": 4599, "old_price": None,
        "currency": "TRY", "is_available": True, "external_url": f"https://www.superstep.com.tr/urun/{code}/",
        "images": [f"https://cdn.example/products/parsed/{code}.jpg"],
        "sizes": [{"size": size, "is_available": available, "stock_quantity": 1000 if available else 0}
                  for size, available in sizes],
        **extra,
    }


def _sports_product(external_id, name, category, subgroup, colours=()):
    attributes = {"superstep_subgroup": subgroup, "gender": "men"}
    if colours:
        attributes["fashion_variants"] = list(colours)
    product = Product.objects.create(
        name=name, slug=external_id.replace(".", "-"), external_id=external_id, product_type="sports",
        category=category, price=Decimal("4599"), currency="TRY",
        external_url=colours[0]["external_url"] if colours else f"https://www.superstep.com.tr/urun/{external_id}/",
        description="Описание карточки",
        external_data={"source": "superstep", "attributes": attributes},
    )
    return product, SportsProduct.objects.get(base_product=product)


def test_tracksuit_becomes_clothing_with_photos_and_translations(catalog, tmp_path):
    black = _colour("FN4877.010", "Siyah", [("M", True), ("L", False)], sort_order=0)
    grey = _colour("FN4877.063", "Gri", [("S", True)], sort_order=1)
    product, sports_row = _sports_product(
        "superstep-FN4877", "Мужской спортивный костюм Nike Club", catalog["tracksuits"], "Eşofman Takımı", [black, grey],
    )
    ball, ball_row = _sports_product("superstep-DX2489.855", "Nike Basketbol Topu", catalog["balls"], "Basketbol Topu")
    ProductTranslation.objects.create(product=product, locale="en", name="Nike Club Men's Tracksuit")
    SportsProductTranslation.objects.create(product=sports_row, locale="ru", name=product.name, description="Описание")
    SportsProduct.objects.filter(pk=sports_row.pk).update(meta_title="Nike Club tracksuit", gender="men")
    for index in range(2):
        SportsProductImage.objects.bulk_create([SportsProductImage(
            product=sports_row, image_file=f"products/sports/tracksuits/nike-{index}.jpg",
            image_url=f"https://cdn.example/nike-{index}.jpg", sort_order=index, is_main=index == 0,
        )])

    call_command(COMMAND)
    assert Product.objects.get(pk=product.pk).product_type == "sports"  # показ ничего не меняет
    assert not ClothingProduct.objects.exists()
    with pytest.raises(CommandError):
        call_command(COMMAND, "--apply")

    backup = tmp_path / "move.json"
    call_command(COMMAND, "--apply", "--backup", str(backup))

    product.refresh_from_db()
    assert (product.product_type, product.category.slug) == ("clothing", "suits")
    assert product.slug == "superstep-FN4877"  # адрес карточки не меняется
    assert product.translations.get(locale="en").name == "Nike Club Men's Tracksuit"
    clothing = ClothingProduct.objects.get(base_product=product)
    assert (clothing.slug, clothing.category.slug, clothing.is_active) == (product.slug, "suits", True)
    assert (clothing.price, clothing.meta_title, clothing.gender) == (Decimal("4599"), "Nike Club tracksuit", "men")
    assert clothing.translations.get(locale="ru").description == "Описание"
    # Цвета и размеры — из сохранённого ответа парсера; фото прежней записи — у главного цвета,
    # общая галерея пуста (у одежды фото у вариантов — после повторного сбора не задвоятся).
    variants = list(clothing.variants.order_by("sort_order"))
    assert [(v.color, v.external_id) for v in variants] == [
        ("Siyah", "superstep-variant-FN4877.010"), ("Gri", "superstep-variant-FN4877.063"),
    ]
    assert [(row.size, row.is_available) for row in variants[0].sizes.order_by("sort_order")] == [("M", True), ("L", False)]
    assert [row.size for row in variants[1].sizes.all()] == ["S"]
    assert sorted(image.image_file.name for image in variants[0].images.all()) == [
        "products/sports/tracksuits/nike-0.jpg", "products/sports/tracksuits/nike-1.jpg",
    ]
    assert not variants[1].images.exists() and not clothing.images.exists()
    assert (product.description, product.name) == ("Описание карточки", "Мужской спортивный костюм Nike Club")
    sports_row.refresh_from_db()
    assert sports_row.is_active is False and sports_row.images.count() == 2  # снята, не удалена
    # Мяч — снаряд: остаётся спорттоваром.
    assert Product.objects.get(pk=ball.pk).product_type == "sports"
    assert SportsProduct.objects.get(pk=ball_row.pk).is_active is True

    # Повторный сбор карточки: товар уже одежда — варианты обновляются, новых не появляется.
    scraped = ScrapedProduct(
        name="Nike Club Erkek Eşofman Takımı", price=4599, currency="TRY", url=product.external_url,
        external_id=product.external_id, source="superstep", category="suits",
        attributes={"gender": "men", "superstep_subgroup": "Eşofman Takımı", "fashion_variants": [
            {**black, "images": [], "sizes": [{"size": "M", "is_available": False, "stock_quantity": 0}]},
            {**grey, "images": []},
        ]},
    )
    scraped._category_override = catalog["suits"]
    status, _ = ScraperIntegrationService()._update_existing_product(None, scraped, product)
    assert status == "updated"
    assert clothing.variants.count() == 2
    assert [(row.size, row.is_available) for row in variants[0].sizes.all()] == [("M", False)]
    product.refresh_from_db()
    assert (product.product_type, product.category.slug, product.name) == ("clothing", "suits", "Мужской спортивный костюм Nike Club")
    assert SportsProduct.objects.get(pk=sports_row.pk).is_active is False

    call_command(COMMAND, "--rollback", str(backup))

    product.refresh_from_db()
    assert (product.product_type, product.category.slug) == ("sports", "tracksuits")
    assert SportsProduct.objects.get(pk=sports_row.pk).is_active is True
    assert ClothingProduct.objects.get(pk=clothing.pk).is_active is False  # не удалена: на её фото есть ссылки
    assert json.loads(backup.read_text(encoding="utf-8"))["products"][0]["product_id"] == product.pk


def test_section_moves_to_clothing_with_its_products(catalog, tmp_path):
    """Вариант «перенести сам раздел»: адрес раздела тот же, товары становятся одеждой в нём же."""
    product, _row = _sports_product("superstep-FN4877", "Nike Club Erkek Eşofman Takımı", catalog["tracksuits"], "Eşofman Takımı")
    manual = Product.objects.create(
        name="Костюм из Instagram", slug="ig-suit", product_type="sports", category=catalog["tracksuits"],
    )

    call_command(COMMAND, "--move-section", "tracksuits:suits")
    assert Category.objects.get(slug="tracksuits").parent.slug == "sportswear-footwear"  # показ откатывает раздел

    backup = tmp_path / "move.json"
    call_command(COMMAND, "--move-section", "tracksuits:suits", "--apply", "--backup", str(backup))

    assert Category.objects.get(slug="tracksuits").parent.slug == "suits"
    for item in (product, manual):
        item.refresh_from_db()
        assert (item.product_type, item.category.slug) == ("clothing", "tracksuits")
        assert ClothingProduct.objects.get(base_product=item).category.slug == "tracksuits"

    call_command(COMMAND, "--rollback", str(backup))
    assert Category.objects.get(slug="tracksuits").parent.slug == "sportswear-footwear"
    assert Product.objects.get(pk=manual.pk).product_type == "sports"


def test_explicit_product_and_markup_guard(catalog, tmp_path):
    """Бриджи из Instagram — по решению владельца, явной парой; другая наценка = другая цена — только с флагом."""
    Category.objects.filter(pk=catalog["shorts"].pk).update(margin_percent=Decimal("40"))
    shorts = Product.objects.create(
        name="Мужские бриджи для плавания", slug="ig-shorts", product_type="sports",
        category=catalog["sports"], price=Decimal("1000"), currency="TRY",
    )
    backup = tmp_path / "move.json"
    args = (COMMAND, "--move", f"{shorts.pk}:shorts", "--apply", "--backup", str(backup))

    with pytest.raises(CommandError, match="наценка"):
        call_command(*args)
    assert Product.objects.get(pk=shorts.pk).product_type == "sports"

    call_command(*args, "--allow-markup-change")
    shorts.refresh_from_db()
    assert (shorts.product_type, shorts.category.slug) == ("clothing", "shorts")
