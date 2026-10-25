"""Точечный обход: карточка открывается, только если строка списка изменилась."""

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.scrapers.base.listing_snapshot import (
    ListingGuard,
    listing_fingerprint,
    record_listing_snapshot,
)
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.models import ListingSnapshot, ScraperConfig, SiteScraperTask
from apps.scrapers.parsers.flo import FloParser
from apps.scrapers.parsers.ikea import IkeaParser
from apps.scrapers.parsers.lcw import LcwParser
from apps.scrapers.parsers.ummaland import UmmalandParser
from apps.scrapers.parsers.zara import ZaraParser
from apps.scrapers.services import ScraperIntegrationService
from apps.scrapers.test_flo_parser import _detail, _product_html
from apps.scrapers.test_zara_parser import (
    _category_component,
    _category_payload,
    _detail_payload,
    _payload_html,
)


class FakeGuard:
    """Отпечатки в памяти: решение без базы."""

    def __init__(self, known=None):
        self.known = dict(known or {})
        self.unchanged = 0
        self.attached = {}
        self.covered = []

    def prefetch(self, identities):
        list(identities)

    def should_open(self, identity, fingerprint):
        if self.known.get(identity) == fingerprint:
            self.unchanged += 1
            return False
        return True

    def attach(self, product, identity, fingerprint, *, covers=()):
        self.attached[identity] = (fingerprint, tuple(covers))

    def remember_covered(self, identity, fingerprint):
        self.covered.append(identity)
        return True


# --- общий отпечаток и ListingGuard -------------------------------------------------


def test_fingerprint_ignores_key_order_and_sees_value_change():
    assert listing_fingerprint({"a": 1, "b": [1, 2]}) == listing_fingerprint({"b": [1, 2], "a": 1})
    assert listing_fingerprint({"price": 100}) != listing_fingerprint({"price": 101})


def _product(name="Товар"):
    return Product.objects.create(name=name, slug=f"listing-test-{uuid.uuid4().hex}")


@pytest.mark.django_db
def test_guard_opens_new_row_and_skips_unchanged_after_save():
    product = _product()
    guard = ListingGuard("flo")
    assert guard.should_open("111", "fp-1") is True

    scraped = ScrapedProduct(name="x")
    guard.attach(scraped, "111", "fp-1")
    record_listing_snapshot(scraped, product)

    next_run = ListingGuard("flo")
    assert next_run.should_open("111", "fp-1") is False
    assert next_run.unchanged == 1
    assert next_run.should_open("111", "fp-2") is True
    # Строка другого парсера с тем же id — своя.
    assert ListingGuard("zara").should_open("111", "fp-1") is True


@pytest.mark.django_db
def test_guard_reopens_card_after_refresh_window():
    product = _product()
    ListingSnapshot.objects.create(
        parser_key="flo",
        identity="111",
        fingerprint="fp-1",
        product=product,
        card_checked_at=timezone.now() - timedelta(days=40),
    )
    assert ListingGuard("flo").should_open("111", "fp-1") is True

    ListingSnapshot.objects.filter(identity="111").update(
        card_checked_at=timezone.now() - timedelta(days=10)
    )
    assert ListingGuard("flo").should_open("111", "fp-1") is False


@pytest.mark.django_db
def test_open_all_cards_ignores_snapshots_and_deleted_product_reopens():
    product = _product()
    ListingSnapshot.objects.create(
        parser_key="flo", identity="111", fingerprint="fp-1",
        product=product, card_checked_at=timezone.now(),
    )
    assert ListingGuard("flo", open_all=True).should_open("111", "fp-1") is True

    product.delete()
    assert not ListingSnapshot.objects.exists()
    assert ListingGuard("flo").should_open("111", "fp-1") is True


