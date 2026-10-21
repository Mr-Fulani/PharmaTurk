"""Аксессуары Zara/Inditex не сохраняются одеждой (косметичка Massimo Dutti, 21.10)."""

import json
from types import SimpleNamespace

import pytest

from apps.catalog.constants import get_or_create_root_category
from apps.catalog.models import AccessoryProduct, Category, ClothingProduct
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.parsers.bershka import BershkaParser
from apps.scrapers.parsers.inditex_categories import resolve_inditex_category_slugs
from apps.scrapers.parsers.massimodutti import MassimoDuttiParser
from apps.scrapers.parsers.zara import ZaraParser
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.services import ScraperIntegrationService, scraping_in_progress_context
from apps.scrapers.test_inditex_parsers import _fixture, _parser, _routes
from apps.scrapers.test_zara_parser import _payload_html


def _parse_toiletry_bag(monkeypatch):
    parser = _parser(
        MassimoDuttiParser,
        [
            ("/product/69539551/detail", [(200, _fixture("massimodutti_toiletry_bag_detail.json"))]),
            ("massimodutti.com/tr/", [(200, "<html>home</html>")]),
            ("/itxrest/2/catalog/store/34009471?", [(200, _fixture("bershka_store.json"))]),
        ],
        monkeypatch,
    )

    return parser.parse_product_detail(
        "https://www.massimodutti.com/tr/buyuk-napa-deri-makyaj-cantas%C4%B1-l02350316?pelement=69539551"
    )


def test_massimodutti_toiletry_bag_from_live_fixture_is_mens_bag(monkeypatch):
    # Фрагмент ответа /itxrest 21.10 для товара 69539551: турецкое семейство
    # «DERİ DIŞ GİYİM» (кожаная верхняя одежда) неверно, решают название и EN-семейство.
    product = _parse_toiletry_bag(monkeypatch)

    assert product.name == "Büyük napa deri makyaj çantası"
    assert product.attributes["family"] == "DERİ DIŞ GİYİM"
    assert product.attributes["gender"] == "men"
    assert product.attributes["inditex_category_slugs"] == ["mens-bags", "bags-wallets", "accessories"]
    assert len(product.images) == 5


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("bag", ["womens-bags", "bags-wallets", "accessories"]),
        ("jewelry", ["earrings", "jewelry"]),
        ("men_acc", ["headwear"]),
    ],
)
def test_zara_accessories_from_live_fixture(monkeypatch, key, expected):
    row = json.loads(_fixture("zara_accessories_detail.json"))[key]
    parser = ZaraParser()
    monkeypatch.setattr(parser, "_make_ajax_request", lambda url: _payload_html(row["payload"]))

    product = parser.parse_product_detail(row["url"])

    assert product.attributes["inditex_category_slugs"] == expected


def test_clothing_gets_no_category_hint(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{"/product/228309045/detail": [(200, _fixture("bershka_product_detail.json"))]}),
        monkeypatch,
    )

    product = parser.parse_product_detail(
        "https://www.bershka.com/tr/kisa-kollu-baskili-boxy-fit-tisort-c0p228309045.html"
    )

    assert "inditex_category_slugs" not in product.attributes


@pytest.mark.parametrize(
    ("name", "labels", "gender", "expected"),
    [
        ("Deri kemer", (), "men", ["mens-belts", "belts", "accessories"]),
        ("Bel çantası", (), "women", ["acc-belt-bags", "womens-bags", "bags-wallets", "accessories"]),
        ("Deri kartlık", (), "", ["card-holders", "wallets", "bags-wallets", "accessories"]),
        ("ÇİZGİLİ DERİ APLİKELİ ASKILAR", ("Complementos", "ASKI"), "men", ["accessories"]),
        # Одежда с «аксессуарными» словами не в конце названия
        ("Kemerli midi elbise", ("B.DRESS", "DRESS"), "women", []),
        ("Şal yaka hırka", ("KNITWEAR",), "women", []),
        ("Takım elbise ceketi", ("BLAZER",), "men", []),
        ("Baggy jean", ("BAGGY",), "women", []),
    ],
)
def test_resolve_inditex_category_slugs(name, labels, gender, expected):
    assert resolve_inditex_category_slugs(name, labels, gender) == expected


