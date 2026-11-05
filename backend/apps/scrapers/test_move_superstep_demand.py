"""Перенос уже загруженных товаров SuperStep в разделы по спросу (без сети)."""

import json
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, Product


def _cat(slug, parent=None, **extra):
    return Category.objects.create(slug=slug, name=slug, parent=parent, **extra)


def _product(external_id, name, category, subgroup, gender=""):
    return Product.objects.create(
        name=name, slug=external_id, external_id=external_id, product_type="shoes", category=category,
        external_data={"attributes": {"superstep_subgroup": subgroup, "gender": gender}},
    )


@pytest.fixture
def catalog(db):
    shoes = _cat("shoes-x")
    boots = _cat("boots", shoes)
    _cat("ugg-boots", boots)
    sandals = _cat("sandals", shoes)
    slides = _cat("slides", sandals)
    _cat("clogs", sandals, margin_percent=Decimal("40"))
    return {"boots": boots, "slides": slides}


def test_dry_run_and_apply_move_only_demand_categories(catalog, tmp_path):
    ugg = _product("superstep-1116109", "UGG Classic Ultra Mini Kadın Bot", catalog["boots"], "Bot", "women")
    boots = _product("superstep-TB0A1", "Timberland 6 Inch Erkek Bot", catalog["boots"], "Bot", "men")
    clog = _product("superstep-207006", "Crocs Crocband Clog Çocuk Terlik", catalog["slides"], "Terlik", "kids")
    translated = _product("superstep-1173891", "Женские угги UGG Classic Micro", catalog["boots"], "Bot", "women")

    call_command("move_superstep_to_demand_categories")
    assert Product.objects.get(pk=ugg.pk).category.slug == "boots"  # показ ничего не меняет

    with pytest.raises(CommandError):
        call_command("move_superstep_to_demand_categories", "--apply")

    backup = tmp_path / "move.json"
    call_command("move_superstep_to_demand_categories", "--apply", "--backup", str(backup))

    assert Product.objects.get(pk=ugg.pk).category.slug == "ugg-boots"
    assert Product.objects.get(pk=boots.pk).category.slug == "boots"  # не новый раздел — не трогаем
    assert Product.objects.get(pk=clog.pk).category.slug == "slides"  # у «Сабо» своя наценка — цена бы изменилась
    # название уже переведено: угги/сабо/флис узнаются по турецкому названию — не угадываем
    assert Product.objects.get(pk=translated.pk).category.slug == "boots"
    assert Product.objects.get(pk=ugg.pk).slug == "superstep-1116109"  # адрес не меняется
    assert json.loads(backup.read_text(encoding="utf-8")) == [
        {"product_id": ugg.pk, "category_id": catalog["boots"].pk, "new_category_id": Category.objects.get(slug="ugg-boots").pk}
    ]