@pytest.mark.django_db
def test_sibling_colour_loaded_with_group_is_remembered_without_opening():
    product = _product()
    guard = ListingGuard("flo")
    scraped = ScrapedProduct(name="x")
    guard.attach(scraped, "111", "fp-1", covers=["111", "222"])
    record_listing_snapshot(scraped, product)

    assert guard.remember_covered("222", "fp-2") is True
    assert guard.remember_covered("333", "fp-3") is False
    row = ListingSnapshot.objects.get(identity="222")
    assert (row.fingerprint, row.product_id) == ("fp-2", product.pk)
    assert ListingGuard("flo").should_open("222", "fp-2") is False


def test_product_without_listing_row_records_nothing():
    record_listing_snapshot(ScrapedProduct(name="x"), SimpleNamespace(pk=1))


# --- FLO --------------------------------------------------------------------------


def _flo_tile(
    sku, *, price="3499", special="2999", qty=5, sizes_in_stock=(True, False), swatches=(),
):
    data = {
        "sku": sku,
        "name": f"Shoe {sku}",
        "price": price,
        "special_price": special,
        "is_in_stock": True,
        "options": [
            {"option_value": str(36 + i), "is_in_stock": stock, "qty": qty if stock else 0}
            for i, stock in enumerate(sizes_in_stock)
        ],
        "color_options": [
            {"sku": color, "is_in_stock": True, "qty": qty} for color in (sku, *swatches)
        ],
    }
    attr = json.dumps(data).replace("&", "&amp;").replace("'", "&#39;")
    links = "".join(f'<a href="/urun/nike-sneaker-{color}">c</a>' for color in swatches)
    return (
        f"<div data-gtm-product='{attr}'>"
        f'<a href="/urun/nike-sneaker-{sku}">x</a>{links}</div>'
    )


def _flo_listing(tiles, *, has_next=False):
    nxt = '<link rel="next" href="https://www.flo.com.tr/ayakkabi?page=9" />' if has_next else ""
    return f"<html><body>{''.join(tiles)}{nxt}</body></html>"


def test_flo_tile_fingerprint_tracks_price_and_sizes_but_not_quantity():
    parser = FloParser()

    def fp(tile):
        from bs4 import BeautifulSoup

        return parser._listing_fingerprints(BeautifulSoup(_flo_listing([tile]), "html.parser"))[0]["111111"]

    base = fp(_flo_tile("111111"))
    assert fp(_flo_tile("111111", qty=1)) == base
    assert fp(_flo_tile("111111", special="2799")) != base
    assert fp(_flo_tile("111111", sizes_in_stock=(False, False))) != base


def test_flo_opens_only_changed_cards(monkeypatch):
    parser = FloParser()
    url = "https://www.flo.com.tr/sandalet"
    listing = _flo_listing([_flo_tile("111111"), _flo_tile("222222")])
    from bs4 import BeautifulSoup

    known, _ = parser._listing_fingerprints(BeautifulSoup(listing, "html.parser"))
    known["222222"] = "old"
    parser.listing_guard = FakeGuard(known)
    requested = []

    def fetch(requested_url):
        requested.append(requested_url)
        if "/urun/" in requested_url:
            sku = requested_url.rsplit("-", 1)[-1]
            return _product_html({**_detail(sku=sku), "color_options": []})
        return listing

    monkeypatch.setattr(parser, "_make_request", fetch)

    products = list(parser.parse_product_list(url, max_pages=1))

    assert [p.sku for p in products] == ["222222"]
    assert [u for u in requested if "/urun/" in u] == ["https://www.flo.com.tr/urun/nike-sneaker-222222"]
    assert parser.listing_guard.unchanged == 1
    assert parser.listing_guard.attached["222222"][0] != "old"


