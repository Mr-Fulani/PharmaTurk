import json
from decimal import Decimal

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.scrapers.base.scraper import ScrapedProduct, ScraperAccessBlockedError
from apps.scrapers.base.catalog_state import CatalogTraversalState
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser, IlacFiyatiSourceError


IMMUNITY_URL = "https://ilacfiyati.com/takviye-edici-gida/bagisiklik-destek-urunleri"
SUPPLEMENT_URL = "https://ilacfiyati.com/takviye-edici-gida/supradyn-multivitamin-mineral-ve-koenzim-q10-iceren-takviye-edici-gida-30-tablet"


def _supplement_listing_html(product_urls, next_page=2):
    # Structure verified in the live immunity category on 2026-09-14.
    cards = "".join(
        f'<div class="card h-100"><a href="{url}">Image</a>'
        f'<div class="card-body"><a href="{url}">Product</a></div></div>'
        for url in product_urls
    )
    return f'''<html><body>
      <div class="dropdown-menu"><a href="{IMMUNITY_URL}">Immunity</a></div>
      <div id="filterContent">
        <a href="/takviye-edici-gida/antioksidanlar">Antioxidants</a>
        <a href="/takviye-edici-gida/new-category">New category</a>
      </div>
      <div class="row g-3 mt-4"><h2>Arama Sonuçları</h2>{cards}
        <ul class="pagination"><li><a href="{IMMUNITY_URL}?pg={next_page}">{next_page}</a></li></ul>
      </div>
      <footer><a href="/ilaclar/unrelated-drug">Unrelated</a></footer>
    </body></html>'''


@pytest.mark.parametrize("url", [
    IMMUNITY_URL,
    IMMUNITY_URL + "/?brand=Solgar&pg=2",
    "https://www.ilacfiyati.com/takviye-edici-gida/antioksidanlar",
    "https://ilacfiyati.com/takviye-edici-gida/probiyotikler",
    "https://ilacfiyati.com/takviye-edici-gida/kadin-sagligi",
    "https://ilacfiyati.com/takviye-edici-gida",
    "https://ilacfiyati.com/ilaclar?brand=Rinvoq",
])
def test_ilacfiyati_catalog_routes_and_chunking(url):
    assert IlacFiyatiParser.is_category_url(url)
    assert IlacFiyatiParser.supports_page_chunking_for_url(url)
    assert not IlacFiyatiParser.is_product_url(url)


@pytest.mark.parametrize("url", [
    SUPPLEMENT_URL,
    SUPPLEMENT_URL + "/ozet?utm_source=catalog",
    "https://ilacfiyati.com/takviye-edici-gida/solgar-vitamin-c",
    "https://ilacfiyati.com/ilaclar/lasirin-20-mg/ilac-bilgileri",
])
def test_ilacfiyati_direct_product_routes_remain_unchanged(url):
    assert IlacFiyatiParser.is_product_url(url)
    assert not IlacFiyatiParser.is_category_url(url)
    assert not IlacFiyatiParser.supports_page_chunking_for_url(url)


@pytest.mark.parametrize("url", [
    "https://example.com/takviye-edici-gida/bagisiklik-destek-urunleri",
    "https://ilacfiyati.com.evil.example/ilaclar/medicine",
])
def test_ilacfiyati_url_detection_rejects_other_hosts(url):
    assert not IlacFiyatiParser.is_product_url(url)
    assert not IlacFiyatiParser.is_category_url(url)


def test_ilacfiyati_listing_excludes_category_menu_and_duplicate_links():
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    html = _supplement_listing_html([SUPPLEMENT_URL, SUPPLEMENT_URL + "?utm_source=card"])
    assert parser._extract_listing_product_urls(html) == [SUPPLEMENT_URL]
    # An empty modern listing must not fall back to navigation links.
    assert parser._extract_listing_product_urls(_supplement_listing_html([])) == []


def test_ilacfiyati_legacy_listing_keeps_products_and_excludes_categories():
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    html = f'''
      <a href="{IMMUNITY_URL}">Immunity</a>
      <a href="/ilaclar/first-drug">First</a>
      <a href="/ilaclar/first-drug/ilac-bilgileri">Details</a>
      <a href="{SUPPLEMENT_URL}">Supplement</a>
      <a href="https://example.com/ilaclar/wrong-host">Other</a>
    '''
    assert parser._extract_listing_product_urls(html) == [
        "https://ilacfiyati.com/ilaclar/first-drug", SUPPLEMENT_URL,
    ]