def _session(target=None, default=None):
    return SimpleNamespace(
        target_category=target,
        scraper_config=SimpleNamespace(default_category=default),
    )


def _bag(**attrs):
    return ScrapedProduct(
        name="Büyük napa deri makyaj çantası",
        url="https://www.massimodutti.com/tr/x-l02350316?pelement=69539551",
        category="SEYAHAT ÜRÜNLERİ",
        source="massimodutti",
        attributes={"inditex_category_slugs": ["mens-bags", "bags-wallets", "accessories"], **attrs},
    )


@pytest.fixture
def categories():
    clothing = get_or_create_root_category("clothing")
    accessories = get_or_create_root_category("accessories")
    bags = Category.objects.create(name="Сумки и кошельки", slug="bags-wallets", parent=accessories)
    mens_bags = Category.objects.create(name="Мужские сумки", slug="mens-bags", parent=bags)
    womens_bags = Category.objects.create(name="Женские сумки", slug="womens-bags", parent=bags)
    mens_clothing = Category.objects.create(name="Мужская одежда", slug="mens-clothing", parent=clothing)
    return SimpleNamespace(
        clothing=clothing, accessories=accessories, mens_bags=mens_bags,
        womens_bags=womens_bags, mens_clothing=mens_clothing,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("target", [None, "clothing", "mens_clothing"])
def test_clothing_task_category_does_not_make_bag_clothing(categories, target):
    session = _session(
        target=getattr(categories, target) if target else None,
        default=categories.clothing,
    )
    product = _bag()

    ScraperIntegrationService()._apply_category_mapping(session, product)

    assert product.category == "mens-bags"
    # Существующему товару категорию и тип не меняем — override нет.
    assert getattr(product, "_category_override", None) is None
    category, product_type = resolve_category_and_product_type(product.category)
    assert (category, product_type) == (categories.mens_bags, "accessories")


@pytest.mark.django_db
def test_explicit_non_clothing_task_category_wins(categories):
    session = _session(target=categories.womens_bags, default=categories.clothing)
    product = _bag()

    ScraperIntegrationService()._apply_category_mapping(session, product)

    assert product.category == "womens-bags"
    assert product._category_override == categories.womens_bags


@pytest.mark.django_db
def test_missing_subcategories_fall_back_to_type_root():
    clothing = get_or_create_root_category("clothing")
    product = _bag()

    ScraperIntegrationService()._apply_category_mapping(_session(default=clothing), product)

    assert product.category == "accessories"
    assert resolve_category_and_product_type(product.category)[1] == "accessories"


@pytest.mark.django_db
def test_new_massimodutti_toiletry_bag_is_saved_as_accessory_with_gallery(monkeypatch, categories):
    monkeypatch.setattr("apps.catalog.signals._download_url_to_file", lambda url: None)
    scraped = _parse_toiletry_bag(monkeypatch)
    config = ScraperConfig.objects.create(
        name="md-accessory", parser_class="massimodutti",
        base_url="https://www.massimodutti.com/tr/", default_category=categories.clothing,
    )
    session = ScrapingSession.objects.create(
        scraper_config=config, start_url=scraped.url, max_pages=1, max_products=1, status="running",
    )
    service = ScraperIntegrationService()

    service._apply_category_mapping(session, scraped)
    with scraping_in_progress_context():
        action, product = service._process_single_product(session, scraped)

    assert action == "created"
    assert (product.product_type, product.category) == ("accessories", categories.mens_bags)
    assert AccessoryProduct.objects.get(base_product=product).gallery_images.count() == 5
    assert not ClothingProduct.objects.filter(base_product=product).exists()
