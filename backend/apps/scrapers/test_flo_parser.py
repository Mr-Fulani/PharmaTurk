import json
from types import SimpleNamespace

import pytest

from apps.scrapers.base.scraper import ScrapedProduct, ScraperAccessBlockedError
from apps.scrapers.parsers.flo import FloParser, resolve_flo_shoe_category_slug
from apps.scrapers.services import ScraperIntegrationService
from apps.catalog.models import Category


def _detail(sku="101792825", name="COURT BOROUGH LOW RECRAFT Beyaz Unisex Sneaker"):
    return {
        "id": "36310805520",
        "sku": sku,
        "model_code": sku,
        "name": name,
        "manufacturer": "Nike",
        "price": "3499",
        "description": "Nike Court Borough Low Recraft<br /><br />Yeni favori Borough modelin.",
        "url": f"/urun/nike-court-borough-low-recraft-beyaz-unisex-sneaker-{sku}",
        "is_in_stock": "True",
        "cinsiyet": "Unisex",
        "renk": "Beyaz",
        "materyal": "Suni Deri",
        "taban": "KAUCUK",
        "ic_astar_1": "TEKSTIL",
        "media_gallery": [
            {
                "position": 1,
                "url_vertical": "https://floimages.mncdn.com/media/catalog/product/d2.jpg",
                "image_vertical_type": "D2",
            },
            {
                "url": "https://floimages.mncdn.com/media/catalog/product/ai-square.jpg",
                "url_vertical": "https://floimages.mncdn.com/media/catalog/product/ai-vertical.jpg",
            },
            # дубликат d2 — должен схлопнуться
            {"url_vertical": "https://floimages.mncdn.com/media/catalog/product/d2.jpg"},
        ],
        "breadcrumb": [
            {"category_id": "18", "name": "Ayakkabı", "url": "ayakkabi"},
            {"category_id": "26", "name": "Sneaker", "url": "sneaker"},
            {"category_id": "253", "name": "Klasik Sneaker", "url": "klasik-sneaker"},
        ],
        "options": [
            {
                "option_value": "35.5",
                "sku": f"{sku}008",
                "barcode": "196968173624",
                "is_in_stock": False,
                "option_name": "beden",
            },
            {
                "option_value": "36.5",
                "sku": f"{sku}001",
                "barcode": "196968173648",
                "is_in_stock": True,
                "option_name": "beden",
            },
        ],
    }


def _product_html(detail):
    return (
        "<html><body><script> window.productDetail = "
        f"{json.dumps(detail, ensure_ascii=False)};\n"
        "</script></body></html>"
    )


def _listing_html(skus, *, has_next=True):
    links = "".join(f'<a href="/urun/nike-sneaker-{s}">x</a>' for s in skus)
    nxt = '<link rel="next" href="https://www.flo.com.tr/ayakkabi?page=9" />' if has_next else ""
    return f"<html><body>{links}{nxt}</body></html>"


def test_flo_url_detection():
    assert FloParser.is_flo_product_url(
        "https://www.flo.com.tr/urun/nike-sneaker-101792825"
    )
    assert FloParser.is_flo_category_url("https://www.flo.com.tr/ayakkabi?cinsiyet=erkek")
    assert not FloParser.is_flo_category_url(
        "https://www.flo.com.tr/urun/nike-sneaker-101792825"
    )
    # чужой домен и нестандартный путь не считаем товаром FLO
    assert not FloParser.is_flo_product_url("https://www.lcw.com/urun-o-4827603")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Erkek Sandalet", "sandals"),
        ("Klasik Sneaker", "sneakers"),
        ("Kadın Çizme", "boots"),
        ("Ev Terliği", "home-shoes"),
        ("Bilinmeyen Ayakkabı", ""),
    ],
)
def test_resolve_flo_shoe_category_slug(value, expected):
    assert resolve_flo_shoe_category_slug(value) == expected


@pytest.mark.django_db
def test_flo_root_task_keeps_inferred_sandals_subcategory():
    shoes = Category.objects.create(name="Обувь", slug="shoes")
    Category.objects.create(name="Сандалии", slug="sandals", parent=shoes)
    session = SimpleNamespace(
        target_category=shoes,
        scraper_config=SimpleNamespace(default_category=None),
    )
    product = ScrapedProduct(
        name="Hakiki Deri Erkek Sandalet",
        url="https://www.flo.com.tr/urun/erkek-sandalet-12345",
        category="Erkек Sandalet",
        source="flo",
    )

    ScraperIntegrationService()._apply_category_mapping(session, product)

    assert product.category == "sandals"


def test_flo_chunking_only_for_category_not_product():
    # авточепочка по страницам — только для листинга, не для одиночного товара
    assert FloParser.supports_page_chunking_for_url(
        "https://www.flo.com.tr/ayakkabi?cinsiyet=erkek"
    )
    assert not FloParser.supports_page_chunking_for_url(
        "https://www.flo.com.tr/urun/nike-revolution-8-102688450"
    )


def test_flo_extract_product_detail_marker():
    parser = FloParser()
    detail = parser._extract_product_detail(_product_html(_detail()))
    assert detail["sku"] == "101792825"
    assert parser._extract_product_detail("<html>no payload</html>") is None