def test_flo_colour_links_inside_unchanged_tile_are_not_opened(monkeypatch):
    from bs4 import BeautifulSoup

    parser = FloParser()
    url = "https://www.flo.com.tr/sandalet"
    listing = _flo_listing([_flo_tile("111111", swatches=("111112",)), _flo_tile("222222")])
    known, swatches = parser._listing_fingerprints(BeautifulSoup(listing, "html.parser"))
    assert swatches == {"111112": "111111"}
    known["222222"] = "old"
    parser.listing_guard = FakeGuard(known)
    opened = []

    def fetch(requested_url):
        if "/urun/" in requested_url:
            opened.append(requested_url.rsplit("-", 1)[-1])
            return _product_html({**_detail(sku=opened[-1]), "color_options": []})
        return listing

    monkeypatch.setattr(parser, "_make_request", fetch)

    list(parser.parse_product_list(url, max_pages=1))

    assert opened == ["222222"]


def test_flo_unchanged_pages_do_not_trip_stall_guard(monkeypatch):
    from apps.scrapers.base.catalog_state import CatalogTraversalState
    from bs4 import BeautifulSoup

    parser = FloParser()
    parser.catalog_state = CatalogTraversalState()
    url = "https://www.flo.com.tr/sandalet"
    pages = {
        url: _flo_listing([_flo_tile("111111")], has_next=True),
        f"{url}?page=2": _flo_listing([_flo_tile("222222")], has_next=True),
        f"{url}?page=3": _flo_listing([_flo_tile("333333")], has_next=True),
        f"{url}?page=4": _flo_listing([_flo_tile("444444")], has_next=False),
    }
    known = {}
    for html in pages.values():
        known.update(parser._listing_fingerprints(BeautifulSoup(html, "html.parser"))[0])
    parser.listing_guard = FakeGuard(known)
    monkeypatch.setattr(parser, "_make_request", lambda u: pages.get(u) or pytest.fail(u))

    assert list(parser.parse_product_list(url, max_pages=10)) == []
    assert parser.pages_processed == 4
    assert parser.listing_guard.unchanged == 4
    assert parser.stop_reason == "Достигнута последняя страница каталога."


# --- Zara -------------------------------------------------------------------------


def test_zara_skips_card_request_for_unchanged_component(monkeypatch):
    category_url = "https://www.zara.com/tr/tr/kadin-elbiseler-l1066.html"
    same = _category_component("03897114", "KISA ELBISE", page=1)
    changed = _category_component("02693645", "KEMERLI ELBISE", page=1)
    parser = ZaraParser()
    old_changed = {**changed, "price": 199000}
    parser.listing_guard = FakeGuard(
        {
            "03897114": parser._listing_fingerprint(same),
            "02693645": parser._listing_fingerprint(old_changed),
        }
    )
    category_html = _payload_html(_category_payload([same, changed], page=1, is_last_page=True))
    requested = []

    def fake_request(url):
        requested.append(url)
        if url == category_url:
            return category_html
        if "p02693645.html" in url:
            return _payload_html(_detail_payload(product_id="02693645", name="KEMERLI ELBISE"))
        return None

    monkeypatch.setattr(parser, "_make_ajax_request", fake_request)

    products = list(parser.parse_product_list(category_url, max_pages=1))

    assert [p.external_id for p in products] == ["zara-02693645"]
    assert not any("p03897114" in url for url in requested)
    assert set(parser.listing_guard.attached) == {"02693645"}


def test_zara_fingerprint_sees_colour_availability():
    parser = ZaraParser()
    component = _category_component("03897114", "KISA ELBISE", page=1)
    component["detail"] = {"colors": [{"id": "064", "price": 249000, "availability": "in_stock"}]}
    sold_out = json.loads(json.dumps(component))
    sold_out["detail"]["colors"][0]["availability"] = "out_of_stock"
    assert parser._listing_fingerprint(component) != parser._listing_fingerprint(sold_out)


# --- LC Waikiki -------------------------------------------------------------------


