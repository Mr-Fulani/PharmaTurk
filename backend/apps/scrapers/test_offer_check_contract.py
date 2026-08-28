from decimal import Decimal

import httpx
import pytest

from apps.http_errors import ExternalAccessBlockedError
from apps.scrapers.base.offers import (
    OfferAvailability,
    OfferCheckContext,
    OfferCheckErrorCode,
    OfferGone,
    OfferNotFound,
    MalformedOfferResponse,
    OfferOptionNotFound,
    OfferSourceUnavailable,
    OfferStockPrecision,
    UnsupportedOfferVerification,
)
from apps.scrapers.base.scraper import BaseScraper, ScrapedProduct
from apps.scrapers.parsers.flo import FloParser
from apps.scrapers.parsers.bershka import BershkaParser
from apps.scrapers.parsers.ikea import IkeaParser
from apps.scrapers.parsers.ilacabak import IlacabakParser
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser
from apps.scrapers.parsers.instagram import InstagramParser
from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.parsers.massimodutti import MassimoDuttiParser
from apps.scrapers.parsers.pullandbear import PullAndBearParser
from apps.scrapers.parsers.ummaland import UmmalandParser
from apps.scrapers.parsers.zara import ZaraParser


def _context(**overrides):
    payload = {
        "canonical_url": "https://supplier.example/product-1",
        "external_product_id": "product-1",
        "external_sku": "SKU-M",
        "variant_key": "variant-black",
        "size_key": "M",
        "selected_options": {"color": "Black", "size": "M"},
    }
    payload.update(overrides)
    return OfferCheckContext(**payload)


def _fashion_product(*, stock=1000, available=True, raw_availability="in_stock"):
    return ScrapedProduct(
        name="Checked product",
        price=Decimal("99.90"),
        currency="TRY",
        url="https://supplier.example/product-1",
        external_id="product-1",
        source="test",
        attributes={
            "fashion_variants": [
                {
                    "external_id": "variant-black",
                    "sku": "BLACK",
                    "color": "Black",
                    "price": Decimal("109.90"),
                    "currency": "TRY",
                    "external_url": "https://supplier.example/product-1",
                    "is_available": available,
                    "stock_quantity": stock,
                    "availability": raw_availability,
                    "sizes": [
                        {
                            "size": "M",
                            "sku": "SKU-M",
                            "is_available": available,
                            "stock_quantity": stock,
                            "availability": raw_availability,
                        }
                    ],
                }
            ]
        },
    )


class UnsupportedParser(BaseScraper):
    def get_name(self):
        return "unsupported-test"

    def get_supported_domains(self):
        return ["supplier.example"]

    def parse_product_list(self, category_url, max_pages=10):
        return []

    def parse_product_detail(self, product_url):
        return None


def test_base_parser_requires_explicit_offer_support():
    parser = UnsupportedParser("https://supplier.example")
    with pytest.raises(UnsupportedOfferVerification) as error:
        parser.check_offer(_context())
    assert error.value.error.code == OfferCheckErrorCode.UNSUPPORTED


@pytest.mark.parametrize(
    "parser_class",
    [InstagramParser, IlacFiyatiParser, IlacabakParser],
)
def test_manual_or_unreliable_sources_are_explicitly_unsupported(parser_class):
    parser = object.__new__(parser_class)
    with pytest.raises(UnsupportedOfferVerification):
        parser.check_offer(_context())


@pytest.mark.parametrize(
    "parser_class",
    [BershkaParser, PullAndBearParser, MassimoDuttiParser],
)
def test_inditex_siblings_inherit_the_read_only_zara_contract(parser_class):
    assert parser_class.check_offer is ZaraParser.check_offer


def test_zara_offer_check_returns_decimal_and_hides_synthetic_quantity(monkeypatch):
    parser = ZaraParser()
    monkeypatch.setattr(parser, "parse_product_detail", lambda url: _fashion_product())

    result = parser.check_offer(_context())

    assert result.source_price == Decimal("109.90")
    assert result.source_currency == "TRY"
    assert result.availability_status == OfferAvailability.IN_STOCK
    assert result.stock_precision == OfferStockPrecision.BOOLEAN
    assert result.stock_quantity is None


def test_offer_check_reports_missing_size_as_typed_error(monkeypatch):
    parser = ZaraParser()
    monkeypatch.setattr(parser, "parse_product_detail", lambda url: _fashion_product())

    with pytest.raises(OfferOptionNotFound) as error:
        parser.check_offer(_context(size_key="XXL"))

    assert error.value.error.code == OfferCheckErrorCode.OPTION_NOT_FOUND
    assert error.value.error.retryable is False


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (httpx.ReadTimeout("supplier timeout"), OfferCheckErrorCode.TIMEOUT),
        (
            ExternalAccessBlockedError(
                source="Zara",
                status_code=403,
                url="https://www.zara.com/product-p1.html",
            ),
            OfferCheckErrorCode.ACCESS_BLOCKED,
        ),
    ],
)
def test_offer_check_translates_known_transport_errors(monkeypatch, exception, expected_code):
    parser = ZaraParser()

    def fail(_url):
        raise exception

    monkeypatch.setattr(parser, "parse_product_detail", fail)
    with pytest.raises(OfferSourceUnavailable) as error:
        parser.check_offer(_context())

    assert error.value.error.code == expected_code
    assert error.value.error.retryable is True


