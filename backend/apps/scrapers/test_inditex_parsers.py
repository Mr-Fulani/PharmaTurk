import json

import pytest

from apps.scrapers.parsers.bershka import BershkaParser
from apps.scrapers.parsers.massimodutti import MassimoDuttiParser
from apps.scrapers.parsers.pullandbear import PullAndBearParser
from apps.scrapers.services import ScraperIntegrationService

from apps.scrapers.test_zara_parser import _Session, _detail_payload


@pytest.mark.parametrize(
    ("parser_class", "name", "brand", "url"),
    [
        (
            MassimoDuttiParser,
            "massimodutti",
            "Massimo Dutti",
            "https://www.massimodutti.com/tr/keten-tshirt-l00648198?pelement=61733884",
        ),
        (
            BershkaParser,
            "bershka",
            "Bershka",
            "https://www.bershka.com/tr/erkek-tshirt-c0p123456789.html",
        ),
        (
            PullAndBearParser,
            "pullandbear",
            "Pull&Bear",
            "https://www.pullandbear.com/tr/erkek-tshirt-c0p123456789.html",
        ),
    ],
)
def test_inditex_sibling_detail_uses_isolated_source_contract(
    monkeypatch, parser_class, name, brand, url
):
    parser = parser_class()
    monkeypatch.setattr(
        parser,
        "_make_ajax_request",
        lambda requested_url: json.dumps(_detail_payload(product_id="00648198")),
    )

    product = parser.parse_product_detail(url)

    assert product is not None
    assert product.source == name
    assert product.brand == brand
    assert product.external_id == f"{name}-00648198"
    assert all(
        variant["external_id"].startswith(f"{name}-variant-")
        for variant in product.attributes["fashion_variants"]
    )


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
