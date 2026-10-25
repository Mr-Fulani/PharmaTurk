"""Бренд товара у магазинов одного бренда и мультибрендовых (FLO)."""

from types import SimpleNamespace

import pytest

from apps.catalog.models import Brand, Product
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService, clean_scraped_brand_name


def _session(default_brand=None, is_multibrand=False, override_brand=None):
    return SimpleNamespace(
        _override_brand=override_brand,
        scraper_config=SimpleNamespace(default_brand=default_brand, is_multibrand=is_multibrand),
    )


def _other_brand():
    return Brand.objects.get_or_create(slug="other", defaults={"name": "Другое"})[0]


@pytest.mark.django_db
def test_single_brand_store_puts_config_brand_on_every_product():
    lcw = Brand.objects.create(name="LC Waikiki", slug="lc-waikiki")
    product = ScrapedProduct(name="Футболка", brand="LCW Vision")

    ScraperIntegrationService()._apply_brand_mapping(_session(default_brand=lcw), product)

    assert product.brand == "LC Waikiki"


@pytest.mark.django_db
def test_multibrand_store_keeps_brand_from_product_page():
    fallback = Brand.objects.create(name="FLO Fallback", slug="flo-fallback")
    product = ScrapedProduct(name="Ботинки", brand="Lumberjack")

    ScraperIntegrationService()._apply_brand_mapping(
        _session(default_brand=fallback, is_multibrand=True), product
    )

    assert product.brand == "Lumberjack"
    assert product._brand_override is None


@pytest.mark.django_db
@pytest.mark.parametrize("page_brand", ["", "  ", "Diğer", "Markasız", "-"])
def test_multibrand_store_falls_back_to_config_brand_without_page_brand(page_brand):
    fallback = Brand.objects.create(name="FLO Fallback", slug="flo-fallback")
    product = ScrapedProduct(name="Ботинки", brand=page_brand)

    ScraperIntegrationService()._apply_brand_mapping(
        _session(default_brand=fallback, is_multibrand=True), product
    )

    assert product.brand == "FLO Fallback"


@pytest.mark.django_db
def test_task_brand_beats_page_brand_in_multibrand_store():
    task_brand = Brand.objects.create(name="Puma", slug="puma-task")
    product = ScrapedProduct(name="Кроссовки", brand="Nike")

    ScraperIntegrationService()._apply_brand_mapping(
        _session(is_multibrand=True, override_brand=task_brand), product
    )

    assert product.brand == "Puma"
    assert product._brand_override == task_brand


@pytest.mark.parametrize("raw", [None, "", "x", "Другое", "OTHER", "Diğer", "12345", "https://flo.com.tr"])
def test_placeholder_brand_names_are_rejected(raw):
    assert clean_scraped_brand_name(raw) == ""


def test_brand_name_whitespace_is_collapsed():
    assert clean_scraped_brand_name("  New   Balance ") == "New Balance"


@pytest.mark.django_db
def test_new_product_gets_new_brand_instead_of_other():
    _other_brand()
    scraped = ScrapedProduct(
        name="Lumberjack Erkek Bot",
        price=1500,
        currency="TRY",
        url="https://www.flo.com.tr/urun/lumberjack-bot-1",
        external_id="flo-brand-new-1",
        category="shoes",
        brand="Lumberjack",
        source="flo",
    )

    status, product = ScraperIntegrationService()._process_single_product(None, scraped)

    product.refresh_from_db()
    assert status == "created"
    assert product.brand.name == "Lumberjack"
    assert product.brand.slug != "other"
    assert "shoes" in product.brand.category_slugs


@pytest.mark.django_db
def test_new_product_with_placeholder_brand_gets_other_without_creating_brand():
    _other_brand()
    scraped = ScrapedProduct(
        name="Erkek Bot",
        price=1500,
        currency="TRY",
        url="https://www.flo.com.tr/urun/bot-2",
        external_id="flo-brand-new-2",
        category="shoes",
        brand="Diğer",
        source="flo",
    )

    _, product = ScraperIntegrationService()._process_single_product(None, scraped)

    product.refresh_from_db()
    assert product.brand.slug == "other"
    assert not Brand.objects.filter(name__iexact="Diğer").exists()


def _existing_flo_product(brand, external_id):
    return Product.objects.create(
        name="Erkek Bot",
        slug=f"erkek-bot-{external_id}",
        product_type="shoes",
        brand=brand,
        price=1500,
        currency="TRY",
        external_id=external_id,
        external_url=f"https://www.flo.com.tr/urun/{external_id}",
        external_data={"source": "flo"},
    )


