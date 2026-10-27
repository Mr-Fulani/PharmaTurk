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


@pytest.mark.parametrize(
    ("furniture_type", "expected_slug"),
    [
        ("2'li yataklı kanepe", "sofa-beds"),
        ("4'lü modüler köşe kanepe", "modular-sofas"),
        ("tepsili sehpa", "coffee-tables"),
        ("döner berjer", "armchairs"),
    ],
)
def test_resolve_legacy_ikea_furniture_type(furniture_type, expected_slug):
    match = resolve_ikea_category(furniture_type=furniture_type)

    assert match.category_slug == expected_slug


@pytest.mark.parametrize(
    ("pid", "source", "category_url", "function_name", "expected_slug"),
    [
        # Очередь модерации 27.10.2026: общий раздел запуска стоял раньше точного типа.
        (13822, "karyolalar", "kategori/karyola-latasi", "karyola latası", "bed-bases"),
        (13887, "karyolalar", "kategori/karyola-latasi", "ayarlanabilir karyola latası", "bed-bases"),
        (14015, "gardiroplar", "kategori/smastad-kombinasyonlar", "ranza", "bunk-beds"),
        (14363, "gardiroplar", "kategori/smastad-kombinasyonlar", "çocuk şifonyeri", "kids-dressers"),
        (9430, "koltuklar", "kategori/vimle-koltuk-takimlari", "2'li yataklı kanepe", "sofa-beds"),
        (10470, "koltuklar", "kategori/vimle-koltuk-takimlari", "bazalı yataklı köşe kanepe", "sofa-beds"),
        (386, "koltuklar", "kategori/kivik-koltuk-takimlari", "yataklı tekli koltuk", "sofa-beds"),
        (13549, "koltuklar", "kategori/sallanan-koltuklar", "sallanan koltuk iskeleti", "rocking-armchairs"),
        (13428, "sifonyerler", "kategori/vihals-depolama-sistemleri", "dolap kombinasyonu", "storage-cabinets"),
        # Реклайнер остаётся креслом, а не уходит в игровые кресла по категории API.
        (13489, "koltuklar", "kategori/oyuncu-koltuklari", "yatar koltuk", "armchairs"),
        # «Bazalar» — кровати с подъёмным основанием: решение владельца 27.10.2026.
        (13688, "bazalar", "kategori/cift-kisilik-bazalar", "çift kişilik baza", "storage-beds"),
        (13692, "bazalar", "kategori/tek-kisilik-bazalar", "tek kişilik baza", "storage-beds"),
        # Без точного типа общий раздел по-прежнему решает.
        (14138, "karyolalar", "kategori/cift-kisilik-karyolalar", "çift kişilik karyola", "beds"),
        (14392, "gardiroplar", "kategori/pax-tum-parcalar", "sürgülü raf içi düzenleyici", "wardrobes"),
    ],
)
def test_exact_ikea_type_beats_broad_source_section(
    pid, source, category_url, function_name, expected_slug
):
    match = resolve_ikea_category(
        source_category_slug=source,
        raw_category={"url": category_url, "name": category_url.split("/")[-1]},
        raw_function={"url": "fonksiyon/x", "name": function_name},
        furniture_type=function_name,
    )

    assert match.category_slug == expected_slug, pid


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
