import csv
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalog.models import Brand, MedicineProduct, Product, SupplementProduct
from apps.catalog.utils.manufacturer_brands import (
    manufacturer_brand_key,
    manufacturer_display_name,
    manufacturer_key_tokens,
    root_tokens,
)


def _roots(variants):
    tokens = [manufacturer_key_tokens(v) for v in variants]
    return {root_tokens(t, set(tokens)) for t in tokens}


@pytest.mark.parametrize(
    "variants",
    [
        ["Abdi İbrahim", "Abdi İbrahim İlaç Sanayi Ve Ticaret A.Ş", "ABDI IBRAHIM"],
        ["World Medicine", "World Medıcıne İlaç San. Ve Tic. A.Ş.", "World Medıcıne İlaçları Ltd. Şti."],
        ["Farma-Tek", "Farmatek", "Farma-Tek İlaç Sanayi Ve Ticaret A.Ş"],
        ["Türktıpsan", "Turktıpsan Sağlık Turizm Eğitim Ve Ticaret A.Ş."],
        ["TEB", "Teb Yurt Dışından İlaç Temini Birimi"],
        ["Pfizer", "Pfizer Pfe", "Pfizer Pfe İlaçları Anonim Şirketi"],
        ["Abbott", "Abbott Laboratuarları İthalat İhracat Ve Ticaret Limited Şirketi"],
        ["Sanofi", "Sanofi Pasteur", "Sanofi Pasteur Aşı Tic. A.Ş."],
        ["Galen", "Galen İlaç San.Ve Tic.A.Ş"],
    ],
)
def test_manufacturer_spellings_share_one_root(variants):
    assert len(_roots(variants)) == 1


@pytest.mark.parametrize(
    "variants",
    [
        ["Merck İlaç", "Merck Sharp Dohme"],
        ["Fresenius Medikal", "Fresenius Kabi"],
        ["Bio-Gen", "Biogen Turkey"],
    ],
)
def test_different_firms_keep_different_roots(variants):
    assert len(_roots(variants)) == len(variants)


def test_key_and_display_handle_dotted_legal_form():
    assert manufacturer_brand_key("Galen İlaç San.Ve Tic.A.Ş") == manufacturer_brand_key("Galen")
    assert manufacturer_display_name("Mentis İlaç San.Tic.Ltd.Şti") == "Mentis İlaç"
    assert manufacturer_brand_key("B.Braun Medikal Dış Ticaret A.Ş.") == "bbraun"


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
    assert rows["abdi ibrahim"]["to_assign"] == "3"
    assert rows["abdi ibrahim"]["kept_other_brand"] == "1"
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
def test_assign_brands_merges_pharma_duplicates_but_not_other_categories(other_brand, tmp_path):
    abbott = Brand.objects.create(name="Abbott", slug="abbott", category_slugs=["medicines"])
    duplicate = Brand.objects.create(
        name="Abbott Laboratuarları", slug="abbott-laboratuarlari", category_slugs=["medicines"],
    )
    curated = Brand.objects.create(
        name="Abbott Diagnostics", slug="abbott-diagnostics", category_slugs=["medicines"],
        description="Ручное описание",
    )
    apple = Brand.objects.create(name="Apple", slug="apple", category_slugs=["electronics"])
    on_duplicate = _medicine("abbott-1", "Abbott Laboratuarları", brand=duplicate)
    on_curated = _medicine("abbott-2", "Abbott", brand=curated)
    pharma_apple = _medicine("apple-1", "Apple Pharma İlaç A.Ş.")

    call_command("assign_manufacturer_brands", "--apply", "--report", str(tmp_path / "m.csv"), stdout=StringIO())

    on_duplicate.refresh_from_db()
    assert on_duplicate.brand_id == abbott.pk
    assert Product.objects.get(pk=on_duplicate.base_product_id).brand_id == abbott.pk
    assert not Brand.objects.filter(pk=duplicate.pk).exists()
    on_curated.refresh_from_db()
    assert on_curated.brand_id == abbott.pk
    assert Brand.objects.filter(pk=curated.pk).exists()  # ручное описание — не удаляем
    pharma_apple.refresh_from_db()
    assert pharma_apple.brand_id not in (apple.pk, other_brand.pk)
    assert pharma_apple.brand.external_data == {"source": "manufacturer"}


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
