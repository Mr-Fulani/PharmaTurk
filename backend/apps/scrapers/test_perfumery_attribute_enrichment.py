import pytest

from apps.catalog.models import Product
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


@pytest.mark.django_db
def test_perfumery_set_enrichment_maps_notes_gender_and_meta():
    service = ScraperIntegrationService()
    category, product_type = resolve_category_and_product_type("Parfüm")
    product = Product.objects.create(
        name="Parfüm Seti - Markalar - 999,99 TL",
        slug="parfum-seti-lcw",
        category=category,
        product_type=product_type,
        price=999.99,
        currency="TRY",
        external_id="lcw-5083477",
        description=(
            "Bordo - S000423895 Altınyıldız Classics Premiere Grup: odunsu aromatik, "
            "Üst notalar: kekik, lavanta, bergamot, nane, "
            "Orta notalar: sardunya, sandal ağacı, yasemin, meşe yosunu, sedir, "
            "Temel notalar: misk, vanilla, amber. "
            "Hacim: 100 ml, Türü: EDP, "
            "Deodorant Hacim: 150 ml, Duş Jeli Hacim: 400 ml."
        ),
        external_data={},
    )

    scraped = ScrapedProduct(
        name=product.name,
        description=product.description,
        category="Parfüm",
        brand="LC Waikiki",
        url="https://www.lcw.com/erkek-bordo-premiere-parfum-deodorant-dus-jeli-aksesuar-set-bordo-o-5083477",
        external_id=product.external_id,
        source="lcw",
    )
    prepared_attrs = service._prepare_scraped_attributes(scraped, product.product_type)

    assert prepared_attrs["gender"] == "men"
    assert prepared_attrs["fragrance_family"] == "woody"
    assert prepared_attrs["volume"] == "100 ml"
    assert prepared_attrs["top_notes"].startswith("kekik")
    assert prepared_attrs["heart_notes"].startswith("sardunya")
    assert prepared_attrs["base_notes"].startswith("misk")
    assert prepared_attrs["is_perfume_set"] is True
    assert prepared_attrs["volume_options"] == ["100 ml", "150 ml", "400 ml"]
    assert "deodorant" in prepared_attrs["component_types"]
    assert "dus jeli" in prepared_attrs["component_types"]

    updated = service._update_product_attributes(product, prepared_attrs)
    assert updated is True

    perfumery = product.perfumery_item
    perfumery.refresh_from_db()

    assert perfumery.gender == "men"
    assert perfumery.fragrance_family == "woody"
    assert perfumery.fragrance_type == "edp"
    assert perfumery.volume == "100 ml"
    assert perfumery.top_notes.startswith("kekik")
    assert perfumery.heart_notes.startswith("sardunya")
    assert perfumery.base_notes.startswith("misk")
    assert perfumery.external_data["perfumery_meta"]["is_perfume_set"] is True
    assert perfumery.external_data["perfumery_meta"]["volume_options"] == ["100 ml", "150 ml", "400 ml"]


@pytest.mark.django_db
def test_single_perfume_enrichment_sets_type_and_volume():
    service = ScraperIntegrationService()
    scraped = ScrapedProduct(
        name="Erkek Parfüm",
        description="Erkek parfüm. Grup: aromatik. Hacim: 50 ml. Türü: EDT.",
        category="Parfüm",
        brand="LC Waikiki",
        url="https://www.lcw.com/erkek-parfum-o-1",
        external_id="lcw-perfume-1",
        source="lcw",
    )

    prepared_attrs = service._prepare_scraped_attributes(scraped, "perfumery")

    assert prepared_attrs["gender"] == "men"
    assert prepared_attrs["fragrance_family"] == "aromatic"
    assert prepared_attrs["fragrance_type"] == "edt"
    assert prepared_attrs["volume"] == "50 ml"


@pytest.mark.django_db
def test_mixed_perfume_set_is_marked_unisex_and_keeps_gender_options():
    service = ScraperIntegrationService()
    category, product_type = resolve_category_and_product_type("Parfüm")
    product = Product.objects.create(
        name="Parfüm Seti - Markalar - 999,90 TL",
        slug="parfum-seti-mixed-lcw",
        category=category,
        product_type=product_type,
        price=999.90,
        currency="TRY",
        external_id="lcw-4101590",
        description=(
            "Paket İçeriği : Avon Elite Gentleman in Black Erkek Parfüm Edp 75 Ml. "
            "Avon Perceive Kadın Parfüm Edp 50 Ml."
        ),
        external_data={},
    )

    scraped = ScrapedProduct(
        name=product.name,
        description=product.description,
        category="Parfüm",
        brand="LC Waikiki",
        url="https://www.lcw.com/elite-gentleman-in-black-erkek-parfum-ve-perceive-kadin-parfum-paketi-renksiz-o-4101590",
        external_id=product.external_id,
        source="lcw",
    )

    prepared_attrs = service._prepare_scraped_attributes(scraped, product.product_type)

    assert prepared_attrs["gender"] == "unisex"
    assert prepared_attrs["gender_options"] == ["men", "women"]
    assert prepared_attrs["is_perfume_set"] is True
    assert prepared_attrs["fragrance_type"] == "edp"
    assert prepared_attrs["volume"] == "75 ml / 50 ml"
    assert prepared_attrs["volume_options"] == ["75 ml", "50 ml"]

    updated = service._update_product_attributes(product, prepared_attrs)
    assert updated is True

    perfumery = product.perfumery_item
    perfumery.refresh_from_db()

    assert perfumery.gender == "unisex"
    assert perfumery.fragrance_type == "edp"
    assert perfumery.volume == "75 ml / 50 ml"
    assert perfumery.external_data["perfumery_meta"]["gender_options"] == ["men", "women"]
    assert perfumery.external_data["perfumery_meta"]["volume_options"] == ["75 ml", "50 ml"]
