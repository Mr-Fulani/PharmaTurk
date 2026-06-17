import json

import requests

from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.parsers.zara import ZaraParser
from apps.scrapers.services import ScraperIntegrationService


def _payload_html(payload):
    return (
        "<html><body><script>"
        f"window.zara.viewPayload = {json.dumps(payload, ensure_ascii=False)};\n"
        "</script></body></html>"
    )


def _media(asset_id, name="image"):
    return {
        "type": "image",
        "url": f"https://static.zara.net/{name}.jpg?w={{width}}",
        "extraInfo": {
            "assetId": asset_id,
            "deliveryUrl": f"https://static.zara.net/{name}.jpg",
        },
    }


def _detail_payload(*, product_id="03897114", name="BALON KOLLU KISA ELBİSE"):
    return {
        "product": {
            "id": 537507721,
            "name": name,
            "sectionName": "WOMAN",
            "familyName": "DRESS",
            "subfamilyName": "B.DRESS",
            "seo": {
                "seoProductId": product_id,
                "description": "SEO açıklaması",
            },
            "detail": {
                "reference": f"{product_id}-V2026",
                "displayReference": "3897/114",
                "detailedComposition": {"parts": [{"name": "DIŞ", "components": []}]},
                "colors": [
                    {
                        "id": "064",
                        "productId": 537507721,
                        "name": "Siyah / Beyaz",
                        "reference": "C03897114064000-V2026",
                        "canonicalReference": "03897114064-V2026",
                        "price": 249000,
                        "availability": "in_stock",
                        "rawDescription": "Balon kollu kısa elbise.",
                        "pdpMedia": _media("hero", "hero"),
                        "xmedia": [
                            _media("hero", "hero-duplicate"),
                            _media("gallery-1", "gallery-1"),
                        ],
                        "sizes": [
                            {
                                "id": 1,
                                "name": "XS",
                                "availability": "in_stock",
                                "sku": 523323729,
                            },
                            {
                                "id": 2,
                                "name": "S",
                                "availability": "out_of_stock",
                                "sku": 523323730,
                            },
                        ],
                    },
                    {
                        "id": "712",
                        "productId": 522391829,
                        "name": "Ekru",
                        "reference": "C02700957712000-V2026",
                        "price": 249000,
                        "availability": "coming_soon",
                        "xmedia": [_media("gallery-2", "gallery-2")],
                        "sizes": [
                            {
                                "id": 3,
                                "name": "M",
                                "availability": "coming_soon",
                                "sku": 522391832,
                            }
                        ],
                    },
                ],
            },
        },
        "breadCrumbs": [{"text": "KADIN"}, {"text": "ELBİSE"}],
        "analyticsData": {"mainPrice": 249000},
        "clientAppConfig": {"formatterConfig": {"currencyCode": "TRY"}},
    }


def _category_component(product_id, name, *, page):
    return {
        "id": int(product_id),
        "type": "Product",
        "name": name,
        "price": 249000,
        "reference": f"{product_id}-V2026",
        "availability": "in_stock",
        "serverPage": page,
        "familyName": "DRESS",
        "seo": {
            "keyword": name.lower().replace(" ", "-"),
            "seoProductId": product_id,
        },
        "detail": {"colors": []},
    }


def _category_payload(components, *, page, is_last_page):
    return {
        "category": {"id": 2420896, "name": "ELBİSE"},
        "productGroups": [
            {
                "elements": [
                    {"commercialComponents": [component]}
                    for component in components
                ]
            }
        ],
        "paginationInfo": {
            "page": page,
            "pageSize": 20,
            "isLastPage": is_last_page,
        },
        "clientAppConfig": {"formatterConfig": {"currencyCode": "TRY"}},
    }


def test_zara_url_detection_and_chunking_policy():
    assert ZaraParser.is_zara_product_url(
        "https://www.zara.com/tr/tr/kisa-elbise-p03897114.html"
    )
    assert ZaraParser.is_zara_category_url(
        "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html"
    )
    assert ZaraParser.is_zara_category_url(
        "https://www.zara.com/tr/tr/kadin-mkt1000.html"
    )
    assert not ZaraParser.is_zara_product_url("https://www.lcw.com/urun-o-4827603")
    assert ZaraParser.supports_page_chunking_for_url(
        "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html"
    )
    assert not ZaraParser.supports_page_chunking_for_url(
        "https://www.zara.com/tr/tr/kadin-mkt1000.html"
    )


