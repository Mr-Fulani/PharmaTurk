"""Regression coverage for IlacFiyati's inline detail layout."""
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup

from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser

URL = "https://ilacfiyati.com/ilaclar/zovirax-5-krem-2-gr"
CURRENT_HTML = """
<html><head><meta property="og:image" content="/dosyalar/zovirax.png"></head><body>
<h1>Marketing heading</h1><h1 class="page-title">ZOVIRAX %5 KREM (2 GR)</h1>
<div class="medicine-detail-swiper"><div class="swiper-slide">
<img class="product-image" src="/dosyalar/zovirax.png">
<img class="product-image" src="/dosyalar/zovirax-back.jpg">
</div></div>
<div><p class="info-card__label">İlaç Fiyatı</p><p class="info-card__value">152,63 TL</p></div>
<div><p class="info-card__label">Barkod</p><p class="info-card__value">8699522352692</p></div>
<div><p class="info-card__label">Etkin Madde</p><p class="info-card__value">Asiklovir</p></div>
<div><p class="info-card__label">SGK Durumu</p><p class="info-card__value">Bedeli Ödenir</p></div>
<div><p class="info-card__label">Reçete Bilgisi</p><p class="info-card__value">Beyaz Reçete</p></div>
<div><p class="info-card__label">Firma Adı</p><p class="info-card__value">Glaxosmithkline</p></div>
<nav><a href="/ilaclar/category">Not an analog</a></nav>
<div id="medicineAccordion">
  <div id="active-ingredient-equivalent"><div class="medicine-item">
    <img class="product-image" src="/dosyalar/foreign.png">
    <a href="/ilaclar/asiviral-400-mg-25-tablet">ASIVIRAL 400 MG 25 TABLET</a>
    <div>BARKOD 8699546090114</div>
    <table><tr><td>Barkod</td><td>WRONG</td></tr></table>
    <div><p class="info-card__label">Etkin Madde</p><p class="info-card__value">WRONG</p></div>
  </div></div>
  <div id="sgk-equivalent"><div class="medicine-item">
    <img src="/dosyalar/another.png">
    <a href="/ilaclar/other-cream">OTHER CREAM</a><div>BARKOD 1234567890123</div>
  </div></div>
  <div id="content-ozet"><p>KULLANMA TALİMATI</p><p>Only summary.</p><script>noise</script></div>
  <div id="content-nasil-kullanilir"><p>Only usage.</p></div>
  <div id="ilac-bilgileri"><table>
    <tr><th>ATC KODU</th><td>D06BB03</td></tr>
    <tr><th>FORMU</th><td>Dermatolojik Krem</td></tr>
    <tr><th>SGK EŞDEĞER KODU</th><td>E007D</td></tr>
    <tr><th>SGK ETKİN MADDE KODU</th><td>SGKES6</td></tr>
  </table></div>
</div>
<div class="swiper-slide"><img src="/dosyalar/unrelated.jpg"></div>
</body></html>
"""