@pytest.mark.parametrize(
    ("status_code", "expected_exception", "expected_code"),
    [
        (404, OfferNotFound, OfferCheckErrorCode.NOT_FOUND),
        (410, OfferGone, OfferCheckErrorCode.GONE),
    ],
)
def test_offer_check_distinguishes_not_found_and_gone(
    monkeypatch,
    status_code,
    expected_exception,
    expected_code,
):
    parser = ZaraParser()
    request = httpx.Request("GET", "https://www.zara.com/product-p1.html")
    response = httpx.Response(status_code, request=request)

    def fail(_url):
        raise httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=request,
            response=response,
        )

    monkeypatch.setattr(parser, "parse_product_detail", fail)
    with pytest.raises(expected_exception) as error:
        parser.check_offer(_context())

    assert error.value.error.code == expected_code
    assert error.value.error.retryable is False


def test_flo_offer_check_fetches_only_saved_variant(monkeypatch):
    parser = FloParser()
    calls = []
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda url, **kwargs: (
            calls.append((url, kwargs)) or ("html", "https://www.flo.com.tr/urun/model-10001")
        ),
    )
    monkeypatch.setattr(parser, "_extract_product_detail", lambda html: {"name": "FLO"})
    monkeypatch.setattr(
        parser,
        "_build_color_variant",
        lambda detail, url, sort_order: _fashion_product().attributes["fashion_variants"][0],
    )
    monkeypatch.setattr(
        parser,
        "parse_product_detail",
        lambda url: pytest.fail("full color-group parse must not run"),
    )

    result = parser.check_offer(_context(canonical_url="https://www.flo.com.tr/urun/model-10001"))

    assert calls == [
        (
            "https://www.flo.com.tr/urun/model-10001",
            {"include_final_url": True},
        )
    ]
    assert result.source_price == Decimal("109.90")


def test_flo_offer_check_reports_malformed_payload(monkeypatch):
    parser = FloParser()
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda url, **kwargs: ("html", url),
    )
    monkeypatch.setattr(parser, "_extract_product_detail", lambda html: None)

    with pytest.raises(MalformedOfferResponse) as error:
        parser.check_offer(_context(canonical_url="https://www.flo.com.tr/urun/model-10001"))

    assert error.value.error.code == OfferCheckErrorCode.MALFORMED_RESPONSE


@pytest.mark.parametrize(
    "final_url",
    [
        "https://www.flo.com.tr/yuruyus-ayakkabisi",
        "https://www.flo.com.tr/urun/replacement-20002",
    ],
)
def test_flo_offer_check_treats_redirect_away_from_saved_sku_as_not_found(
    monkeypatch,
    final_url,
):
    parser = FloParser()
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda url, **kwargs: ("category html", final_url),
    )

    with pytest.raises(OfferNotFound) as error:
        parser.check_offer(_context(canonical_url="https://www.flo.com.tr/urun/old-name-10001"))

    assert error.value.error.code == OfferCheckErrorCode.NOT_FOUND
    assert error.value.error.retryable is False


def test_flo_offer_check_accepts_canonical_rename_with_same_sku(monkeypatch):
    parser = FloParser()
    final_url = "https://www.flo.com.tr/urun/new-name-10001"
    monkeypatch.setattr(
        parser,
        "_make_offer_request",
        lambda url, **kwargs: ("html", final_url),
    )
    monkeypatch.setattr(parser, "_extract_product_detail", lambda html: {"name": "FLO"})
    variant = _fashion_product().attributes["fashion_variants"][0]
    variant["external_url"] = final_url
    monkeypatch.setattr(
        parser,
        "_build_color_variant",
        lambda detail, url, sort_order: variant,
    )

    result = parser.check_offer(
        _context(canonical_url="https://www.flo.com.tr/urun/old-name-10001")
    )

    assert result.canonical_url == final_url


def test_lcw_offer_check_fetches_only_saved_variant(monkeypatch):
    parser = LcwParser()
    calls = []
    parsed = {"name": "LCW"}
    monkeypatch.setattr(parser, "_make_offer_request", lambda url: calls.append(url) or "html")
    monkeypatch.setattr(parser, "_parse_single_variant", lambda url, html: parsed)
    monkeypatch.setattr(
        parser,
        "_variant_payload_from_parsed",
        lambda row, sort_order: _fashion_product().attributes["fashion_variants"][0],
    )
    monkeypatch.setattr(
        parser,
        "_parse_product_group",
        lambda *args, **kwargs: pytest.fail("full color-group parse must not run"),
    )

    result = parser.check_offer(_context(canonical_url="https://www.lcw.com/item-o-1"))

    assert calls == ["https://www.lcw.com/item-o-1"]
    assert result.stock_quantity is None


