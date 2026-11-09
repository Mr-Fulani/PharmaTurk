"""Парсер Seniorah на сохранённых ответах Shopify (07.11.2026).

Фрагменты настоящих ``/products.json``, ``/collections/topuklu-ayakkabi/products.json``
и ``/collections.json``: у товаров оставлены 3 фото и поля, которые читает парсер,
рекламные абзацы описаний укорочены.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from apps.catalog.models import Category
from apps.scrapers.base.scraper import (
    CategoryPageNotFoundError,
    ScrapedProduct,
    ScraperAccessBlockedError,
    SiteCategoriesError,
)
from apps.scrapers.models import ScrapedProductLog, ScraperConfig, ScrapingSession
from apps.scrapers.parsers.registry import get_parser
from apps.scrapers.parsers.seniorah import (
    SeniorahFormatError,
    SeniorahParser,
    resolve_seniorah_category_slugs,
)
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.test_superstep_parser import _catalog_slugs

FIXTURES = Path(__file__).parent / "test_fixtures" / "seniorah"
SITE = "https://seniorah.com"


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    """Паузы парсера (2,5 с между запросами, 30/60/120 с на 429) — без настоящего сна."""
    from apps.scrapers.parsers import seniorah

    waits = []
    monkeypatch.setattr(seniorah.time, "sleep", waits.append)
    monkeypatch.setattr(seniorah.SeniorahParser, "_last_request_at", 0.0)
    return waits


NODA_BLACK = "/products/siyah-cilt-lastik-detayli-kadin-topuklu-ayakkabi"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _catalog():
    return json.loads(_fixture("products_page1.json"))


def _parser(routes=None, catalog=None):
    """Парсер, который отвечает сохранёнными JSON и запоминает запросы (путь, страница)."""
    parser = SeniorahParser()
    parser.requests = []
    catalog = catalog or _catalog()
    by_handle = {row["handle"]: row for row in catalog["products"]}
    table = {
        ("/products.json", "1"): json.dumps(catalog),
        ("/products.json", "2"): json.dumps({"products": []}),
        ("/collections/topuklu-ayakkabi/products.json", "1"): _fixture("collection_topuklu_ayakkabi.json"),
        ("/collections.json", ""): _fixture("collections.json"),
    }
    table.update(routes or {})

    def fake_request(url, **kwargs):
        parsed = urlparse(url)
        path = unquote(parsed.path)  # «i̇» в адресе — как его кодирует парсер
        page = (parse_qs(parsed.query).get("page") or [""])[0]
        parser.requests.append((path, page))
        if (path, page) in table:
            return table[(path, page)]
        if path.startswith("/products/") and path.endswith(".json"):
            row = by_handle.get(path[len("/products/"):-len(".json")])
            return json.dumps({"product": row}) if row else None
        return None

    parser._make_request = fake_request
    return parser


def _variants(product):
    return {v["color"]: v for v in product.attributes["fashion_variants"]}


# --- модель из цветов ----------------------------------------------------------


@pytest.mark.parametrize(
    "sku, expected",
    [
        ("P-057-04-C-BLACK/3473152243705", ("P-057-04-C", "BLACK")),
        ("P-057-09-C-D-RED/2149111082852", ("P-057-09-C", "D-RED")),
        ("P-057-11-R-D.RED/7992419666539", ("P-057-11-R", "D.RED")),
        ("P-913-217-S-VİZON/7239624457485", ("P-913-217-S", "VIZON")),
        ("P-059-5601-S-BEIGE-BROWN/2512856277898", ("P-059-5601-S", "BEIGE-BROWN")),
        ("P-913-217-S-L-TABA/1", ("P-913-217-S", "L-TABA")),
        ("P-MO86-1RF-PLATINUM-BLACK/9387455830828", ("P-MO86-1RF", "PLATINUM-BLACK")),
        ("P-583-101-BLACK/6684201956140", ("P-583-101", "BLACK")),
        # у одного размера сайта нет «/» перед штрихкодом
        ("P-057-09-C-BROWN1924214362770", ("P-057-09-C", "BROWN")),
        ("P-17-72K-KOT-JEANS-TABA/1", ("P-17-72K-KOT-JEANS", "TABA")),
        # турецкие буквы в коде — латиницей, а не обрезком «T-15-30-TA»
        ("T-15-30-TAŞ-BLACK/1", ("T-15-30-TAS", "BLACK")),
    ],
)
def test_sku_splits_into_model_and_color(sku, expected):
    assert SeniorahParser.split_sku(sku) == expected


def test_product_url_collects_all_colors_of_the_model_from_the_catalog():
    parser = _parser()

    product = parser.parse_product_detail(SITE + NODA_BLACK)

    assert product.external_id == "seniorah-P-057-09-C"
    assert product.name == "Noda Cilt Lastik Detaylı Kadın Topuklu Ayakkabı"
    assert list(_variants(product)) == ["Siyah", "Kahverengi", "Krem", "Bordo", "Haki"]
    assert product.brand == "Seniorah" and product.currency == "TRY"
    assert product.attributes["gender"] == "women"
    assert product.attributes["seniorah_category_slugs"] == ["heels", "dress-shoes", "shoes"]
    assert product.attributes["variant_group_id"] == "seniorah-P-057-09-C"
    assert product.attributes["sizes"] == ["36", "37", "38", "39", "40"]
    black = _variants(product)["Siyah"]
    assert black["external_id"] == "seniorah-variant-8857996198115"
    assert black["external_url"] == SITE + NODA_BLACK
    assert black["price"] == 1449.9 and black["old_price"] is None  # «старая» = цене
    assert len(black["images"]) == 3 and black["images"][0].startswith("https://cdn.shopify.com/")
    # Карточка цвета + весь каталог: два запроса на всю модель из пяти цветов.
    assert parser.requests == [(NODA_BLACK + ".json", ""), ("/products.json", "1"), ("/products.json", "2")]


def test_sizes_keep_availability():
    product = _parser().parse_product_detail(SITE + NODA_BLACK)

    cream = _variants(product)["Krem"]
    assert [(size["size"], size["is_available"]) for size in cream["sizes"]] == [
        ("36", False), ("37", False), ("38", False), ("39", True), ("40", True),
    ]
    assert cream["is_available"] is True
    assert cream["sizes"][0]["sku"] == "P-057-09-C-CREAM/7883612669864"
    assert product.is_available is True and product.attributes["color"] == "Siyah"


def test_sold_out_color_is_kept_but_not_primary():
    catalog = _catalog()
    for row in catalog["products"]:
        if row["handle"].startswith("siyah-cilt-lastik"):
            for variant in row["variants"]:
                variant["available"] = False
    product = _parser(catalog=catalog).parse_product_detail(SITE + NODA_BLACK)

    black = _variants(product)["Siyah"]
    assert black["is_available"] is False and black["stock_quantity"] == 0
    assert product.attributes["color"] == "Kahverengi"
    assert product.url == SITE + "/products/kahverengi-cilt-lastik-detayli-kadin-topuklu-ayakkabi"


def test_vizon_with_turkish_i_and_hyphen_colors_stay_in_their_models():
    parser = _parser()

    daisy = parser.parse_product_detail(SITE + "/products/daisy-vizon-suet-kadin-topuklu-bot")
    sabo = parser.parse_product_detail(SITE + "/products/siyah-suet-sabo-kadin-mantar-terlik")

    assert daisy.external_id == "seniorah-P-913-217-S"
    assert list(_variants(daisy)) == ["Vizon"]
    assert daisy.is_available is False and daisy.stock_quantity == 0
    assert daisy.attributes["seniorah_category_slugs"][0] == "ankle-boots"
    assert sabo.external_id == "seniorah-P-059-5601-S"
    assert list(_variants(sabo)) == ["Siyah", "Vizon", "Bej-Kahve", "Bej"]
    assert sabo.attributes["seniorah_category_slugs"][0] == "clogs"


def test_old_price_only_when_higher_than_price():
    catalog = _catalog()
    for row in catalog["products"]:
        if row["handle"].startswith("siyah-cilt-lastik"):
            for variant in row["variants"]:
                variant["compare_at_price"] = "1999.90"
    product = _parser(catalog=catalog).parse_product_detail(SITE + NODA_BLACK)

    assert product.old_price == 1999.9 and product.price == 1449.9
    assert _variants(product)["Kahverengi"]["old_price"] is None


def test_description_has_features_without_shop_advertising():
    product = _parser().parse_product_detail(SITE + NODA_BLACK)

    assert product.description.splitlines() == [
        "İç materyal: Cilt",
        "Dış materyal: Cilt",
        "Topuk boyu: 5 cm",
        "Kalıp bilgisi: Tam kalıptır. Kendi numaranızı tercih edebilirsiniz.",
    ]
    assert product.attributes["material"] == "Cilt"
    assert product.attributes["heel_height"] == "5 cm"
    assert product.attributes["size_advice"] == "Tam kalıptır. Kendi numaranızı tercih edebilirsiniz."


def test_features_from_live_description_formats():
    html = (
        "<h1><strong>Hazel Siyah Süet Kadın Çizme</strong></h1>"
        "<p><strong>İç materyal </strong>: Peluş sıcak astar</p>"
        "<p><strong>Dış materyal </strong>: Cilt - Süet</p>"
        "<p><strong>37 numara için baldır ölçüsü </strong>: 46 cm</p>"
        "<p><strong>Not: Bu ölçüler 37 numara için dir .Numara büyüdükce ölçüler 0,5 cm büyür.</strong></p>"
        "<p>Tam kalıptır kendi numaranızı tercih ediniz.</p>"
        "<p>Şık Tasarım: Seniorah kadın botlarımız, zarif ve modern tasarımıyla her tarza uyum sağlar.</p>"
        "<p>Yüksek kaliteli kalıplarıyla ve sağlam tabanlarıyla hem zarafeti hem de rahatlığı bir arada "
        "sunar, her adımda kendinizi özel hissedeceksiniz.</p>"
    )
    features = SeniorahParser._features(html)

    assert features["lines"] == [
        "İç materyal: Peluş sıcak astar",
        "Dış materyal: Cilt - Süet",
        "37 numara için baldır ölçüsü: 46 cm",
        "Not: Bu ölçüler 37 numara için dir .Numara büyüdükce ölçüler 0,5 cm büyür.",
        "Tam kalıptır kendi numaranızı tercih ediniz.",
    ]
    assert features["material"] == "Cilt/Süet"  # части материала — как у FLO, через «/»
    assert features["size_advice"] == "Tam kalıptır kendi numaranızı tercih ediniz."


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Kitten Siyah Cilt Kısa İnce Topuklu Kadın Ayakkabı", "heels"),
        ("Minimalist Siyah Rugan Yüksek İnce Topuklu Kadın Stiletto", "heels"),
        ("Bordo Rugan Toka Detaylı Balerin Kadın Babet", "ballet-flats"),
        ("Veraloaf Kadın Siyah Rugan Loafer Ayakkabı - Günlük Rahat Ve Şık Maskülen Tarz Kadın Babet", "loafers"),
        ("Daisy Vizon Süet Kadın Topuklu Bot", "ankle-boots"),
        ("Meriella Cilt Siyah Dokuma Örgü Desenli Sivri Burun İnce Topuklu Yarım Bot Bootie", "ankle-boots"),
        ("Brunella Kadın Kahverengi Sivri Burun Süet Dolgu Topuk Çizme", "boots-classic"),
        ("Marisella Kadın Siyah Cilt Düz Taban Yuvarlak Burun Alçak Kalın Topuklu Binici Çizmesi", "boots-classic"),
        ("Lisa Siyah Süet Kadın İçi Kürklü Sabo Ev Terliği", "slippers"),
        ("Siyah Süet Sabo Kadın Mantar Terlik", "clogs"),
        ("Cilt Tek Bant Topuklu Kadın Terlik", "slides"),
        ("Gaia Taba Süet Parmak Arası Kadın Sandalet", "sandals-classic"),
        ("Zenna Siyah Yüksek Taban Süet Kadın Spor Ayakkabı", "sneakers"),
        ("Seniorah Hediye Kartı", ""),
    ],
)
def test_category_by_shoe_kind_in_title(title, expected):
    route = resolve_seniorah_category_slugs(title)
    assert (route[0] if route else "") == expected


def test_every_route_slug_exists_in_catalog_tree():
    """Опечатка в slug молча увела бы товары в родительский раздел."""
    from apps.scrapers.parsers.seniorah import SENIORAH_CATEGORY_ROUTES

    known = _catalog_slugs()
    assert {slug for _, route in SENIORAH_CATEGORY_ROUTES for slug in route} - known == set()


def test_unknown_kind_is_not_loaded():
    catalog = _catalog()
    catalog["products"][0]["title"] = "Seniorah Hediye Kartı"
    parser = _parser(catalog=catalog)

    assert parser.parse_product_detail(SITE + "/products/" + catalog["products"][0]["handle"]) is None
    assert sum(parser.unmapped.values()) == 1


def test_removed_product_is_skipped():
    assert _parser().parse_product_detail(SITE + "/products/yok") is None


def test_html_instead_of_json_stops_as_blocked():
    parser = _parser({("/products.json", "1"): "<html>Just a moment...</html>"})

    with pytest.raises(ScraperAccessBlockedError):
        parser.parse_product_detail(SITE + NODA_BLACK)


def test_empty_catalog_is_a_format_error():
    parser = _parser({("/products.json", "1"): json.dumps({"products": []})})

    with pytest.raises(SeniorahFormatError):
        parser.parse_product_detail(SITE + NODA_BLACK)


# --- обход раздела -------------------------------------------------------------


class _Guard:
    """ListingGuard без базы: запоминает решения и отпечатки."""

    def __init__(self, known=None):
        self.known = dict(known or {})
        self.attached = []

    def prefetch(self, identities):
        pass

    def should_open(self, identity, fingerprint):
        return self.known.get(identity) != fingerprint

    def attach(self, product, identity, fingerprint, *, covers=()):
        self.attached.append(identity)
        self.known[identity] = fingerprint


def test_collection_loads_each_model_once_and_skips_unchanged_models():
    parser = _parser()
    parser.listing_guard = _Guard()

    products = list(parser.parse_product_list(SITE + "/collections/topuklu-ayakkabi", max_pages=1))

    # 10 цветов раздела — две модели; карточки по отдельности не открываются.
    assert [p.external_id for p in products] == ["seniorah-P-057-09-C", "seniorah-P-057-04-C"]
    assert len(products[1].attributes["fashion_variants"]) == 5  # TABA есть только во всём каталоге
    assert parser.requests == [
        ("/collections/topuklu-ayakkabi/products.json", "1"),
        ("/products.json", "1"),
        ("/products.json", "2"),
    ]
    assert parser.has_more_pages is False

    again = _parser()
    again.listing_guard = _Guard(parser.listing_guard.known)
    assert list(again.parse_product_list(SITE + "/collections/topuklu-ayakkabi", max_pages=1)) == []


def test_fingerprint_changes_with_price_and_stock():
    rows = _catalog()["products"][5:10]
    parser = SeniorahParser()
    base = parser._fingerprint(rows)

    cheaper = json.loads(json.dumps(rows))
    cheaper[0]["variants"][0]["price"] = "999.90"
    sold_out = json.loads(json.dumps(rows))
    sold_out[1]["variants"][2]["available"] = False

    assert parser._fingerprint(cheaper) != base
    assert parser._fingerprint(sold_out) != base
    assert parser._fingerprint(list(reversed(rows))) == base


def test_unmapped_rows_are_reported():
    collection = json.loads(_fixture("collection_topuklu_ayakkabi.json"))
    catalog = _catalog()
    for data in (collection, catalog):
        for row in data["products"]:
            row["title"] = row["title"].replace("Topuklu Ayakkabı", "Hediye Kartı")
    parser = _parser({("/collections/topuklu-ayakkabi/products.json", "1"): json.dumps(collection)}, catalog=catalog)

    assert list(parser.parse_product_list(SITE + "/collections/topuklu-ayakkabi", max_pages=1)) == []
    assert "Не разложено (не загружены): 2" in parser.stop_reason


def test_missing_collection_is_not_found():
    with pytest.raises(CategoryPageNotFoundError):
        list(_parser().parse_product_list(SITE + "/collections/yok", max_pages=1))


def test_site_categories_are_shop_collections():
    categories = _parser().parse_categories()

    assert [row["url"] for row in categories][:3] == [
        SITE + "/collections/babet",
        SITE + "/collections/bot",
        SITE + "/collections/sandalet",
    ]
    assert len(categories) == 8 and {row["source"] for row in categories} == {"seniorah"}


def test_site_categories_fail_without_collections():
    parser = _parser({("/collections.json", ""): json.dumps({"error": "x"})})

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()


@pytest.mark.parametrize(
    "url, is_product, is_category",
    [
        (SITE + NODA_BLACK, True, False),
        (SITE + "/collections/bot/products/daisy-vizon-suet-kadin-topuklu-bot", True, False),
        (SITE + "/collections/topuklu-ayakkabi", False, True),
        (SITE + "/", False, False),
        ("https://www.superstep.com.tr/collections/bot", False, False),
    ],
)
def test_url_kinds(url, is_product, is_category):
    assert SeniorahParser.is_product_url(url) is is_product
    assert SeniorahParser.is_category_url(url) is is_category


def test_parser_does_not_ask_for_brotli():
    """Shopify отвечает brotli на «br»; без пакета brotli ответ не распаковался бы."""
    assert SeniorahParser().client.headers["accept-encoding"] == "gzip, deflate"


def test_parser_is_registered_for_its_domain():
    assert get_parser(SITE + NODA_BLACK) is SeniorahParser
    assert get_parser("seniorah") is SeniorahParser


# --- раскладка при сохранении --------------------------------------------------


@pytest.mark.django_db
def test_service_takes_most_specific_existing_category_over_root_task():
    shoes = Category.objects.create(name="Обувь", slug="shoes")
    Category.objects.create(name="Туфли", slug="dress-shoes", parent=shoes)
    product = ScrapedProduct(
        name="Kitten Cilt Kadın Ayakkabı",
        source="seniorah",
        attributes={"seniorah_category_slugs": ["heels", "dress-shoes", "shoes"]},
    )
    session = SimpleNamespace(target_category=shoes, scraper_config=SimpleNamespace(default_category=shoes))

    ScraperIntegrationService()._apply_category_mapping(session, product)

    # «Туфли на каблуке» ещё не созданы (ensure_demand_categories) — ближайший родитель
    assert product.category == "dress-shoes"
    assert product._category_override.slug == "dress-shoes"


@pytest.mark.django_db
def test_product_without_catalog_section_is_not_loaded():
    shoes = Category.objects.create(name="Обувь", slug="shoes-x")
    config = ScraperConfig.objects.create(
        name="seniorah-test", parser_class="seniorah", base_url=SITE, default_category=shoes,
    )
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url=SITE)
    product = ScrapedProduct(
        name="Kitten Cilt Kadın Ayakkabı",
        url=SITE + NODA_BLACK,
        external_id="seniorah-P-057-09-C",
        source="seniorah",
        images=["https://cdn.shopify.com/s/files/1/0731/6373/5267/files/x.jpg"],
        attributes={"seniorah_category_slugs": ["heels", "dress-shoes", "shoes"]},
    )
    service = ScraperIntegrationService()
    service._normalize_scraped_media = lambda *args, **kwargs: pytest.fail("фото не качаются")
    service._process_single_product = lambda *args, **kwargs: pytest.fail("товар не сохраняется")

    results = service._process_scraped_products(session, [product])

    assert results["skipped"] == 1 and results["created"] == 0
    log = ScrapedProductLog.objects.get(session=session)
    assert "Не разложено" in log.message and "heels" in log.message


# --- проверка наличия и обновление карточки ------------------------------------


def _offer_parser(routes):
    """Парсер с подменённым HTTP: путь → (статус, тело) или адрес редиректа."""
    import httpx

    parser = SeniorahParser()
    parser.requests = []

    def handle(request):
        parser.requests.append(unquote(request.url.path))
        status, body = routes.get(unquote(request.url.path), (404, "<html>404</html>"))
        if status in (301, 302):
            return httpx.Response(status, headers={"Location": body}, request=request)
        return httpx.Response(status, text=body, request=request)

    parser.client.close()
    parser.client = httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)
    return parser


def _noda_card(**changes):
    row = next(r for r in _catalog()["products"] if r["handle"].startswith("krem-cilt-lastik"))
    row.update(changes)
    return (200, json.dumps({"product": row}))


NODA_CREAM = "/products/krem-cilt-lastik-detayli-kadin-topuklu-ayakkabi"


def _offer_context(size="39", **overrides):
    from apps.scrapers.base.offers import OfferCheckContext

    payload = {
        "canonical_url": SITE + NODA_CREAM,
        "external_product_id": "seniorah-P-057-09-C",
        "variant_key": "seniorah-variant-8857996296419",
        "size_key": size,
        "selected_options": {"color": "Krem", "size": size},
    }
    payload.update(overrides)
    return OfferCheckContext(**payload)


@pytest.mark.parametrize("size, in_stock", [("39", True), ("36", False)])
def test_offer_check_reads_one_json_of_the_saved_color(size, in_stock):
    from apps.scrapers.base.offers import OfferAvailability, OfferStockPrecision

    parser = _offer_parser({NODA_CREAM + ".json": _noda_card()})

    result = parser.check_offer(_offer_context(size))

    assert parser.requests == [NODA_CREAM + ".json"]  # весь каталог не грузится
    expected = OfferAvailability.IN_STOCK if in_stock else OfferAvailability.OUT_OF_STOCK
    assert result.availability_status == expected
    assert result.stock_precision == OfferStockPrecision.BOOLEAN and result.stock_quantity is None
    assert str(result.source_price) == "1449.90" and result.source_currency == "TRY"


def test_offer_check_removed_product_is_not_found():
    from apps.scrapers.base.offers import OfferNotFound

    with pytest.raises(OfferNotFound):
        _offer_parser({}).check_offer(_offer_context())


def test_offer_check_never_substitutes_another_product_after_redirect():
    from apps.scrapers.base.offers import OfferNotFound

    other = "/products/noda-krem-yeni"
    parser = _offer_parser({
        NODA_CREAM + ".json": (301, SITE + other + ".json"),
        other + ".json": _noda_card(id=1),
    })

    with pytest.raises(OfferNotFound):
        parser.check_offer(_offer_context())


@pytest.mark.parametrize(
    "routes, code",
    [
        ({NODA_CREAM + ".json": (200, "<html>Just a moment...</html>")}, "access_blocked"),
        ({NODA_CREAM + ".json": (200, json.dumps({"product": {"title": "x"}}))}, "malformed_response"),
        (
            {NODA_CREAM + ".json": (302, SITE + "/collections/topuklu-ayakkabi"),
             "/collections/topuklu-ayakkabi": (200, "{}")},
            "transport_error",
        ),
    ],
    ids=["html", "no-variants", "redirect-to-collection"],
)
def test_offer_check_does_not_turn_broken_response_into_out_of_stock(routes, code):
    from apps.scrapers.base.offers import OfferVerificationError

    with pytest.raises(OfferVerificationError) as error:
        _offer_parser(routes).check_offer(_offer_context())

    assert error.value.error.code.value == code


def test_card_refresh_opens_only_the_saved_color():
    parser = _parser()

    product = parser.parse_product_detail(SITE + NODA_BLACK, include_sibling_variants=False)

    assert parser.requests == [(NODA_BLACK + ".json", "")]
    assert product.external_id == "seniorah-P-057-09-C"
    assert list(_variants(product)) == ["Siyah"]


# --- настройка в «Конфигурациях парсеров» --------------------------------------


@pytest.mark.django_db
def test_migration_creates_disabled_schedule_config_once():
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.scrapers.migrations.0033_seniorah_scraper_config")
    ScraperConfig.objects.filter(parser_class="seniorah").delete()
    migration.create_config(django_apps, None)
    assert not ScraperConfig.objects.filter(parser_class="seniorah").exists()  # нет «Обуви» — ничего

    shoes = Category.objects.create(name="Обувь", slug="shoes")
    migration.create_config(django_apps, None)
    config = ScraperConfig.objects.get(parser_class="seniorah")
    assert (config.name, config.base_url, config.default_category) == ("seniorah", SITE, shoes)
    assert config.is_enabled is True and config.sync_enabled is False and config.use_proxy is False
    assert config.is_multibrand is False and config.max_images_per_product == 8

    config.sync_enabled = True
    config.save()
    migration.create_config(django_apps, None)  # ручная запись не перезаписывается
    assert ScraperConfig.objects.filter(parser_class="seniorah").count() == 1
    assert ScraperConfig.objects.get(parser_class="seniorah").sync_enabled is True


@pytest.mark.parametrize(
    "code, expected",
    [("GOLDEN", "Altın"), ("D-RED", "Bordo"), ("D.RED", "Bordo"), ("L-TABA", "Açık-Taba"),
     ("BLACK-PLATINUM", "Siyah-Platin"), ("FUSHIA", "Fuşya"), ("NUDE", "Nude")],
)
def test_color_from_sku_is_a_turkish_dictionary_word(code, expected):
    assert SeniorahParser._sku_color_tr(code) == expected


def test_same_russian_colors_inside_model_get_a_detail():
    """«Siyah», «Siyah-Bej» — оба «Черный» на сайте: уточнение через « · », как у SuperStep."""
    from apps.catalog.utils.tr_vocab import translate_turkish_color

    variants = [
        {"color": color, "display_name": f"Dimity {color} Kadın Spor Ayakkabı - {color}", "mpn": f"P-002-4-{code}"}
        for color, code in (("Beyaz", "WHITE"), ("Siyah", "BLACK"), ("Siyah-Bej", "BLACK-BEIGE"), ("Siyah-Gri", "BLACK"))
    ]
    SeniorahParser._distinct_colors(variants)

    assert [v["color"] for v in variants] == ["Beyaz", "Siyah · Black", "Siyah · Black-Beige", "Siyah · Black-Gray"]
    assert [translate_turkish_color(v["color"], "ru") for v in variants] == [
        "Белый", "Черный · Black", "Черный · Black-Beige", "Черный · Black-Gray",
    ]
    assert variants[2]["display_name"] == "Dimity Siyah-Bej Kadın Spor Ayakkabı - Siyah · Black-Beige"


def test_compound_colors_keep_the_main_color():
    """«platin», «fuşya» добавлены как запасные: «Siyah-Platin» — по-прежнему «Черный» (ревью #336)."""
    from apps.catalog.utils.tr_vocab import translate_turkish_color

    assert translate_turkish_color("Siyah-Platin", "ru") == "Черный"
    assert translate_turkish_color("Siyah-Fuşya", "ru") == "Черный"
    assert translate_turkish_color("Platin", "ru") == "Платиновый"
    assert translate_turkish_color("Fuşya", "en") == "Fuchsia"


# --- ограничение частоты запросов (429) ----------------------------------------


def _http_parser(responses):
    """Парсер, которому магазин отвечает по очереди заданными ответами."""
    import httpx

    parser = SeniorahParser()
    parser.requests = []
    queue = list(responses)

    def handle(request):
        parser.requests.append(unquote(request.url.path))
        status, body, headers = queue.pop(0)
        return httpx.Response(status, text=body, headers=headers, request=request)

    parser.client.close()
    parser.client = httpx.Client(transport=httpx.MockTransport(handle))
    return parser


CARD = json.dumps({"product": _catalog()["products"][5]})


def test_rate_limit_is_retried_after_waiting(no_waits):
    parser = _http_parser([(429, "", {}), (503, "", {"Retry-After": "7"}), (200, CARD, {})])

    assert json.loads(parser._make_request(SITE + NODA_BLACK + ".json"))["product"]["id"] == 8857996198115

    assert len(parser.requests) == 3
    assert 30 in no_waits and 7.0 in no_waits  # 30 с — по умолчанию, 7 с — по Retry-After


def test_rate_limit_after_all_retries_stops_with_clear_reason(no_waits):
    from apps.http_errors import SourceRateLimitedError

    parser = _http_parser([(429, "", {})] * 4)

    with pytest.raises(SourceRateLimitedError) as error:
        parser.parse_product_detail(SITE + NODA_BLACK)

    assert len(parser.requests) == 4  # первая попытка и три повтора, больше не стучимся
    assert [wait for wait in no_waits if wait >= 30] == [30, 60, 120]
    assert "магазин ограничил запросы (HTTP 429, seniorah.com)" in str(error.value)


def test_requests_are_at_least_two_and_a_half_seconds_apart(no_waits):
    from apps.scrapers.parsers import seniorah

    parser = _http_parser([(200, CARD, {}), (200, CARD, {})])
    seniorah.SeniorahParser._last_request_at = seniorah.time.monotonic()

    parser._make_request(SITE + NODA_BLACK + ".json")

    assert no_waits and 2.4 < no_waits[0] <= 2.5
    assert SeniorahParser().delay_range == (2.5, 4)


@pytest.mark.django_db
def test_rate_limited_session_ends_with_reason_and_keeps_config_active(monkeypatch):
    from apps.http_errors import SourceRateLimitedError

    shoes = Category.objects.create(name="Обувь", slug="shoes-rl")
    config = ScraperConfig.objects.create(
        name="seniorah-rl", parser_class="seniorah", base_url=SITE, default_category=shoes,
    )

    def limited(self, url, **kwargs):
        raise SourceRateLimitedError(source="Seniorah", status_code=429, url=url, attempts=4)

    monkeypatch.setattr(SeniorahParser, "_make_request", limited)

    with pytest.raises(SourceRateLimitedError):
        ScraperIntegrationService().run_scraper(config, start_url=SITE + "/collections/spor-ayakkabi", max_products=20)

    session = ScrapingSession.objects.get(scraper_config=config)
    assert session.status == "failed"
    assert "магазин ограничил запросы" in session.error_message
    config.refresh_from_db()
    assert config.status == "active"  # временный лимит магазина — не «Ошибка» парсера


def test_requests_identify_as_bot_without_browser_disguise():
    """08.11.2026: на заголовки «браузера» Seniorah отвечал 429 на каждый запрос."""
    parser = SeniorahParser()
    headers = {key.lower(): value for key, value in parser.client.headers.items()}
    assert headers["user-agent"] == SeniorahParser.BOT_USER_AGENT
    assert headers["accept-encoding"] == "gzip, deflate"
    assert not {"referer", "upgrade-insecure-requests", "cache-control"} & headers.keys()
    assert not any(key.startswith("sec-fetch") for key in headers)


def test_measurements_go_to_attributes():
    """Обхваты для 37 размера — атрибутом: после записи карточки описание товара уже русское."""
    html = (
        "<p>İç mataryel: Sıcak astar</p><p>37 numara için bilek ölçüsü: 28 cm</p>"
        "<p>37 numara için baldır ölçüsü: 39 cm</p><p>37 numara için boy ölçüsü topuk dahil: 45.5 cm</p>"
        "<p>Not: Bu ölçüler 37 numara için dir .Numara büyüdükce ölçüler 0,5 cm büyür.</p>"
    )
    assert SeniorahParser._features(html)["measurements"] == {"ankle": "28 cm", "calf": "39 cm", "height": "45.5 cm"}


@pytest.mark.parametrize(
    "line",
    ["37 numara için topuk boy ölçüsü: 8 cm", "37 numara için konç boy ölçüsü: 20 cm", "Topuk boy: 4 cm"],
)
def test_other_heights_are_not_height_with_heel(line):
    """«Высота с каблуком» — только «topuk dahil … boy»: высота каблука или голенища — не она."""
    assert "height" not in (SeniorahParser._features(f"<p>{line}</p>").get("measurements") or {})
