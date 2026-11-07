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
