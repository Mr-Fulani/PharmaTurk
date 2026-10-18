import json
from pathlib import Path

import pytest
from curl_cffi import requests as curl_requests

from apps.catalog.models import Category
from apps.scrapers.base.offers import OfferGone
from apps.scrapers.base.scraper import ScraperAccessBlockedError
from apps.scrapers.models import ScraperConfig, ScrapingSession
from apps.scrapers.parsers import inditex
from apps.scrapers.parsers.bershka import BershkaParser
from apps.scrapers.parsers.massimodutti import MassimoDuttiParser
from apps.scrapers.parsers.pullandbear import PullAndBearParser
from apps.scrapers.services import ScraperIntegrationService

from apps.scrapers.test_zara_parser import _Session

FIXTURES = Path(__file__).parent / "test_fixtures" / "inditex"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class _Response:
    def __init__(self, text, status_code=200, url=""):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = {}


class _FakeSession:
    """Отдаёт ответы по подстроке URL; записывает запросы."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append(url)
        for marker, responses in self.routes:
            if marker in url:
                response = responses.pop(0) if len(responses) > 1 else responses[0]
                return _Response(response[1], response[0], url)
        raise AssertionError(f"unexpected request {url}")

    def close(self):
        return None


def _parser(parser_class, routes, monkeypatch):
    parser = parser_class()
    parser.ajax_session.close()
    parser.ajax_session = _FakeSession(routes)
    parser.max_retries = 0
    monkeypatch.setattr(parser, "_wait_before_ajax_request", lambda: None)
    monkeypatch.setattr(inditex.time, "sleep", lambda seconds: None)
    return parser


def _routes(**extra):
    # Первым совпавшим маркером выигрывают переданные маршруты, затем общие.
    return list(extra.items()) + [
        ("bershka.com/tr/", [(200, "<html>home</html>")]),
        ("pullandbear.com/tr/", [(200, "<html>home</html>")]),
        ("/itxrest/2/catalog/store/44109521?", [(200, _fixture("bershka_store.json"))]),
        ("/itxrest/2/catalog/store/25009521?", [(200, _fixture("bershka_store.json"))]),
    ]


def test_bershka_detail_from_itxrest_fixture(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{"/product/228309045/detail": [(200, _fixture("bershka_product_detail.json"))]}),
        monkeypatch,
    )

    product = parser.parse_product_detail(
        "https://www.bershka.com/tr/k%C4%B1sa-kollu-bask%C4%B1l%C4%B1-boxy-fit-ti%C5%9F%C3%B6rt"
        "-c0p228309045.html?colorId=403"
    )

    assert product.name == "Kısa kollu baskılı boxy fit tişört"
    assert product.external_id == "bershka-228309045"
    assert product.source == "bershka"
    assert product.brand == "Bershka"
    assert product.price == 950.0
    assert product.currency == "TRY"
    assert product.category == "T-Shirtler"
    assert product.attributes["gender"] == "men"
    assert product.url == (
        "https://www.bershka.com/tr/k%C4%B1sa-kollu-bask%C4%B1l%C4%B1-boxy-fit-tisort"
        "-c0p228309045.html"
    )
    variants = product.attributes["fashion_variants"]
    assert [v["external_id"] for v in variants] == [
        "bershka-variant-228309045-403",
        "bershka-variant-228309045-902",
    ]
    first = variants[0]
    assert first["color"] == "Açık mavi"
    assert [(s["size"], s["is_available"]) for s in first["sizes"]] == [
        ("XS", False), ("S", True), ("M", True), ("L", False), ("XL", False),
    ]
    # Галерея — location 1 в порядке сайта, без служебного ховер-кадра r1.
    assert [url.split("/")[-1].split("?")[0] for url in first["images"]] == [
        "03249734403-p.jpg",
        "03249734403-a1t.jpg",
        "03249734403-a2d.jpg",
        "03249734403-a3o.jpg",
        "03249734403-a4o.jpg",
        "03249734403-b.jpg",
    ]
    assert product.images == first["images"]
    assert product.is_available is True
    # Запросы: прогрев, каталог магазина, карточка — HTML карточки не нужен.
    assert len(parser.ajax_session.requests) == 3


def test_pullandbear_detail_keeps_pelement_url_and_description(monkeypatch):
    parser = _parser(
        PullAndBearParser,
        _routes(**{"/product/752040619/detail": [(200, _fixture("pullandbear_product_detail.json"))]}),
        monkeypatch,
    )

    product = parser.parse_product_detail(
        "https://www.pullandbear.com/tr/stwd-logolu-boxy-tisort-l03233901?cS=809&pelement=752040619"
    )

    assert product.url == (
        "https://www.pullandbear.com/tr/stwd-logolu-boxy-tisort-l03233901?pelement=752040619"
    )
    assert product.external_id == "pullandbear-752040619"
    assert product.price == 1090.0
    assert product.description.startswith("STWD logolu")
    assert len(product.attributes["fashion_variants"]) == 2
    assert all(v["images"] for v in product.attributes["fashion_variants"])


def test_akamai_interstitial_is_passed_by_following_refresh(monkeypatch):
    interstitial = _fixture("akamai_interstitial.html")
    sleeps = []
    parser = _parser(
        BershkaParser,
        _routes(**{
            "/tr/?bm-verify=": [(200, "<html>home</html>")],
            "bershka.com/tr/": [(200, interstitial)],
            "/product/228309045/detail": [(200, _fixture("bershka_product_detail.json"))],
        }),
        monkeypatch,
    )
    monkeypatch.setattr(inditex.time, "sleep", sleeps.append)

    product = parser.parse_product_detail("https://www.bershka.com/tr/x-c0p228309045.html")

    assert product is not None
    assert sleeps == [5.5]
    assert parser.ajax_session.requests[1].startswith("https://www.bershka.com/tr/?bm-verify=")


def test_unsolved_akamai_interstitial_is_explicit_access_error(monkeypatch):
    parser = _parser(
        BershkaParser,
        [("bershka.com", [(200, _fixture("akamai_interstitial.html"))])],
        monkeypatch,
    )

    with pytest.raises(ScraperAccessBlockedError, match="bm-verify"):
        parser.parse_product_detail("https://www.bershka.com/tr/x-c0p228309045.html")


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(403, ScraperAccessBlockedError), (402, ScraperAccessBlockedError), (410, OfferGone)],
)
def test_itxrest_status_codes_map_to_typed_errors(monkeypatch, status_code, expected):
    parser = _parser(
        BershkaParser,
        _routes(**{"/product/228309045/detail": [(status_code, "")]}),
        monkeypatch,
    )

    with pytest.raises(expected):
        parser.parse_product_detail("https://www.bershka.com/tr/x-c0p228309045.html")


def test_category_listing_pages_product_ids_through_products_array(monkeypatch):
    product = json.loads(_fixture("bershka_product_detail.json"))
    products_array = []
    for product_id in ("231041613", "230329907", "230330375"):
        row = dict(product, id=int(product_id))
        products_array.append(row)
    parser = _parser(
        BershkaParser,
        _routes(**{
            "/category/1010193239/product": [(200, _fixture("bershka_category_products.json"))],
            "productIds=231041613%2C230329907": [
                (200, json.dumps({"products": products_array[:2]}, ensure_ascii=False))
            ],
            "productIds=230330375": [
                (200, json.dumps({"products": products_array[2:]}, ensure_ascii=False))
            ],
        }),
        monkeypatch,
    )
    parser.API_PAGE_SIZE = 2
    url = "https://www.bershka.com/tr/erkek/giyim/t-shirt-n3294.html?celement=1010193239"

    first_page = list(parser.parse_product_list(url, max_pages=1, start_page=1))
    assert [p.external_id for p in first_page] == ["bershka-231041613", "bershka-230329907"]
    assert parser.has_more_pages is True

    second_page = list(parser.parse_product_list(url, max_pages=1, start_page=2))
    assert [p.external_id for p in second_page] == ["bershka-230330375"]
    assert parser.has_more_pages is False


@pytest.mark.parametrize(
    ("parser_class", "html", "expected"),
    [
        (
            PullAndBearParser,
            "<script>inditex.iStoreId = 25009521; inditex.iCategoryId = 1030204792;</script>",
            "1030204792",
        ),
        (
            MassimoDuttiParser,
            '<script id="mdfrontw-state">{"iCategoryId":"2028560","categoryId":"1842525"}</script>',
            "2028560",
        ),
        (
            BershkaParser,
            '<link rel="canonical" href="https://www.bershka.com/tr/erkek/giyim/t-shirt-n3294.html'
            '?celement=1010193239"><a href="/tr/x-n1.html?celement=1010835578">',
            "1010193239",
        ),
    ],
)
def test_category_id_is_read_from_category_page(monkeypatch, parser_class, html, expected):
    parser = _parser(parser_class, [("-n", [(200, html)])], monkeypatch)
    host = parser.WARMUP_URL.rstrip("/")

    assert parser._category_id_from_url(f"{host}/erkek/x-n6323") == expected


def test_category_without_id_reports_clear_error(monkeypatch):
    parser = _parser(PullAndBearParser, [("-n", [(200, "<html></html>")])], monkeypatch)

    with pytest.raises(Exception, match="id категории"):
        list(parser.parse_product_list("https://www.pullandbear.com/tr/erkek/x-n6323"))


@pytest.mark.django_db
def test_removed_source_item_does_not_mark_scraper_as_broken(monkeypatch):
    category = Category.objects.create(name="Zara test", slug="zara-test")
    config = ScraperConfig.objects.create(
        name="Zara-test",
        parser_class="zara",
        base_url="https://www.zara.com/tr/",
        default_category=category,
    )

    def gone(*args, **kwargs):
        raise OfferGone("https://www.zara.com/tr/tr/x-p02727401.html?ajax=true")

    monkeypatch.setattr(ScraperIntegrationService, "_run_parser_scraping", gone)

    with pytest.raises(OfferGone):
        ScraperIntegrationService().run_scraper(
            config, start_url="https://www.zara.com/tr/tr/x-p02727401.html", max_products=1,
        )

    config.refresh_from_db()
    session = ScrapingSession.objects.get(scraper_config=config)
    assert config.status == "active"
    assert config.last_error_message == ""
    assert config.total_runs == 1
    assert session.status == "failed"
    assert "снята у источника" in session.error_message


@pytest.mark.parametrize(
    ("parser", "url"),
    [
        (
            MassimoDuttiParser(),
            "https://www.massimodutti.com/tr/keten-tshirt-l00648198?pelement=61733884",
        ),
        (BershkaParser(), "https://www.bershka.com/tr/tshirt-c0p123456789.html"),
        (PullAndBearParser(), "https://www.pullandbear.com/tr/tshirt-c0p123456789.html"),
    ],
)
def test_service_routes_inditex_single_product_to_detail(monkeypatch, parser, url):
    calls = []
    monkeypatch.setattr(parser, "parse_product_detail", lambda value: calls.append(value))
    monkeypatch.setattr(
        parser,
        "parse_product_list",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("list path used")),
    )

    products, incremental = ScraperIntegrationService()._run_parser_scraping(
        parser, _Session(), url
    )

    assert products == []
    assert incremental is None
    assert calls == [url]


@pytest.mark.parametrize("parser_class", [BershkaParser, PullAndBearParser, MassimoDuttiParser])
def test_inditex_category_url_supports_chunking(parser_class):
    url = f"https://www.{parser_class().get_name()}.com/tr/erkek-tshirt-n6323"
    assert parser_class.is_category_url(url)
    assert parser_class.supports_page_chunking_for_url(url)


@pytest.mark.parametrize("parser_class", [BershkaParser, PullAndBearParser, MassimoDuttiParser])
def test_inditex_category_links_extract_external_id(parser_class):
    parser = parser_class()
    try:
        base_url = f"https://www.{parser.get_name()}.com/tr/"
        html = (
            '<a href="/tr/erkek-tshirt-n6323">Tişört</a>'
            '<a href="/tr/kadin-elbise-n1234.html">Elbise</a>'
            '<a href="/tr/erkek-tshirt-c0p123456789.html">Ürün</a>'
        )

        categories = parser._extract_category_links(html, base_url)

        assert [(item["url"], item["external_id"]) for item in categories] == [
            (f"{base_url}erkek-tshirt-n6323", "6323"),
            (f"{base_url}kadin-elbise-n1234.html", "1234"),
        ]
    finally:
        parser.__exit__(None, None, None)


@pytest.mark.parametrize("parser_class", [BershkaParser, PullAndBearParser, MassimoDuttiParser])
def test_inditex_siblings_use_browser_fingerprint_transport(parser_class):
    parser = parser_class()
    try:
        assert isinstance(parser.ajax_session, curl_requests.Session)
        assert parser.ajax_session.impersonate == "chrome"
    finally:
        parser.__exit__(None, None, None)


def test_scraper_config_identity_reaches_inditex_transport():
    parser = BershkaParser()
    try:
        parser.configure_request_identity(
            user_agent="Configured Chrome UA",
            headers={"X-Test-Header": "configured"},
            cookies={"session": "configured-cookie"},
        )

        assert parser.ajax_session.headers["User-Agent"] == "Configured Chrome UA"
        assert parser.ajax_session.headers["X-Test-Header"] == "configured"
        assert parser.ajax_session.cookies.get("session") == "configured-cookie"
        assert parser.client.headers["User-Agent"] == "Configured Chrome UA"
    finally:
        parser.__exit__(None, None, None)
