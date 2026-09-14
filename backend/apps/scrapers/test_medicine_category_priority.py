"""Task/config priority and opt-in category changes against real save paths."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from apps.catalog.models import (
    Brand, Category, CategoryType, MedicineProduct, MedicineProductImage, Product,
)
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.medicine_categories import resolve_medicine_category
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
    item = scraped(attributes={"atc_code": "N03AX12"})
    ScraperIntegrationService()._apply_category_mapping(
        session(catalog.get(target), catalog.get(default)), item,
    )
    if getattr(item, "_medicine_category_root", None):
        assert resolve_medicine_category(item) == catalog[expected]
    else:
        assert item.category == expected
    assert bool(getattr(item, "_category_override", None)) is authoritative


def test_disabled_feature_retains_old_task_root_override(catalog, settings):
    settings.MEDICINE_CATEGORY_AUTOMATION_ENABLED = False
    item = scraped()
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"], catalog["cardio"]), item)
    assert item._category_override == catalog["root"]
    assert not hasattr(item, "_medicine_category_root")


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
    for _ in range(2):
        item = scraped(attributes=deepcopy(before_base["external_data"]["attributes"]))
        service._apply_category_mapping(session(catalog["root"], catalog["nervous-system"]), item)
        with scraping_in_progress_context():
            service._update_existing_product(None, item, base)
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
    base, domain = existing_card(catalog, atc="N03AX12" if case == "atc" else "J01CA04")
    item = scraped()
    if case == "barcode":
        item.barcode = "9999999999999"
        item.attributes["barcode"] = item.barcode
    if case == "stub":
        MedicineProduct.objects.filter(pk=domain.pk).update(external_data={"attributes": {"is_stub": True}})
    ScraperIntegrationService()._apply_category_mapping(session(catalog["root"]), item)
    assert resolve_medicine_category(item, existing=base, is_variant_update=case == "variant") == catalog["root"]


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
