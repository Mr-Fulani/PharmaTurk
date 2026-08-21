import json
from decimal import Decimal

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser, IlacFiyatiSourceError


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
