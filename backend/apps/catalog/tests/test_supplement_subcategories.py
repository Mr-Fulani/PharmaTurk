import csv
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Category, CategoryType, Product, SupplementProduct
from apps.catalog.supplement_taxonomy import (
    RETIRED_SUBCATEGORY_SLUGS,
    SUBCATEGORY_SLUGS,
    SUBSTANCE_RULES,
    supplement_category_slug,
    supplement_category_slug_ru,
    supplement_substance_slug,
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


@pytest.mark.parametrize("section, name, name_ru, brand, slug", [
    ("minerals", "LIGONE MAGNEZYUM SITRAT TABLET 60 tablet", "", "", "magnesium"),
    ("minerals", "NSUP KALSIYUM VE VITAMIN D ICEREN TAKVIYE EDICI GIDA 1400 mg 30 tablet", "", "", "calcium"),
    # Комплекс из нескольких минералов остаётся в разделе.
    ("minerals", "OPREVA CARE KALSIYUM, MAGNEZYUM VE VITAMIN D ICEREN TAKVIYE EDICI GIDA 30 kapsül", "", "", None),
    # «DEMİRHİNDİ» — тамаринд, не железо.
    ("minerals", "LAKSO MINI INCIR, DISBUDAK, DEMIRHINDI ICEREN SIVI TAKVIYE EDICI GIDA 150 ml", "", "", None),
    ("minerals", "MATRIKS DEMIR ICEREN TAKVIYE EDICI DAMLA 30 ml şişe", "", "", "iron"),
    ("vitamins", "NEW LIFE B12 PLUS METHYLCOBALAMIN FOLIC ACID BIOTIN TABLET 30 tablet", "", "", "vitamin-b"),
    ("vitamins", "INOVIT VITAMIN D3 İÇEREN SPREY TAKVİYE EDİCİ GIDA 400 IU 20 ml şişe", "", "", "vitamin-d"),
    ("vitamins", "NUTRAXIN E VITAMIN D-ALPHA TOCOPHEROL YUMUSAK KAPSUL 200 IU 60 kapsül", "", "", "vitamin-e"),
    ("vitamins", "NATURMAX VITAMIN C, VITAMIN D3 VE ÇİNKO İÇEREN TAKVİYE EDİCİ GIDA 20 tablet", "", "", None),
    # Три витамина и больше — мультивитамины.
    ("vitamins", "SUNLIFE C EXTRA VITAMIN C, ÇINKO, VITAMIN E VE VITAMIN D3 ICEREN 20 tablet", "", "", "multivitamins"),
    ("vitamins", "SUDUVIT MULTIVITAMIN SURUP 100 ml şişe", "", "", "multivitamins"),
    # «VITAMIN VE MINERAL» карточка перевела как «Витамины E и минералы» — RU-название не используется.
    ("vitamins", "REDOXON PRO EFERVESAN TABLET VITAMIN VE MINERAL ICEREN 15 tablet",
     "REDOXON PRO Витамины E и минералы, 15 шипучих таблеток", "REDOXON PRO", None),
    # Турецкое название — только бренд: вещество по RU-названию карточки.
    ("vitamins", "FOLICA TABLET 30 tablet", "FOLICA Фолиевая кислота, 30 таблеток", "FOLICA", "vitamin-b"),
    ("omega-fatty-acids", "MRB OMEGA 3 FORTE TUTTI FRUTTI AROMALI BALIK YAGI SURUBU 100 ml şişe", "", "", "fish-oil"),
    ("omega-fatty-acids", "NEPTUNE KRILL OIL OMEGA-3 KAPSUL 180 kapsül", "", "", "omega-3"),
    # Бренд «IMUNEKS» — не состав.
    ("immunity", "IMUNEKS VITAMIN D3 ORAL SPREY TAKVIYE EDICI GIDA 20 ml şişe", "", "", None),
    ("immunity", "TALYA EKINEZYA, VITAMIN C VE ÇINKO ICEREN PASTIL 12 pastil", "", "", "vitamin-c-complexes"),
    ("digestive-health", "NUTRIGEN INULIN SASE 10 saşe", "", "", "prebiotics"),
    ("digestive-health", "SWISS BORK PROBIOTIC BOOST 7 STRAINS+INULIN ICEREN 30 kapsül", "", "", None),
    ("energy-vitality", "DOPPELHERZ KOENZIM Q10 KAPSUL 30 kapsül", "", "", "coq10"),
    ("herbal-supplements", "ZADE VITAL COREK OTU YAGI KAPSUL 60 kapsül", "", "", None),
    ("kids-supplements", "ZADE VITAL OMEGA 3 KIDS PORTAKAL SURUP 100 ml şişe", "", "", "omega-kids"),
    ("collagen", "COLLAQUIN HIDROLIZE KOLLAJEN 30 saşe", "", "", None),
])
def test_substance_subcategory(section, name, name_ru, brand, slug):
    assert supplement_substance_slug(section, name, name_ru, brand) == slug


def test_retired_subcategories_are_not_substances():
    substances = {slug for rules in SUBSTANCE_RULES.values() for slug, _ in rules if slug}
    assert len(substances) == 23
    assert not substances & set(RETIRED_SUBCATEGORY_SLUGS)
    assert len(RETIRED_SUBCATEGORY_SLUGS) == 19


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
    for section, rules in SUBSTANCE_RULES.items():
        for slug, _ in rules:
            if slug:
                tree[slug], _ = Category.objects.update_or_create(
                    slug=slug,
                    defaults={"name": slug, "category_type": kind, "parent": tree[section], "is_active": True},
                )
    return tree


def _supplement(tree, slug, source_name, name="Переведённое название", category="root"):
    item = SupplementProduct.objects.create(
        name=name, slug=slug, category=tree[category], external_data={"source_name": source_name},
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

    assert "DRY-RUN: в корне «БАДы» 2, в разделах 0; переносится 1, остаются в корне 1" in out.getvalue()
    assert "NUTRAXIN B12" in out.getvalue()
    assert Product.objects.filter(category=supplement_tree["root"]).count() == 2
    rows = {row["product_id"]: row for row in csv.DictReader(report.open(encoding="utf-8"))}
    assert rows[str(vitamin.base_product_id)]["new_category_slug"] == "vitamin-b"
    assert rows[str(vitamin.base_product_id)]["old_category_id"] == str(supplement_tree["root"].pk)
    assert rows[str(unknown.base_product_id)]["new_category_slug"] == ""

    call_command("assign_supplement_subcategories", "--apply", "--report", str(tmp_path / "a.csv"),
                 stdout=StringIO())

    vitamin.refresh_from_db()
    base = Product.objects.get(pk=vitamin.base_product_id)
    assert vitamin.category == supplement_tree["vitamin-b"]
    assert base.category == supplement_tree["vitamin-b"]
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


@pytest.mark.django_db
def test_section_products_move_to_substance_and_retired_empty_subcategories_are_disabled(
    supplement_tree, tmp_path,
):
    magnesium = _supplement(supplement_tree, "mg", "LIGONE MAGNEZYUM SITRAT TABLET 60 tablet", category="minerals")
    complex_ = _supplement(
        supplement_tree, "ca-mg", "DOPPELHERZ MAGNEZYUM KALSIYUM TABLET 30 tablet", category="minerals",
    )
    kind = supplement_tree["root"].category_type
    potassium, _ = Category.objects.update_or_create(
        slug="potassium", defaults={"name": "Калий", "category_type": kind,
                                    "parent": supplement_tree["minerals"], "is_active": True},
    )
    creatine, _ = Category.objects.update_or_create(
        slug="creatine", defaults={"name": "Креатин", "category_type": kind,
                                   "parent": supplement_tree["sports-nutrition"], "is_active": True},
    )
    _supplement(supplement_tree, "kreatin", "VENATURA KREATIN MONOHIDRAT 150 gr kutu", category="sports-nutrition")
    SupplementProduct.objects.filter(slug="kreatin").update(category=creatine)
    Product.objects.filter(slug="kreatin").update(category=creatine)

    out = StringIO()
    call_command("assign_supplement_subcategories", "--report", str(tmp_path / "dry.csv"), stdout=out)
    assert "в разделах 2; переносится 1" in out.getvalue()
    assert "выключаются пустые подкатегории: potassium" in out.getvalue()
    assert "не выключены — в них есть товары или дочерние категории: creatine" in out.getvalue()
    assert Category.objects.get(pk=potassium.pk).is_active

    call_command("assign_supplement_subcategories", "--apply", "--report", str(tmp_path / "a.csv"),
                 stdout=StringIO())

    assert SupplementProduct.objects.get(pk=magnesium.pk).category == supplement_tree["magnesium"]
    assert Product.objects.get(pk=magnesium.base_product_id).category == supplement_tree["magnesium"]
    assert Product.objects.get(pk=complex_.base_product_id).category == supplement_tree["minerals"]
    assert not Category.objects.get(pk=potassium.pk).is_active
    assert Category.objects.get(pk=creatine.pk).is_active

    out = StringIO()
    call_command("assign_supplement_subcategories", "--report", str(tmp_path / "again.csv"), stdout=out)
    assert "переносится 0" in out.getvalue()