def _rescraped(product, brand):
    return ScrapedProduct(
        name=product.name,
        price=1500,
        currency="TRY",
        url=product.external_url,
        external_id=product.external_id,
        brand=brand,
        source="flo",
    )


@pytest.mark.django_db
def test_rescrape_replaces_other_placeholder_with_page_brand():
    existing_nike = Brand.objects.create(name="Nike", slug="nike-existing")
    product = _existing_flo_product(_other_brand(), "flo-rescrape-1")

    status, _ = ScraperIntegrationService()._process_single_product(None, _rescraped(product, "NIKE"))

    product.refresh_from_db()
    assert status == "updated"
    assert product.brand == existing_nike
    existing_nike.refresh_from_db()
    assert "shoes" in existing_nike.category_slugs


@pytest.mark.django_db
def test_rescrape_keeps_manually_chosen_brand():
    manual = Brand.objects.create(name="Kinetix", slug="kinetix-manual")
    product = _existing_flo_product(manual, "flo-rescrape-2")

    ScraperIntegrationService()._process_single_product(None, _rescraped(product, "Lumberjack"))

    product.refresh_from_db()
    assert product.brand == manual
    assert not Brand.objects.filter(name="Lumberjack").exists()


@pytest.mark.django_db
def test_rescrape_with_placeholder_brand_keeps_other():
    other = _other_brand()
    product = _existing_flo_product(other, "flo-rescrape-3")

    ScraperIntegrationService()._process_single_product(None, _rescraped(product, "Markasız"))

    product.refresh_from_db()
    assert product.brand == other


FLO_LISTING_HTML = """
<label data-value="manufacturer__9__Nike__1__nike"></label>
<label data-value="manufacturer__12__Polaris__1__polaris"></label>
<label data-value="manufacturer__13__Polaris 5 Nokta__1__polaris-5-nokta"></label>
<label data-value="manufacturer__40__Jack %26 Jones__1__jack-jones"></label>
"""


def test_flo_brand_is_taken_from_longest_slug_prefix():
    from apps.scrapers.management.commands.repair_flo_brands import brand_for_url, listing_brands

    brands = listing_brands(FLO_LISTING_HTML)

    assert brands["jack-jones"] == "Jack & Jones"
    assert brand_for_url("https://www.flo.com.tr/urun/polaris-5-nokta-bot-siyah-102265597", brands) == "Polaris 5 Nokta"
    assert brand_for_url("https://www.flo.com.tr/urun/polaris-sandalet-102265598", brands) == "Polaris"
    assert brand_for_url("https://www.flo.com.tr/urun/nikeair-bot-102265599", brands) == ""


@pytest.mark.django_db
def test_repair_flo_brands_replaces_only_placeholder(tmp_path):
    from django.core.management import call_command

    other = _other_brand()
    manual = Brand.objects.create(name="Kinetix", slug="kinetix-manual")
    nike_product = _existing_flo_product(other, "flo-repair-1")
    Product.objects.filter(pk=nike_product.pk).update(
        external_url="https://www.flo.com.tr/urun/nike-nike-star-runner-5-siyah-102265597"
    )
    manual_product = _existing_flo_product(manual, "flo-repair-2")
    Product.objects.filter(pk=manual_product.pk).update(
        external_url="https://www.flo.com.tr/urun/polaris-sandalet-102265598"
    )
    unknown_product = _existing_flo_product(other, "flo-repair-3")
    Product.objects.filter(pk=unknown_product.pk).update(
        external_url="https://www.flo.com.tr/urun/nobrand-terlik-102265599"
    )
    listing = tmp_path / "listing.html"
    listing.write_text(FLO_LISTING_HTML, encoding="utf-8")
    report = tmp_path / "report.csv"

    call_command("repair_flo_brands", "--listing-html", str(listing), "--report", str(report))
    nike_product.refresh_from_db()
    assert nike_product.brand == other  # dry-run ничего не пишет

    call_command("repair_flo_brands", "--listing-html", str(listing), "--report", str(report), "--apply")

    nike_product.refresh_from_db()
    manual_product.refresh_from_db()
    unknown_product.refresh_from_db()
    assert nike_product.brand.name == "Nike"
    assert "shoes" in nike_product.brand.category_slugs
    assert nike_product.shoe_item.brand == nike_product.brand
    assert manual_product.brand == manual
    assert unknown_product.brand == other
