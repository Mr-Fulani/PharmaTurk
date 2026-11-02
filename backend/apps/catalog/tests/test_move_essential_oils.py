"""Эфирные масла PHYTOIL из БАДов → раздел «Эфирные масла» (тип incense).

02.11.2026: ilacfiyati держит линейку PHYTOIL (Elentra İlaç) среди БАДов, карточки
масел писали «Биологически активная добавка к пище», AI-тексты стояли на модерации
(PHYTOIL EUCALYPTUS 50/10 мл — товары 23956 и 23923).
"""

import json
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.ai.services.supplement_content import DISCLAIMER
from apps.catalog.essential_oils import essential_oil_category_slug
from apps.catalog.models import (
    Brand,
    Category,
    CategoryType,
    IncenseProduct,
    IncenseProductImage,
    IncenseProductTranslation,
    Product,
    ProductTranslation,
    SupplementProduct,
    SupplementProductImage,
    SupplementProductTranslation,
)

pytestmark = pytest.mark.django_db

PHOTO = "https://cdn.mudaroba.com/products/supplements/gallery/phytoil-eucalyptus.jpg"
TEXT_RU = "<p>Эвкалиптовое эфирное масло во флаконе 10 мл.</p>"


@pytest.mark.parametrize("name,expected", [
    ("PHYTOIL EUCALYPTUS 10 ML", "eucalyptus-oil"),
    ("PHYTOIL OKALİPTÜS UÇUCU YAĞI 50 ML", "eucalyptus-oil"),
    ("PHYTOIL ÇAY AĞACI YAĞI 10 ML", "tea-tree-oil"),
    ("PHYTOIL GÜL SUYU 250 ML", "essential-oils"),
    ("PHYTOIL NANE HİDROLATI 200 ML", "essential-oils"),
    ("PHYTOIL BERGAMOT 10 ML", "single-essential-oils"),
    ("PHYTOIL LAVANTA VE NANE 10 ML", "single-essential-oils"),
    ("LAVANTA UÇUCU YAĞI 20 ML", "lavender-oil"),
    # Принимают внутрь — БАДы.
    ("ÇÖREK OTU YAĞI 100 ML", None),
    ("BALIK YAĞI OMEGA 3 60 KAPSÜL", None),
    ("PHYTOIL NANE YAĞI 30 KAPSÜL", None),
    ("SOLGAR VITAMIN C 1000 MG 100 TABLET", None),
])
def test_essential_oil_rule(name, expected):
    assert essential_oil_category_slug(name) == expected


def test_essential_oil_rule_reads_russian_name_without_source():
    assert essential_oil_category_slug("", "Эфирное масло бергамота PHYTOIL, 10 мл") == "single-essential-oils"
    assert essential_oil_category_slug("", "Масло чёрного тмина, 100 мл") is None


@pytest.fixture(autouse=True)
def quiet_signals(monkeypatch):
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    # Доставка в ответе resolve пересчитывается по курсам — без запросов в сеть.
    monkeypatch.setattr("apps.catalog.services.product_resolve.build_shipping_rates", lambda product_type: None)


@pytest.fixture
def catalog():
    supplements_type, _ = CategoryType.objects.get_or_create(slug="supplements", defaults={"name": "БАДы"})
    incense_type, _ = CategoryType.objects.get_or_create(slug="incense", defaults={"name": "Благовония"})
    supplements, _ = Category.objects.update_or_create(
        slug="supplements", defaults={"name": "БАДы", "category_type": supplements_type, "parent": None, "is_active": True},
    )
    herbal, _ = Category.objects.update_or_create(
        slug="herbal-supplements", defaults={"name": "Растительные", "parent": supplements, "is_active": True},
    )
    incense, _ = Category.objects.update_or_create(
        slug="incense", defaults={"name": "Благовония", "category_type": incense_type, "parent": None, "is_active": True},
    )
    oils, _ = Category.objects.update_or_create(
        slug="essential-oils", defaults={"name": "Эфирные масла", "parent": incense, "is_active": True},
    )
    single, _ = Category.objects.update_or_create(
        slug="single-essential-oils", defaults={"name": "Одиночные масла", "parent": oils, "is_active": True},
    )
    eucalyptus, _ = Category.objects.update_or_create(
        slug="eucalyptus-oil", defaults={"name": "Эвкалиптовое", "parent": single, "is_active": True},
    )
    return SimpleNamespace(supplements=supplements, herbal=herbal, oils=oils, single=single, eucalyptus=eucalyptus)


