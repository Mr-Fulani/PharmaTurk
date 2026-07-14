from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from apps.catalog.ikea_category_mapping import resolve_ikea_category
from apps.catalog.models import Brand, Category, FurnitureProduct
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.services import ScraperIntegrationService


def test_resolve_ikea_category_uses_exact_api_values():
    match = resolve_ikea_category(
        source_category_slug="yatakli-kanepeler",
        raw_category={"name": "Mobilyalar"},
        raw_function={"name": "Kanepe"},
    )

    assert match.category_slug == "sofa-beds"
    assert match.reason == "slug категории запуска IKEA"
    assert resolve_ikea_category(raw_category={"name": "Mobilyalar"}) is None


@pytest.mark.django_db
def test_manual_subcategory_has_priority_over_ikea_mapping():
    root = Category.objects.create(name="Мебель", slug="furniture")
    manual = Category.objects.create(name="Кресла", slug="armchairs", parent=root)
    Category.objects.create(name="Диваны", slug="sofas", parent=root)
    scraped = ScrapedProduct(
        external_id="ikea-1",
        name="Диван",
        price=Decimal("100"),
        currency="TRY",
        source="ikea",
        attributes={"ikea_source_category_slug": "sofas"},
    )
    session = SimpleNamespace(
        target_category=manual,
        scraper_config=SimpleNamespace(default_category=root),
    )

    ScraperIntegrationService()._apply_category_mapping(session, scraped)

    assert scraped.category == "armchairs"


@pytest.mark.django_db
def test_furniture_root_allows_automatic_ikea_subcategory():
    root = Category.objects.create(name="Мебель", slug="furniture")
    Category.objects.create(name="Диваны", slug="sofas", parent=root)
    scraped = ScrapedProduct(
        name="Диван",
        source="ikea",
        attributes={"ikea_source_category_slug": "kanepeler"},
    )
    session = SimpleNamespace(
        target_category=root,
        scraper_config=SimpleNamespace(default_category=root),
    )

    ScraperIntegrationService()._apply_category_mapping(session, scraped)

    assert scraped.category == "sofas"
    assert scraped.attributes["ikea_category_match"]["confidence"] == "high"


@pytest.mark.django_db
def test_remap_ikea_categories_is_dry_run_by_default_and_applies_explicitly(capsys):
    root = Category.objects.create(name="Мебель", slug="furniture")
    target = Category.objects.create(name="Диваны-кровати", slug="sofa-beds", parent=root)
    brand = Brand.objects.create(name="IKEA", slug="ikea")
    product = FurnitureProduct.objects.create(
        name="FRIHETEN",
        slug="ikea-friheten",
        external_id="12345678",
        price=Decimal("1000"),
        currency="TRY",
        category=root,
        brand=brand,
        furniture_type="Yataklı kanepe",
        external_data={
            "source": "ikea",
            "attributes": {"ikea_source_category_slug": "yatakli-kanepeler"},
        },
    )

    call_command("remap_ikea_categories")
    product.refresh_from_db()
    assert product.category == root
    assert "Данные не изменены" in capsys.readouterr().out

    call_command("remap_ikea_categories", "--apply")
    product.refresh_from_db()
    product.base_product.refresh_from_db()
    assert product.category == target
    assert product.base_product.category == target
