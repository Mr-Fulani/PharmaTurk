"""Проверка лекарства по источникам: расхождения выделены, каталог не меняется, сеть — фикстуры."""

import time
from datetime import date
from decimal import Decimal

import pytest

from apps.catalog.models import MedicineProduct
from apps.drug_check.service import check_barcode, check_medicine
from apps.drug_check.sources.base import ALERT, ERROR, OK, WARN
from apps.drug_check.sources.selcuk import SelcukSource
from apps.drug_check.sources.skrs import SkrsSource
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser

from .fixtures import ilacfiyati_card, ilacfiyati_search, selcuk_xlsx, skrs_xlsx

NEXIUM_URL = "https://ilacfiyati.com/ilaclar/nexium-40-mg-enterik-kapli-14-pellet-tablet"


@pytest.fixture
def lists(db):
    SkrsSource().load_content(skrs_xlsx(), file_name="skrs.xlsx", file_date=date(2026, 11, 10))
    SelcukSource().load_content(selcuk_xlsx(), file_name="WEBLISTE-13-10-2026.xlsx", file_date=date(2026, 10, 13))


@pytest.fixture
def web(monkeypatch):
    """IlacFiyati без сети: адрес → HTML; список запросов — для проверки «один-два на товар»."""
    pages, calls = {}, []

    def fake_request(self, url, **kwargs):
        calls.append(url)
        if url not in pages:
            return None
        return pages[url]

    monkeypatch.setattr(IlacFiyatiParser, "_make_request", fake_request)
    return pages, calls


def _medicine(**extra):
    data = dict(
        name="NEXIUM (эзомепразол) 40 мг, 14 таб.",
        slug=f"nexium-{time.monotonic_ns()}",
        barcode="8699786040021",
        price=Decimal("202.15"),
        currency="TRY",
        is_active=True,
        is_available=True,
        external_url=NEXIUM_URL,
    )
    data.update(extra)
    return MedicineProduct.objects.create(**data)


def _by_key(report):
    return {result.key: result for result in report.results}


@pytest.mark.django_db
def test_nexium_in_stock_but_passive_in_skrs_is_highlighted_and_catalog_untouched(lists, web):
    pages, calls = web
    pages[NEXIUM_URL] = ilacfiyati_card()
    medicine = _medicine()

    report = check_medicine(medicine)

    results = _by_key(report)
    assert [r.key for r in report.results] == ["skrs", "ilacfiyati", "selcuk"]
    assert results["skrs"].level == ALERT
    assert results["skrs"].status == "Пассивен с 15.04.2025"
    assert results["ilacfiyati"].level == OK
    assert results["ilacfiyati"].price == Decimal("202.15")
    assert results["ilacfiyati"].price_date == date(2026, 4, 1)
    assert results["ilacfiyati"].status == "Aktif"
    assert results["selcuk"].level == WARN
    assert results["selcuk"].status == "Нет в прайсе"
    assert report.level == ALERT
    assert calls == [NEXIUM_URL]  # один запрос на товар
    line = report.telegram_line()
    assert line.startswith("• NEXIUM (эзомепразол) 40 мг, 14 таб.: ⚠️ SKRS: пассивен с 15.04.2025")
    assert "IlacFiyati 202,15 TL (= наша)" in line
    assert "у склада нет" in line
    medicine.refresh_from_db()
    assert (medicine.price, medicine.is_available, medicine.is_active) == (Decimal("202.15"), True, True)


@pytest.mark.django_db
def test_price_differences_with_source_and_warehouse_are_alerts(lists, web):
    pages, _calls = web
    url = "https://ilacfiyati.com/ilaclar/parol-500-mg-30-tablet"
    pages[url] = ilacfiyati_card(name="PAROL 500 MG 30 TABLET", price="110,00 TL", barcode="8699717010093")
    medicine = _medicine(name="PAROL 500 мг", barcode="8699717010093", price=Decimal("100.00"), external_url=url)

    results = _by_key(check_medicine(medicine))

    assert results["skrs"].level == OK
    assert results["skrs"].status == "Активен с 29.01.2013"
    assert results["skrs"].note == "Фирма: ATABAY KİMYA SANAYİ VE TİC. A.Ş."  # без «..»
    assert results["ilacfiyati"].level == ALERT
    assert "разница +10.0 %" in results["ilacfiyati"].note
    assert results["selcuk"].level == ALERT
    assert results["selcuk"].price == Decimal("105.16")
    assert results["selcuk"].short == "склад 105,16 TL ≠ наша"


