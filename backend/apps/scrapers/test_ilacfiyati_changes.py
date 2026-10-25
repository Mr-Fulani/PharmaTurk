"""Режим «Только изменения» IlacFiyati: строки листинга, sitemap, решение «открывать или нет».

Фикстуры — фрагменты живых страниц от 25.10.2026: строки «Arama Sonuçları»
(лекарство AKTİF, лекарство PASİF, БАД) и инфо-карточки PASİF-препарата.
"""

import gzip
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from apps.scrapers.base.listing_changes import (
    GONE, OPEN, SKIP, KnownProduct, ListingRow, listing_decision,
)
from apps.scrapers.base.scraper import ScrapedProduct
from apps.scrapers.parsers.ilacfiyati import (
    ILACFIYATI_SITEMAP_URL, IlacFiyatiParser, IlacFiyatiSourceError,
)

FIXTURES = Path(__file__).parent / "test_fixtures" / "ilacfiyati_changes"
LISTING_HTML = (FIXTURES / "ilacfiyati_listing_rows.html").read_text(encoding="utf-8")
PASIF_CARD_HTML = (FIXTURES / "ilacfiyati_card_pasif_info.html").read_text(encoding="utf-8")

THERMO = "https://ilacfiyati.com/ilaclar/thermo-sulidin-1-0025-likit-jel-50-gr"
IZOTONIK = "https://ilacfiyati.com/ilaclar/09-izotonik-sodyum-klorur-cozeltisi-1000-ml-bfs-setli"
ANEVITA = "https://ilacfiyati.com/takviye-edici-gida/anevita-folic-acid-tablet-90-tablet"


def _parser():
    return IlacFiyatiParser(base_url="https://ilacfiyati.com")


def _row(url=THERMO, *, name="THERMO SULIDIN", price="411,03 TL", status="AKTIF"):
    from apps.scrapers.base.utils import normalize_price

    return ListingRow(
        url=url, name=name, barcode="8699584340859", price=normalize_price(price),
        price_text=price, status=status, prescription="Beyaz Reçete",
    )


# --- строка листинга ---------------------------------------------------------


def test_listing_rows_read_live_card_fields():
    rows = _parser().parse_listing_rows(LISTING_HTML)

    assert [row.url for row in rows] == [THERMO, IZOTONIK, ANEVITA]
    thermo, izotonik, anevita = rows
    assert thermo.name == "THERMO SULIDIN %1 + %0,025 LIKIT JEL 50 GR"
    assert thermo.barcode == "8699584340859"
    assert thermo.price == Decimal("411.03")
    assert thermo.price_text == "411,03 TL"
    assert thermo.status == "AKTIF" and thermo.is_active
    assert thermo.prescription == "Beyaz Reçete"
    assert izotonik.status == "PASIF" and not izotonik.is_active
    assert anevita.prescription == "Reçetesiz"
    assert anevita.price == Decimal("49.70")


def test_listing_rows_without_results_block_is_none():
    assert _parser().parse_listing_rows("<html><body><h2>Kategoriler</h2></body></html>") is None


def test_fingerprint_follows_listed_fields():
    assert _row().fingerprint == _row().fingerprint
    assert _row(price="415,00 TL").fingerprint != _row().fingerprint
    assert _row(name="THERMO SULIDIN JEL").fingerprint != _row().fingerprint
    assert _row(status="PASIF").fingerprint != _row().fingerprint


# --- решение «открывать или нет» ---------------------------------------------

AVAILABLE = KnownProduct(name="THERMO SULIDIN", price=Decimal("411.03"), is_available=True, is_stub=False)


@pytest.mark.parametrize("row,fingerprint,product,expected", [
    (_row(), "", None, OPEN),  # новый товар
    (_row(), "", KnownProduct("THERMO SULIDIN", None, True, True), OPEN),  # заглушка аналога
    (_row(), _row().fingerprint, KnownProduct("THERMO SULIDIN", Decimal("411.03"), False, False), OPEN),
    (_row(), _row().fingerprint, AVAILABLE, SKIP),  # строка не изменилась
    (_row(price="415,00 TL"), _row().fingerprint, AVAILABLE, OPEN),  # цена изменилась
    (_row(), "", AVAILABLE, SKIP),  # первый проход: совпадает с БД
    (_row(name="thermo sulidin "), "", AVAILABLE, SKIP),  # регистр/пробелы не изменение
    (_row(price="415,00 TL"), "", AVAILABLE, OPEN),  # первый проход: цена другая
    (_row(name="THERMO SULIDIN 100 GR"), "", AVAILABLE, OPEN),  # первый проход: название другое
    (_row(price="0,00 TL"), "", KnownProduct("THERMO SULIDIN", None, True, False), SKIP),
    (_row(status="PASIF"), "", AVAILABLE, GONE),  # источник снял препарат
    (_row(status="PASIF"), "", None, SKIP),  # пассивный, которого у нас нет, не заводим
    (_row(status="PASIF"), "", KnownProduct("THERMO SULIDIN", None, False, False), SKIP),
    (_row(status="PASIF"), "", KnownProduct("THERMO SULIDIN", None, True, True), SKIP),
])
def test_listing_decision(row, fingerprint, product, expected):
    assert listing_decision(row, known_fingerprint=fingerprint, product=product) == expected


