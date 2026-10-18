import csv
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Brand, MedicineProduct, Product, SupplementProduct
from apps.catalog.utils.manufacturer_brands import (
    manufacturer_brand_key,
    manufacturer_display_name,
)


@pytest.mark.parametrize(
    "variants",
    [
        ["Abdi İbrahim", "Abdi İbrahim İlaç Sanayi Ve Ticaret A.Ş", "ABDI IBRAHIM"],
        ["World Medicine", "World Medıcıne İlaç San. Ve Tic. A.Ş.", "World Medıcıne İlaçları Ltd. Şti."],
        ["Farma-Tek", "Farmatek", "Farma-Tek İlaç Sanayi Ve Ticaret A.Ş"],
        ["Türktıpsan", "Turktıpsan Sağlık Turizm Eğitim Ve Ticaret A.Ş."],
        ["TEB", "Teb Yurt Dışından İlaç Temini Birimi"],
        ["Pfizer", "Pfizer Pfe", "Pfizer Pfe İlaçları Anonim Şirketi"],
    ],
)
def test_manufacturer_spellings_share_one_key(variants):
    assert len({manufacturer_brand_key(v) for v in variants}) == 1


def test_different_firms_keep_different_keys():
    assert manufacturer_brand_key("Neutec") != manufacturer_brand_key("Neutec İnhaler")
    assert manufacturer_brand_key("Santa Farma") != manufacturer_brand_key("Santa")


def test_display_name_drops_only_legal_form():
    assert manufacturer_display_name("Nobel İlaç Sanayii Ve Ticaret A.Ş.") == "Nobel İlaç"
    assert manufacturer_display_name("Koçak Farma İlaç Ve Kimya Sanayi A.Ş.") == "Koçak Farma İlaç"
    assert manufacturer_display_name("Sanofi") == "Sanofi"


@pytest.fixture
def other_brand():
    return Brand.objects.get_or_create(slug="other", defaults={"name": "Другое"})[0]


def _medicine(slug, manufacturer, brand=None):
    product = MedicineProduct.objects.create(name=slug, slug=slug, manufacturer=manufacturer, brand=brand)
    return MedicineProduct.objects.get(pk=product.pk)


@pytest.mark.django_db
def test_assign_brands_dry_run_then_apply(other_brand, tmp_path):
    deva = Brand.objects.create(name="Deva Holding", slug="deva-holding", category_slugs=["medicines"])
    manual = Brand.objects.create(name="Manual", slug="manual")
    m1 = _medicine("abdi-1", "Abdi İbrahim")
    m2 = _medicine("abdi-2", "Abdi İbrahim İlaç Sanayi Ve Ticaret A.Ş")
    m3 = _medicine("deva-1", "Deva Holding Anonim Şirketi")
    kept = _medicine("kept-1", "Abdi İbrahim", brand=manual)
    supplement = SupplementProduct.objects.create(
        name="sup", slug="sup-1", external_data={"attributes": {"manufacturer": "Abdi İbrahim"}},
    )
    assert m1.brand_id == other_brand.pk  # сигнал ставит заглушку «Другое»

    report = tmp_path / "dry.csv"
    out = StringIO()
    call_command("assign_manufacturer_brands", "--report", str(report), stdout=out)

    assert "DRY-RUN" in out.getvalue()
    assert "новых=1" in out.getvalue()
    assert not Brand.objects.filter(name="Abdi İbrahim").exists()
    rows = {row["key"]: row for row in csv.DictReader(report.open(encoding="utf-8"))}
    assert rows["abdiibrahim"]["to_assign"] == "3"
    assert rows["abdiibrahim"]["kept_other_brand"] == "1"
    assert rows["deva"]["existing_brand_id"] == str(deva.pk)

    call_command("assign_manufacturer_brands", "--apply", "--report", str(tmp_path / "a.csv"), stdout=StringIO())

    abdi = Brand.objects.get(name="Abdi İbrahim")
    assert set(abdi.category_slugs) == {"medicines", "supplements"}
    for item in (m1, m2):
        item.refresh_from_db()
        assert item.brand_id == abdi.pk
        assert Product.objects.get(pk=item.base_product_id).brand_id == abdi.pk
    m3.refresh_from_db()
    assert m3.brand_id == deva.pk
    supplement.refresh_from_db()
    assert supplement.brand_id == abdi.pk
    kept.refresh_from_db()
    assert kept.brand_id == manual.pk

    brands_before = Brand.objects.count()
    out = StringIO()
    call_command("assign_manufacturer_brands", "--apply", "--report", str(tmp_path / "b.csv"), stdout=out)
    assert Brand.objects.count() == brands_before
    assert "проставить=0" in out.getvalue()


@pytest.mark.django_db
def test_assign_brands_refuses_empty_catalog(tmp_path):
    with pytest.raises(CommandError):
        call_command("assign_manufacturer_brands", "--report", str(tmp_path / "r.csv"))


@pytest.mark.django_db
def test_scraper_sets_manufacturer_brand_only_over_placeholder(other_brand):
    from apps.scrapers.services import ScraperIntegrationService

    service = ScraperIntegrationService()
    medicine = _medicine("scraped-1", "")
    product = Product.objects.get(pk=medicine.base_product_id)

    assert service._assign_manufacturer_brand(product, {"manufacturer": "Sanovel İlaç Sanayi Ve Ticaret A.Ş."})
    brand = Brand.objects.get(name="Sanovel İlaç")
    assert product.brand_id == brand.pk
    medicine.refresh_from_db()
    assert medicine.brand_id == brand.pk

    assert not service._assign_manufacturer_brand(product, {"manufacturer": "Other Firm"})
    assert not Brand.objects.filter(name="Other Firm").exists()
