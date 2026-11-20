"""Глазные капли, назальные спреи и пластыри из БАДов → раздел лекарств (тип medicines).

20.11.2026: ilacfiyati держит CACICOL (глазные капли) в «Takviye edici gıda», на сайте они
стояли среди БАДов с оговоркой «Биологически активная добавка к пище». Владелец утвердил
список из 18 товаров; команда переносит только названные id.
"""

import json
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command

from apps.ai.services.supplement_content import DISCLAIMER
from apps.catalog.currency_models import GlobalCurrencySettings, MarkupScale, MarkupScaleStep
from apps.catalog.domain_sync import MOVED_FROM_SUPPLEMENTS_KEY
from apps.catalog.models import (
    Brand,
    Category,
    CategoryType,
    MedicineProduct,
    MedicineProductImage,
    MedicineProductTranslation,
    Product,
    ProductTranslation,
    SupplementProduct,
    SupplementProductImage,
    SupplementProductTranslation,
)
from apps.catalog.utils.product_markup import get_effective_product_markup

pytestmark = pytest.mark.django_db

COMMAND = "move_supplements_to_medicines"
PHOTO = "https://cdn.mudaroba.com/products/supplements/gallery/cacicol.jpg"
TEXT_RU = "<p>Глазные капли во флаконах по 0,33 мл.</p>"
TEXT_EN = "<p>Eye drops in 0.33 ml vials.</p>"


@pytest.fixture(autouse=True)
def quiet_signals(monkeypatch):
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)


@pytest.fixture
def catalog():
    supplements_type, _ = CategoryType.objects.get_or_create(slug="supplements", defaults={"name": "БАДы"})
    medicines_type, _ = CategoryType.objects.get_or_create(slug="medicines", defaults={"name": "Лекарства"})
    # Наценки как на проде 20.11.2026: корень «БАДы» 70 %, у лекарств шкала 150 % / 100 % от 10 000 лир.
    scale = MarkupScale.objects.create(name="Лекарства")
    for price_from, percent in ((0, 150), (10000, 100)):
        MarkupScaleStep.objects.create(scale=scale, price_from=price_from, percent=percent)
    settings = GlobalCurrencySettings.load()
    settings.default_margin_percentage = 25
    settings.save()
    supplements, _ = Category.objects.update_or_create(
        slug="supplements", defaults={"name": "БАДы", "category_type": supplements_type, "parent": None,
                                      "is_active": True, "margin_percent": 70},
    )
    eyes, _ = Category.objects.update_or_create(
        slug="eye-supplements", defaults={"name": "Для глаз", "parent": supplements, "is_active": True},
    )
    medicines, _ = Category.objects.update_or_create(
        slug="medicines", defaults={"name": "Лекарства", "category_type": medicines_type, "parent": None,
                                    "is_active": True, "markup_scale": scale},
    )
    return SimpleNamespace(supplements=supplements, eyes=eyes, medicines=medicines)


@pytest.fixture
def drops(catalog):
    """CACICOL в состоянии прода: БАД с фото, переводами и оговоркой БАДа в описании."""
    brand = Brand.objects.create(name="Thea Pharma", slug="thea-pharma", category_slugs=["supplements"],
                                 primary_category_slug="supplements")
    description = TEXT_RU + f"<p>{DISCLAIMER['ru']}</p>"
    description_en = TEXT_EN + f"<p>{DISCLAIMER['en']}</p>"
    product = Product.objects.create(
        name="CACICOL Капли для глаз, 5 флаконов", slug="cacicol-goz-damlasi", product_type="supplements",
        category=catalog.eyes, brand=brand, price=200, currency="TRY", is_featured=True,
        description=description, external_id="cacicol-goz-damlasi",
        external_url="https://ilacfiyati.com/takviye-edici-gida/cacicol-goz-damlasi",
        external_data={"source": "ilacfiyati", "source_name": "CACICOL GOZ DAMLASI"},
        main_image=PHOTO,
    )
    Product.objects.filter(pk=product.pk).update(
        seo_title="CACICOL капли для глаз из Турции",
        keywords=["CACICOL", "капли для глаз", "БАД капли для глаз"],
        meta_keywords="CACICOL, капли для глаз, БАД капли для глаз",
        stock_quantity=0,  # наследие импорта БАДов: «в наличии» при остатке 0
    )
    supplement = SupplementProduct.objects.get(base_product=product)
    SupplementProduct.objects.filter(pk=supplement.pk).update(
        stock_quantity=0, meta_title="CACICOL eye drops", dosage_form="drops", active_ingredient="Poly-carboxymethylglucose sulfate",
    )
    SupplementProductImage.objects.create(product=supplement, image_url=PHOTO, sort_order=0, is_main=True)
    SupplementProductTranslation.objects.create(
        product=supplement, locale="ru", name="CACICOL Капли для глаз", description=description,
        dosage_form="Глазные капли во флаконах-капельницах",
    )
    SupplementProductTranslation.objects.create(
        product=supplement, locale="en", name="CACICOL Eye Drops", description=description_en,
        meta_keywords="CACICOL, eye drops, food supplement eye drops",
    )
    ProductTranslation.objects.create(
        product=product, locale="en", name="CACICOL Eye Drops", description=description_en,
        meta_keywords="CACICOL, eye drops, food supplement eye drops",
    )
    vitamin = Product.objects.create(
        name="SOLGAR VITAMIN C 1000 MG 100 TABLET", slug="solgar-vitamin-c", product_type="supplements",
        category=catalog.supplements, price=950, currency="TRY",
    )
    return SimpleNamespace(product=product, supplement=supplement, brand=brand, vitamin=vitamin)