def test_ilacfiyati_immunity_subcatalog_keeps_filters_and_stops_on_empty_page(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    url = IMMUNITY_URL + "?brand=Solgar"
    second_product = "https://ilacfiyati.com/takviye-edici-gida/solgar-vitamin-c"
    pages = {
        url: _supplement_listing_html([SUPPLEMENT_URL]),
        url + "&pg=2": _supplement_listing_html([second_product], next_page=3),
        url + "&pg=3": _supplement_listing_html([]),
    }
    requests, details = [], []

    def fetch(page_url):
        requests.append(page_url)
        return pages[page_url]

    def detail(product_url):
        details.append(product_url)
        return ScrapedProduct(name="Supplement", url=product_url, source="ilacfiyati")

    monkeypatch.setattr(parser, "_make_request", fetch)
    monkeypatch.setattr(parser, "parse_product_detail", detail)
    assert len(list(parser.parse_product_list(url, max_pages=10))) == 2
    assert details == [SUPPLEMENT_URL, second_product]
    assert requests == list(pages)
    assert parser.pages_processed == 2
    assert parser.has_more_pages is False


def test_ilacfiyati_supplement_remaining_limit_does_not_reload_duplicates(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    parser.max_products = 2
    parser.catalog_state = CatalogTraversalState()
    parser.catalog_state.mark_product(SUPPLEMENT_URL)
    second = "https://ilacfiyati.com/takviye-edici-gida/solgar-vitamin-c"
    third = "https://ilacfiyati.com/takviye-edici-gida/solgar-vitamin-d"
    fourth = "https://ilacfiyati.com/takviye-edici-gida/solgar-vitamin-e"
    html = _supplement_listing_html([SUPPLEMENT_URL, second, third, fourth])
    loaded = []
    monkeypatch.setattr(parser, "_make_request", lambda url: html)

    def detail(url):
        loaded.append(url)
        return ScrapedProduct(name="Supplement", url=url, source="ilacfiyati")

    monkeypatch.setattr(parser, "parse_product_detail", detail)
    assert len(list(parser.parse_product_list(IMMUNITY_URL))) == 2
    assert loaded == [second, third]
    assert parser.catalog_skipped == 1
    assert parser.has_more_pages is False


def test_ilacfiyati_explicit_last_page_does_not_fetch_another_page(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    loaded = []

    def fetch(url):
        loaded.append(url)
        assert url == IMMUNITY_URL
        return _supplement_listing_html([SUPPLEMENT_URL], next_page=1)

    monkeypatch.setattr(parser, "_make_request", fetch)
    monkeypatch.setattr(parser, "parse_product_detail", lambda url: ScrapedProduct(
        name="Supplement", url=url, source="ilacfiyati",
    ))
    assert len(list(parser.parse_product_list(IMMUNITY_URL, max_pages=10))) == 1
    assert loaded == [IMMUNITY_URL]
    assert parser.has_more_pages is False


@pytest.mark.parametrize("url,is_listing", [(IMMUNITY_URL, True), (SUPPLEMENT_URL, False)])
def test_ilacfiyati_service_distinguishes_subcatalog_from_direct_product(monkeypatch, url, is_listing):
    from types import SimpleNamespace
    from apps.scrapers.services import ScraperIntegrationService

    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    product = ScrapedProduct(name="Supplement", url=SUPPLEMENT_URL, source="ilacfiyati")
    calls = []

    def listing(page_url, **kwargs):
        calls.append(("listing", page_url, kwargs))
        return iter([product])

    monkeypatch.setattr(parser, "parse_product_list", listing)
    monkeypatch.setattr(parser, "parse_product_detail", lambda u: calls.append(("detail", u)) or product)
    session = SimpleNamespace(max_pages=1, max_products=10, pages_processed=0, errors_count=0, save=lambda: None)
    service = ScraperIntegrationService()
    monkeypatch.setattr(service, "_process_scraped_products", lambda *args: {
        "found": 1, "created": 1, "updated": 0, "skipped": 0, "errors": 0,
    })

    products, results = service._run_parser_scraping(parser, session, url, start_page=2)
    if is_listing:
        assert calls == [("listing", url, {"max_pages": 1, "start_page": 2})]
        assert products == []
        assert results["found"] == 1
    else:
        assert calls == [("detail", url)]
        assert products == [product]
        assert results is None


def test_ilacfiyati_market_snapshot_skips_instruction_tabs(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    captured = {}
    expected = ScrapedProduct(name="LASIRIN", price=100, currency="TRY")

    def fake_detail(
        url,
        *,
        include_detail_tabs,
        include_analogs,
        tolerate_analog_errors,
        preserve_transport_errors,
    ):
        captured.update(
            url=url,
            include_detail_tabs=include_detail_tabs,
            include_analogs=include_analogs,
            tolerate_analog_errors=tolerate_analog_errors,
            preserve_transport_errors=preserve_transport_errors,
        )
        return expected

    monkeypatch.setattr(parser, "parse_product_detail", fake_detail)

    result = parser.parse_market_snapshot(
        "https://ilacfiyati.com/ilaclar/lasirin-20-mg/ilac-bilgileri"
    )

    assert result is expected
    assert captured == {
        "url": "https://ilacfiyati.com/ilaclar/lasirin-20-mg",
        "include_detail_tabs": False,
        "include_analogs": True,
        "tolerate_analog_errors": True,
        "preserve_transport_errors": True,
    }


def test_ilacfiyati_supplement_market_snapshot_does_not_fetch_medicine_equivalents(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    captured = {}

    def fake_detail(
        url,
        *,
        include_detail_tabs,
        include_analogs,
        tolerate_analog_errors,
        preserve_transport_errors,
    ):
        captured.update(
            url=url,
            include_detail_tabs=include_detail_tabs,
            include_analogs=include_analogs,
            tolerate_analog_errors=tolerate_analog_errors,
            preserve_transport_errors=preserve_transport_errors,
        )
        return ScrapedProduct(name="VITAMIN C", price=50, currency="TRY")

    monkeypatch.setattr(parser, "parse_product_detail", fake_detail)

    parser.parse_market_snapshot("https://ilacfiyati.com/takviye-edici-gida/vitamin-c/ozet")

    assert captured == {
        "url": "https://ilacfiyati.com/takviye-edici-gida/vitamin-c",
        "include_detail_tabs": False,
        "include_analogs": False,
        "tolerate_analog_errors": True,
        "preserve_transport_errors": True,
    }


def test_ilacfiyati_market_snapshot_keeps_price_when_optional_analog_tab_fails(
    monkeypatch,
):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    product_url = "https://ilacfiyati.com/ilaclar/lasirin-20-mg"
    responses = {
        product_url: """
            <html><body><h1>LASIRIN 20 MG</h1>
            <table><tr><td>İLAÇ FİYATI</td><td>125,45 TL</td></tr></table>
            </body></html>
        """,
        f"{product_url}/esdegeri": ScraperAccessBlockedError("HTTP 403"),
        f"{product_url}/sgk-esdegeri": "<html><body></body></html>",
    }

    def fake_request(url):
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(parser, "_make_request", fake_request)

    product = parser.parse_market_snapshot(product_url)

    assert product.price == Decimal("125.45")
    assert product.is_available is False
    assert product.stock_quantity is None
    assert product.analogs == []
    assert product.analog_fetch_errors == 1


def test_ilacfiyati_parser_fetches_instruction_tabs(monkeypatch):
    base_url = "https://ilacfiyati.com"
    product_url = f"{base_url}/ilaclar/zovirax-5-krem-2-gr"
    parser = IlacFiyatiParser(base_url=base_url)

    main_html = """
    <html><head><meta property="og:image" content="/img/zovirax.png"></head><body>
      <h1>ZOVIRAX %5 KREM (2 GR)</h1>
      <table>
        <tr><td>İLAÇ FİYATI</td><td>152,62 TL</td></tr>
        <tr><td>FİRMA ADI</td><td>Glaxosmithkline İlaçları San. Ve Tic. A.Ş.</td></tr>
        <tr><td>BARKOD</td><td>8699522352692</td></tr>
        <tr><td>ETKİN MADDE</td><td>Asiklovir</td></tr>
        <tr><td>ATC KODU</td><td>D06BB03</td></tr>
        <tr><td>FORMU</td><td>Dermatolojik Krem</td></tr>
        <tr><td>UYGULAMA YOLU</td><td>Topikal</td></tr>
        <tr><td>RAF ÖMRÜ</td><td>24 Ay</td></tr>
        <tr><td>REÇETE</td><td>Beyaz Reçete</td></tr>
      </table>
    </body></html>
    """
    tab_pages = {
        "ozet": "<h3>ZOVİRAX KREM %5 KULLANMA TALİMATI</h3><p>Cilt üzerine uygulanır.</p>",
        "ne-icin-kullanilir": "<h3>1. ZOVİRAX NEDİR VE NE İÇİN KULLANILIR?</h3><p>ZOVİRAX, antiviral bir ilaçtır.</p>",
        "kullanmadan-dikkat-edilecekler": "<h3>2. ZOVİRAX'I KULLANMADAN ÖNCE DİKKAT EDİLMESİ GEREKENLER</h3><p>Asiklovire alerjiniz varsa kullanmayınız.</p>",
        "nasil-kullanilir": "<h3>3. ZOVİRAX NASIL KULLANILIR?</h3><p>Doktorunuzun söylediği şekilde kullanınız.</p>",
        "yan-etkileri": "<h3>4. OLASI YAN ETKİLER NELERDİR?</h3><p>Kaşıntı görülebilir.</p>",
        "saklanmasi": "<h3>5. ZOVİRAX'IN SAKLANMASI</h3><p>25°C altındaki oda sıcaklığında saklayınız.</p>",
        "ilac-bilgileri": "<h3>İLAÇ BİLGİLERİ</h3><p>BARKOD 8699522352692</p>",
        "esdegeri": """
          <h3>EŞDEĞERİ</h3>
          <table>
            <tr>
              <td><a href="/ilaclar/asiviral-400-mg-25-tablet">ASIVIRAL 400 MG 25 TABLET</a></td>
              <td>Barkod: 8699546090114</td>
              <td>ATC Kodu: D06BB03</td>
              <td>SGK Eşdeğer Kodu: E007D</td>
            </tr>
          </table>
        """,
        "sgk-esdegeri": """
          <h3>SGK EŞDEĞERİ</h3>
          <table>
            <tr>
              <td><a href="/ilaclar/asiviral-400-mg-25-tablet">ASIVIRAL 400 MG 25 TABLET</a></td>
              <td>SGK Eşdeğer Kodu: E007D</td>
            </tr>
          </table>
        """,
    }

    responses = {product_url: main_html}
    responses.update(
        {
            f"{product_url}/{path}": f"<html><body>{html}<h6>İlaç Katılım Payı Hesaplama</h6></body></html>"
            for path, html in tab_pages.items()
        }
    )

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(parser, "_make_request", lambda url: responses.get(url.rstrip("/"), ""))

    product = parser.parse_product_detail(product_url)

    assert product is not None
    assert product.name == "ZOVIRAX %5 KREM (2 GR)"
    assert "Özet:" in product.description
    assert "Ne İçin Kullanılır:" in product.description
    assert "Kullanmadan Dikkat Edilecekler:" in product.description
    assert "Nasıl Kullanılır:" in product.description
    assert "Yan Etkileri:" in product.description
    assert "Saklanması:" in product.description
    assert product.attributes["source_tabs"]["indications"]["text"].startswith("1. ZOVİRAX")
    assert "Doktorunuzun söylediği" in product.attributes["usage_instructions_source"]
    assert "Kaşıntı görülebilir" in product.attributes["side_effects_source"]
    assert "25°C" in product.attributes["storage_conditions_source"]
    assert product.analogs == [
        {
            "name": "ASIVIRAL 400 MG 25 TABLET",
            "url": "https://ilacfiyati.com/ilaclar/asiviral-400-mg-25-tablet",
            "price": None,
            "external_id": "asiviral-400-mg-25-tablet",
            "source_tab": "Eşdeğeri, SGK Eşdeğeri",
            "barcode": "8699546090114",
            "atc_code": "D06BB03",
            "sgk_equivalent_code": "E007D",
        }
    ]
    assert product.analog_fetch_errors == 0


def test_ilacfiyati_parser_uses_product_slug_as_external_id_for_tab_urls():
    base_url = "https://ilacfiyati.com"
    tab_url = f"{base_url}/ilaclar/lasirin-20-mg-tablet-20-tablet/ilac-bilgileri"
    parser = IlacFiyatiParser(base_url=base_url)

    assert parser._extract_external_id_from_url(tab_url) == "lasirin-20-mg-tablet-20-tablet"


def test_scraped_product_to_dict_is_json_serializable_with_decimal_analogs(monkeypatch):
    base_url = "https://ilacfiyati.com"
    product_url = f"{base_url}/ilaclar/zovirax-5-krem-2-gr"
    parser = IlacFiyatiParser(base_url=base_url)

    main_html = """
    <html><body>
      <h1>ZOVIRAX %5 KREM (2 GR)</h1>
      <table>
        <tr><td>İLAÇ FİYATI</td><td>152,62 TL</td></tr>
      </table>
    </body></html>
    """
    analog_tab_html = """
      <h3>EŞDEĞERİ</h3>
      <table>
        <tr>
          <td><a href="/ilaclar/asiviral-400-mg-25-tablet">ASIVIRAL 400 MG 25 TABLET</a></td>
          <td>Fiyat: 125,45 TL</td>
        </tr>
      </table>
    """
    responses = {
        product_url: main_html,
        f"{product_url}/esdegeri": f"<html><body>{analog_tab_html}</body></html>",
        f"{product_url}/sgk-esdegeri": "",
    }

    for path in (
        "ilac-bilgileri",
        "ozet",
        "ne-icin-kullanilir",
        "kullanmadan-dikkat-edilecekler",
        "nasil-kullanilir",
        "yan-etkileri",
        "saklanmasi",
    ):
        responses[f"{product_url}/{path}"] = "<html><body></body></html>"

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(parser, "_make_request", lambda url: responses.get(url.rstrip("/"), ""))

    product = parser.parse_product_detail(product_url)

    assert product is not None
    assert product.analogs[0]["price"] == Decimal("125.45")
    assert json.dumps(product.to_dict())


def test_ilacfiyati_listing_page_url_preserves_filters():
    url = "https://ilacfiyati.com/ilaclar?brand=Rinvoq&status=active"

    assert IlacFiyatiParser._listing_page_url(url, 1) == url
    assert (
        IlacFiyatiParser._listing_page_url(url, 2)
        == "https://ilacfiyati.com/ilaclar?brand=Rinvoq&status=active&pg=2"
    )
    assert (
        IlacFiyatiParser._listing_page_url(f"{url}&pg=7", 3)
        == "https://ilacfiyati.com/ilaclar?brand=Rinvoq&status=active&pg=3"
    )


def test_ilacfiyati_filtered_catalog_reports_exact_page_progress(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    category_url = "https://ilacfiyati.com/ilaclar?brand=Rinvoq"
    requested = []
    pages = {
        category_url: '<a href="/ilaclar/rinvoq-15-mg-28-tablet">Rinvoq 15</a>',
        f"{category_url}&pg=2": '<a href="/ilaclar/rinvoq-30-mg-28-tablet">Rinvoq 30</a>',
    }

    def fake_request(url):
        requested.append(url)
        return pages[url]

    monkeypatch.setattr(parser, "_make_request", fake_request)
    monkeypatch.setattr(
        parser,
        "parse_product_detail",
        lambda url: ScrapedProduct(name="RINVOQ", url=url, source="ilacfiyati"),
    )

    products = list(parser.parse_product_list(category_url, max_pages=1, start_page=2))

    assert len(products) == 1
    assert requested[:2] == [category_url, f"{category_url}&pg=2"]
    assert parser.pages_processed == 1
    assert parser.next_start_page == 3
    assert parser.has_more_pages is True


def test_ilacfiyati_empty_filtered_page_explains_zero_result(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    category_url = "https://ilacfiyati.com/ilaclar?brand=Rinvoq"
    pages = {
        category_url: '<a href="/ilaclar/rinvoq-15-mg-28-tablet">Rinvoq</a>',
        f"{category_url}&pg=2": "<html><body>no products</body></html>",
    }
    monkeypatch.setattr(parser, "_make_request", lambda url: pages[url])

    assert list(parser.parse_product_list(category_url, max_pages=1, start_page=2)) == []
    assert parser.pages_processed == 0
    assert parser.has_more_pages is False
    assert "странице 2" in parser.stop_reason
    assert "товары не найдены" in parser.stop_reason


def test_ilacfiyati_soft_timeout_keeps_current_page_as_resume_cursor(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    category_url = "https://ilacfiyati.com/ilaclar"
    page_html = """
      <a href="/ilaclar/first-drug">First</a>
      <a href="/ilaclar/second-drug">Second</a>
    """
    monkeypatch.setattr(parser, "_make_request", lambda _url: page_html)

    def parse_detail(url):
        if url.endswith("second-drug"):
            raise SoftTimeLimitExceeded()
        return ScrapedProduct(name="FIRST", url=url, source="ilacfiyati")

    monkeypatch.setattr(parser, "parse_product_detail", parse_detail)

    with pytest.raises(SoftTimeLimitExceeded):
        list(parser.parse_product_list(category_url, max_pages=1, start_page=1))

    assert parser.pages_processed == 0
    assert parser.next_start_page == 1


def test_ilacfiyati_invalid_detail_page_is_not_silent_success(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    monkeypatch.setattr(parser, "_make_request", lambda _url: "<html><body>blocked</body></html>")

    with pytest.raises(IlacFiyatiSourceError, match="название препарата не найдено"):
        parser.parse_product_detail("https://ilacfiyati.com/ilaclar/missing")
