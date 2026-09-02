import json
from decimal import Decimal

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.scrapers.base.scraper import ScrapedProduct, ScraperAccessBlockedError
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser, IlacFiyatiSourceError


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
    assert product.currency == "TRY"
    assert product.is_available is False
    assert product.stock_quantity is None
    assert product.analogs == []
    assert product.analog_fetch_errors == 1


def test_ilacfiyati_parser_preserves_eur_price_from_turkish_dotted_label(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    product_url = "https://ilacfiyati.com/ilaclar/iclusig-45-mg-30-tablet"
    html = """
        <html><body><h1>ICLUSIG 45 MG 30 TABLET</h1>
        <table><tr><td>İLAÇ FİYATI</td><td>4.200,00 €</td></tr></table>
        </body></html>
    """
    monkeypatch.setattr(parser, "_make_request", lambda _url: html)

    product = parser.parse_product_detail(
        product_url,
        include_detail_tabs=False,
        include_analogs=False,
    )

    assert product.price == Decimal("4200.00")
    assert product.currency == "EUR"


def test_ilacfiyati_parser_marks_zero_source_price_as_unpublished(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    product_url = "https://ilacfiyati.com/ilaclar/ponatinix-15-tablet"
    html = """
        <html><body><h1>PONATINIX 15 TABLET</h1>
        <table><tr><td>İLAÇ FİYATI</td><td>0,00 TL</td></tr></table>
        </body></html>
    """
    monkeypatch.setattr(parser, "_make_request", lambda _url: html)

    product = parser.parse_product_detail(
        product_url,
        include_detail_tabs=False,
        include_analogs=False,
    )

    assert product.price is None
    assert product.currency == "TRY"
    assert product.price_unpublished is True


def test_ilacfiyati_parser_reads_zero_price_from_current_card_layout(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    product_url = "https://ilacfiyati.com/ilaclar/ponatinix-15-tablet"
    html = """
        <html><body>
        <h1 class="fs-2x">37 Binden Fazla İlaç ve Ürün Bilgisi</h1>
        <h1 class="page-title text-primary">PONATINIX 15 TABLET</h1>
        <div class="info-card">
          <p class="info-card__label">İlaç Fiyatı</p>
          <p class="info-card__value text-truncate" title="0,00 TL">0,00 TL</p>
        </div>
        </body></html>
    """
    monkeypatch.setattr(parser, "_make_request", lambda _url: html)

    product = parser.parse_product_detail(
        product_url,
        include_detail_tabs=False,
        include_analogs=False,
    )

    assert product.name == "PONATINIX 15 TABLET"
    assert product.price is None
    assert product.currency == "TRY"
    assert product.price_unpublished is True


def test_ilacfiyati_parser_reads_eur_price_from_current_card_layout(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    product_url = "https://ilacfiyati.com/ilaclar/iclusig-45-mg-30-tablet"
    html = """
        <html><body>
        <h1 class="page-title">ICLUSIG 45 MG 30 TABLET</h1>
        <div class="price-card price-card--main-price">
          <div class="price-card-label">İlaç Fiyatı</div>
          <div class="price-card-value">4.200,00 €</div>
        </div>
        </body></html>
    """
    monkeypatch.setattr(parser, "_make_request", lambda _url: html)

    product = parser.parse_product_detail(
        product_url,
        include_detail_tabs=False,
        include_analogs=False,
    )

    assert product.price == Decimal("4200.00")
    assert product.currency == "EUR"
    assert product.price_unpublished is False


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
