"""Регрессии парсера UmmaLand на разметке живой карточки (октябрь 2026)."""

from decimal import Decimal

import pytest

from apps.scrapers.parsers.ummaland import UmmalandParser

DISCOUNTED_CARD = """
<html><body>
<h1 class="product-block__heading">Большая книга РАМАДАНА</h1>
<div class="product-available"><p class="product-available__text"> В наличии</p></div>
<div class="product-prices">
  <div class="product-price"> 768 ₽<p class="product-percentage"> -20%</p></div>
  <p class="product-old-price"> 960 ₽</p>
</div>
<button class="button product-buy-button" data-id="2718"> В корзину </button>
</body></html>
"""


def _parser_with_pages(monkeypatch, pages):
    parser = UmmalandParser("https://umma-land.com")
    monkeypatch.setattr(parser, "_make_request", lambda url, **kwargs: pages.get(url))
    return parser


def test_discount_badge_is_not_glued_to_price(monkeypatch):
    url = "https://umma-land.com/product/bolshaya-kniga-ramadana"
    parser = _parser_with_pages(monkeypatch, {url: DISCOUNTED_CARD})

    product = parser.parse_product_detail(url)

    assert product is not None
    assert product.price == Decimal("768")
    assert product.is_available is True


def test_sold_out_book_from_listing_has_zero_stock(monkeypatch):
    url = "https://umma-land.com/product/sold-out"
    parser = _parser_with_pages(monkeypatch, {url: DISCOUNTED_CARD})
    monkeypatch.setattr(parser, "_get_category_id", lambda category_url: 16)
    monkeypatch.setattr(
        parser,
        "_fetch_products_from_api",
        lambda category_id: [
            {"id": 1, "name": "Распродана", "link": url, "price": "500", "in_stock": False},
            {"id": 2, "name": "Есть", "link": url, "price": "500", "in_stock": True},
        ],
    )

    products = parser.parse_product_list("https://umma-land.com/product-category/books")

    assert [(p.is_available, p.stock_quantity) for p in products] == [(False, 0), (True, 3)]


def test_listing_yields_books_one_by_one(monkeypatch):
    # Генератор: первая книга уже отдана на сохранение, когда на второй
    # срабатывает мягкий лимит Celery, и лимит не глушится обработкой ошибок.
    from celery.exceptions import SoftTimeLimitExceeded

    url = "https://umma-land.com/product/first"
    parser = _parser_with_pages(monkeypatch, {url: DISCOUNTED_CARD})
    monkeypatch.setattr(parser, "_get_category_id", lambda category_url: 16)
    monkeypatch.setattr(
        parser,
        "_fetch_products_from_api",
        lambda category_id: [
            {"id": 1, "name": "Первая", "link": url, "price": "500", "in_stock": True},
            {"id": 2, "name": "Вторая", "link": "https://umma-land.com/product/second", "price": "500", "in_stock": True},
        ],
    )
    original_detail = parser.parse_product_detail

    def detail(product_url):
        if product_url.endswith("/second"):
            raise SoftTimeLimitExceeded()
        return original_detail(product_url)

    monkeypatch.setattr(parser, "parse_product_detail", detail)
    listing = parser.parse_product_list("https://umma-land.com/product-category/books")

    first = next(listing)
    assert first.name == "Первая"
    with pytest.raises(SoftTimeLimitExceeded):
        next(listing)


def test_category_api_retries_timeout(monkeypatch):
    import httpx

    parser = UmmalandParser("https://umma-land.com")
    parser.max_retries = 1
    monkeypatch.setattr("apps.scrapers.parsers.ummaland.time.sleep", lambda seconds: None)
    calls = []

    class _Ok:
        status_code = 200
        url = parser.API_URL

        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": 1}]

    def post(url, **kwargs):
        calls.append(kwargs.get("timeout"))
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out")
        return _Ok()

    monkeypatch.setattr(parser.client, "post", post)

    assert parser._fetch_products_from_api(16) == [{"id": 1}]
    assert len(calls) == 2 and calls[0] >= 90
