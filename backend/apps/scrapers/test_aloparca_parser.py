"""Парсер Aloparça на сохранённых фрагментах настоящих страниц (24.11.2026), без сети.

Карточки: свеча Bosch с 915 строками применимости на 26 марок, сцепление Mapa без
OEM-номеров, лямбда-зонд Bosch «Stokta yok». От страницы оставлены снимки компонентов
``breadcrumb`` и ``product-detail`` и блок товара до характеристик (меню, подвал и
отрисованные списки убраны). Карта сайта — 12 адресов настоящего ``products-1.xml``.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from apps.catalog.models import AutoPartFitment, AutoPartNumber, AutoPartProduct, Category, Product
from apps.http_errors import SourceRateLimitedError
from apps.scrapers.base.offers import (
    MalformedOfferResponse,
    OfferAvailability,
    OfferCheckContext,
    OfferNotFound,
    OfferSourceUnavailable,
)
from apps.scrapers.base.scraper import (
    CategoryPageNotFoundError,
    ScraperAccessBlockedError,
    SiteCategoriesError,
)
from apps.scrapers.models import ListingSnapshot, ScraperConfig, ScrapingSession
from apps.scrapers.parsers.aloparca import (
    ALOPARCA_SECTION_ROUTES,
    ALOPARCA_SUBSECTION_ROUTES,
    AloparcaFormatError,
    AloparcaParser,
    parse_fitment_row,
    resolve_aloparca_category_slugs,
    unwrap_livewire,
)
from apps.scrapers.parsers.registry import get_parser
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.test_superstep_parser import _catalog_slugs

FIXTURES = Path(__file__).parent / "test_fixtures" / "aloparca"
SITE = "https://aloparca.com"
SITEMAP = f"{SITE}/sitemaps/products-1.xml"
BOSCH = "/product/bosch-0242236596-atesleme-bujisi-fr7dii33x-iridyum-lazer-chevrolet-cruze-16-09-kalos-14-05-07"
MAPA = "/product/mapa-008240800-debriyaj-seti-baskidiskbilya-nissan-x-trail-20-4x4-01-13"
LAMBDA = "/product/bosch-0258010246-oksijen-lambda-sensoru-benzin"
CARDS = {
    BOSCH: "card_bosch_spark_plug.html",
    MAPA: "card_mapa_clutch_no_oem.html",
    LAMBDA: "card_bosch_lambda_out_of_stock.html",
}


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    """Паузы парсера (2,5 с между запросами, ожидание на 429) — без настоящего сна."""
    from apps.scrapers.parsers import aloparca

    waits = []
    monkeypatch.setattr(aloparca.time, "sleep", waits.append)
    monkeypatch.setattr(aloparca.AloparcaParser, "_last_request_at", 0.0)
    return waits


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parser(extra=None):
    """Парсер, который отвечает сохранёнными страницами и запоминает запрошенные пути."""
    parser = AloparcaParser()
    pages = {
        "/sitemap.xml": _fixture("sitemap_index.xml"),
        "/sitemaps/products-1.xml": _fixture("sitemap_products_1.xml"),
        **{path: _fixture(name) for path, name in CARDS.items()},
        **(extra or {}),
    }
    parser.requested = []

    def fake_request(url, **kwargs):
        path = httpx.URL(url).path
        parser.requested.append(path)
        return pages.get(path)

    parser._make_request = fake_request
    return parser


def _http_parser(handler):
    """Парсер с подменённым транспортом: проверяется настоящий ``_make_request``."""
    parser = AloparcaParser()
    parser.client = httpx.Client(transport=httpx.MockTransport(handler), headers=parser.default_headers)
    return parser


# --- карточка ----------------------------------------------------------------------


def test_card_with_large_fitment_table():
    product = _parser().parse_product_detail(SITE + BOSCH)

    assert product.name == "Ateşleme Bujisi BOSCH 0242236596"
    assert product.brand == "BOSCH" and product.sku == "0242236596"
    assert product.external_id == "aloparca-6674"
    assert (product.price, product.currency, product.is_available) == (515.98, "TRY", True)
    assert len(product.images) == 7
    assert product.images[0] == (
        "https://googlecdn.aloparca.com/yedek-parca-resimleri/30/d609cf79d409f34b540a2fdda064ff1c6840024e.webp"
    )
    attrs = product.attributes
    assert attrs["aloparca_breadcrumbs"][2:] == ["Ateşleme Sistemi", "Ateşleme Bujisi", "Ateşleme Bujisi"]
    assert attrs["aloparca_category_slugs"] == ["electrical-system", "auto-parts"]
    assert attrs["specs"]["Elektrot aralığı [mm]"] == "1,1"
    assert attrs["specs"]["Dişli ölçüsü"] == "M 14 x 1,25"
    assert len(attrs["specs"]) == 16
    assert attrs["source_title"].startswith("ATEŞLEME BUJİSİ FR7DII33X")
    # Описание не пустое: название источника, характеристики, OEM и марки.
    assert "Sıkma torku [Nm]: 28" in product.description and "OEM: 2741025000" in product.description

    numbers = product.auto_part["numbers"]
    assert [row["number"] for row in numbers] == ["2741025000", "980795515V", "MD361067", "SMW253694"]
    assert numbers[0] == {"number": "2741025000", "kind": "oem", "maker": "KIA"}

    fitments = product.auto_part["fitments"]
    assert len(fitments) == attrs["fitment_count"] == 915
    assert attrs["fitment_unparsed"] == 0
    assert len(attrs["fitment_makes"]) == 26 and "CITROËN" in attrs["fitment_makes"]
    assert fitments[0] == {
        "make": "FORD",
        "model": "ESCORT",
        "generation": "Escort Mk4 Hatchback (GAF, AWF, ABFT) (03.1983 - 10.1990)",
        "year_from": 1986,
        "month_from": 1,
        "year_to": 1990,
        "month_to": 7,
        "engine": "1.4",
        "power_kw": 54,
        "power_hp": 73,
        "note": "",
    }
    # Тяжёлые списки не попадают в атрибуты (external_data) и журнал товаров.
    assert "fitments" not in attrs and "auto_part" not in product.to_dict()


def test_card_without_oem_numbers():
    product = _parser().parse_product_detail(SITE + MAPA)

    assert product.name == "Debriyaj Seti MAPA 008240800"
    assert product.price == 4159.19 and product.is_available is True
    assert product.auto_part["numbers"] == [] and product.attributes["oem_count"] == 0
    assert len(product.auto_part["fitments"]) == 9
    assert product.attributes["aloparca_category_slugs"] == ["clutch-kits", "transmission", "auto-parts"]
    assert "OEM:" not in product.description


def test_out_of_stock_card_keeps_price():
    """«Stokta yok»: цена остаётся (зачёркнута у источника), товар — «нет в наличии»."""
    product = _parser().parse_product_detail(SITE + LAMBDA)

    assert product.is_available is False and product.stock_quantity == 0
    assert product.price == 989.5
    assert product.attributes["aloparca_category_slugs"] == ["sensors", "electrical-system", "auto-parts"]
    assert len(product.auto_part["numbers"]) == 3


def test_removed_card_is_skipped_not_an_error():
    assert _parser().parse_product_detail(SITE + "/product/net-takoy-kartochki") is None


def test_page_without_data_block_is_a_format_error():
    parser = _parser({"/product/x-1-y": "<html><body><h1>Aloparça</h1></body></html>"})

    with pytest.raises(AloparcaFormatError, match="product-detail"):
        parser.parse_product_detail(SITE + "/product/x-1-y")


def test_card_without_stock_mark_is_a_format_error():
    page = _fixture(CARDS[MAPA]).replace("Stokta var", "Stok bilgisi")
    parser = _parser({MAPA: page})

    with pytest.raises(AloparcaFormatError, match="наличия"):
        parser.parse_product_detail(SITE + MAPA)


# --- применимость и раскладка ------------------------------------------------------


def test_fitment_row_open_period_and_fractional_power():
    row = parse_fitment_row(
        "FORD",
        {
            "label": "FOCUS",
            "model_name": "Focus Mk3 Kombi (DYB) (07.2010 - ...)",
            "vehicle_name": "2.0 Ti-GDi (125,5 kW / 170 PS)  (07.2010 - ...)",
        },
    )

    assert (row["year_from"], row["month_from"], row["year_to"], row["month_to"]) == (2010, 7, None, None)
    assert (row["engine"], row["power_kw"], row["power_hp"]) == ("2.0 Ti-GDi", 126, 170)
    assert row["unparsed"] is False


def test_unparsed_fitment_row_is_kept_in_note():
    """Строку двигателя не узнали — она целиком в примечании, годы — от кузова."""
    row = parse_fitment_row(
        "LAND ROVER",
        {
            "label": "FREELANDER",
            "model_name": "Freelander 2 Panelvan (L359) (10.2006 - 12.2014)",
            "vehicle_name": "2.2 TD4 4x4, 110 kW",
        },
    )

    assert row["unparsed"] is True
    assert row["note"] == "2.2 TD4 4x4, 110 kW" and row["engine"] == ""
    assert (row["make"], row["model"]) == ("LAND ROVER", "FREELANDER")
    assert row["generation"] == "Freelander 2 Panelvan (L359) (10.2006 - 12.2014)"
    assert (row["year_from"], row["year_to"]) == (2006, 2014)


def test_unwrap_livewire_snapshot():
    data = {
        "product": [None, {"class": "App\\Models\\Product", "key": 9, "s": "mdl"}],
        "oems": [[[{"oem": "A1", "brands": [["VW", "AUDI"], {"s": "arr"}]}, {"s": "std"}]], {"s": "clctn"}],
    }

    assert unwrap_livewire(data) == {"product": {"key": 9}, "oems": [{"oem": "A1", "brands": ["VW", "AUDI"]}]}


def test_routes():
    assert resolve_aloparca_category_slugs("fren", "fren-disk") == ("brake-discs", "brake-system", "auto-parts")
    # «Rot Başı» у источника в подвеске, у нас — в рулевом управлении.
    assert resolve_aloparca_category_slugs("suspansiyon", "rot-basi") == (
        "tie-rod-ends", "steering-system", "auto-parts",
    )
    assert resolve_aloparca_category_slugs("motor", "motor-takozu") == ("engine-parts", "auto-parts")
    # Масла и жидкости: нашего раздела нет — в корень «Автозапчасти».
    assert resolve_aloparca_category_slugs("yaglar-ve-sivilar", "motor-yag") == ("auto-parts",)
    assert resolve_aloparca_category_slugs("", "") == ("auto-parts",)


def test_every_route_slug_exists_in_catalog_tree():
    """Опечатка в slug молча увела бы товары в родительский раздел."""
    used = set(ALOPARCA_SECTION_ROUTES.values()) | {s for route in ALOPARCA_SUBSECTION_ROUTES.values() for s in route}

    assert used - _catalog_slugs() == set()


# --- карта сайта: раздел и весь сайт ----------------------------------------------


def test_parse_categories_lists_product_sitemap_files():
    categories = _parser().parse_categories()

    assert len(categories) == 17
    assert categories[0]["url"] == SITEMAP and categories[0]["source"] == "aloparca"
    assert all("/sitemaps/products-" in row["url"] for row in categories)


def test_parse_categories_fails_without_product_files():
    parser = _parser({"/sitemap.xml": "<sitemapindex></sitemapindex>"})

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()


def test_listing_filters_by_brand_and_words_without_opening_other_cards():
    parser = _parser()
    parser.max_products = None

    products = list(parser.parse_product_list(f"{SITEMAP}?brand=bosch&q=atesleme-bujisi", max_pages=5))

    assert [product.sku for product in products] == ["0242236596"]
    assert parser.requested == ["/sitemaps/products-1.xml", BOSCH]
    assert parser.has_more_pages is False and "до конца" in parser.stop_reason


def test_listing_goes_page_by_page_and_skips_removed_cards():
    """12 адресов файла: карточек-фикстур три, остальные отвечают 404 и пропускаются."""
    parser = _parser()
    parser.max_products = None
    parser.PAGE_SIZE = 5

    first = list(parser.parse_product_list(SITEMAP, max_pages=1))
    assert first == [] and parser.pages_processed == 1
    assert parser.has_more_pages is True and parser.next_start_page == 2

    rest = list(parser.parse_product_list(SITEMAP, max_pages=5, start_page=2))
    assert [product.sku for product in rest] == ["0242236596", "008240800", "0258010246"]
    assert parser.has_more_pages is False and parser.item_errors == 0


def test_listing_stops_at_product_limit():
    parser = _parser()
    parser.max_products = 1

    products = list(parser.parse_product_list(f"{SITEMAP}?brand=bosch", max_pages=5))

    assert len(products) == 1
    assert parser.has_more_pages is False and parser.stop_reason == "Достигнут лимит товаров."
    assert LAMBDA not in parser.requested


def test_filter_without_matches_is_reported():
    parser = _parser()
    parser.max_products = None

    assert list(parser.parse_product_list(f"{SITEMAP}?brand=netu", max_pages=2)) == []
    assert parser.has_more_pages is False and "карточек нет" in parser.stop_reason


def test_not_a_sitemap_link_and_missing_file():
    with pytest.raises(CategoryPageNotFoundError):
        list(_parser().parse_product_list(f"{SITE}/yedek-parcalar/kategori/fren"))
    with pytest.raises(CategoryPageNotFoundError):
        list(_parser().parse_product_list(f"{SITE}/sitemaps/products-99.xml"))


def test_sitemap_without_cards_is_a_format_error():
    parser = _parser({"/sitemaps/products-1.xml": "<urlset></urlset>"})

    with pytest.raises(AloparcaFormatError):
        list(parser.parse_product_list(SITEMAP))


def test_layout_change_stops_the_listing():
    """Пять карточек подряд без блока данных — вёрстка сменилась, обход останавливается."""
    broken = "<html><body>Yeni tasarım</body></html>"
    urls = [f"/product/elring-{n}-x" for n in range(6)]
    sitemap = "<urlset>" + "".join(
        f"<url><loc>{SITE}{u}</loc><lastmod>2026-11-24T08:00:03+03:00</lastmod></url>" for u in urls
    ) + "</urlset>"
    parser = _parser({"/sitemaps/products-1.xml": sitemap, **{u: broken for u in urls}})
    parser.max_products = None

    with pytest.raises(AloparcaFormatError):
        list(parser.parse_product_list(SITEMAP))
    assert parser.item_errors == 5


def test_url_kinds_and_registry():
    assert AloparcaParser.is_product_url(SITE + BOSCH)
    assert AloparcaParser.is_category_url(f"{SITEMAP}?brand=bosch")
    assert not AloparcaParser.is_category_url(f"{SITE}/sitemaps/vehicles.xml")
    assert not AloparcaParser.is_product_url("https://example.com" + BOSCH)
    assert get_parser("aloparca") is AloparcaParser
    assert get_parser(SITE + BOSCH) is AloparcaParser


# --- вежливый режим ---------------------------------------------------------------


def test_requests_are_direct_honest_and_throttled(no_waits):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, text="ok")

    parser = _http_parser(handler)
    AloparcaParser._last_request_at = __import__("time").monotonic()

    assert parser._make_request(SITE + BOSCH) == "ok"
    assert seen[0].headers["user-agent"].startswith("MudarobaBot/")
    assert seen[0].headers["accept-encoding"] == "gzip, deflate"
    assert parser.use_proxy is False and not parser.proxy_url
    assert len(no_waits) == 1 and 2.4 < no_waits[0] <= 2.5


def test_proxy_is_used_only_when_the_config_enables_it(settings, tmp_path):
    """Серверу сайт закрыт: прокси включает галочка настройки, имя робота остаётся честным."""
    ca_bundle = tmp_path / "ca.crt"
    ca_bundle.write_text("test")
    settings.SCRAPER_PROXY_URL = "http://user:secret@brd.superproxy.io:44445"
    settings.SCRAPER_PROXY_CA_BUNDLE = str(ca_bundle)

    with patch("apps.scrapers.base.scraper.httpx.Client") as client:
        assert not AloparcaParser().proxy_url
        parser = AloparcaParser(use_proxy=True)

    assert parser.proxy_url == settings.SCRAPER_PROXY_URL
    assert client.call_args.kwargs["proxy"] == settings.SCRAPER_PROXY_URL
    assert parser.default_headers["User-Agent"].startswith("MudarobaBot/")
    assert AloparcaParser.MEDIA_PROXY_USER_AGENT == AloparcaParser.BOT_USER_AGENT


# --- проверка цены и наличия при открытии карточки ----------------------------------


def _offer(path, external_id=""):
    return OfferCheckContext(canonical_url=SITE + path, external_product_id=external_id)


def test_offer_check_reads_price_and_stock_with_one_request():
    parser = _parser()

    in_stock = parser.check_offer(_offer(BOSCH, "aloparca-6674"))
    sold_out = parser.check_offer(_offer(LAMBDA))

    assert parser.requested == [BOSCH, LAMBDA]
    assert in_stock.availability_status == OfferAvailability.IN_STOCK
    assert in_stock.source_price is not None and in_stock.source_currency == "TRY"
    assert in_stock.canonical_url == SITE + BOSCH and in_stock.stock_quantity is None
    assert sold_out.availability_status == OfferAvailability.OUT_OF_STOCK
    assert float(sold_out.source_price) == 989.5


def test_offer_check_removed_or_other_card_is_not_found():
    with pytest.raises(OfferNotFound):
        _parser().check_offer(_offer("/product/snyat-s-prodazhi"))
    with pytest.raises(OfferNotFound):
        _parser().check_offer(_offer(BOSCH, "aloparca-1"))
    with pytest.raises(OfferNotFound):
        _parser().check_offer(OfferCheckContext(canonical_url=SITEMAP))


def test_offer_check_layout_change_is_malformed_not_out_of_stock():
    parser = _parser({BOSCH: "<html><body>Yeni tasarım</body></html>"})

    with pytest.raises(MalformedOfferResponse):
        parser.check_offer(_offer(BOSCH))


def test_offer_check_does_not_wait_or_pass_a_cloudflare_check(no_waits):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429 if len(calls) == 1 else 403, headers={"cf-mitigated": "challenge"})

    with pytest.raises(OfferSourceUnavailable):  # 429: без ожиданий 60 и 180 с
        _http_parser(handler).check_offer(_offer(BOSCH))
    with pytest.raises(OfferSourceUnavailable):  # проверка Cloudflare: стоп
        _http_parser(handler).check_offer(_offer(BOSCH))
    assert len(calls) == 2 and [w for w in no_waits if w >= 60] == []


def test_nightly_check_skips_the_paid_source(settings):
    assert "aloparca" in settings.NIGHTLY_STOCK_CHECK_PAID_SOURCES


@pytest.mark.django_db
@pytest.mark.parametrize("use_proxy", [True, False])
def test_photos_go_through_the_proxy_only_when_enabled(use_proxy):
    """Фото закрыты серверу так же, как сайт: с галочкой — через прокси, без неё — напрямую."""
    root = Category.objects.create(name="Автозапчасти", slug="auto-parts")
    config = ScraperConfig.objects.create(
        name="aloparca-media", parser_class="aloparca", base_url=SITE, default_category=root, use_proxy=use_proxy,
    )
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url=SITEMAP)
    photo = "https://googlecdn.aloparca.com/yedek-parca-resimleri/30/a.webp"

    with patch("apps.scrapers.services.download_and_optimize_parsed_media", return_value="https://cdn/x.webp") as load:
        ScraperIntegrationService()._download_parsed_media_urls(
            session, source_urls=[photo], parser_name="aloparca", product_id="aloparca-1", sub_folder=None,
        )

    assert load.call_args.kwargs.get("use_proxy", False) is use_proxy
    agent = (load.call_args.kwargs["headers"] or {}).get("User-Agent", "")
    assert agent.startswith("MudarobaBot/") is use_proxy


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, text="Forbidden"),
        httpx.Response(403, headers={"cf-mitigated": "challenge"}, text="<title>Just a moment...</title>"),
        httpx.Response(503, text='<script src="/cdn-cgi/challenge-platform/h/b/orchestrate"></script>'),
    ],
)
def test_block_or_cloudflare_check_stops_without_retries(response, no_waits):
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with pytest.raises(ScraperAccessBlockedError):
        _http_parser(handler)._make_request(SITE + BOSCH)
    assert len(calls) == 1 and no_waits == []


def test_rate_limit_waits_then_stops(no_waits):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, text="Too Many Requests")

    with pytest.raises(SourceRateLimitedError):
        _http_parser(handler)._make_request(SITE + BOSCH)
    assert len(calls) == 3 and [w for w in no_waits if w >= 60] == [60, 180]


def test_removed_card_statuses_return_none():
    assert _http_parser(lambda request: httpx.Response(404))._make_request(SITE + BOSCH) is None
    assert _http_parser(lambda request: httpx.Response(410))._make_request(SITE + BOSCH) is None


# --- запись в каталог -------------------------------------------------------------


@pytest.fixture
def auto_parts_session(db):
    root = Category.objects.create(name="Автозапчасти", slug="auto-parts")
    electrics = Category.objects.create(name="Электрика", slug="electrical-system", parent=root)
    Category.objects.create(name="Датчики", slug="sensors", parent=electrics)
    config = ScraperConfig.objects.create(
        name="aloparca-test", parser_class="aloparca", base_url=SITE, default_category=root, is_multibrand=True,
    )
    session = ScrapingSession.objects.create(scraper_config=config, status="running", start_url=SITEMAP)
    service = ScraperIntegrationService()
    # Фото не качаем: конвейер медиа проверяется своими тестами (test_parser_media_pipeline).
    service._normalize_scraped_media = lambda *args, **kwargs: None
    service.catalog_normalizer._normalize_product_images = lambda *args, **kwargs: False
    return session, service


def test_service_saves_numbers_fitments_and_normalized_part_number(auto_parts_session):
    session, service = auto_parts_session
    scraped = _parser().parse_product_detail(SITE + LAMBDA)

    results = service._process_scraped_products(session, [scraped])

    assert (results["created"], results["errors"]) == (1, 0)
    product = Product.objects.get(external_id="aloparca-10893")
    assert product.product_type == "auto_parts" and product.category.slug == "sensors"
    assert product.brand.name.upper() == "BOSCH"
    assert product.is_available is False and float(product.price) == 989.5 and product.currency == "TRY"
    part = AutoPartProduct.objects.get(base_product=product)
    assert (part.part_number, part.part_number_normalized) == ("0258010246", "0258010246")
    assert (part.car_brand, part.car_model) == ("FORD", "FOCUS")
    assert sorted(part.numbers.values_list("number", "kind", "maker", "source")) == [
        ("5129058", "oem", "FORD", "aloparca"),
        ("BV619G444AA", "oem", "FORD", "aloparca"),
        ("CV6Z9G444A", "oem", "FORD", "aloparca"),
    ]
    assert part.fitments.count() == 12
    fitment = part.fitments.get(engine="2.0 Ti-GDi", generation__startswith="Focus Mk3 Kombi")
    assert (fitment.make_slug, fitment.model_slug) == ("ford", "focus")
    assert (fitment.year_from, fitment.year_to, fitment.power_kw, fitment.power_hp) == (2010, None, 125, 170)
    # В external_data — только сводка, без сотен строк применимости.
    saved = product.external_data["attributes"]
    assert saved["fitment_count"] == 12 and "fitments" not in saved
    assert saved["specs"]["Komple uzunluk [mm]"] == "718"


def test_card_with_address_longer_than_200_characters_is_saved_and_logged(auto_parts_session):
    """Адрес карточки Aloparça — до ~230 знаков (перечень машин): журнал парсинга его принимает."""
    from apps.scrapers.models import ScrapedProductLog

    session, service = auto_parts_session
    scraped = _parser().parse_product_detail(SITE + LAMBDA)
    scraped.url = f"{SITE}/product/bosch-0258010246-oksijen-lambda-sensoru-" + "peugeot-208-i-15-bluehdi-18-" * 7

    results = service._process_scraped_products(session, [scraped])

    assert len(scraped.url) > 200 and (results["created"], results["errors"]) == (1, 0)
    assert ScrapedProductLog.objects.get(session=session).external_url == scraped.url


def test_rescrape_replaces_only_rows_of_this_source(auto_parts_session):
    session, service = auto_parts_session
    service._process_scraped_products(session, [_parser().parse_product_detail(SITE + LAMBDA)])
    part = AutoPartProduct.objects.get(external_id="aloparca-10893")
    manual = AutoPartNumber.objects.create(product=part, number="0 258 010-999", kind="cross", maker="NGK")
    AutoPartFitment.objects.create(product=part, make="MAZDA", model="3", note="добавлено вручную")
    assert manual.number_normalized == "0258010999"

    again = _parser().parse_product_detail(SITE + LAMBDA)
    again.auto_part["numbers"] = again.auto_part["numbers"][:2]
    again.auto_part["fitments"] = again.auto_part["fitments"][:5]
    again.price = 1010.0
    results = service._process_scraped_products(session, [again])

    assert (results["updated"], results["created"], results["errors"]) == (1, 0, 0)
    part.refresh_from_db()
    assert float(part.price) == 1010.0
    assert part.numbers.filter(source="aloparca").count() == 2
    assert part.numbers.filter(pk=manual.pk).exists()
    assert part.fitments.filter(source="aloparca").count() == 5
    assert part.fitments.filter(make="MAZDA", source="").count() == 1


def test_unchanged_rescrape_does_not_rewrite_tables(auto_parts_session):
    session, service = auto_parts_session
    service._process_scraped_products(session, [_parser().parse_product_detail(SITE + LAMBDA)])
    ids = set(AutoPartFitment.objects.values_list("pk", flat=True))

    service._process_scraped_products(session, [_parser().parse_product_detail(SITE + LAMBDA)])

    assert set(AutoPartFitment.objects.values_list("pk", flat=True)) == ids
    assert AutoPartNumber.objects.count() == 3


def test_new_part_is_queued_for_its_card_once(auto_parts_session, django_capture_on_commit_callbacks):
    """Русская и английская карточка ставится в обработку сразу при сборе, повторный сбор её не дублирует."""
    session, service = auto_parts_session

    with patch("apps.ai.tasks.process_product_ai_task.apply_async") as submit:
        with django_capture_on_commit_callbacks(execute=True):
            service._process_scraped_products(session, [_parser().parse_product_detail(SITE + LAMBDA)])
        with django_capture_on_commit_callbacks(execute=True):
            service._process_scraped_products(session, [_parser().parse_product_detail(SITE + LAMBDA)])

    product = Product.objects.get(external_id="aloparca-10893")
    assert submit.call_count == 1
    kwargs = submit.call_args.kwargs["kwargs"]
    assert (kwargs["product_id"], kwargs["processing_type"], kwargs["auto_apply"]) == (product.pk, "full", True)
    assert product.ai_logs.count() == 1


def test_card_open_refresh_updates_price_and_stock_but_not_the_card_text(auto_parts_session, settings):
    """Открытие карточки: с источника — только цена и наличие, название и таблицы не трогаются."""
    from apps.catalog.services.product_card_source_refresh import ProductCardSourceRefreshService, RefreshTarget

    settings.SOURCE_OFFER_RECORDING_ENABLED = True
    session, service = auto_parts_session
    service._process_scraped_products(session, [_parser().parse_product_detail(SITE + BOSCH)])
    part = AutoPartProduct.objects.get()
    AutoPartProduct.objects.filter(pk=part.pk).update(name="Свеча зажигания Bosch 0242236596")
    fitments = part.fitments.count()
    fresh = _parser().parse_product_detail(SITE + BOSCH)
    fresh.price, fresh.is_available, fresh.stock_quantity = fresh.price + 100, False, 0
    refresh = ProductCardSourceRefreshService()
    target = RefreshTarget(
        product=part.base_product, offer=part.base_product.source_offers.get(), parser_class=AloparcaParser,
    )

    refresh._reconcile(target, fresh, refresh._validated_snapshots(target, fresh))

    part.refresh_from_db()
    product = Product.objects.get(pk=part.base_product_id)
    assert float(part.price) == float(product.price) == fresh.price
    assert part.is_available is False and product.is_available is False
    assert part.name == "Свеча зажигания Bosch 0242236596" and part.fitments.count() == fitments


def test_category_route_wins_over_root_task(db):
    root = Category.objects.create(name="Автозапчасти", slug="auto-parts")
    Category.objects.create(name="Тормоза", slug="brake-system", parent=root)
    scraped = SimpleNamespace(
        source="aloparca", name="Fren Disk", url="", category="",
        attributes={"aloparca_category_slugs": ["brake-discs", "brake-system", "auto-parts"]},
    )
    session = SimpleNamespace(target_category=root, scraper_config=SimpleNamespace(default_category=root))

    ScraperIntegrationService()._apply_category_mapping(session, scraped)

    # «Тормозные диски» в этой базе нет — ближайший родитель.
    assert scraped.category == "brake-system"


def test_second_pass_skips_cards_with_same_sitemap_date(auto_parts_session):
    """Дата изменения в карте сайта та же — карточка не открывается (ListingGuard)."""
    from apps.scrapers.base.listing_snapshot import ListingGuard

    session, service = auto_parts_session
    url = f"{SITEMAP}?brand=bosch&q=lambda"
    parser = _parser()
    parser.max_products = None
    parser.listing_guard = ListingGuard("aloparca")
    for scraped in parser.parse_product_list(url, max_pages=2):
        service._process_scraped_products(session, [scraped])
    assert ListingSnapshot.objects.filter(parser_key="aloparca").count() == 1

    second = _parser()
    second.max_products = None
    second.listing_guard = ListingGuard("aloparca")
    assert list(second.parse_product_list(url, max_pages=2)) == []
    assert second.requested == ["/sitemaps/products-1.xml"] and second.listing_guard.unchanged == 1