@pytest.mark.parametrize(("quantity", "precision"), [(5, "exact"), (None, "boolean")])
def test_ikea_offer_check_preserves_only_real_quantity(monkeypatch, quantity, precision):
    parser = IkeaParser("https://www.ikea.com.tr")
    monkeypatch.setattr(
        parser.ikea_service,
        "fetch_item_details",
        lambda code, **_kwargs: {"sprCode": code},
    )
    monkeypatch.setattr(
        parser,
        "_to_scraped_product",
        lambda raw: ScrapedProduct(
            name="IKEA",
            price=Decimal("799.00"),
            currency="TRY",
            url="https://www.ikea.com.tr/urun/123",
            external_id="123",
            sku="123",
            is_available=True,
            stock_quantity=quantity,
            source="ikea",
        ),
    )
    monkeypatch.setattr(
        parser.ikea_service,
        "collect_color_variant_details",
        lambda raw: pytest.fail("color sibling collection must not run"),
    )

    result = parser.check_offer(
        _context(
            canonical_url="https://www.ikea.com.tr/urun/123",
            external_product_id="123",
            external_sku="123",
            variant_key="",
            size_key="",
        )
    )

    assert result.stock_precision.value == precision
    assert result.stock_quantity == quantity


def test_ikea_offer_check_treats_variant_key_as_exact_article(monkeypatch):
    parser = IkeaParser("https://www.ikea.com.tr")
    calls = []
    monkeypatch.setattr(
        parser.ikea_service,
        "fetch_item_details",
        lambda code, **_kwargs: calls.append(code) or {"sprCode": code},
    )
    monkeypatch.setattr(
        parser,
        "_to_scraped_product",
        lambda raw: ScrapedProduct(
            name="DYVLINGE",
            price=Decimal("12999.00"),
            currency="TRY",
            url=f"https://www.ikea.com.tr/urun/{raw['sprCode']}",
            external_id=raw["sprCode"],
            sku=raw["sprCode"],
            is_available=True,
            stock_quantity=29,
            source="ikea",
        ),
    )

    result = parser.check_offer(
        _context(
            canonical_url="https://www.ikea.com.tr/urun/00581918",
            external_product_id="00581918",
            external_sku="",
            variant_key="00623862",
            size_key="",
            selected_options={"color": "kelinge bej"},
        )
    )

    assert calls == ["00623862"]
    assert result.is_success is True
    assert result.source_price == Decimal("12999.00")
    assert result.stock_precision == OfferStockPrecision.EXACT
    assert result.stock_quantity == 29
    assert result.canonical_url.endswith("/00623862")


def test_ikea_offer_check_does_not_turn_dns_failure_into_not_found(monkeypatch):
    parser = IkeaParser("https://www.ikea.com.tr")
    request = httpx.Request(
        "GET",
        "https://frontendapi.ikea.com.tr/api/product/00623862/detail?language=tr",
    )

    def fail(_url):
        raise httpx.ConnectError("temporary DNS failure", request=request)

    monkeypatch.setattr(parser.ikea_service.client, "get", fail)

    with pytest.raises(OfferSourceUnavailable) as error:
        parser.check_offer(
            _context(
                canonical_url="https://www.ikea.com.tr/urun/00581918",
                external_product_id="00581918",
                external_sku="",
                variant_key="00623862",
                size_key="",
            )
        )

    assert error.value.error.code == OfferCheckErrorCode.TRANSPORT_ERROR
    assert error.value.error.retryable is True


def test_ikea_offer_check_does_not_turn_server_error_into_not_found(monkeypatch):
    parser = IkeaParser("https://www.ikea.com.tr")
    request = httpx.Request(
        "GET",
        "https://frontendapi.ikea.com.tr/api/product/00623862/detail?language=tr",
    )
    response = httpx.Response(503, request=request)
    monkeypatch.setattr(parser.ikea_service.client, "get", lambda _url: response)

    with pytest.raises(OfferSourceUnavailable) as error:
        parser.check_offer(
            _context(
                canonical_url="https://www.ikea.com.tr/urun/00581918",
                external_product_id="00581918",
                external_sku="",
                variant_key="00623862",
                size_key="",
            )
        )

    assert error.value.error.code == OfferCheckErrorCode.TRANSPORT_ERROR
    assert error.value.error.retryable is True
    assert error.value.error.http_status == 503


def test_ummaland_check_is_boolean_and_read_only(monkeypatch):
    parser = UmmalandParser("https://umma-land.com")
    monkeypatch.setattr(
        parser,
        "parse_product_detail",
        lambda url: ScrapedProduct(
            name="Book",
            price=Decimal("500"),
            currency="RUB",
            url=url,
            external_id="book-1",
            is_available=False,
            source="ummaland",
        ),
    )

    result = parser.check_offer(
        _context(
            canonical_url="https://umma-land.com/product/book-1",
            external_product_id="book-1",
            external_sku="",
            variant_key="",
            size_key="",
        )
    )

    assert result.availability_status == OfferAvailability.OUT_OF_STOCK
    assert result.stock_precision == OfferStockPrecision.BOOLEAN
