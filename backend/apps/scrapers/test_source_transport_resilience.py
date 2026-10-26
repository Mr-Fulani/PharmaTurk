"""Сбой источника ≠ «товара нет»; пустой ответ API ≠ «категория закончилась»."""

import json

import pytest
import requests

from apps.scrapers.base.offers import (
    MalformedOfferResponse,
    OfferCheckContext,
    OfferCheckErrorCode,
    OfferNotFound,
    OfferSourceUnavailable,
)
from apps.scrapers.parsers.bershka import BershkaParser
from apps.scrapers.parsers.zara import ZaraParser
from apps.scrapers.test_inditex_parsers import _fixture, _parser, _routes

ZARA_URL = "https://www.zara.com/tr/tr/kisa-balon-kollu-elbise-p03897114.html"
BERSHKA_URL = "https://www.bershka.com/tr/x-c0p228309045.html"
BERSHKA_CATEGORY = "https://www.bershka.com/tr/erkek/giyim/t-shirt-n3294.html?celement=1010193239"


def _offer(url):
    return OfferCheckContext(canonical_url=url)


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.url = ZARA_URL
        self.headers = {}


def _zara_with_ajax_error(monkeypatch, exc):
    parser = ZaraParser()
    parser.max_retries = 0
    monkeypatch.setattr(parser, "_warm_session", lambda: None)
    monkeypatch.setattr(parser, "_wait_before_ajax_request", lambda: None)

    def fail(*args, **kwargs):
        raise exc

    monkeypatch.setattr(parser.ajax_session, "get", fail)
    monkeypatch.setattr(parser, "_make_request", lambda url, **kwargs: None)
    return parser


@pytest.mark.parametrize(
    "exc",
    [
        requests.ConnectionError("proxy timeout"),
        requests.HTTPError(response=_Response(503)),
    ],
)
def test_zara_check_offer_reports_unavailable_source_not_out_of_stock(monkeypatch, exc):
    parser = _zara_with_ajax_error(monkeypatch, exc)

    with pytest.raises(OfferSourceUnavailable) as exc_info:
        parser.check_offer(_offer(ZARA_URL))

    assert exc_info.value.error.code == OfferCheckErrorCode.TRANSPORT_ERROR
    assert exc_info.value.error.retryable is True


def test_zara_check_offer_still_reports_removed_card_as_not_found(monkeypatch):
    parser = _zara_with_ajax_error(monkeypatch, requests.HTTPError(response=_Response(404)))

    with pytest.raises(OfferNotFound):
        parser.check_offer(_offer(ZARA_URL))


def test_zara_category_without_payload_is_an_error_not_end_of_category(monkeypatch):
    parser = ZaraParser()
    monkeypatch.setattr(parser, "_request_payload", lambda url: None)

    with pytest.raises(MalformedOfferResponse):
        list(parser.parse_product_list("https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html"))


def test_inditex_check_offer_reports_unavailable_source_on_5xx(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{"/product/228309045/detail": [(503, "")]}),
        monkeypatch,
    )

    with pytest.raises(OfferSourceUnavailable) as exc_info:
        parser.check_offer(_offer(BERSHKA_URL))

    assert exc_info.value.error.retryable is True


def _detail_without_colors():
    detail = json.loads(_fixture("bershka_product_detail.json"))
    for summary in detail["bundleProductSummaries"]:
        summary["detail"]["colors"] = []
    return detail


def test_inditex_detail_without_colors_is_malformed_not_sold_out(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{"/product/228309045/detail": [(200, json.dumps(_detail_without_colors()))]}),
        monkeypatch,
    )

    with pytest.raises(MalformedOfferResponse):
        parser.parse_product_detail(BERSHKA_URL)


@pytest.mark.parametrize("listing", ["", json.dumps({"unexpected": []})])
def test_inditex_listing_without_product_ids_is_an_error(monkeypatch, listing):
    parser = _parser(
        BershkaParser,
        _routes(**{"/category/1010193239/product": [(200, listing)]}),
        monkeypatch,
    )

    with pytest.raises(MalformedOfferResponse):
        list(parser.parse_product_list(BERSHKA_CATEGORY, max_pages=1))


def test_inditex_empty_category_is_a_legit_end(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{"/category/1010193239/product": [(200, json.dumps({"sortedProductIds": []}))]}),
        monkeypatch,
    )

    assert list(parser.parse_product_list(BERSHKA_CATEGORY, max_pages=1)) == []
    assert parser.has_more_pages is False
    # Раздел-витрина (MD «ERKEK > PARFÜM» 26.10.2026): в журнале задачи — причина.
    assert "выберите подраздел" in parser.stop_reason


def test_inditex_products_array_failure_is_an_error(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{
            "/category/1010193239/product": [(200, json.dumps({"sortedProductIds": [231041613]}))],
            "productsArray": [(200, json.dumps({}))],
        }),
        monkeypatch,
    )

    with pytest.raises(MalformedOfferResponse):
        list(parser.parse_product_list(BERSHKA_CATEGORY, max_pages=1))


def test_inditex_listing_skips_colorless_row_and_keeps_others(monkeypatch):
    good = json.loads(_fixture("bershka_product_detail.json"))
    colorless = dict(_detail_without_colors(), id=230329907)
    parser = _parser(
        BershkaParser,
        _routes(**{
            "/category/1010193239/product": [
                (200, json.dumps({"sortedProductIds": [good["id"], 230329907]}))
            ],
            "productsArray": [(200, json.dumps({"products": [good, colorless]}))],
        }),
        monkeypatch,
    )

    products = list(parser.parse_product_list(BERSHKA_CATEGORY, max_pages=1))

    assert [p.external_id for p in products] == [f"bershka-{good['id']}"]
