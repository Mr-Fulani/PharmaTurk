"""parse_categories для обхода всего сайта: фрагменты настоящих ответов от 21.10.2026.

Каждый адрес из списка должен открываться категорийным режимом своего парсера,
а сбой источника — давать ошибку, а не пустой «успешный» список.
"""

import json
from pathlib import Path

import pytest

from apps.scrapers.base.scraper import SiteCategoriesError
from apps.scrapers.parsers.bershka import BershkaParser
from apps.scrapers.parsers.flo import FloParser
from apps.scrapers.parsers.ikea import IkeaParser
from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.parsers.zara import ZaraParser
from apps.scrapers.test_inditex_parsers import _parser, _routes

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


# --- Inditex (Bershka, Pull&Bear, Massimo Dutti) -----------------------------


def test_inditex_categories_come_from_itxrest_tree(monkeypatch):
    # Дерево Bershka урезано; безымянный служебный контейнер с «PARFÜM»
    # взят из дерева Massimo Dutti, где такие контейнеры держат лукбуки.
    parser = _parser(
        BershkaParser,
        _routes(**{"/40259537/category?": [(200, _fixture("bershka_category_tree.json"))]}),
        monkeypatch,
    )

    categories = parser.parse_categories()

    base = "https://www.bershka.com/tr"
    assert _pairs(categories) == [
        (
            "KADıN > DESTACADOS > ÖZEL FİYATLAR",
            f"{base}/kadin/promo-up-to-3025-n4404.html?celement=1010419519",
            "1010419519",
        ),
        (
            "KADıN > YENI KOLEKSIYON > Ceket",
            f"{base}/kadinlar/kiyafetler/ceketler-n4364.html?celement=1010193212",
            "1010193212",
        ),
        (
            "KADıN > YENI KOLEKSIYON > Ceket > Blazer",
            f"{base}/kadin/giyim/ceket-ve-kaban/blazer-n3811.html?celement=1010193258",
            "1010193258",
        ),
    ]
    assert parser.ajax_session.requests[-1].startswith(
        "https://www.bershka.com/itxrest/2/catalog/store/44109521/40259537/category?"
    )
    assert "typeCatalog=1" in parser.ajax_session.requests[-1]
    for row in categories:
        assert BershkaParser.is_category_url(row["url"])
        # id категории листинг берёт из адреса, без загрузки страницы.
        assert parser._category_id_from_url(row["url"]) == row["external_id"]


def test_inditex_categories_fail_when_tree_is_missing(monkeypatch):
    parser = _parser(
        BershkaParser,
        _routes(**{"/40259537/category?": [(200, '{"errorCode": 1}')]}),
        monkeypatch,
    )

    with pytest.raises(SiteCategoriesError, match="Bershka"):
        parser.parse_categories()


# --- LCW ---------------------------------------------------------------------


def _lcw_parser(monkeypatch, pages, roots):
    parser = LcwParser()
    parser.SITE_ROOT_PATHS = roots
    requested = []

    def fake_request(url, **kwargs):
        requested.append(url)
        return pages.get(url)

    monkeypatch.setattr(parser, "_make_request", fake_request)
    return parser, requested


def test_lcw_categories_are_root_subtrees(monkeypatch):
    parser, requested = _lcw_parser(
        monkeypatch,
        {
            "https://www.lcw.com/kadin-t-1": _fixture("lcw_kadin_t_1.html"),
            "https://www.lcw.com/cocuk-t-3": _fixture("lcw_cocuk_t_3.html"),
        },
        ("/kadin-t-1", "/hediye-t-6526", "/cocuk-t-3"),
    )

    categories = parser.parse_categories()

    assert requested == [
        "https://www.lcw.com/kadin-t-1",
        "https://www.lcw.com/hediye-t-6526",
        "https://www.lcw.com/cocuk-t-3",
    ]
    # Kadın — шесть подразделов; у Çocuk среди подразделов адреса -u-, которые
    # категорийный режим не принимает, поэтому корень обходится целиком.
    # Недоступный корень (Hediye) пропускается.
    assert _pairs(categories) == [
        ("Kadın Ev Giyim", "https://www.lcw.com/kadin-ev-giyim-t-7009", "7009"),
        ("Kadın Giyim", "https://www.lcw.com/kadin-giyim-t-10", "10"),
        ("Kadın Aksesuar", "https://www.lcw.com/kadin-aksesuar-t-26", "26"),
        ("Kadın Ayakkabı", "https://www.lcw.com/kadin-ayakkabi-t-33", "33"),
        ("Kadın İç Giyim", "https://www.lcw.com/kadin-ic-giyim-t-6983", "6983"),
        ("Kadın Plaj Havlusu", "https://www.lcw.com/kadin-plaj-havlusu-t-282", "282"),
        ("Çocuk", "https://www.lcw.com/cocuk-t-3", "3"),
    ]
    assert all(LcwParser.is_lcw_category_url(row["url"]) for row in categories)


def test_lcw_categories_fail_when_root_page_lacks_its_tree(monkeypatch):
    # Корень открылся, но дерево на странице чужое (редирект/смена вёрстки).
    parser, _ = _lcw_parser(
        monkeypatch,
        {"https://www.lcw.com/erkek-t-2": _fixture("lcw_kadin_t_1.html")},
        ("/erkek-t-2",),
    )

    with pytest.raises(SiteCategoriesError, match="erkek-t-2"):
        parser.parse_categories()


def test_lcw_categories_fail_when_no_root_opens(monkeypatch):
    parser, _ = _lcw_parser(monkeypatch, {}, ("/kadin-t-1", "/erkek-t-2"))

    with pytest.raises(SiteCategoriesError):
        parser.parse_categories()