def _lcw_tile(option_id, price="449,99 TL"):
    return (
        f'<a href="/tisort-o-{option_id}"><img src="x.jpg"></a>'
        f'<a href="/tisort-o-{option_id}"><div class="product-card-info">'
        f'<div class="product-brand">LCWAIKIKI Classic</div>'
        f'<div class="product-description">Erkek Tişört</div>'
        f'<div class="product-price"><span class="current-price">{price}</span></div>'
        f"</div></a>"
    )


def test_lcw_opens_only_changed_tiles(monkeypatch):
    parser = LcwParser()
    category_url = "https://www.lcw.com/erkek-tisort-t-345"
    listing = f"<html><body>{_lcw_tile('111')}{_lcw_tile('222')}</body></html>"
    from bs4 import BeautifulSoup

    known = parser._listing_fingerprints(BeautifulSoup(listing, "html.parser"))
    cheaper = parser._listing_fingerprints(
        BeautifulSoup(_lcw_tile("222", price="399,99 TL"), "html.parser")
    )
    assert cheaper["222"] != known["222"]
    known["111"] = "old"
    parser.listing_guard = FakeGuard(known)
    opened = []
    monkeypatch.setattr(
        parser,
        "_make_request",
        lambda url, **kwargs: listing if url == category_url else "",
    )

    def fetch(url):
        opened.append(url)
        return None, url

    monkeypatch.setattr(parser, "_fetch_with_final_url", fetch)
    monkeypatch.setattr(
        parser,
        "parse_product_detail",
        lambda url: ScrapedProduct(name="T", url=url, external_id=url, attributes={}),
    )

    products = list(parser.parse_product_list(category_url, max_pages=1))

    assert opened == ["https://www.lcw.com/tisort-o-111"]
    assert [p.url for p in products] == ["https://www.lcw.com/tisort-o-111"]
    assert parser.listing_guard.unchanged == 1


# --- IKEA -------------------------------------------------------------------------


def _ikea_brief(code, price=42999):
    return {
        "sprCode": code,
        "title": "BÅRSLÖV",
        "subTitle": "köşe kanepe",
        "price": price,
        "isSellable": True,
        "stockStatus": 2,
        "images": [{"code": "PE1"}],
    }


def test_ikea_fetches_details_only_for_changed_rows(monkeypatch):
    parser = IkeaParser("https://www.ikea.com.tr")
    briefs = [_ikea_brief("11111111"), _ikea_brief("22222222", price=39999)]
    parser.listing_guard = FakeGuard(
        {
            "11111111": parser._listing_fingerprint(briefs[0]),
            "22222222": parser._listing_fingerprint(_ikea_brief("22222222")),
        }
    )
    fetched = []
    monkeypatch.setattr(
        parser.ikea_service,
        "get_category_products",
        lambda slug, limit, language, page: briefs if page == 1 else [],
    )

    def fetch_items(codes):
        fetched.extend(codes)
        return [{"sprCode": code} for code in codes]

    monkeypatch.setattr(parser.ikea_service, "fetch_items", fetch_items)
    monkeypatch.setattr(parser.ikea_service, "collect_color_variant_details", lambda item: [item])
    monkeypatch.setattr(
        parser,
        "_scraped_product_from_variant_details",
        lambda details, canonical_spr: ScrapedProduct(name=canonical_spr, external_id=canonical_spr),
    )

    products = list(parser.parse_product_list("https://www.ikea.com.tr/kategori/kanepeler", max_pages=1))

    assert fetched == ["22222222"]
    assert [p.external_id for p in products] == ["22222222"]
    assert parser.listing_guard.attached["22222222"][1] == ("22222222",)


# --- UmmaLand ---------------------------------------------------------------------