def apply(product, backup, *extra):
    call_command(COMMAND, "--product", str(product.pk), "--apply", "--allow-markup-change",
                 "--backup", str(backup), *extra)


def test_product_ids_are_required(drops):
    with pytest.raises(CommandError, match="автоотбора нет"):
        call_command(COMMAND)


def test_dry_run_shows_price_change_and_changes_nothing(drops, capsys):
    call_command(COMMAND, "--product", str(drops.product.pk))

    out = capsys.readouterr().out
    assert f"{drops.product.pk} | CACICOL Капли для глаз, 5 флаконов | eye-supplements → medicines" in out
    assert "| 340.00 → 500.00 (" in out
    assert "Наценка меняется:" in out
    assert "Dry-run: ничего не изменено" in out
    drops.product.refresh_from_db()
    assert drops.product.product_type == "supplements"
    assert not MedicineProduct.objects.exists()


def test_apply_requires_backup(drops):
    with pytest.raises(CommandError, match="--backup"):
        call_command(COMMAND, "--product", str(drops.product.pk), "--apply", "--allow-markup-change")


def test_apply_refuses_when_site_price_changes(drops, tmp_path):
    backup = tmp_path / "meds.json"
    with pytest.raises(CommandError, match="Цена на сайте изменится"):
        call_command(COMMAND, "--product", str(drops.product.pk), "--apply", "--backup", str(backup))

    drops.product.refresh_from_db()
    assert drops.product.product_type == "supplements"
    assert not MedicineProduct.objects.exists()
    assert not backup.exists()


def test_not_a_supplement_stops_command(drops, catalog, tmp_path):
    other = Product.objects.create(
        name="Parol 500 mg", slug="parol-500", product_type="medicines", category=catalog.medicines,
        price=50, currency="TRY",
    )

    with pytest.raises(CommandError, match="Не БАДы"):
        apply(drops.product, tmp_path / "meds.json", "--product", str(other.pk))

    drops.product.refresh_from_db()
    assert drops.product.product_type == "supplements"