def test_zara_request_payload_prefers_ajax_json(monkeypatch):
    url = "https://www.zara.com/tr/tr/kisa-elbise-p03897114.html"
    payload = _detail_payload()
    requested_urls = []
    parser = ZaraParser()

    def fake_request(requested_url):
        requested_urls.append(requested_url)
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(parser, "_make_ajax_request", fake_request)

    assert parser._request_payload(url) == payload
    assert requested_urls == [url]
    assert parser._ajax_url(url) == f"{url}?ajax=true"


def test_zara_long_run_uses_batch_pause(monkeypatch):
    parser = ZaraParser()
    parser._last_ajax_response_at = 99.0
    parser._ajax_request_count = parser.BATCH_REQUEST_SIZE
    sleep_calls = []
    monkeypatch.setattr("apps.scrapers.parsers.zara.time.monotonic", lambda: 100.0)
    monkeypatch.setattr(
        "apps.scrapers.parsers.zara.random.uniform",
        lambda low, high: low,
    )
    monkeypatch.setattr(
        "apps.scrapers.parsers.zara.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    parser._wait_before_ajax_request()

    assert sleep_calls == [15.0]


def test_zara_retry_uses_retry_after_header(monkeypatch):
    parser = ZaraParser(max_retries=1)
    limited = requests.Response()
    limited.status_code = 429
    limited.headers["Retry-After"] = "7"
    limited.url = "https://www.zara.com/test?ajax=true"
    success = requests.Response()
    success.status_code = 200
    success._content = b'{"ok": true}'
    success.url = limited.url
    responses = iter([limited, success])
    sleep_calls = []
    monkeypatch.setattr(parser, "_wait_before_ajax_request", lambda: None)
    monkeypatch.setattr(parser.ajax_session, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(
        "apps.scrapers.parsers.zara.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    result = parser._make_ajax_request("https://www.zara.com/test")

    assert json.loads(result) == {"ok": True}
    assert sleep_calls == [7.0]


def test_zara_parse_product_detail_builds_color_variants_and_sizes(monkeypatch):
    url = "https://www.zara.com/tr/tr/kisa-balon-kollu-elbise-p03897114.html"
    parser = ZaraParser()
    monkeypatch.setattr(
        parser,
        "_make_ajax_request",
        lambda requested_url: _payload_html(_detail_payload()),
    )

    product = parser.parse_product_detail(url)

    assert product is not None
    assert product.external_id == "zara-03897114"
    assert product.price == 2490.0
    assert product.currency == "TRY"
    assert product.category == "ELBİSE"
    assert product.description == "Balon kollu kısa elbise."
    assert product.attributes["gender"] == "women"
    assert product.attributes["variant_group_id"] == "zara-03897114"

    variants = product.attributes["fashion_variants"]
    assert len(variants) == 2
    assert variants[0]["external_id"] == "zara-variant-537507721"
    assert variants[0]["images"] == [
        "https://static.zara.net/hero.jpg",
        "https://static.zara.net/gallery-1.jpg",
    ]
    assert variants[0]["sizes"][0]["is_available"] is True
    assert variants[0]["sizes"][0]["stock_quantity"] == 1000
    assert variants[0]["sizes"][1]["is_available"] is False
    assert variants[0]["sizes"][1]["stock_quantity"] == 0
    assert variants[1]["is_available"] is False


def test_zara_parse_category_uses_pagination_and_ignores_accumulated_products(monkeypatch):
    category_url = "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html"
    first = _category_component("03897114", "KISA ELBISE", page=1)
    second = _category_component("02693645", "KEMERLI ELBISE", page=2)
    pages = {
        category_url: _payload_html(
            _category_payload([first], page=1, is_last_page=False)
        ),
        f"{category_url}?page=2": _payload_html(
            _category_payload([first, second], page=2, is_last_page=True)
        ),
    }
    detail_payloads = {
        "03897114": _payload_html(_detail_payload(product_id="03897114", name="KISA ELBISE")),
        "02693645": _payload_html(_detail_payload(product_id="02693645", name="KEMERLI ELBISE")),
    }
    requested_urls = []

    def fake_request(url):
        requested_urls.append(url)
        if url in pages:
            return pages[url]
        for product_id, html in detail_payloads.items():
            if f"p{product_id}.html" in url:
                return html
        return None

    parser = ZaraParser()
    monkeypatch.setattr(parser, "_make_ajax_request", fake_request)

    products = list(parser.parse_product_list(category_url, max_pages=3))

    assert [product.external_id for product in products] == [
        "zara-03897114",
        "zara-02693645",
    ]
    assert f"{category_url}?page=2" in requested_urls
    assert f"{category_url}?page=3" not in requested_urls


def test_zara_category_falls_back_to_list_data_when_detail_is_unavailable(monkeypatch):
    category_url = "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html"
    component = _category_component("03897114", "KISA ELBISE", page=1)
    category_html = _payload_html(
        _category_payload([component], page=1, is_last_page=True)
    )
    parser = ZaraParser()
    monkeypatch.setattr(
        parser,
        "_make_ajax_request",
        lambda url: category_html if url == category_url else None,
    )
    monkeypatch.setattr(parser, "_make_request", lambda url: None)

    products = list(parser.parse_product_list(category_url, max_pages=1))

    assert len(products) == 1
    assert products[0].external_id == "zara-03897114"
    assert products[0].attributes["is_list_fallback"] is True


def test_zara_marketing_category_deduplicates_products_from_nested_categories(monkeypatch):
    marketing_url = "https://www.zara.com/tr/tr/kadin-mkt1000.html"
    marketing_payload = {
        "categories": [
            {
                "id": 1,
                "name": "Elbise",
                "layout": "products-category-view",
                "seo": {"keyword": "kadin-elbiseler", "seoCategoryId": 1066},
            },
            {
                "id": 2,
                "name": "Tişört",
                "layout": "products-category-view",
                "seo": {"keyword": "kadin-tishertler", "seoCategoryId": 1362},
            },
        ]
    }
    parser = ZaraParser()
    monkeypatch.setattr(
        parser,
        "_make_ajax_request",
        lambda url: json.dumps(marketing_payload, ensure_ascii=False),
    )
    duplicate = ScrapedProduct(name="A", external_id="zara-1", source="zara")
    unique = ScrapedProduct(name="B", external_id="zara-2", source="zara")

    def fake_product_list(url, **kwargs):
        if "elbiseler" in url:
            return iter([duplicate])
        return iter([duplicate, unique])

    monkeypatch.setattr(parser, "parse_product_list", fake_product_list)

    products = list(parser._parse_marketing_category(marketing_url, max_categories=10))

    assert [product.external_id for product in products] == ["zara-1", "zara-2"]


class _Session:
    max_pages = 1
    max_products = 10
    pages_processed = 0
    errors_count = 0

    def save(self):
        return None


def test_scraper_service_routes_zara_product_to_detail(monkeypatch):
    parser = ZaraParser()
    expected = ScrapedProduct(name="Zara ürün", source="zara")
    calls = []
    monkeypatch.setattr(
        parser,
        "parse_product_detail",
        lambda url: calls.append(("detail", url)) or expected,
    )
    monkeypatch.setattr(
        parser,
        "parse_product_list",
        lambda *args, **kwargs: calls.append(("list", args[0])) or iter(()),
    )

    products, incremental = ScraperIntegrationService()._run_parser_scraping(
        parser,
        _Session(),
        "https://www.zara.com/tr/tr/kisa-elbise-p03897114.html",
    )

    assert products == [expected]
    assert incremental is None
    assert calls == [
        ("detail", "https://www.zara.com/tr/tr/kisa-elbise-p03897114.html")
    ]


def test_scraper_service_routes_zara_category_to_list(monkeypatch):
    parser = ZaraParser()
    expected = ScrapedProduct(name="Zara ürün", source="zara")
    calls = []
    monkeypatch.setattr(
        parser,
        "parse_product_list",
        lambda url, **kwargs: calls.append((url, kwargs)) or iter([expected]),
    )
    service = ScraperIntegrationService()
    monkeypatch.setattr(
        service,
        "_process_scraped_products",
        lambda session, products: {
            "found": len(products),
            "created": len(products),
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        },
    )

    products, incremental = service._run_parser_scraping(
        parser,
        _Session(),
        "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html",
        start_page=2,
    )

    assert products == []
    assert incremental["found"] == 1
    assert calls == [
        (
            "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html",
            {"max_pages": 1, "start_page": 2},
        )
    ]