@pytest.mark.django_db
def test_pasif_on_source_and_other_barcode_on_page_are_alerts(lists, web):
    pages, _calls = web
    pages[NEXIUM_URL] = ilacfiyati_card(status="Pasif", barcode="8699786040038")

    result = _by_key(check_medicine(_medicine()))["ilacfiyati"]

    assert result.level == ALERT
    assert "Pasif" in result.note
    assert "Штрихкод на странице другой: 8699786040038" in result.note
    assert result.short.endswith(", Pasif")


@pytest.mark.django_db
def test_out_of_stock_but_active_and_at_warehouse_is_a_hint(lists, web):
    pages, _calls = web
    url = "https://ilacfiyati.com/ilaclar/xarelto-10-mg"
    pages[url] = ilacfiyati_card(name="XARELTO", price="451,28 TL", barcode="8699546093885")
    medicine = _medicine(name="XARELTO", barcode="8699546093885", price=Decimal("451.28"), external_url=url,
                         is_available=False)

    results = _by_key(check_medicine(medicine))

    assert results["skrs"].level == WARN
    assert "возможно, зря скрыт" in results["skrs"].note
    assert results["selcuk"].level == OK
    assert results["selcuk"].short == "склад 451,28 TL (= наша)"


@pytest.mark.django_db
def test_service_barcode_is_not_compared(lists, web):
    medicine = _medicine(barcode="1111111234567", external_url="")

    report = check_medicine(medicine)

    results = _by_key(report)
    assert results["skrs"].status == "Сверить нельзя"
    assert results["selcuk"].status == "Сверить нельзя"
    assert results["ilacfiyati"].level == ERROR
    assert web[1] == []  # ни ссылки, ни настоящего штрихкода — запросов нет


@pytest.mark.django_db
def test_source_unreachable_and_deadline_passed_are_not_checked(lists, web):
    _pages, calls = web
    medicine = _medicine()

    unreachable = _by_key(check_medicine(medicine))["ilacfiyati"]
    late = _by_key(check_medicine(medicine, deadline=time.monotonic()))["ilacfiyati"]

    assert unreachable.level == ERROR
    assert "не открылась" in unreachable.note
    assert late.level == ERROR
    assert "не успели проверить" in late.note
    assert calls == [NEXIUM_URL]  # после срока запрос не начинается


@pytest.mark.django_db
def test_barcode_without_card_uses_source_search_two_requests(lists, web):
    pages, calls = web
    search = "https://ilacfiyati.com/tum-urunler?q=8699786090262"
    card = "https://ilacfiyati.com/ilaclar/crestor-5-mg-28-film-tablet"
    pages[search] = ilacfiyati_search("crestor-5-mg-28-film-tablet")
    pages[card] = ilacfiyati_card(name="CRESTOR 5 MG 28 FILM TABLET", price="197,12 TL", barcode="8699786090262")

    report = check_barcode("8699786090262")

    results = _by_key(report)
    assert report.medicine is None
    assert calls == [search, card]
    assert results["ilacfiyati"].price == Decimal("197.12")
    assert results["ilacfiyati"].url == card
    assert results["skrs"].status == "Пассивен с 21.10.2025"
    # у нас карточки нет — «пассивен» не расхождение, а сведение
    assert results["skrs"].level == OK


@pytest.mark.django_db
def test_barcode_search_with_several_cards_asks_for_manual_check(lists, web):
    pages, calls = web
    pages["https://ilacfiyati.com/tum-urunler?q=8699786090262"] = ilacfiyati_search("a-1", "a-2")

    result = _by_key(check_barcode("8699786090262"))["ilacfiyati"]

    assert result.level == ERROR
    assert "несколько карточек (2)" in result.note
    assert len(calls) == 1


@pytest.mark.django_db
def test_barcode_of_our_card_checks_the_card(lists, web):
    pages, calls = web
    pages[NEXIUM_URL] = ilacfiyati_card()
    medicine = _medicine()

    report = check_barcode("8699786040021")

    assert report.medicine == medicine
    assert calls == [NEXIUM_URL]


@pytest.mark.django_db
def test_lists_not_loaded_are_reported(web):
    report = check_medicine(_medicine())

    results = _by_key(report)
    assert results["skrs"].status == "Файл не загружен"
    assert results["selcuk"].level == ERROR