# --- sitemap и карточка -------------------------------------------------------


def _sitemap(urls):
    body = "".join(f"<url><loc>{url}</loc><lastmod>2026-10-25</lastmod></url>" for url in urls)
    return gzip.compress(f'<?xml version="1.0"?><urlset>{body}</urlset>'.encode())


def test_sitemap_keeps_only_product_cards(monkeypatch):
    import apps.scrapers.parsers.ilacfiyati as module

    monkeypatch.setattr(module, "ILACFIYATI_SITEMAP_MIN_PRODUCTS", 2)
    parser = _parser()
    content = _sitemap([
        THERMO, THERMO + "/yan-etkileri", "https://ilacfiyati.com/ilaclar",
        "https://ilacfiyati.com/takviye-edici-gida/probiyotikler", ANEVITA,
        "https://ilacfiyati.com/blog/yazi", "https://ilacfiyati.com/ilaclar/a-b-c?x=1&amp;y=2",
    ])
    monkeypatch.setattr(parser.client, "get", lambda url: httpx.Response(
        200, content=content, request=httpx.Request("GET", url),
    ))

    assert parser.fetch_sitemap_product_urls() == [
        THERMO, ANEVITA, "https://ilacfiyati.com/ilaclar/a-b-c",
    ]


def test_truncated_sitemap_is_an_error_not_mass_removal(monkeypatch):
    parser = _parser()
    monkeypatch.setattr(parser.client, "get", lambda url: httpx.Response(
        200, content=_sitemap([THERMO]), request=httpx.Request("GET", url),
    ))
    with pytest.raises(IlacFiyatiSourceError, match="оборван"):
        parser.fetch_sitemap_product_urls()


def test_card_inactive_status_is_read_from_info_cards():
    from bs4 import BeautifulSoup

    parser = _parser()
    assert parser._card_is_inactive(BeautifulSoup(PASIF_CARD_HTML, "html.parser"))
    active = PASIF_CARD_HTML.replace("Pasif", "Aktif")
    assert not parser._card_is_inactive(BeautifulSoup(active, "html.parser"))


def test_sitemap_is_a_changes_stage_after_both_listings():
    sources = _parser().parse_change_sources()
    assert [row["url"] for row in sources] == [
        "https://ilacfiyati.com/ilaclar", "https://ilacfiyati.com/takviye-edici-gida",
        ILACFIYATI_SITEMAP_URL,
    ]
    assert IlacFiyatiParser.is_category_url(ILACFIYATI_SITEMAP_URL)
    assert IlacFiyatiParser.supports_page_chunking_for_url(ILACFIYATI_SITEMAP_URL)
    assert not IlacFiyatiParser.is_product_url(ILACFIYATI_SITEMAP_URL)


def test_sitemap_outside_changes_mode_is_an_error():
    with pytest.raises(IlacFiyatiSourceError, match="Только изменения"):
        list(_parser().parse_product_list(ILACFIYATI_SITEMAP_URL))


# --- обход с трекером (без БД) -----------------------------------------------


class FakeTracker:
    def __init__(self, decisions=None, to_open=(), to_check=()):
        self.decisions = decisions or {}
        self.to_open, self.to_check = list(to_open), list(to_check)
        self.saved, self.seen, self.gone = [], [], []
        self.counts = {}

    def decide(self, rows):
        return {row.url: self.decisions.get(row.url, SKIP) for row in rows}

    def remember_saved(self, url):
        self.saved.append(url)

    def mark_seen(self, urls):
        self.seen.extend(urls)

    def sitemap_work(self, urls, is_product_url, canonical_url):
        return self.to_open, self.to_check

    def mark_url_gone(self, url, *, reason):
        self.gone.append((url, reason))


