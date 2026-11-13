"""Парсер SPX (spx.com.tr): спортивное снаряжение на общем движке Akinon.

Фикстуры — настоящие ответы ``?format=json`` от 13.11.2026 (``test_fixtures/spx``); списки
собраны из настоящих строк раздела «Ekipman».
"""

import ast
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from apps.catalog.models import Category
from apps.scrapers.models import ScraperConfig
from apps.scrapers.parsers.registry import get_parser
from apps.scrapers.parsers.spx import (
    SPX_GROUP_ROUTES,
    SPX_NAME_ROUTES,
    SPX_SUBGROUP_ROUTES,
    SpxParser,
    spx_name_with_article,
    spx_route,
    spx_volume_ml,
)
from apps.scrapers.services import ScraperIntegrationService

FIXTURES = Path(__file__).parent / "test_fixtures" / "spx"
SITE = "https://www.spx.com.tr"

GLOVE = "/nike-alpha-training-grip-unisex-fitness-eldiveni-siyah-n-lg-66-029-lg-20110/"
OAKLEY = "/oakley-mod1-pro-erkek-kask-antrasit-465-s1-19764/"
SAIMA = "/jack-wolfskin-saima-straw-unisex-kahverengi-termos-antrasit-a64000-6168/"
DRT5 = "/oakley-drt5-maven-eu-erkek-mavi-kask-renkli-fos901303-22965/"
MEN = "/erkek/ekipman/"

CARDS = {
    GLOVE: "card_nike_alpha_glove.json",
    OAKLEY: "card_oakley_mod1_pro.json",
    SAIMA: "card_jack_wolfskin_saima.json",
    DRT5: "card_oakley_drt5.json",
}


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parser():
    """Парсер, который отвечает сохранёнными JSON и запоминает запросы."""
    parser = SpxParser()
    parser.requests = []

    def fake_request(url, **kwargs):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        assert query.get("format") == ["json"]
        assert not any("integration_" in key or key == "category_ids" for key in query), "фильтры закрыты robots.txt"
        page = query.get("page", ["1"])[0]
        parser.requests.append(parsed.path + ("" if page == "1" else f"?page={page}"))
        if parsed.path in CARDS:
            return _fixture(CARDS[parsed.path])
        if parsed.path in ("/erkek/ekipman/", "/kadin/ekipman/", "/cocuk/ekipman/"):
            return _fixture(f"list_ekipman_page{page}.json")
        return None

    parser._make_request = fake_request
    return parser


def test_parser_is_registered_for_site_domain():
    assert get_parser(f"{SITE}{MEN}") is SpxParser and get_parser("spx") is SpxParser
    assert SpxParser.is_product_url(SITE + OAKLEY) and SpxParser.is_product_url(f"{SITE}/product/145677/")
    assert SpxParser.is_category_url(SITE + MEN) and not SpxParser.is_product_url(f"{SITE}/erkek/")


# --- раскладка ------------------------------------------------------------------


@pytest.mark.parametrize(
    "group, subgroup, name, slug",
    [
        ("KAYAK/SNOWBOARD EKİPMAN", "KASK", "Oakley Mod1 Pro Erkek Kask", "winter-helmets"),
        # Тот же «Kask» в группе велоспорта — велосипедный шлем.
        ("TEKERLEKLİ SPORLAR EKİPMAN", "KASK", "Oakley Drt5 Maven Eu Erkek Mavi Kask", "cycling-helmets"),
        ("KAYAK/SNOWBOARD EKİPMAN", "GOGGLE", "Oakley Flight Deck M Unisex Goggle", "winter-goggles"),
        ("TENİS EKİPMAN", "TENİS RAKET", "Babolat Pure Drive Unisex Tenis Raketi", "tennis-rackets"),
        ("TENİS EKİPMAN", "PADEL RAKET", "Babolat Air Vertuo 2.6 Unisex Padel Raket", "racket-sports"),
        ("SU SPORLARI EKİPMAN", "YÜZÜCÜ GÖZLÜĞÜ", "Arena Tracks Unisex Yüzücü Gözlüğü", "swimming-goggles"),
        ("OUTDOOR EKİPMAN", "ÇADIR", "Easy Camp Energy 200 Unisex Çadır", "tents"),
        ("OUTDOOR EKİPMAN", "TERMOS", "Jack Wolfskin Saima Straw Unisex Termos", "thermoses"),
        ("KOŞU/FITNESS EKİPMAN", "KOŞU BANDI", "Urevo Foldi Mini Unisex Koşu Bandı", "treadmills"),
        ("OUTDOOR AKSESUAR", "ÇEŞİTLİ AKSESUAR", "Easy Camp Pyro Lantern 3 Kademeli Kamp Lambası Unisex Gri Aksesuar", "flashlights"),
    ],
)
def test_section_comes_from_group_and_subgroup(group, subgroup, name, slug):
    assert spx_route(group, subgroup, name, "")[0] == slug


