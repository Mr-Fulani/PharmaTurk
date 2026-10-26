import csv
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, CategoryType, Product, SupplementProduct
from apps.catalog.supplement_taxonomy import (
    SUBCATEGORY_SLUGS,
    supplement_category_slug,
    supplement_category_slug_ru,
)
from apps.catalog.utils.product_markup import get_effective_product_markup


@pytest.mark.parametrize("name, slug", [
    ("NUTRAXIN B12 VITAMINI DILALTI TABLET 60 tablet", "vitamins"),
    ("WELLCARE MAGNEZYUM+VITAMIN B6 ICEREN TAKVIYE EDICI GIDA 60 tablet", "minerals"),
    ("NATURMAX VITAMIN C, VITAMIN D3 VE ÇİNKO İÇEREN TAKVİYE EDİCİ GIDA 20 tablet", "vitamins"),
    ("OMEGANAZ PORTAKALLI BALIK YAĞI İÇEREN SIVI TAKVİYE EDİCİ GIDA 150 ml şişe", "omega-fatty-acids"),
    ("ZADE VITAL OMEGA 3 KIDS PORTAKAL SURUP 100 ml şişe", "kids-supplements"),
    ("ZADE VITAL FEMINEN PROBIYOTIK BAKTERI ICEREN KAPSUL 30 kapsül", "probiotics"),
    ("COLLAQUIN HYDROLYZED COLLAGEN HIDROLIZE KOLLAJEN ICEREN TAKVIYE EDICI GIDA 30 saşe", "collagen"),
    ("MARNYS PROPALMAR PROPOLIS VE EKINEZYA ICEREN TAKVIYE EDICI GIDA 125 ml şişe", "immunity"),
    ("DOPPELHERZ KOENZIM Q10 KAPSUL 30 kapsül", "energy-vitality"),
    ("LIFE TIME CO-ENZYME Q10 KAPSUL 100 mg 30 kapsül", "energy-vitality"),
    ("VENATURA KARNIYARIK OTU TOZU TAKVIYE EDICI GIDA 500 mg 100 kapsül", "digestive-health"),
    ("DOPPELHERZ L-ARJININ KAPSUL 30 kapsül", "protein-amino"),
    ("VENATURA KREATIN MONOHIDRAT TAKVIYE EDICI GIDA 150 gr kutu", "sports-nutrition"),
    ("ZADE VITAL COREK OTU YAGI KAPSUL 60 kapsül", "herbal-supplements"),
    ("SOLGAR MELATONIN TABLET 60 tablet", None),
    ("AVICENNA GLUKOZAMIN, KONDROITIN & MSM, BROMELAIN ICEREN TAKVIYE EDICI GIDA 90 tablet", None),
    ("COSAKONDRIN PLUS KOLLAJEN TIP 2 KOMPLEKS FORMUL TABLET 60 tablet", "collagen"),
    ("APTAMIL PRONUTRA 1 0-6 AY BEBEK SUTU 350 g toz", None),
    ("", None),
])
def test_subcategory_by_source_name(name, slug):
    assert supplement_category_slug(name) == slug


@pytest.mark.parametrize("name, brand, slug", [
    # Очередь 26.10.2026: турецкое название — только бренд, вещество называет RU-название карточки.
    ("MAXBIOTIC Пробиотик, 14 жевательных таблеток", "MAXBIOTIC", "probiotics"),
    ("VITELEGANS MAGNIVIT Магниевая добавка, 30 таблеток", "VITELEGANS", "minerals"),
    ("Фолиевая кислота ANEVITA 90 таблеток", "", "vitamins"),
    ("SOLGAR Коэнзим Q10 100 мг, 30 капсул", "SOLGAR", "energy-vitality"),
    ("PROBAC Пробиотик для детей, 20 саше", "PROBAC", "kids-supplements"),
    # Как у турецких правил: сон, суставы и детское питание — в корне.
    ("HAVER Мелатонин 3 мг, 60 таблеток", "HAVER", None),
    ("FRISOLAC GOLD Сухая молочная смесь для детей, порошок, 400 г", "FRISOLAC", None),
    ("SUITENDO, пищевая добавка, 30 капсул", "SUITENDO", None),
    ("SUITENDO KAPSUL 30 kapsül", "SUITENDO", None),  # не RU — не запасной путь
])
def test_subcategory_by_russian_card_name(name, brand, slug):
    assert supplement_category_slug_ru(name, brand) == slug