@pytest.fixture
def oil(catalog):
    """PHYTOIL EUCALYPTUS в состоянии прода: БАД с фото, переводами и оговоркой БАДа в описании."""
    brand = Brand.objects.create(name="Elentra İlaç", slug="elentra-ilac", category_slugs=["supplements"],
                                 primary_category_slug="supplements")
    description = TEXT_RU + f"<p>{DISCLAIMER['ru']}</p>"
    product = Product.objects.create(
        name="PHYTOIL EUCALYPTUS 10 ML", slug="phytoil-eucalyptus-10-ml", product_type="supplements",
        category=catalog.herbal, brand=brand, price=180, currency="TRY", is_featured=True,
        description=description, external_id="phytoil-eucalyptus-10-ml",
        external_url="https://ilacfiyati.com/takviye-edici-gida/phytoil-eucalyptus-10-ml",
        external_data={"source": "ilacfiyati", "source_name": "PHYTOIL EUCALYPTUS 10 ML"},
        main_image=PHOTO,
    )
    Product.objects.filter(pk=product.pk).update(seo_title="PHYTOIL EUCALYPTUS 10 мл — купить из Турции")
    supplement = SupplementProduct.objects.get(base_product=product)
    SupplementProduct.objects.filter(pk=supplement.pk).update(meta_title="PHYTOIL EUCALYPTUS 10 ml", active_ingredient="Eucalyptus")
    SupplementProductImage.objects.create(product=supplement, image_url=PHOTO, sort_order=0, is_main=True)
    SupplementProductTranslation.objects.create(product=supplement, locale="ru", name="PHYTOIL EUCALYPTUS", description=description)
    SupplementProductTranslation.objects.create(
        product=supplement, locale="en", name="PHYTOIL EUCALYPTUS",
        description=f"<p>Eucalyptus essential oil.</p><p>{DISCLAIMER['en']}</p>",
    )
    ProductTranslation.objects.create(product=product, locale="en", name="PHYTOIL EUCALYPTUS",
                                      description=f"<p>Eucalyptus essential oil.</p><p>{DISCLAIMER['en']}</p>")
    vitamin = Product.objects.create(
        name="SOLGAR VITAMIN C 1000 MG 100 TABLET", slug="solgar-vitamin-c", product_type="supplements",
        category=catalog.supplements, price=950, currency="TRY",
    )
    return SimpleNamespace(product=product, supplement=supplement, brand=brand, vitamin=vitamin)


def test_dry_run_lists_oil_and_changes_nothing(oil, capsys):
    call_command("move_essential_oils_from_supplements")

    out = capsys.readouterr().out
    assert f"{oil.product.pk} | PHYTOIL EUCALYPTUS 10 ML | herbal-supplements → eucalyptus-oil" in out
    assert "SOLGAR" not in out
    oil.product.refresh_from_db()
    assert oil.product.product_type == "supplements"
    assert not IncenseProduct.objects.exists()


def test_apply_requires_backup(oil):
    with pytest.raises(CommandError):
        call_command("move_essential_oils_from_supplements", "--apply")


def test_apply_moves_oil_to_essential_oils(oil, catalog, tmp_path):
    backup = tmp_path / "oils.json"
    call_command("move_essential_oils_from_supplements", "--apply", "--backup", str(backup))

    product = Product.objects.get(pk=oil.product.pk)
    assert product.product_type == "incense"
    assert product.category == catalog.eucalyptus
    assert product.slug == "phytoil-eucalyptus-10-ml"
    assert product.seo_title == "PHYTOIL EUCALYPTUS 10 мл — купить из Турции", "RU SEO не затирается"
    assert product.is_featured is False
    assert product.description == TEXT_RU
    assert ProductTranslation.objects.get(product=product, locale="en").description == "<p>Eucalyptus essential oil.</p>"

    incense = IncenseProduct.objects.get(base_product=product)
    assert incense.is_active and incense.category == catalog.eucalyptus
    assert (incense.price, incense.currency, incense.meta_title) == (180, "TRY", "PHYTOIL EUCALYPTUS 10 ml")
    assert incense.description == TEXT_RU
    assert list(IncenseProductImage.objects.filter(product=incense).values_list("image_url", "is_main")) == [(PHOTO, True)]
    assert dict(IncenseProductTranslation.objects.filter(product=incense).values_list("locale", "description")) == {
        "ru": TEXT_RU, "en": "<p>Eucalyptus essential oil.</p>",
    }

    supplement = SupplementProduct.objects.get(pk=oil.supplement.pk)
    assert supplement.is_active is False, "запись БАДа снята, но не удалена"
    oil.brand.refresh_from_db()
    assert oil.brand.category_slugs == ["supplements", "incense"]

    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert saved[0]["product"]["product_type"] == "supplements"
    assert saved[0]["product"]["category_id"] == catalog.herbal.pk
    assert DISCLAIMER["ru"] in saved[0]["product"]["description"]
    assert saved[0]["supplement"] == {"pk": oil.supplement.pk, "is_active": True, "is_featured": True}

    body = APIClient().get(f"/api/catalog/products/resolve/{product.slug}").json()
    assert body["product_type"] == "incense"
    assert body["canonical_path"] == f"/product/{product.slug}", "адрес карточки не меняется"
    assert Product.objects.get(pk=oil.vitamin.pk).product_type == "supplements"


def test_second_apply_finds_nothing(oil, tmp_path, capsys):
    call_command("move_essential_oils_from_supplements", "--apply", "--backup", str(tmp_path / "1.json"))
    call_command("move_essential_oils_from_supplements", "--apply", "--backup", str(tmp_path / "2.json"))

    assert "Перенесено товаров: 0" in capsys.readouterr().out
    assert IncenseProduct.objects.filter(base_product=oil.product).count() == 1


def test_saving_retired_supplement_keeps_oil_type(oil, catalog, tmp_path):
    call_command("move_essential_oils_from_supplements", "--apply", "--backup", str(tmp_path / "oils.json"))

    SupplementProduct.objects.get(pk=oil.supplement.pk).save()

    product = Product.objects.get(pk=oil.product.pk)
    assert (product.product_type, product.category, product.is_active) == ("incense", catalog.eucalyptus, True)


def test_missing_essential_oils_category_stops_command(oil, catalog):
    Category.objects.filter(slug__in=["essential-oils", "single-essential-oils", "eucalyptus-oil"]).update(is_active=False)

    with pytest.raises(CommandError):
        call_command("move_essential_oils_from_supplements")
