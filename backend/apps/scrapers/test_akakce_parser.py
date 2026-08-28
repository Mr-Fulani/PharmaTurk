from decimal import Decimal

import pytest

from apps.scrapers.base.offers import (
    MalformedOfferResponse,
    OfferAvailability,
    OfferCheckContext,
    OfferNotFound,
    OfferStockPrecision,
)
from apps.scrapers.parsers.akakce import (
    AkakceParser,
    akakce_product_match_score,
)


PRODUCT_URL = (
    "https://www.akakce.com/vitamin-mineral/"
    "en-ucuz-imuplus-imuplus-7-24-150-ml-surup-fiyati,1325897213.html"
)


def _product_html(*, name="İMUPLUS Imuplus 7/24 150 Ml Şurup", offers=True):
    offer_payload = (
        '"offers":{"@type":"AggregateOffer","availability":"https://schema.org/InStock",'
        '"offerCount":"3","lowPrice":"545.99","priceCurrency":"TRY","offers":['
        '{"@type":"Offer","availability":"https://schema.org/InStock",'
        '"price":"615.00","priceCurrency":"TRY",'
        '"url":"https://shop.example/expensive",'
        '"seller":{"@type":"Organization","name":"Shop B"}},'
        '{"@type":"Offer","availability":"https://schema.org/InStock",'
        '"price":"545.99","priceCurrency":"TRY",'
        '"url":"https://shop.example/cheapest#tracking",'
        '"seller":{"@type":"Organization","name":"Shop A"}},'
        '{"@type":"Offer","availability":"https://schema.org/OutOfStock",'
        '"price":"100.00","priceCurrency":"TRY",'
        '"url":"https://shop.example/unavailable",'
        '"seller":{"@type":"Organization","name":"Shop C"}}]}'
        if offers
        else ""
    )
    comma = "," if offers else ""
    return (
        "<html><head><script type=\"application/ld+json\">"
        f'{{"@context":"https://schema.org","@type":"Product","name":"{name}"'
        f"{comma}{offer_payload}}}"
        "</script></head></html>"
    )


def _context(**overrides):
    payload = {
        "canonical_url": PRODUCT_URL,
        "external_product_id": "1325897213",
        "parser_config": {"expected_name": "IMUPLUS 7/24 150 ML SURUP"},
    }
    payload.update(overrides)
    return OfferCheckContext(**payload)


def test_product_identity_match_preserves_dosage_and_count():
    assert akakce_product_match_score(
        "IMUPLUS 7/24 150 ML SURUP",
        "İMUPLUS Imuplus 7/24 150 Ml Şurup",
    ) is not None
    assert akakce_product_match_score(
        "Ocean D3K2 20 ml Damla",
        "Ocean D3K2 50 ml Damla",
    ) is None
    assert akakce_product_match_score("Vitamin C", "Vitamin C Plus") is None


def test_search_uses_only_actual_result_anchors(monkeypatch):
    parser = AkakceParser()
    html = f"""
        <a class="iC" href="{PRODUCT_URL}" title="İMUPLUS Imuplus 7/24 150 Ml Şurup"></a>
        <a href="/vitamin-mineral/en-ucuz-wrong-fiyati,999.html" title="Popular item"></a>
    """
    monkeypatch.setattr(parser, "_make_offer_request", lambda _url: html)

    candidates = parser.search_products("IMUPLUS 7/24 150 ML")

    assert len(candidates) == 1
    assert candidates[0].external_id == "1325897213"
    assert candidates[0].url == PRODUCT_URL


def test_offer_check_chooses_cheapest_live_seller_and_hides_quantity(monkeypatch):
    parser = AkakceParser()
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda _url, **_kwargs: (_product_html(), PRODUCT_URL),
    )

    result = parser.check_offer(_context())

    assert result.availability_status == OfferAvailability.IN_STOCK
    assert result.stock_precision == OfferStockPrecision.BOOLEAN
    assert result.stock_quantity is None
    assert result.source_price == Decimal("545.99")
    assert result.source_currency == "TRY"
    assert result.response_metadata["seller_name"] == "Shop A"
    assert result.response_metadata["seller_url"] == "https://shop.example/cheapest"
    assert result.response_metadata["in_stock_seller_count"] == 2


def test_offer_check_blocks_product_without_current_sellers(monkeypatch):
    parser = AkakceParser()
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda _url, **_kwargs: (_product_html(offers=False), PRODUCT_URL),
    )

    with pytest.raises(OfferNotFound):
        parser.check_offer(_context())


def test_offer_check_requires_saved_identity_and_rejects_title_drift(monkeypatch):
    parser = AkakceParser()
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda _url, **_kwargs: (
            _product_html(name="IMUPLUS 7/24 500 Ml Şurup"),
            PRODUCT_URL,
        ),
    )

    with pytest.raises(MalformedOfferResponse):
        parser.check_offer(_context())
    with pytest.raises(MalformedOfferResponse):
        parser.check_offer(_context(parser_config={}))


@pytest.mark.parametrize(
    "url",
    [
        "http://www.akakce.com/vitamin-mineral/en-ucuz-x-fiyati,1.html",
        "https://evil.example/vitamin-mineral/en-ucuz-x-fiyati,1.html",
        "https://www.akakce.com/cep-telefonu/en-ucuz-x-fiyati,1.html",
        "https://user:pass@www.akakce.com/vitamin-mineral/en-ucuz-x-fiyati,1.html",
    ],
)
def test_canonical_product_url_rejects_untrusted_or_non_supplement_pages(url):
    assert AkakceParser.canonical_product_url(url) is None