@pytest.mark.parametrize(
    "group, subgroup, name, brand",
    [
        # Ножи, баллон со сжатым газом и экзоскелет с аккумулятором не везём.
        ("OUTDOOR AKSESUAR", "ÇEŞİTLİ AKSESUAR", "Victorinox Victçaki Explorer Unisex Aksesuar", "Victorinox"),
        ("KAYAK/SNOWBOARD EKİPMAN", "ÇEŞİTLİ AKSESUAR", "Arva Reactor Steel Cartridge Eu Unisex Aksesuar", "Arva"),
        ("OUTDOOR AKSESUAR", "ÇEŞİTLİ AKSESUAR", "Hypershell X Ultra Exoskeleton", "Hypershell"),
        # Смешанная подгруппа без понятного вида в названии.
        ("TEKERLEKLİ SPORLAR AKSESUAR", "ÇEŞİTLİ AKSESUAR", "Zoid Dilber Unisex Mor Aksesuar", "Zoid"),
        # Одежда и наушники.
        ("KAYAK/SNOWBOARD TEKSTİL", "SNOWBOARD CEKETİ", "Burton Unisex Snowboard Ceketi", "Burton"),
        ("KOŞU/FITNESS EKİPMAN", "KULAKLIK", "Suunto Aqua Light Unisex Kulaklık", "Suunto"),
        # Stanley уже приходит из SuperStep.
        ("OUTDOOR EKİPMAN", "TERMOS", "Stanley Hot Coral Unisex Turuncu Termos", "Stanley"),
    ],
)
def test_not_carried_goods_are_not_routed(group, subgroup, name, brand):
    assert spx_route(group, subgroup, name, brand) == ()


