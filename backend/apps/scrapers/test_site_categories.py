"""parse_categories для обхода всего сайта: фрагменты настоящих ответов от 21.10.2026.

Каждый адрес из списка должен открываться категорийным режимом своего парсера,
а сбой источника — давать ошибку, а не пустой «успешный» список.
"""

import json
from pathlib import Path

import pytest

from apps.scrapers.base.scraper import SiteCategoriesError
from apps.scrapers.parsers.flo import FloParser
from apps.scrapers.parsers.ikea import IkeaParser
from apps.scrapers.parsers.zara import ZaraParser

FIXTURES = Path(__file__).parent / "test_fixtures" / "site_categories"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _pairs(categories):
    return [(row["name"], row["url"], row["external_id"]) for row in categories]


# --- общий хвост -----------------------------------------------------------


def test_site_categories_dedupes_by_url_and_sets_source():
    parser = FloParser()

    categories = parser._site_categories(
        [
            {"name": "Bot", "url": "https://www.flo.com.tr/bot", "external_id": "21"},
            {"name": "Bot (menü)", "url": "https://www.flo.com.tr/bot", "external_id": "21"},
            {"name": "Sneaker", "url": "https://www.flo.com.tr/sneaker", "external_id": 26},
        ]
    )

    assert categories == [
        {"name": "Bot", "url": "https://www.flo.com.tr/bot", "external_id": "21", "source": "flo"},
        {
            "name": "Sneaker",
            "url": "https://www.flo.com.tr/sneaker",
            "external_id": "26",
            "source": "flo",
        },
    ]


def test_site_categories_is_bounded():
    parser = FloParser()
    parser.MAX_SITE_CATEGORIES = 2

    categories = parser._site_categories(
        {"name": str(index), "url": f"https://www.flo.com.tr/c-{index}"} for index in range(5)
    )

    assert [row["name"] for row in categories] == ["0", "1"]


def test_site_categories_empty_list_is_source_error():
    with pytest.raises(SiteCategoriesError, match="flo"):
        FloParser()._site_categories([])


# --- FLO ---------------------------------------------------------------------


def test_flo_categories_come_from_listing_category_filter(monkeypatch):
    parser = FloParser()
    requested = []
    monkeypatch.setattr(
        parser,
        "_fetch",
        lambda url: requested.append(url) or _fixture("flo_tum_kategoriler.html"),
    )

    categories = parser.parse_categories()

    assert requested == ["https://www.flo.com.tr/tum-kategoriler"]
    # Второй уровень (листинг включает подразделы) и корень без подразделов;
    # ссылка мега-меню и подразделы третьего уровня не дублируются.
    assert _pairs(categories) == [
        ("Ayakkabı > Günlük Ayakkabı", "https://www.flo.com.tr/gunluk-ayakkabi", "19"),
        ("Ayakkabı > Bot", "https://www.flo.com.tr/bot", "21"),
        ("Spor&Outdoor > Ekipman&Aksesuar", "https://www.flo.com.tr/ekipman-aksesuar", "9216"),
        ("Kozmetik & Kişisel Bakım", "https://www.flo.com.tr/kozmetik-kisisel-bakim", "310"),
    ]
    assert all(FloParser.is_flo_category_url(row["url"]) for row in categories)
    assert {row["source"] for row in categories} == {"flo"}


@pytest.mark.parametrize("html", [None, "<html><body><a href='/bot'>Bot</a></body></html>"])
def test_flo_categories_fail_without_category_filter(monkeypatch, html):
    parser = FloParser()
    monkeypatch.setattr(parser, "_fetch", lambda url: html)

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()


# --- IKEA --------------------------------------------------------------------


def test_ikea_categories_are_product_menu_sections(monkeypatch):
    parser = IkeaParser(base_url="https://www.ikea.com.tr")
    menu = json.loads(_fixture("ikea_menuproduct.json"))
    monkeypatch.setattr(parser.ikea_service, "fetch_product_menu", lambda: menu)

    categories = parser.parse_categories()

    # Заголовки меню («Tüm Mobilyalar» > 10 000 товаров, кампании) и
    # подкатегории разделов не берутся.
    assert _pairs(categories) == [
        (
            "Günlük İhtiyaçlar",
            "https://www.ikea.com.tr/kategori/gunluk-ihtiyaclar",
            "gunluk-ihtiyaclar",
        ),
        ("Bebek & Çocuk", "https://www.ikea.com.tr/kategori/bebek-ve-cocuk", "bebek-ve-cocuk"),
        (
            "IKEA Yiyecek-İçecek",
            "https://www.ikea.com.tr/kategori/ikea-yiyecek-icecek",
            "ikea-yiyecek-icecek",
        ),
    ]
    assert all("/kategori/" in row["url"] for row in categories)


@pytest.mark.parametrize("menu", [{}, {"headlines": [], "categories": []}])
def test_ikea_categories_fail_on_menu_without_sections(monkeypatch, menu):
    parser = IkeaParser(base_url="https://www.ikea.com.tr")
    monkeypatch.setattr(parser.ikea_service, "fetch_product_menu", lambda: menu)

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()


# --- Zara --------------------------------------------------------------------


def test_zara_categories_come_from_ajax_category_tree(monkeypatch):
    parser = ZaraParser()
    requested = []
    monkeypatch.setattr(
        parser,
        "_make_ajax_request",
        lambda url: requested.append(url) or _fixture("zara_categories.json"),
    )

    categories = parser.parse_categories()

    assert requested == ["https://www.zara.com/tr/tr/categories"]
    # CEKET и MAKYAJ: все дети скрыты — берётся redirect-ребёнок «TÜMÜNÜ GÖR»;
    # подарочная карта, магазины и разделители — не листинги.
    assert _pairs(categories) == [
        (
            "KADIN > YENİ ÜRÜNLER > THE NEW",
            "https://www.zara.com/tr/tr/kadin-yeni-gelenler-l1180.html",
            "1180",
        ),
        (
            "KADIN > KOLEKSİYON > CEKET",
            "https://www.zara.com/tr/tr/kadin-ceketler-l1114.html",
            "1114",
        ),
        (
            "ZARA HOME > KİTAP | DERGİ | KIRTASİYE",
            "https://www.zara.com/tr/tr/home-kiosco-l5293.html",
            "5293",
        ),
        (
            "BEAUTY > KADIN > MAKYAJ",
            "https://www.zara.com/tr/tr/kadin-beauty-makyaj-l4414.html",
            "4414",
        ),
    ]
    assert all(ZaraParser.is_zara_category_url(row["url"]) for row in categories)
    assert all(ZaraParser.supports_page_chunking_for_url(row["url"]) for row in categories)


def test_zara_categories_fail_when_tree_is_missing(monkeypatch):
    parser = ZaraParser()
    monkeypatch.setattr(parser, "_make_ajax_request", lambda url: None)
    # Резервный HTML Zara без viewPayload — тоже не дерево категорий.
    monkeypatch.setattr(parser, "_make_request", lambda url, **kwargs: "<html></html>")

    with pytest.raises(SiteCategoriesError, match="Zara"):
        parser.parse_categories()