def test_changes_listing_opens_only_changed_rows_and_does_not_stall(monkeypatch):
    parser = _parser()
    parser.change_tracker = FakeTracker({ANEVITA: OPEN})
    pages = {
        f"https://ilacfiyati.com/takviye-edici-gida{suffix}": LISTING_HTML.replace(
            "/ilaclar/thermo", f"/ilaclar/thermo{n}"
        )
        for n, suffix in enumerate(["", "?pg=2", "?pg=3", "?pg=4", "?pg=5"])
    }
    monkeypatch.setattr(parser, "_make_request", lambda url: pages[url])
    opened = []

    def detail(url):
        opened.append(url)
        return ScrapedProduct(name="Anevita", url=url, source="ilacfiyati")

    monkeypatch.setattr(parser, "parse_product_detail", detail)
    list(parser.parse_product_list("https://ilacfiyati.com/takviye-edici-gida", max_pages=5))

    # Одна и та же строка БАДа на всех страницах — открыта один раз (CatalogTraversalState).
    assert opened == [ANEVITA]
    assert parser.change_tracker.saved == [ANEVITA]
    assert parser.catalog_skipped == 14  # остальные строки без изменений
    # Пять страниц без новых карточек — не «застой»: обход идёт дальше.
    assert parser.pages_processed == 5
    assert parser.has_more_pages is True


def test_changes_sitemap_stage_opens_new_and_checks_missing(monkeypatch):
    parser = _parser()
    parser.SITEMAP_BATCH_SIZE = 2
    gone_404 = "https://ilacfiyati.com/ilaclar/removed-drug"
    pasif = "https://ilacfiyati.com/ilaclar/pasif-drug"
    still_active = "https://ilacfiyati.com/ilaclar/active-but-not-in-sitemap"
    tracker = FakeTracker(to_open=[THERMO], to_check=[gone_404, pasif, still_active])
    parser.change_tracker = tracker
    monkeypatch.setattr(parser, "fetch_sitemap_product_urls", lambda url: [THERMO])
    monkeypatch.setattr("apps.scrapers.parsers.ilacfiyati.time.sleep", lambda seconds: None)

    def offer_request(url):
        if url == gone_404:
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))
        return PASIF_CARD_HTML if url == pasif else "<html>aktif</html>"

    opened = []

    def detail(url, html=None):
        opened.append((url, html))
        return ScrapedProduct(name="Drug", url=url, source="ilacfiyati")

    monkeypatch.setattr(parser, "_make_offer_request", offer_request)
    monkeypatch.setattr(parser, "parse_product_detail", detail)

    first = list(parser.parse_product_list(ILACFIYATI_SITEMAP_URL, max_pages=1))
    assert [product.url for product in first] == [THERMO]
    assert tracker.seen == [THERMO, gone_404]
    assert tracker.gone == [(gone_404, "not_found")]
    assert parser.has_more_pages is True

    # Следующий чанк считает список заново — проверенные ссылки из него выпали.
    tracker.to_open, tracker.to_check = [], [pasif, still_active]
    second = list(parser.parse_product_list(ILACFIYATI_SITEMAP_URL, max_pages=1))
    assert tracker.gone[-1] == (pasif, "inactive")
    assert opened == [(THERMO, None), (still_active, "<html>aktif</html>")]
    assert [product.url for product in second] == [still_active]
    assert parser.has_more_pages is False


# --- трекер с БД --------------------------------------------------------------


def _product(url=THERMO, *, price="411.03", source_name="THERMO SULIDIN", **external):
    from apps.catalog.models import Product

    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return Product.objects.create(
        name="Термо Сулидин гель",  # название после AI — сверяется source_name
        slug=f"p-{uuid.uuid4().hex[:8]}",
        product_type="medicines",
        external_id=slug,
        external_url=url,
        external_data={"source": "ilacfiyati", "source_name": source_name, **external},
        price=Decimal(price),
        currency="TRY",
    )


@pytest.mark.django_db
def test_tracker_bootstraps_fingerprint_then_opens_on_change():
    from apps.scrapers.listing_changes import ListingChangeTracker
    from apps.scrapers.models import SourceListingRow

    _product()
    token = uuid.uuid4()
    tracker = ListingChangeTracker("ilacfiyati", token)

    assert tracker.decide([_row()]) == {THERMO: SKIP}
    stored = SourceListingRow.objects.get(url=THERMO)
    assert stored.fingerprint == _row().fingerprint and stored.run_token == token

    changed = _row(price="415,00 TL")
    assert tracker.decide([changed]) == {THERMO: OPEN}
    # Отпечаток OPEN-строки пишется только после сохранения карточки.
    assert SourceListingRow.objects.get(url=THERMO).fingerprint == _row().fingerprint
    tracker.remember_saved(THERMO)
    assert SourceListingRow.objects.get(url=THERMO).fingerprint == changed.fingerprint
    assert tracker.decide([changed]) == {THERMO: SKIP}


@pytest.mark.django_db
def test_tracker_marks_inactive_row_gone_without_deleting():
    from apps.catalog.models import Product
    from apps.scrapers.listing_changes import ListingChangeTracker

    product = _product()
    tracker = ListingChangeTracker("ilacfiyati", uuid.uuid4())

    assert tracker.decide([_row(status="PASIF")]) == {THERMO: GONE}
    product = Product.objects.get(pk=product.pk)
    assert product.is_available is False
    # Повторно пассивная строка уже ничего не меняет.
    assert tracker.decide([_row(status="PASIF")]) == {THERMO: SKIP}
    # Вернулся в продажу — карточка откроется и вернёт наличие обычным сохранением.
    assert tracker.decide([_row()]) == {THERMO: OPEN}