def test_flo_parse_product_detail_builds_sizes_and_attributes(monkeypatch):
    parser = FloParser()
    url = "https://www.flo.com.tr/urun/nike-court-borough-low-recraft-beyaz-unisex-sneaker-101792825"
    monkeypatch.setattr(parser, "_make_request", lambda requested_url: _product_html(_detail()))

    product = parser.parse_product_detail(url)

    assert product is not None
    assert product.external_id == "flo-101792825"
    assert product.brand == "Nike"
    assert product.price == 3499.0
    assert product.currency == "TRY"
    assert product.category == "Klasik Sneaker"
    assert product.description.startswith("Nike Court Borough")
    assert "<br" not in product.description
    assert product.is_available is True

    assert product.attributes["gender"] == "unisex"
    assert product.attributes["color"] == "Beyaz"
    # turkish-поля смаплены на распознаваемые attribute_specs ключи
    assert product.attributes["material"] == "Suni Deri"
    assert product.attributes["sole_material"] == "KAUCUK"
    assert product.attributes["sizes"] == ["35.5", "36.5"]

    # дубликат изображения схлопнут
    assert product.images == [
        "https://floimages.mncdn.com/media/catalog/product/d2.jpg",
        "https://floimages.mncdn.com/media/catalog/product/ai-vertical.jpg",
    ]

    variants = product.attributes["fashion_variants"]
    assert len(variants) == 1
    sizes = variants[0]["sizes"]
    assert sizes[0]["size"] == "35.5"
    assert sizes[0]["is_available"] is False
    assert sizes[0]["stock_quantity"] == 0
    assert sizes[1]["size"] == "36.5"
    assert sizes[1]["is_available"] is True
    assert sizes[1]["barcode"] == "196968173648"


def test_flo_groups_color_variants_into_one_card(monkeypatch):
    parser = FloParser()
    blue = _detail(sku="222", name="REVOLUTION 8 Mavi")
    blue["renk"] = "Mavi"
    blue["color_options"] = [
        {"sku": "222", "url": "/urun/x-mavi-222", "is_in_stock": True},
        {"sku": "111", "url": "/urun/x-siyah-111", "is_in_stock": True},
    ]
    black = _detail(sku="111", name="REVOLUTION 8 Siyah")
    black["renk"] = "Siyah"
    black["color_options"] = blue["color_options"]

    def fake_request(url):
        if "111" in url:
            return _product_html(black)
        return _product_html(blue)

    monkeypatch.setattr(parser, "_make_request", fake_request)

    product = parser.parse_product_detail("https://www.flo.com.tr/urun/x-mavi-222")

    # id группы — минимальный sku среди цветов
    assert product.external_id == "flo-111"
    variants = product.attributes["fashion_variants"]
    assert len(variants) == 2
    assert sorted(v["color"] for v in variants) == ["Mavi", "Siyah"]
    # верхний уровень — со стартового цвета
    assert product.attributes["color"] == "Mavi"
    assert {v["sku"] for v in variants} == {"111", "222"}


def test_flo_parse_product_detail_returns_none_without_payload(monkeypatch):
    parser = FloParser()
    monkeypatch.setattr(parser, "_make_request", lambda url: "<html>no payload here</html>")
    assert parser.parse_product_detail("https://www.flo.com.tr/urun/x-1234") is None


def test_flo_recaptcha_challenge_raises_access_blocked(monkeypatch):
    parser = FloParser()
    challenge = (
        '<!doctype html><html><head>'
        '<base href="https://www.google.com/recaptcha/challengepage/"></head></html>'
    )
    monkeypatch.setattr(parser, "_make_request", lambda url: challenge)

    with pytest.raises(ScraperAccessBlockedError, match="HTTP 403"):
        parser.parse_product_detail(
            "https://www.flo.com.tr/urun/nike-revolution-8-102688450"
        )


def test_flo_parse_list_paginates_and_dedupes(monkeypatch):
    parser = FloParser()
    category_url = "https://www.flo.com.tr/ayakkabi?cinsiyet=erkek"
    pages = {
        category_url: _listing_html(["111111", "222222"], has_next=True),
        f"{category_url}&page=2": _listing_html(["222222", "333333"], has_next=False),
    }
    requested = []

    def fake_request(url):
        requested.append(url)
        if "/urun/" in url:
            sku = url.rsplit("-", 1)[-1]
            return _product_html(_detail(sku=sku, name=f"Shoe {sku}"))
        return pages.get(url)

    monkeypatch.setattr(parser, "_make_request", fake_request)

    products = list(parser.parse_product_list(category_url, max_pages=3))

    assert [p.external_id for p in products] == ["flo-111111", "flo-222222", "flo-333333"]
    assert f"{category_url}&page=2" in requested
    assert parser.has_more_pages is False
    # третьей страницы нет — остановились по отсутствию rel="next"
    assert f"{category_url}&page=3" not in requested


class _Session:
    max_pages = 1
    max_products = 10
    pages_processed = 0
    errors_count = 0

    def save(self):
        return None


def test_scraper_service_routes_flo_product_to_detail(monkeypatch):
    parser = FloParser()
    expected = ScrapedProduct(name="Flo ürün", source="flo")
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

    url = "https://www.flo.com.tr/urun/nike-nike-revolution-8-mavi-erkek-kosu-ayakkabisi-102688450"
    products, incremental = ScraperIntegrationService()._run_parser_scraping(
        parser, _Session(), url
    )

    assert products == [expected]
    assert incremental is None
    assert calls == [("detail", url)]


def test_scraper_service_routes_flo_category_to_list(monkeypatch):
    parser = FloParser()
    expected = ScrapedProduct(name="Flo ürün", source="flo")
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
        parser, _Session(), "https://www.flo.com.tr/ayakkabi?cinsiyet=erkek"
    )

    assert products == []
    assert incremental["found"] == 1
    assert calls[0][0] == "https://www.flo.com.tr/ayakkabi?cinsiyet=erkek"
