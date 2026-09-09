"""Task/config priority and opt-in category changes against real save paths."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from apps.catalog.models import (
    Brand, Category, CategoryType, MedicineProduct, MedicineProductImage, Product,
    MedicineProductTranslation, ProductTranslation,
)
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.medicine_categories import MedicineCategoryConflict, resolve_medicine_category
from apps.scrapers.models import ScraperConfig, ScrapingSession, ScrapedProductLog
from apps.scrapers.services import ScraperIntegrationService, scraping_in_progress_context


@pytest.fixture
def catalog(db, settings, monkeypatch):
    settings.MEDICINE_CATEGORY_AUTOMATION_ENABLED = True
    # Currency calculation is unrelated to category changes; external access is
    # forbidden on the isolated test network as a second line of defense.
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    kind, _ = CategoryType.objects.get_or_create(slug="medicines", defaults={"name": "Medicine"})
    root, _ = Category.objects.update_or_create(
        slug="medicines", defaults={"name": "Медицина", "category_type": kind, "parent": None},
    )
    categories = {"root": root}
    for slug in ("antibiotics", "cardio", "nervous-system", "endocrinology-diabetes"):
        category, _ = Category.objects.update_or_create(
            slug=slug, defaults={"name": slug, "parent": root, "category_type": kind, "is_active": True},
        )
        categories[slug] = category
    return categories


def session(target=None, default=None):
    return SimpleNamespace(
        target_category=target, target_category_id=target.pk if target else None,
        scraper_config=SimpleNamespace(default_category=default),
    )


def scraped(**overrides):
    values = dict(
        name="Existing medicine", source="ilacfiyati", category="medicines",
        external_id="category-priority-card", url="https://ilacfiyati.com/ilaclar/category-priority-card",
        price=100, currency="TRY", is_available=True, stock_quantity=None,
        barcode="1234567890123", attributes={"atc_code": "J01CA04", "barcode": "1234567890123"},
    )
    values.update(overrides)
    return ScrapedProduct(**values)


def existing_card(catalog, *, base_category="root", domain_category=None, atc="J01CA04"):
    brand = Brand.objects.create(name="Unchanged manufacturer", slug="unchanged-manufacturer")
    attrs = {"atc_code": atc, "barcode": "1234567890123", "active_ingredient": "Keep ingredient"}
    data = {"source": "ilacfiyati", "attributes": attrs, "ai_enriched": True}
    base = Product.objects.bulk_create([Product(
        name="Existing medicine", slug="category-priority-card", description="Keep full description",
        category=catalog[base_category] if base_category else None, brand=brand,
        product_type="medicines", price=100, currency="TRY", stock_quantity=None,
        is_available=True, external_id="category-priority-card",
        external_url="https://ilacfiyati.com/ilaclar/category-priority-card",
        external_data=deepcopy(data), seo_title="Keep SEO", meta_title="Keep meta",
    )])[0]
    domain = MedicineProduct.objects.bulk_create([MedicineProduct(
        name=base.name, slug=base.slug, description=base.description, brand=brand,
        category=catalog[domain_category or base_category] if (domain_category or base_category) else None,
        base_product=base, price=100, currency="TRY", stock_quantity=None, is_available=True,
        external_id=base.external_id, external_url=base.external_url, external_data=deepcopy(data),
        atc_code=atc, barcode="1234567890123", active_ingredient="Keep ingredient",
        dosage_form="tablet", manufacturer="Keep manufacturer", meta_title="Keep meta",
    )])[0]
    MedicineProductImage.objects.bulk_create([
        MedicineProductImage(product=domain, image_url="https://example.test/existing-image.jpg"),
    ])
    return base, domain


@pytest.mark.parametrize("target,default,expected,authoritative", [
    ("antibiotics", "cardio", "antibiotics", True),
    ("antibiotics", "root", "antibiotics", True),
    ("root", "cardio", "nervous-system", False),
    (None, "root", "nervous-system", False),
    (None, "cardio", "cardio", False),
])
def test_task_priority_and_default_category_contract(catalog, target, default, expected, authoritative):
    item = scraped(attributes={"atc_code": "N05BA01"})
    ScraperIntegrationService()._apply_category_mapping(
        session(catalog.get(target), catalog.get(default)), item,
    )
    if getattr(item, "_medicine_category_root", None):
        assert resolve_medicine_category(item) == catalog[expected]
    else:
        assert item.category == expected
    assert bool(getattr(item, "_category_override", None)) is authoritative


@pytest.mark.parametrize("current", ["root", "antibiotics", None])
def test_disabled_feature_preserves_current_category(catalog, settings, current):
    settings.MEDICINE_CATEGORY_AUTOMATION_ENABLED = False
    base, _ = existing_card(catalog, base_category=current)
    item = scraped()
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"], catalog["cardio"]), item)
    assert not hasattr(item, "_category_override")
    assert resolve_medicine_category(item, existing=base) == catalog.get(current)


@pytest.mark.parametrize("source", ["ilacabak", "flo", "ikea", "instagram", "lcw"])
def test_other_sources_keep_their_existing_root_priority(catalog, source):
    item = scraped(source=source)
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"]), item)
    assert item._category_override == catalog["root"]
    assert not hasattr(item, "_medicine_category_root")


def test_reused_payload_cannot_keep_old_auto_context_over_explicit_task_choice(catalog):
    service = ScraperIntegrationService()
    item = scraped()
    service._apply_category_mapping(session(catalog["root"]), item)
    service._apply_category_mapping(session(catalog["cardio"]), item)
    assert item._category_override == catalog["cardio"]
    assert not hasattr(item, "_medicine_category_root")


@pytest.mark.parametrize("attrs,barcode", [
    ({"atc_code": "?"}, "1234567890123"),
    ({"atc_code": "J01CA04", "is_stub": True}, "1234567890123"),
    ({"atc_code": "S03BA01"}, "1234567890123"),
    ({}, "1234567890123"),
    ({"atc_code": "J01CA04", "barcode": "9999999999999"}, "1234567890123"),
])
def test_uncertain_new_cards_stay_in_root_without_seeding(catalog, attrs, barcode):
    item = scraped(attributes=attrs, barcode=barcode)
    service = ScraperIntegrationService()
    service._apply_category_mapping(session(catalog["root"]), item)
    before = list(Category.objects.order_by("pk").values())
    assert resolve_medicine_category(item) == catalog["root"]
    assert list(Category.objects.order_by("pk").values()) == before


@pytest.mark.parametrize("unavailable", ["missing", "inactive", "wrong_parent"])
def test_target_must_exist_and_be_active_under_medicine_root(catalog, unavailable):
    item = scraped(attributes={"atc_code": "L04AA44" if unavailable == "missing" else "J01CA04"})
    if unavailable == "inactive":
        Category.objects.filter(pk=catalog["antibiotics"].pk).update(is_active=False)
    elif unavailable == "wrong_parent":
        Category.objects.filter(pk=catalog["antibiotics"].pk).update(parent=None)
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"]), item)
    before = Category.objects.count()
    assert resolve_medicine_category(item) == catalog["root"]
    assert Category.objects.count() == before


@pytest.mark.parametrize("base_category,domain_category,expected", [
    ("root", None, "antibiotics"),
    (None, None, "antibiotics"),
    ("cardio", None, "cardio"),
    ("root", "cardio", "cardio"),
])
def test_repeated_save_preserves_all_other_card_fields(catalog, base_category, domain_category, expected):
    base, domain = existing_card(catalog, base_category=base_category, domain_category=domain_category)
    before_base = Product.objects.filter(pk=base.pk).values().get()
    before_domain = MedicineProduct.objects.filter(pk=domain.pk).values().get()
    before_gallery = list(MedicineProductImage.objects.filter(product=domain).values())
    service = ScraperIntegrationService()
    actions = []
    for _ in range(2):
        item = scraped(attributes=deepcopy(before_base["external_data"]["attributes"]))
        service._apply_category_mapping(session(catalog["root"], catalog["nervous-system"]), item)
        with scraping_in_progress_context():
            action, _ = service._update_existing_product(None, item, base)
            actions.append(action)
        base.refresh_from_db()
        domain.refresh_from_db()
        assert base.category_id == domain.category_id == catalog[expected].pk
    after_base = Product.objects.filter(pk=base.pk).values().get()
    after_domain = MedicineProduct.objects.filter(pk=domain.pk).values().get()
    allowed = {"category_id", "external_data", "last_synced_at", "updated_at"}
    assert {key for key in before_base if before_base[key] != after_base[key]} <= allowed
    assert {key for key in before_domain if before_domain[key] != after_domain[key]} <= allowed
    assert after_base["external_data"]["attributes"] == before_base["external_data"]["attributes"]
    assert after_base["external_data"]["ai_enriched"] is True
    assert list(MedicineProductImage.objects.filter(product=domain).values()) == before_gallery
    assert actions[-1] == "skipped"


@pytest.mark.parametrize("target,default,expected", [
    ("root", "cardio", "antibiotics"),
    (None, "root", "antibiotics"),
    ("cardio", "root", "cardio"),
    (None, "cardio", "cardio"),
])
def test_new_card_goes_through_real_normalizer_and_keeps_priority(catalog, target, default, expected):
    item = scraped()
    service = ScraperIntegrationService()
    service._apply_category_mapping(session(catalog.get(target), catalog.get(default)), item)
    with scraping_in_progress_context():
        action, base = service._create_new_product(None, item)
    base.refresh_from_db()
    domain = MedicineProduct.objects.get(base_product=base)
    assert action == "created"
    assert base.category_id == domain.category_id == catalog[expected].pk
    assert domain.atc_code == "J01CA04" and domain.barcode == "1234567890123"
    assert base.stock_quantity is None and domain.stock_quantity is None


@pytest.mark.parametrize("case", ["atc", "barcode", "variant", "stub"])
def test_existing_uncertainty_cannot_assign_a_subcategory(catalog, case):
    base, domain = existing_card(catalog, atc="N05BA01" if case == "atc" else "J01CA04")
    item = scraped()
    if case == "barcode":
        item.barcode = "9999999999999"
        item.attributes["barcode"] = item.barcode
    if case == "stub":
        MedicineProduct.objects.filter(pk=domain.pk).update(external_data={"attributes": {"is_stub": True}})
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"]), item)
    if case in {"atc", "barcode", "variant"}:
        with pytest.raises(MedicineCategoryConflict):
            resolve_medicine_category(item, existing=base, is_variant_update=case == "variant")
    else:
        assert resolve_medicine_category(item, existing=base) == catalog["root"]


def test_conflicting_existing_specific_categories_skip_all_writes(catalog):
    base, domain = existing_card(catalog, base_category="cardio", domain_category="antibiotics")
    before_base = Product.objects.filter(pk=base.pk).values().get()
    before_domain = MedicineProduct.objects.filter(pk=domain.pk).values().get()
    item = scraped(price=999)
    service = ScraperIntegrationService()
    service._apply_category_mapping(session(catalog["root"]), item)
    action, _ = service._update_existing_product(None, item, base)
    assert action == "skipped"
    assert Product.objects.filter(pk=base.pk).values().get() == before_base
    assert MedicineProduct.objects.filter(pk=domain.pk).values().get() == before_domain


def test_explicit_task_subcategory_still_wins_for_existing_medicine(catalog):
    base, domain = existing_card(catalog, base_category="antibiotics")
    item = scraped()
    service = ScraperIntegrationService()
    service._apply_category_mapping(session(catalog["cardio"], catalog["root"]), item)
    with scraping_in_progress_context():
        service._update_existing_product(None, item, base)
    base.refresh_from_db()
    domain.refresh_from_db()
    assert base.category_id == domain.category_id == catalog["cardio"].pk
    assert domain.atc_code == "J01CA04" and domain.active_ingredient == "Keep ingredient"


def test_stale_parser_object_does_not_overwrite_new_manual_category(catalog):
    base, domain = existing_card(catalog)
    Category.objects.filter(pk=catalog["cardio"].pk).exists()
    # Simulate an admin edit committed after the parser initially read Product.
    Product.objects.filter(pk=base.pk).update(category=catalog["cardio"])
    MedicineProduct.objects.filter(pk=domain.pk).update(category=catalog["cardio"])
    assert base.category_id == catalog["root"].pk
    item = scraped()
    service = ScraperIntegrationService()
    service._apply_category_mapping(session(catalog["root"]), item)
    with scraping_in_progress_context():
        service._update_existing_product(None, item, base)
    base.refresh_from_db()
    domain.refresh_from_db()
    assert base.category_id == domain.category_id == catalog["cardio"].pk


def real_session(catalog, target="root"):
    config = ScraperConfig.objects.create(
        name="Isolated medicine category test", parser_class="ilacfiyati",
        base_url="https://ilacfiyati.com", default_category=catalog["root"],
    )
    return ScrapingSession.objects.create(
        scraper_config=config, target_category=catalog.get(target),
        start_url="https://ilacfiyati.com/ilaclar", max_pages=1, max_products=1,
    )


def full_snapshot(base, domain):
    return {
        "base": Product.objects.filter(pk=base.pk).values().get(),
        "domain": MedicineProduct.objects.filter(pk=domain.pk).values().get(),
        "images": list(MedicineProductImage.objects.filter(product=domain).order_by("pk").values()),
        "translations": list(MedicineProductTranslation.objects.filter(product=domain).order_by("pk").values()),
        "base_translations": list(ProductTranslation.objects.filter(product=base).order_by("pk").values()),
    }


@pytest.mark.parametrize("target", ["root", "cardio", None])
@pytest.mark.parametrize("field,value", [
    ("atc_code", "N05BA01"), ("barcode", "9999999999999"),
    ("active_ingredient", "Different ingredient"),
])
def test_full_pipeline_conflict_skips_all_card_and_offer_writes_and_downloads(
    catalog, monkeypatch, settings, target, field, value,
):
    from unittest.mock import Mock

    settings.SOURCE_OFFER_RECORDING_ENABLED = True
    base, domain = existing_card(catalog)
    before = full_snapshot(base, domain)
    run = real_session(catalog, target)
    item = scraped(price=999, images=["https://example.test/unwanted-new-image.jpg"])
    item.attributes[field] = value
    service = ScraperIntegrationService()
    download = Mock(side_effect=AssertionError("Conflict must not download media"))
    offer = Mock(side_effect=AssertionError("Conflict must not update source offers"))
    monkeypatch.setattr(service, "_download_parsed_media_urls", download)
    monkeypatch.setattr("apps.scrapers.source_offers.record_scraped_product_offers", offer)
    result = service._process_scraped_products(run, [item])
    assert result == {"found": 1, "created": 0, "updated": 0, "skipped": 1, "errors": 0}
    assert full_snapshot(base, domain) == before
    download.assert_not_called()
    offer.assert_not_called()
    assert f"{field}_conflict" in ScrapedProductLog.objects.get(session=run).message


@pytest.mark.parametrize("missing", [None, "", "  ", [], {}])
def test_missing_source_sections_preserve_fields_and_translations(catalog, missing):
    base, domain = existing_card(catalog, base_category="antibiotics")
    attrs = {
        **base.external_data["attributes"], "prescription_required": True,
        "source_tabs": {"summary": "Keep summary", "side_effects": "Keep side effects"},
        "summary_source": "Keep clinical summary", "analog_references": [{"barcode": "old"}],
    }
    data = {**base.external_data, "attributes": attrs}
    Product.objects.filter(pk=base.pk).update(external_data=data)
    MedicineProduct.objects.filter(pk=domain.pk).update(external_data=data, prescription_required=True)
    ProductTranslation.objects.bulk_create([
        ProductTranslation(product=base, locale="ru", name="Ручной перевод", description="Описание"),
    ])
    MedicineProductTranslation.objects.bulk_create([
        MedicineProductTranslation(product=domain, locale="en", name="Manual translation",
                                   description="Keep translation", side_effects="Keep warnings"),
    ])
    before = full_snapshot(base, domain)
    run = real_session(catalog)
    service = ScraperIntegrationService()
    for _ in range(2):
        item = scraped(barcode="", description="", attributes={key: missing for key in attrs})
        result = service._process_scraped_products(run, [item])
        assert result["skipped"] == 1 and result["errors"] == 0
    after = full_snapshot(base, domain)
    for part in ("base", "domain"):
        changed = {key for key in before[part] if before[part][key] != after[part][key]}
        assert changed <= {"external_data", "last_synced_at", "updated_at"}
        assert after[part]["external_data"]["attributes"] == before[part]["external_data"]["attributes"]
    for part in ("images", "translations", "base_translations"):
        assert after[part] == before[part]


@pytest.mark.parametrize("field", ["atc_code", "barcode"])
@pytest.mark.parametrize("current", ["root", None])
def test_missing_fresh_identity_cannot_classify_from_stored_data(catalog, field, current):
    base, _ = existing_card(catalog, base_category=current)
    item = scraped()
    item.attributes.pop(field)
    if field == "barcode":
        item.barcode = ""
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"]), item)
    assert resolve_medicine_category(item, existing=base) == catalog.get(current)


def test_old_json_conflict_is_not_hidden_by_matching_domain_and_source(catalog):
    base, domain = existing_card(catalog)
    base.external_data["attributes"]["barcode"] = "9999999999999"
    Product.objects.filter(pk=base.pk).update(external_data=base.external_data)
    before = full_snapshot(base, domain)
    result = ScraperIntegrationService()._process_scraped_products(real_session(catalog), [scraped()])
    assert result["skipped"] == 1 and result["errors"] == 0
    assert full_snapshot(base, domain) == before


def test_partial_tab_dictionary_is_merged_without_erasing_old_sections(catalog):
    base, domain = existing_card(catalog, base_category="antibiotics")
    base.external_data["attributes"]["source_tabs"] = {"summary": "Summary", "usage": "Usage"}
    Product.objects.filter(pk=base.pk).update(external_data=base.external_data)
    MedicineProduct.objects.filter(pk=domain.pk).update(external_data=base.external_data)
    run = real_session(catalog)
    service = ScraperIntegrationService()
    item = scraped(attributes={"source_tabs": {"summary": "", "side_effects": "New section"}})
    first = service._process_scraped_products(run, [item])
    second = service._process_scraped_products(run, [item])
    assert first["updated"] == 1 and second["skipped"] == 1
    domain.refresh_from_db()
    assert domain.external_data["attributes"]["source_tabs"] == {
        "summary": "Summary", "usage": "Usage", "side_effects": "New section",
    }


@pytest.mark.parametrize("case", ["variant", "source_stub", "wrong_type"])
def test_unsafe_existing_medicine_payload_leaves_whole_card_unchanged(catalog, case):
    base, domain = existing_card(catalog)
    item = scraped(price=999)
    if case == "variant":
        item.attributes["source_variant_slug"] = "another-package"
    elif case == "source_stub":
        item.attributes["is_stub"] = True
    else:
        Product.objects.filter(pk=base.pk).update(product_type="supplements")
    before = full_snapshot(base, domain)
    result = ScraperIntegrationService()._process_scraped_products(real_session(catalog), [item])
    assert result["skipped"] == 1 and result["errors"] == 0
    assert full_snapshot(base, domain) == before


def test_full_pipeline_new_card_and_identical_second_pass(catalog):
    service = ScraperIntegrationService()
    run = real_session(catalog)
    first = service._process_scraped_products(run, [scraped()])
    second = service._process_scraped_products(run, [scraped()])
    assert first["created"] == 1 and second["skipped"] == 1
    assert first["errors"] == second["errors"] == 0
    domain = MedicineProduct.objects.get(external_id="category-priority-card")
    assert domain.category == catalog["antibiotics"]
    assert domain.base_product.category == domain.category
    assert domain.barcode == "1234567890123" and domain.atc_code == "J01CA04"
    assert domain.is_available is True and domain.stock_quantity is None


def test_new_card_internal_barcode_conflict_does_not_create_or_download(catalog, monkeypatch):
    service = ScraperIntegrationService()
    run = real_session(catalog)
    item = scraped(attributes={"barcode": "9999999999999", "atc_code": "J01CA04"})

    def forbidden(*args, **kwargs):
        pytest.fail("Conflicting new card must not download media")

    monkeypatch.setattr(service, "_normalize_scraped_media", forbidden)
    before = (Product.objects.count(), MedicineProduct.objects.count())
    result = service._process_scraped_products(run, [item])
    assert result["skipped"] == 1 and result["errors"] == 0
    assert (Product.objects.count(), MedicineProduct.objects.count()) == before


def test_save_error_rolls_back_base_and_domain_together(catalog, monkeypatch):
    base, domain = existing_card(catalog)
    before = full_snapshot(base, domain)
    service = ScraperIntegrationService()

    def fail_after_base_save(*args, **kwargs):
        raise RuntimeError("Simulated domain save failure")

    monkeypatch.setattr(service, "_update_product_attributes", fail_after_base_save)
    result = service._process_scraped_products(real_session(catalog), [scraped(price=999)])
    assert result["errors"] == 1 and result["updated"] == 0
    assert full_snapshot(base, domain) == before


def test_real_html_to_catalog_keeps_own_data_and_reuses_images(catalog, monkeypatch, settings):
    from io import BytesIO
    from unittest.mock import Mock

    import httpx
    from PIL import Image

    from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser
    from apps.scrapers.test_ilacfiyati_card_integrity import CURRENT_HTML, URL

    Category.objects.create(
        slug="dermatology", name="Skin", parent=catalog["root"],
        category_type=catalog["root"].category_type,
    )
    settings.R2_CONFIG = {**getattr(settings, "R2_CONFIG", {}), "public_url": "https://cdn.mudaroba.com"}
    settings.MEDIA_URL = "https://cdn.mudaroba.com/"
    image_bytes = BytesIO()
    Image.new("RGB", (10, 10), color="white").save(image_bytes, format="PNG")
    image_get = Mock(return_value=(image_bytes.getvalue(), "image/png"))
    monkeypatch.setattr("apps.catalog.utils.parser_media_handler._get_media_bytes", image_get)
    monkeypatch.setattr(httpx.Client, "head", lambda *a, **kw: httpx.Response(
        200, headers={"Content-Type": "image/png"},
    ))
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    monkeypatch.setattr(parser, "_make_request", lambda url: CURRENT_HTML)
    service = ScraperIntegrationService()
    run = real_session(catalog)
    first = service._process_scraped_products(run, [parser.parse_product_detail(URL, include_analogs=False)])
    assert first["created"] == 1 and first["errors"] == 0
    domain = MedicineProduct.objects.get(external_id="zovirax-5-krem-2-gr")
    assert domain.category.slug == "dermatology"
    assert domain.atc_code == "D06BB03" and domain.barcode == "8699522352692"
    assert domain.active_ingredient == "Asiklovir"
    before = list(MedicineProductImage.objects.filter(product=domain).order_by("pk").values())
    assert len(before) == 2 and image_get.call_count == 2
    second = service._process_scraped_products(run, [parser.parse_product_detail(URL, include_analogs=False)])
    assert second["skipped"] == 1 and second["errors"] == 0
    assert list(MedicineProductImage.objects.filter(product=domain).order_by("pk").values()) == before
    assert image_get.call_count == 2, "Identical second pass must not download duplicate images"