def test_brand_prefix_is_not_a_substance():
    name = "İMUNEKS FARMA OSTEONEXT PLUS TAKVİYE EDİCİ GIDA ÇİĞNEME TABLETİ 60 tablet"
    assert supplement_category_slug(name) == "immunity"
    assert supplement_category_slug(name, "İmuneks Farma") is None


@pytest.fixture
def supplement_tree(db):
    kind, _ = CategoryType.objects.get_or_create(slug="supplements", defaults={"name": "Supplements"})
    root, _ = Category.objects.update_or_create(
        slug="supplements",
        defaults={"name": "БАДы", "category_type": kind, "parent": None, "is_active": True,
                  "margin_percent": Decimal("50")},
    )
    tree = {"root": root}
    for slug in SUBCATEGORY_SLUGS:
        tree[slug], _ = Category.objects.update_or_create(
            slug=slug, defaults={"name": slug, "category_type": kind, "parent": root, "is_active": True},
        )
    return tree


def _supplement(tree, slug, source_name, name="Переведённое название"):
    item = SupplementProduct.objects.create(
        name=name, slug=slug, category=tree["root"], external_data={"source_name": source_name},
    )
    return SupplementProduct.objects.get(pk=item.pk)


@pytest.mark.django_db
def test_dry_run_reports_without_writing_then_apply_moves_both_records(supplement_tree, tmp_path):
    vitamin = _supplement(supplement_tree, "b12", "NUTRAXIN B12 VITAMINI DILALTI TABLET 60 tablet")
    unknown = _supplement(supplement_tree, "melatonin", "SOLGAR MELATONIN TABLET 60 tablet")
    markup_before = get_effective_product_markup(vitamin.base_product)

    report = tmp_path / "dry.csv"
    out = StringIO()
    call_command("assign_supplement_subcategories", "--report", str(report), stdout=out)

    assert "DRY-RUN: в корне «БАДы» 2, в подкатегории 1, остаются в корне 1" in out.getvalue()
    assert "NUTRAXIN B12" in out.getvalue()
    assert Product.objects.filter(category=supplement_tree["root"]).count() == 2
    rows = {row["product_id"]: row for row in csv.DictReader(report.open(encoding="utf-8"))}
    assert rows[str(vitamin.base_product_id)]["new_category_slug"] == "vitamins"
    assert rows[str(vitamin.base_product_id)]["old_category_id"] == str(supplement_tree["root"].pk)
    assert rows[str(unknown.base_product_id)]["new_category_slug"] == ""

    call_command("assign_supplement_subcategories", "--apply", "--report", str(tmp_path / "a.csv"),
                 stdout=StringIO())

    vitamin.refresh_from_db()
    base = Product.objects.get(pk=vitamin.base_product_id)
    assert vitamin.category == supplement_tree["vitamins"]
    assert base.category == supplement_tree["vitamins"]
    assert base.slug == "b12"
    assert get_effective_product_markup(base) == markup_before == (Decimal("50"), "category")
    assert Product.objects.get(pk=unknown.base_product_id).category == supplement_tree["root"]
    assert SupplementProduct.objects.get(pk=unknown.pk).category == supplement_tree["root"]


@pytest.mark.django_db
def test_refuses_when_subcategory_markup_would_change_prices(supplement_tree, tmp_path):
    Category.objects.filter(pk=supplement_tree["collagen"].pk).update(margin_percent=Decimal("30"))
    _supplement(supplement_tree, "b12", "NUTRAXIN B12 VITAMINI DILALTI TABLET 60 tablet")

    with pytest.raises(CommandError, match="collagen"):
        call_command("assign_supplement_subcategories", "--apply", "--report", str(tmp_path / "r.csv"))

    assert Product.objects.filter(category=supplement_tree["root"]).count() == 1