def test_ummaland_skips_book_page_for_unchanged_api_row(monkeypatch):
    parser = UmmalandParser("https://umma-land.com")
    same = {"id": 1, "name": "Книга", "link": "https://umma-land.com/product/a", "price": "500", "in_stock": True}
    changed = {"id": 2, "name": "Вторая", "link": "https://umma-land.com/product/b", "price": "450", "in_stock": True}
    parser.listing_guard = FakeGuard(
        {
            "1": listing_fingerprint({"v": parser.LISTING_FINGERPRINT_VERSION, "item": same}),
            "2": listing_fingerprint(
                {"v": parser.LISTING_FINGERPRINT_VERSION, "item": {**changed, "price": "500"}}
            ),
        }
    )
    monkeypatch.setattr(parser, "_get_category_id", lambda url: 16)
    monkeypatch.setattr(parser, "_fetch_products_from_api", lambda category_id: [same, changed])
    opened = []

    def detail(url):
        opened.append(url)
        return ScrapedProduct(name="x", url=url)

    monkeypatch.setattr(parser, "parse_product_detail", detail)

    products = list(parser.parse_product_list("https://umma-land.com/product-category/books"))

    assert opened == ["https://umma-land.com/product/b"]
    assert [p.external_id for p in products] == ["2"]


# --- сервис: обход категории ------------------------------------------------------


class _ListingParser:
    SUPPORTS_LISTING_GUARD = True

    def __init__(self, rows):
        self.rows = rows
        self.opened = []
        self.max_products = None

    def get_name(self):
        return "fakeshop"

    def is_category_url(self, url):
        return True

    def parse_product_list(self, url, max_pages=1):
        guard = self.listing_guard
        guard.prefetch(identity for identity, _ in self.rows)
        for identity, fingerprint in self.rows:
            if not guard.should_open(identity, fingerprint):
                continue
            self.opened.append(identity)
            product = ScrapedProduct(name=identity, external_id=identity, source="fakeshop")
            guard.attach(product, identity, fingerprint)
            yield product


def _run_category(monkeypatch, parser, site_task=None):
    service = ScraperIntegrationService()
    saved = {}

    def process(session, products):
        for product in products:
            obj = saved.get(product.external_id) or _product(name=product.name)
            saved[product.external_id] = obj
            record_listing_snapshot(product, obj)
        return {"found": len(products), "created": len(products), "updated": 0, "skipped": 0, "errors": 0}

    monkeypatch.setattr(service, "_process_scraped_products", process)
    session = SimpleNamespace(
        max_pages=1, pages_processed=0, errors_count=0, id=None, save=lambda: None,
        products_found=0, products_created=0, products_updated=0, products_skipped=0,
    )
    _, results = service._run_parser_scraping(
        parser,
        session,
        "https://fakeshop.test/category",
        site_task_id=site_task.pk if site_task else None,
        site_run_token=str(site_task.run_token or "") if site_task else None,
    )
    return results


@pytest.mark.django_db
def test_service_records_snapshots_and_next_run_skips_unchanged(monkeypatch):
    first = _ListingParser([("a", "fp-a"), ("b", "fp-b")])
    results = _run_category(monkeypatch, first)
    assert first.opened == ["a", "b"]
    assert results["found"] == 2
    assert ListingSnapshot.objects.filter(parser_key="fakeshop").count() == 2

    second = _ListingParser([("a", "fp-a"), ("b", "fp-b2"), ("c", "fp-c")])
    results = _run_category(monkeypatch, second)
    assert second.opened == ["b", "c"]
    assert results["found"] == 2
    assert results["skipped"] == 1


@pytest.mark.django_db
def test_service_open_all_cards_task_reopens_everything(monkeypatch):
    _run_category(monkeypatch, _ListingParser([("a", "fp-a")]))
    config = ScraperConfig.objects.create(
        name="fakeshop",
        parser_class="fakeshop",
        base_url="https://fakeshop.test",
        default_category=Category.objects.create(name="Магазин", slug="listing-test-shop"),
    )
    task = SiteScraperTask.objects.create(
        scraper_config=config, start_url="https://fakeshop.test/category", open_all_cards=True,
    )
    parser = _ListingParser([("a", "fp-a")])
    _run_category(monkeypatch, parser, site_task=task)
    assert parser.opened == ["a"]