@pytest.mark.django_db
def test_tracker_dry_run_writes_nothing():
    from apps.catalog.models import Product
    from apps.scrapers.listing_changes import ListingChangeTracker
    from apps.scrapers.models import SourceListingRow

    product = _product()
    tracker = ListingChangeTracker("ilacfiyati", None, dry_run=True)

    assert tracker.decide([_row(status="PASIF")]) == {THERMO: GONE}
    tracker.mark_seen([ANEVITA])
    assert not SourceListingRow.objects.exists()
    assert Product.objects.get(pk=product.pk).is_available is True
    assert tracker.sitemap_work([THERMO, ANEVITA], IlacFiyatiParser.is_product_url) == ([], [])


@pytest.mark.django_db
def test_tracker_sitemap_work_lists_unseen_and_missing():
    from apps.scrapers.listing_changes import ListingChangeTracker

    missing = "https://ilacfiyati.com/ilaclar/missing-drug"
    _product(THERMO)
    _product(missing)
    _product("https://ilacfiyati.com/ilaclar/stub-drug", is_stub=True)
    _product(ANEVITA + "/ilac-bilgileri")  # старая ссылка на вкладку — тот же товар
    tracker = ListingChangeTracker("ilacfiyati", uuid.uuid4())
    tracker.decide([_row()])  # THERMO показан листингом

    to_open, to_check = tracker.sitemap_work(
        [THERMO, ANEVITA, "https://www.ilacfiyati.com/ilaclar/new-drug"],
        IlacFiyatiParser.is_product_url,
        _parser()._canonical_product_url,
    )
    assert to_open == [ANEVITA, "https://www.ilacfiyati.com/ilaclar/new-drug"]
    assert to_check == [missing]  # заглушка и показанный листингом не проверяются


# --- задача ---------------------------------------------------------------------


def test_changes_task_discovers_change_sources(monkeypatch):
    from apps.scrapers import tasks

    calls = []

    def discover(config, source_method="parse_categories"):
        calls.append(source_method)
        return [{"name": "Лекарства", "url": "https://ilacfiyati.com/ilaclar"}]

    monkeypatch.setattr(tasks, "_discover_site_categories", discover)
    monkeypatch.setattr(tasks.SiteScraperTask.objects, "filter", lambda **kw: SimpleNamespace(
        update=lambda **values: None,
    ))
    task = SimpleNamespace(id=1, task_type="changes", site_categories=[], site_category_index=0)
    assert tasks._site_category_url(task, SimpleNamespace()) == "https://ilacfiyati.com/ilaclar"
    assert calls == ["parse_change_sources"]


@pytest.mark.django_db
def test_gone_requires_review_marks_candidate_and_command_applies(settings):
    from django.core.management import call_command

    from apps.catalog.models import Product
    from apps.scrapers.listing_changes import GONE_CANDIDATE_KEY, ListingChangeTracker

    settings.SCRAPER_GONE_REQUIRES_REVIEW = True
    product = _product()
    tracker = ListingChangeTracker("ilacfiyati", uuid.uuid4())

    assert tracker.decide([_row(status="PASIF")]) == {THERMO: GONE}
    product = Product.objects.get(pk=product.pk)
    # Владелец проверяет список до снятия: товар в продаже, только пометка.
    assert product.is_available is True
    assert product.external_data[GONE_CANDIDATE_KEY]["reason"] == "inactive"

    call_command("review_gone_candidates")  # отчёт ничего не меняет
    assert Product.objects.get(pk=product.pk).is_available is True

    call_command("review_gone_candidates", "--apply", "--ids", str(product.pk))
    product = Product.objects.get(pk=product.pk)
    assert product.is_available is False
    assert GONE_CANDIDATE_KEY not in product.external_data


@pytest.mark.django_db
def test_review_gone_candidates_clear_keeps_product_on_sale(settings):
    from django.core.management import call_command

    from apps.catalog.models import Product
    from apps.scrapers.listing_changes import GONE_CANDIDATE_KEY, ListingChangeTracker

    settings.SCRAPER_GONE_REQUIRES_REVIEW = True
    product = _product()
    ListingChangeTracker("ilacfiyati", uuid.uuid4()).decide([_row(status="PASIF")])

    call_command("review_gone_candidates", "--clear", "--ids", str(product.pk))
    product = Product.objects.get(pk=product.pk)
    assert product.is_available is True
    assert GONE_CANDIDATE_KEY not in product.external_data