def test_apply_moves_supplement_to_medicines(drops, catalog, tmp_path):
    backup = tmp_path / "meds.json"
    apply(drops.product, backup)

    product = Product.objects.select_related("category", "brand").get(pk=drops.product.pk)
    assert product.product_type == "medicines"
    assert product.category == catalog.medicines
    assert product.slug == "cacicol-goz-damlasi", "адрес карточки не меняется"
    assert product.seo_title == "CACICOL капли для глаз из Турции", "RU SEO не затирается"
    assert product.is_active is True
    assert product.is_featured is False
    assert product.is_available is True and product.stock_quantity is None, "остаток 0 не даст добавить в заявку"
    assert product.description == TEXT_RU
    assert product.keywords == ["CACICOL", "капли для глаз"]
    assert product.meta_keywords == "CACICOL, капли для глаз"
    assert product.external_data[MOVED_FROM_SUPPLEMENTS_KEY]
    assert product.external_data["source_name"] == "CACICOL GOZ DAMLASI"
    assert get_effective_product_markup(product)[0] == 150
    translation = ProductTranslation.objects.get(product=product, locale="en")
    assert translation.description == TEXT_EN
    assert translation.meta_keywords == "CACICOL, eye drops"

    medicine = MedicineProduct.objects.get(base_product=product)
    assert medicine.is_active and medicine.is_featured is False
    assert (medicine.slug, medicine.category) == (product.slug, catalog.medicines)
    assert (medicine.price, medicine.currency, medicine.meta_title) == (200, "TRY", "CACICOL eye drops")
    assert medicine.stock_quantity is None
    assert medicine.description == TEXT_RU
    assert (medicine.dosage_form, medicine.active_ingredient) == ("drops", "Poly-carboxymethylglucose sulfate")
    # Лекарственных данных у источника нет — поля пустые, товар не больничный и без ограничений ввоза.
    assert (medicine.atc_code, medicine.barcode, medicine.prescription_type) == ("", "", "")
    assert (medicine.is_hospital, medicine.prescription_required, medicine.import_restricted_countries) == (
        False, False, "",
    )
    assert medicine.external_data[MOVED_FROM_SUPPLEMENTS_KEY]
    assert list(MedicineProductImage.objects.filter(product=medicine).values_list("image_url", "is_main")) == [
        (PHOTO, True),
    ]
    translations = {row.locale: row for row in MedicineProductTranslation.objects.filter(product=medicine)}
    assert {locale: row.description for locale, row in translations.items()} == {"ru": TEXT_RU, "en": TEXT_EN}
    assert translations["en"].meta_keywords == "CACICOL, eye drops"
    assert translations["ru"].dosage_form == "", "свободный текст формы БАДа в поле-справочник не переносится"

    supplement = SupplementProduct.objects.get(pk=drops.supplement.pk)
    assert supplement.is_active is False, "запись БАДа снята, но не удалена"
    assert supplement.is_featured is False
    assert SupplementProductImage.objects.filter(product=supplement).count() == 1
    drops.brand.refresh_from_db()
    assert drops.brand.category_slugs == ["supplements", "medicines"]

    saved = json.loads(backup.read_text(encoding="utf-8"))["products"]
    assert len(saved) == 1
    assert saved[0]["product"]["product_type"] == "supplements"
    assert saved[0]["product"]["category_id"] == catalog.eyes.pk
    assert saved[0]["product"]["is_featured"] is True
    assert saved[0]["product"]["stock_quantity"] == 0
    assert DISCLAIMER["ru"] in saved[0]["product"]["description"]
    assert "БАД капли для глаз" in saved[0]["product"]["keywords"]
    assert "CACICOL, eye drops, food supplement eye drops" in [
        row["meta_keywords"] for row in saved[0]["product_translations"]
    ]
    assert saved[0]["supplement"] == {"pk": drops.supplement.pk, "is_active": True, "is_featured": True}
    assert saved[0]["brand"]["category_slugs"] == ["supplements"]

    assert Product.objects.get(pk=drops.vitamin.pk).product_type == "supplements"


def test_second_apply_skips_moved_product(drops, tmp_path, capsys):
    apply(drops.product, tmp_path / "1.json")
    capsys.readouterr()
    apply(drops.product, tmp_path / "2.json")

    out = capsys.readouterr().out
    assert "уже перенесён, пропускаю" in out
    assert "Перенесено товаров: 0" in out
    assert json.loads((tmp_path / "2.json").read_text(encoding="utf-8")) == {"products": []}
    assert MedicineProduct.objects.filter(base_product=drops.product).count() == 1
    assert SupplementProduct.objects.filter(base_product=drops.product).count() == 1
    assert MedicineProductImage.objects.count() == 1
    assert Product.objects.get(pk=drops.product.pk).product_type == "medicines"


def test_saving_product_or_retired_supplement_keeps_medicine(drops, catalog, tmp_path):
    apply(drops.product, tmp_path / "meds.json")

    Product.objects.get(pk=drops.product.pk).save()
    SupplementProduct.objects.get(pk=drops.supplement.pk).save()

    product = Product.objects.get(pk=drops.product.pk)
    assert (product.product_type, product.category, product.is_active) == ("medicines", catalog.medicines, True)
    assert SupplementProduct.objects.get(pk=drops.supplement.pk).is_active is False
    assert MedicineProduct.objects.get(base_product=product).is_active is True