def test_current_layout_reads_own_attributes_gallery_and_inline_tabs(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    calls = []

    def request(url):
        calls.append(url)
        assert url == URL, "Inline sections must not trigger legacy redirect requests"
        return CURRENT_HTML
    monkeypatch.setattr(parser, "_make_request", request)
    product = parser.parse_product_detail(URL)
    assert calls == [URL]
    assert product.name == "ZOVIRAX %5 KREM (2 GR)"
    assert product.price == Decimal("152.63")
    assert product.barcode == "8699522352692"
    assert product.attributes["active_ingredient"] == "Asiklovir"
    assert product.attributes["sgk_status"] == "Bedeli Ödenir"
    assert product.attributes["atc_code"] == "D06BB03"
    assert product.attributes["sgk_equivalent_code"] == "E007D"
    assert product.attributes["sgk_active_ingredient_code"] == "SGKES6"
    assert product.attributes["prescription_required"] is True
    assert product.images == [
        "https://ilacfiyati.com/dosyalar/zovirax.png",
        "https://ilacfiyati.com/dosyalar/zovirax-back.jpg",
    ]
    assert product.is_available is True
    assert product.stock_quantity is None
    assert product.attributes["summary_source"] == "KULLANMA TALİMATI\nOnly summary."
    assert product.attributes["usage_instructions_source"] == "Only usage."
    assert "indications_source" not in product.attributes
    assert "WRONG" not in product.description
    assert "OTHER CREAM" not in product.attributes["summary_source"]
    assert [(a["name"], a["barcode"], a["source_tab"]) for a in product.analogs] == [
        ("ASIVIRAL 400 MG 25 TABLET", "8699546090114", "Eşdeğeri"),
        ("OTHER CREAM", "1234567890123", "SGK Eşdeğeri"),
    ]


def test_missing_own_image_does_not_adopt_analog_images():
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    soup = BeautifulSoup('<div class="medicine-item"><img src="/dosyalar/foreign.jpg"></div>', "html.parser")
    assert parser._extract_product_images(soup) == []


def test_own_placeholder_is_kept_when_also_used_by_equivalents():
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    soup = BeautifulSoup('''
        <div class="medicine-detail-swiper"><img src="/dosyalar/ilaclar.jpg" alt="OWN"></div>
        <div class="medicine-item"><img src="/dosyalar/ilaclar.jpg" alt="OTHER"></div>
    ''', "html.parser")
    assert parser._extract_product_images(soup) == ["https://ilacfiyati.com/dosyalar/ilaclar.jpg"]


def test_missing_inline_section_does_not_read_whole_page():
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    soup = BeautifulSoup(CURRENT_HTML, "html.parser")
    assert parser._extract_tab_text(soup, "side_effects") == ""


def test_repeated_current_parse_produces_identical_content(monkeypatch):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    monkeypatch.setattr(parser, "_make_request", lambda url: CURRENT_HTML)
    first, second = parser.parse_product_detail(URL), parser.parse_product_detail(URL)
    assert first.attributes == second.attributes
    assert first.images == second.images
    assert first.analogs == second.analogs


@pytest.mark.parametrize("label", ["Reçetesiz", "REÇETESİZ"])
def test_non_prescription_label_is_not_treated_as_prescription(monkeypatch, label):
    parser = IlacFiyatiParser(base_url="https://ilacfiyati.com")
    monkeypatch.setattr(parser, "_make_request", lambda url: CURRENT_HTML.replace("Beyaz Reçete", label))
    assert parser.parse_product_detail(URL).attributes["prescription_required"] is False


@pytest.mark.django_db
def test_ilacfiyati_missing_fields_preserve_known_metadata_without_stock_churn(monkeypatch):
    from apps.scrapers.services import ScraperIntegrationService, scraping_in_progress_context
    from apps.catalog.models import Product
    from apps.scrapers.base.scraper import ScrapedProduct

    service = ScraperIntegrationService()
    # Isolate the metadata/stock update policy from domain enrichment and media I/O.
    monkeypatch.setattr(service, "_update_product_attributes", lambda *args, **kwargs: False)
    product = Product.objects.create(
        name="Medicine", slug="ilac-integrity-policy", product_type="medicines",
        external_id="same-medicine", external_url=URL, price=10, currency="TRY",
        is_available=True, stock_quantity=3,
        external_data={"attributes": {"barcode": "1234567890123", "active_ingredient": "Known", "sgk_status": "Known"}},
    )
    scraped = ScrapedProduct(
        name="Medicine", price=10, currency="TRY", url=URL, external_id="same-medicine",
        is_available=True, stock_quantity=None, source="ilacfiyati",
        attributes={"barcode": "", "manufacturer": "Current"},
    )
    with scraping_in_progress_context():
        service._update_existing_product(None, scraped, product)
        product.refresh_from_db()
        action, product = service._update_existing_product(None, scraped, product)
    product.refresh_from_db()
    assert product.external_data["attributes"]["barcode"] == "1234567890123"
    assert product.external_data["attributes"]["active_ingredient"] == "Known"
    assert product.is_available is True
    assert product.stock_quantity == 3
    assert action == "skipped"


@pytest.mark.django_db
def test_ilacfiyati_new_card_has_availability_without_invented_quantity(monkeypatch):
    from apps.scrapers.services import ScraperIntegrationService, scraping_in_progress_context
    from apps.scrapers.base.scraper import ScrapedProduct

    service = ScraperIntegrationService()
    monkeypatch.setattr(service, "_update_product_attributes", lambda *args, **kwargs: False)
    scraped = ScrapedProduct(
        name="Medicine no quantity", price=10, currency="TRY", url=URL,
        external_id="medicine-no-stock", is_available=True, stock_quantity=None,
        source="ilacfiyati", attributes={"barcode": "1234567890123"},
    )
    with scraping_in_progress_context():
        action, product = service._create_new_product(None, scraped)
    product.refresh_from_db()
    assert action == "created"
    assert product.is_available is True
    assert product.stock_quantity is None