def test_route_slugs_are_declared_in_catalog_tree():
    """Опечатка в slug или раздел чужого корня — товар не разложится."""
    from apps.catalog import constants

    declared = {}

    def walk(node, tree_name):
        if isinstance(node, (ast.List, ast.Tuple)):
            head = node.elts[:5]
            if len(head) == 5 and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in head):
                declared.setdefault(head[2].value, set()).add(tree_name)
            for element in node.elts:
                walk(element, tree_name)

    for statement in ast.parse(Path(constants.__file__).read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and getattr(statement.targets[0], "id", "").endswith("_SUBCATEGORIES"):
            walk(statement.value, statement.targets[0].id)
    routes = [*SPX_SUBGROUP_ROUTES.values(), *SPX_GROUP_ROUTES.values(), *SPX_NAME_ROUTES.values()]
    expected_tree = {"sports": "SPORTS_SUBCATEGORIES", "tableware": "TABLEWARE_SUBCATEGORIES"}

    wrong = {
        slug: declared.get(slug)
        for route in routes
        for slug in route[:-1]
        if declared.get(slug) != {expected_tree[route[-1]]}
    }

    assert wrong == {}


@pytest.mark.parametrize(
    "size, volume",
    [("0,47 LT", "470 ml"), ("0,35LT", "350 ml"), ("0.5L", "500 ml"), ("21 OZ", "621 ml"),
     ("200 ml", "200 ml"), ("0.70", "700 ml"), ("50", ""), ("STD", ""), ("M", "")],
)
def test_volume_from_size_field(size, volume):
    assert spx_volume_ml(size) == volume


@pytest.mark.parametrize(
    "name, brand, subgroup, article, expected",
    [
        # Восемь разных масок Salice называются «Salice Unisex Goggle» — модель берётся из артикула.
        ("Salice Unisex Goggle", "Salice", "GOGGLE", "105DARWF", "Salice 105DARWF Unisex Goggle"),
        ("Salice Unisex Gri Goggle", "Salice", "GOGGLE", "101DARWF", "Salice 101DARWF Unisex Gri Goggle"),
        # Модель в названии есть — артикул не нужен.
        ("Oakley Mod1 Pro Erkek Kask", "Oakley", "KASK", "465-S1", "Oakley Mod1 Pro Erkek Kask"),
    ],
)
def test_article_is_added_to_name_without_model(name, brand, subgroup, article, expected):
    assert spx_name_with_article(name, brand, subgroup, article) == expected


# --- список и карточки ------------------------------------------------------------


def test_site_categories_are_three_equipment_sections():
    rows = _parser().parse_categories()

    assert [row["url"] for row in rows] == [f"{SITE}/erkek/ekipman/", f"{SITE}/kadin/ekipman/", f"{SITE}/cocuk/ekipman/"]


def test_listing_follows_pages_and_reports_not_loaded():
    parser = _parser()

    products = list(parser.parse_product_list(SITE + MEN, max_pages=5))

    # Нож, Stanley и наушники не открываются; вторая страница «?page=2» читается.
    assert parser.requests == [MEN, GLOVE, OAKLEY, f"{MEN}?page=2", SAIMA]
    assert [product.external_id for product in products] == [
        "spx-N.LG.66.029.LG.20110", "spx-465-S1.19764", "spx-A64000.6168",
    ]
    assert parser.has_more_pages is False
    assert "Не разложено (не загружены): 3 строк" in parser.stop_reason


def test_ski_helmet_card_is_single_colour_sports_product():
    product = _parser().parse_product_detail(SITE + OAKLEY)

    assert product.name == "Oakley Mod1 Pro Erkek Kask"
    assert product.source == "spx" and product.brand == "Oakley"
    assert product.category == "winter-helmets"
    assert product.attributes["spx_category_slugs"] == ["winter-helmets", "winter-protective-gear", "winter-sports", "sports"]
    assert product.attributes["spx_subgroup"] == "KASK"
    assert "fashion_variants" not in product.attributes
    assert product.sku == "465-S1.19764" and product.attributes["spx_color_ids"] == ["465-S1.19764"]
    assert product.attributes["sizes"] == ["S", "M", "L", "XL"]
    assert product.attributes["gender"] == "men"
    assert (product.price, product.old_price, product.currency) == (7499.99, None, "TRY")
    assert product.is_available is True and product.url == SITE + OAKLEY
    assert product.images and all(url.startswith("https://") for url in product.images)
    assert "MOD1 PRO" in product.description


def test_bike_helmet_card_goes_to_cycling():
    product = _parser().parse_product_detail(SITE + DRT5)

    assert product.category == "cycling-helmets" and product.brand == "Oakley"


def test_thermos_volume_goes_to_name_not_sizes():
    product = _parser().parse_product_detail(SITE + SAIMA)

    assert product.name == "Jack Wolfskin Saima Straw Unisex Kahverengi Termos 700 ml"
    assert product.category == "thermoses" and product.brand == "Jack Wolfskin"
    assert product.attributes["sizes"] == [] and product.attributes["volume"] == "700 ml"


def test_glove_barcode_and_unisex_gender():
    product = _parser().parse_product_detail(SITE + GLOVE)

    assert product.category == "fitness-gloves"
    assert product.attributes["gender"] == "unisex" and product.attributes["sizes"] == ["L"]


# --- сервис и настройка ---------------------------------------------------------------


@pytest.mark.django_db
def test_service_routes_by_parser_slugs():
    sports = Category.objects.create(name="Спорттовары", slug="sports")
    winter = Category.objects.create(name="Зимние виды спорта", slug="winter-sports", parent=sports)
    product = _parser().parse_product_detail(SITE + OAKLEY)
    session = type("Session", (), {"target_category": sports, "scraper_config": None})()

    ScraperIntegrationService()._apply_category_mapping(session, product)

    # «Шлемов» и «Защиты» в каталоге нет — ближайший родитель, а не корень задачи.
    assert product._category_override == winter


@pytest.mark.django_db
def test_migration_creates_disabled_schedule_config_once():
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.scrapers.migrations.0037_spx_scraper_config")
    ScraperConfig.objects.filter(parser_class="spx").delete()
    migration.create_config(django_apps, None)
    assert not ScraperConfig.objects.filter(parser_class="spx").exists()  # нет «Спорттоваров» — ничего

    sports = Category.objects.create(name="Спорттовары", slug="sports")
    migration.create_config(django_apps, None)
    config = ScraperConfig.objects.get(parser_class="spx")
    assert (config.name, config.base_url, config.default_category) == ("spx", SITE, sports)
    assert config.is_enabled is True and config.sync_enabled is False and config.use_proxy is False

    config.sync_enabled = True
    config.save()
    migration.create_config(django_apps, None)  # ручная запись не перезаписывается
    assert ScraperConfig.objects.get(parser_class="spx").sync_enabled is True
