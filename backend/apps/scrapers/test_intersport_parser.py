"""Парсер Intersport Турция: спортивный инвентарь на общем движке Akinon.

Фикстуры — настоящие ответы ``?format=json`` от 12.11.2026
(``test_fixtures/intersport``); список собран из трёх строк настоящих списков.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from apps.catalog.models import Category, Product
from apps.scrapers.base.scraper import ScrapedProduct, SiteCategoriesError
from apps.scrapers.models import ScrapedProductLog, ScraperConfig, ScrapingSession
from apps.scrapers.parsers.intersport import (
    INTERSPORT_NAME_ROUTES,
    INTERSPORT_SUBGROUP_ROUTES,
    IntersportParser,
    intersport_name_route,
)
from apps.scrapers.parsers.registry import get_parser
from apps.scrapers.services import ScraperIntegrationService

FIXTURES = Path(__file__).parent / "test_fixtures" / "intersport"
SITE = "https://www.intersport.com.tr"

TEKMELIK = "/urun/nike-mercurial-lite-unisex-siyah-tekmelik/dn3611-010/"
JORDAN = "/urun/jordan-ultimate-2-0-7-no-turuncu-basketbol-topu/j1008254-855/"
MEN = "/erkek-spor-ekipmanlari/"
WOMEN = "/kadin-spor-ekipmanlari/"
KIDS = "/cocuk-spor-ekipmanlari/"

ROUTES = {
    TEKMELIK: "card_nike_tekmelik_DN3611_010.json",
    JORDAN: "card_jordan_J1008254_855.json",
    MEN: "list_erkek_ekipman_root.json",
    WOMEN: "list_erkek_ekipman_root.json",
    KIDS: "list_erkek_ekipman_root.json",
    "/mixed/": "list_mixed.json",
    "/nine-pages/": "list_nine_pages.json",
}


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parser(routes=None):
    """Парсер, который отвечает сохранёнными JSON и запоминает запросы."""
    parser = IntersportParser()
    parser.requests = []
    table = dict(ROUTES, **(routes or {}))

    def fake_request(url, **kwargs):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        assert query.get("format") == ["json"]
        assert "page" not in query, "страницы «?page=» магазин закрыл для роботов"
        parser.requests.append(parsed.path)
        body = table.get(parsed.path)
        return _fixture(body) if body and body.endswith(".json") else body

    parser._make_request = fake_request
    return parser


def test_parser_is_registered_for_site_domain():
    assert get_parser(f"{SITE}{MEN}") is IntersportParser and get_parser("intersport") is IntersportParser
    assert IntersportParser.is_product_url(SITE + TEKMELIK)
    assert IntersportParser.is_category_url(f"{SITE}{MEN}?attributes_integration_alt_grup=257")


# --- раскладка ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, slug",
    [
        ("Nike Academy Unisex Beyaz Futbol Topu", "football-balls"),
        ("Nike Championship FB 9 Kahverengi Amerikan Futbol Topu", "team-sports"),
        ("Mikasa V360W Sent. Deri Sarı/Lacivert Voleybol Topu", "volleyball-balls"),
        ("Head 3B Head Pro Sarı  Tenis Topu", "tennis-balls"),
        ("Energetics Unisex Gri Pilates Topu 65cm", "fitness-accessories"),
        ("Pro Touch Speed 100 Kırmızı Badminton Raketi", "badminton-rackets"),
        ("Head Mx Attitude Suprm 27 inç Siyah Tenis Raketi", "tennis-rackets"),
        ("Pro Touch Masa Tenisi Ağ Seti", "table-tennis"),
        ("HEAD Bolt Unisex Beyaz Padel Raketi", "racket-sports"),
        ("Nike Streak Unisex Beyaz Voleybol Dizliği", "volleyball-knee-pads"),
        ("adidas Predator Pro Unisex Yeşil Kaleci Eldiveni", "football"),
        ("Arena Classic Silicone Unisex Beyaz Havuz Bonesi", "swim-caps"),
        ("Speedo Dual Lenses Unisex Mavi Maske Şnorkel Seti", "snorkels"),
        ("Energetics Siyah 2Kg Dambıl Seti", "dumbbells"),
        ("Energetics 2.0 Kırmızı Antrenman Güç Bant Seti", "resistance-bands"),
        ("Everlast 1910 CLS TRN 14OZ Unisex Siyah Boks Eldiveni", "boxing-gloves"),
        ("Oakley Mod5 Erkek Gri Kayak/Snowboard Kaskı", "winter-helmets"),
        ("McKinley Flyte 7 Unisex Mavi Kayak Takımı", "skis"),
        ("Firefly Phoenix III Erkek Siyah Buz Hokeyi Pateni", "ice-skates"),
        ("McKinley Ampato 10.2 Yeşil Outdoor Çadır", "tents"),
        ("Led Lenser Neo 1R Unisex Siyah Koşu Kafa Lambası", "flashlights"),
        ("McKinley Faro Tbl Unisex Beyaz Kamp Masası", "outdoor-hiking"),
        ("Pro Touch HARLEM 2000 - BB Set Beyaz Basketbol Potası", "basketball-hoops"),
        ("Pro Touch Pro 1000 Siyah Masa Tenis Raketi", "table-tennis-paddles"),
        # Nike Mercurial магазин подписывает «Futbol Dizlik» — это щитки.
        ("Nike Mercurial Hardshell Unisex Lacivert Futbol Dizlik", "shin-guards"),
        ("Nike Strength Training Unisex Siyah Ağırlık Kemeri", "weightlifting-belts"),
        ("adidas Koşu Unisex Siyah Koşu Kemeri", "running-belts"),
        ("Energetics Yoga Cork Kahverengi Mat", "yoga-mats"),
    ],
)
def test_section_comes_from_product_kind_in_name(name, slug):
    assert intersport_name_route(name)[0] == slug


def test_only_equipment_subgroups_are_loaded():
    """Обувь, одежда и аксессуары — те же, что у SuperStep и FLO: не загружаются,
    даже если в названии есть слово из таблицы видов."""
    route = IntersportParser.subgroup_route
    assert route("T-Shirt", "Nike Futbol Topu Baskılı Erkek T-Shirt", "Nike", "men") == ("T-Shirt", ())
    assert route("Koşu Ayakkabısı", "Nike Pegasus 41 Erkek Koşu Ayakkabısı", "Nike", "men")[1] == ()
    assert route("Bileklik", "Jordan Jumpman Unisex Kırmızı Bileklik", "Jordan", "unisex")[1] == ()
    # Смешанная подгруппа: вратарские перчатки — инвентарь, беговые — одежда.
    assert route("Eldiven", "adidas Predator Pro Unisex Yeşil Kaleci Eldiveni", "adidas", "")[1][0] == "football"
    assert route("Eldiven", "Nike Pacer Lightweight Rg Unisex Siyah Koşu Eldiveni", "Nike", "")[1] == ()
    # Вид в названии не распознан — раздел подгруппы.
    assert route("Bone", "Speedo Pace Cap Unisex Pembe Bone", "Speedo", "")[1][0] == "swim-caps"
    # В «Spor Aksesuarları» лежат и щитки: раздел — по названию. Наушники и прочее без
    # нашего раздела из этой сборной подгруппы не берутся.
    assert route("Spor Aksesuarları", "Nike Charge Unisex Siyah Futbol Tekmeliği", "Nike", "")[1][0] == "shin-guards"
    assert route("Spor Aksesuarları", "Shokz Openfit 2 Plus Unisex Siyah Kulaklık", "Shokz", "")[1] == ()
    assert route("Spor Aksesuarları", "McKinley Unisex Siyah Kayak & Snowboard", "McKinley", "")[1] == ()


def test_every_route_ends_in_sports_root():
    routes = [*INTERSPORT_SUBGROUP_ROUTES.values(), *INTERSPORT_NAME_ROUTES.values()]
    assert {route[-1] for route in routes if route} == {"sports"}


def test_route_slugs_are_declared_under_sports_only():
    """Опечатка в slug или раздел чужого корня (как ``tracksuits``) — товар не разложится."""
    import ast

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
    slugs = {
        slug for route in [*INTERSPORT_SUBGROUP_ROUTES.values(), *INTERSPORT_NAME_ROUTES.values()]
        for slug in route if slug != "sports"
    }

    assert {slug: declared.get(slug) for slug in slugs if declared.get(slug) != {"SPORTS_SUBCATEGORIES"}} == {}


# --- категории сайта ---------------------------------------------------------------


def test_site_categories_are_equipment_subgroups_with_filter():
    parser = _parser()

    categories = parser.parse_categories()

    assert parser.requests == [MEN, WOMEN, KIDS]
    by_url = {row["url"]: row for row in categories}
    football = by_url[f"{SITE}{MEN}?attributes_integration_alt_grup=257"]
    assert football["source"] == "intersport" and football["name"].endswith("Futbol Topu")
    assert f"{SITE}{KIDS}?attributes_integration_alt_grup=228" in by_url  # очки для плавания
    labels = {row["name"].rsplit(": ", 1)[1] for row in categories}
    # Не инвентарь (кепки, сумки, термосы, полотенца) в обход не попадает.
    assert labels.isdisjoint({"Şapka", "Çanta", "Termos", "Suluk", "Plaj Havlusu", "Bileklik", "Kulaklık"})
    assert {"Top", "Raket", "Kask", "Yüzücü Gözlüğü", "Uyku Tulumu", "Boks Eldiveni"} <= labels


def test_site_categories_fail_without_subgroup_filter():
    listing = json.loads(_fixture("list_erkek_ekipman_root.json"))
    listing["facets"] = [facet for facet in listing["facets"] if facet["key"] != "integration_alt_grup"]
    parser = _parser({MEN: json.dumps(listing)})

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()


# --- обход раздела и карточка ------------------------------------------------------


def test_listing_loads_equipment_and_reports_the_rest():
    parser = _parser()

    products = list(parser.parse_product_list(f"{SITE}/mixed/?attributes_integration_alt_grup=262", max_pages=3))

    assert parser.requests == ["/mixed/", TEKMELIK, JORDAN]  # браслет не открывается
    assert [product.external_id for product in products] == ["intersport-DN3611.010", "intersport-J1008254.855"]
    assert parser.has_more_pages is False
    assert "Не разложено (не загружены): 1 строк — Bileklik 1" in parser.stop_reason


def test_shin_guard_card_is_single_colour_sports_product():
    product = _parser().parse_product_detail(SITE + TEKMELIK)

    assert product.name == "Nike Mercurial Lite Unisex Siyah Tekmelik"
    assert product.source == "intersport" and product.brand == "Nike"
    assert product.category == "shin-guards"
    assert product.attributes["intersport_category_slugs"] == ["shin-guards", "football", "team-sports", "sports"]
    assert product.attributes["intersport_subgroup"] == "Tekmelik"
    # Спорттовары — без вариантов цвета: соседние цвета не открываются, цвет = карточка.
    assert "fashion_variants" not in product.attributes
    assert product.attributes["intersport_color_ids"] == ["DN3611.010"]
    assert product.attributes["sizes"] == ["XS", "S", "M", "L", "XL"]
    assert product.attributes["gender"] == "unisex"
    # 2 099 при «прежней цене» 1 949: сайт ничего не зачёркивает.
    assert (product.price, product.old_price, product.currency) == (2099.0, None, "TRY")
    assert product.is_available is True
    assert product.url == SITE + TEKMELIK
    assert product.images and all(url.startswith("https://") for url in product.images)
    assert "Nike Mercurial Lite" in product.description
    # Скидка «в корзине» — только для менеджера.
    assert product.attributes["intersport_basket_offers"][0]["label"] == "SEPETTE %30 İNDİRİM"


def test_ball_card_route_and_identity():
    product = _parser().parse_product_detail(SITE + JORDAN)

    assert product.external_id == "intersport-J1008254.855" and product.sku == "J1008254.855"
    assert product.category == "basketball-balls" and product.brand == "Jordan"
    assert product.attributes["sizes"] == ["07"]
    assert (product.price, product.old_price) == (2199.0, None)


def test_section_that_does_not_fit_one_page_stops_with_reason():
    """robots.txt закрывает «?page=»: вторая страница не запрашивается."""
    parser = _parser()

    products = list(parser.parse_product_list(f"{SITE}/nine-pages/", max_pages=5))

    assert [product.external_id for product in products] == ["intersport-J1008254.855"]
    assert parser.requests == ["/nine-pages/", JORDAN]
    assert parser.has_more_pages is False
    assert "не поместился на одну страницу: всего 602 строк" in parser.stop_reason


# --- сервис: раздел и двойники SuperStep ---------------------------------------------


@pytest.mark.django_db
def test_service_routes_by_parser_slugs():
    sports = Category.objects.create(name="Спорттовары", slug="sports")
    team = Category.objects.create(name="Командные виды спорта", slug="team-sports", parent=sports)
    football = Category.objects.create(name="Футбол", slug="football", parent=team)
    product = _parser().parse_product_detail(SITE + TEKMELIK)
    session = type("Session", (), {"target_category": sports, "scraper_config": None})()

    ScraperIntegrationService()._apply_category_mapping(session, product)

    # «Щитков» в каталоге нет — ближайший родитель, а не корень задачи.
    assert product._category_override == football


def _ball(**overrides):
    values = dict(
        name="Jordan Ultimate 2.0 7 No Turuncu Basketbol Topu",
        url=SITE + JORDAN,
        external_id="intersport-J1008254.855",
        source="intersport",
        images=["https://aad216-intersport.akinoncloudcdn.com/products/x.jpg"],
        attributes={
            "intersport_subgroup": "Basketbol Topu",
            "intersport_category_slugs": ["basketball-balls", "basketball", "team-sports", "sports"],
        },
    )
    values.update(overrides)
    return ScrapedProduct(**values)


@pytest.mark.django_db
def test_product_already_loaded_from_superstep_is_not_created_again():
    sports = Category.objects.create(name="Спорттовары", slug="sports")
    twin = Product.objects.create(
        name="Jordan Ultimate 2.0", slug="jordan-ultimate", external_id="superstep-J1008254.855",
        category=sports, product_type="sports", is_active=True,
    )
    config = ScraperConfig.objects.create(
        name="intersport-test", parser_class="intersport", base_url=SITE, default_category=sports,
    )
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url=SITE)
    service = ScraperIntegrationService()
    service._normalize_scraped_media = lambda *args, **kwargs: pytest.fail("фото не качаются")
    service._process_single_product = lambda *args, **kwargs: pytest.fail("товар не сохраняется")

    results = service._process_scraped_products(session, [_ball()])

    assert results["skipped"] == 1 and results["created"] == 0
    log = ScrapedProductLog.objects.get(session=session)
    assert log.action == "skipped" and "superstep-J1008254.855" in log.message

    # Сосед снят с сайта — товар Intersport загружается.
    Product.objects.filter(pk=twin.pk).update(is_active=False)
    assert service._sibling_store_product(_ball()) == ""


@pytest.mark.django_db
def test_own_product_is_updated_even_if_sibling_exists():
    sports = Category.objects.create(name="Спорттовары", slug="sports")
    for source in ("superstep", "intersport"):
        Product.objects.create(
            name=f"Jordan {source}", slug=f"jordan-{source}", external_id=f"{source}-J1008254.855",
            category=sports, product_type="sports", is_active=True,
        )
    service = ScraperIntegrationService()

    assert service._sibling_store_product(_ball()) == ""
    # И в обратную сторону: новый товар SuperStep не дублирует загруженный из Intersport.
    Product.objects.filter(external_id="superstep-J1008254.855").delete()
    superstep_ball = _ball(external_id="superstep-J1008254.855", source="superstep")
    assert service._sibling_store_product(superstep_ball) == "intersport-J1008254.855"
    # Карточка модели обуви SuperStep (код без цвета) с инвентарём не пересекается.
    assert service._sibling_store_product(_ball(external_id="superstep-B75806", source="superstep")) == ""


@pytest.mark.django_db
def test_migration_creates_disabled_schedule_config_once():
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.scrapers.migrations.0035_intersport_scraper_config")
    ScraperConfig.objects.filter(parser_class="intersport").delete()
    migration.create_config(django_apps, None)
    assert not ScraperConfig.objects.filter(parser_class="intersport").exists()  # нет «Спорттоваров» — ничего

    sports = Category.objects.create(name="Спорттовары", slug="sports")
    migration.create_config(django_apps, None)
    config = ScraperConfig.objects.get(parser_class="intersport")
    assert (config.name, config.base_url, config.default_category) == ("intersport", SITE, sports)
    assert config.is_enabled is True and config.sync_enabled is False and config.use_proxy is False
    assert config.is_multibrand is True and config.default_brand is None

    config.sync_enabled = True
    config.save()
    migration.create_config(django_apps, None)  # ручная запись не перезаписывается
    assert ScraperConfig.objects.get(parser_class="intersport").sync_enabled is True
