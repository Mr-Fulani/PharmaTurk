"""Файлы SKRS и склада: разбор, загрузка в таблицу, скачивание без лишних запросов."""

from datetime import date
from decimal import Decimal
from io import StringIO

import httpx
import pytest
from django.core.management import call_command

from apps.drug_check.models import DrugReferenceEntry, DrugReferenceLoad
from apps.drug_check.sources import base
from apps.drug_check.sources.selcuk import SelcukSource
from apps.drug_check.sources.skrs import SkrsSource, reason_ru
from apps.drug_check.xlsx import XlsxError, barcode_from, excel_date

from .fixtures import (
    AKLAV,
    ITS_REASON,
    NEXIUM,
    PAROL,
    SELCUK_PAGE,
    TITCK_FILE_URL,
    TITCK_PAGE,
    selcuk_xlsx,
    skrs_xlsx,
)


def _by_barcode(entries):
    return {entry.barcode: entry for entry in entries}


def test_skrs_parse_statuses_dates_and_weekly_reason():
    entries = _by_barcode(SkrsSource().parse(skrs_xlsx(), date(2026, 11, 10)))

    assert len(entries) == 5
    nexium = entries["8699786040021"]
    assert nexium.status == DrugReferenceEntry.Status.PASSIVE
    assert nexium.status_date == date(2025, 4, 15)
    assert nexium.reason == ""
    parol = entries["8699717010093"]
    assert parol.status == DrugReferenceEntry.Status.ACTIVE
    assert parol.status_date == date(2013, 1, 29)
    assert parol.firm.startswith("ATABAY")
    assert parol.atc_code == "N02BE01"
    # причина есть только на листе изменений этой недели
    assert entries["8699591280063"].reason == ITS_REASON
    assert reason_ru(ITS_REASON) == "по данным İTS нет на рынке"
    assert all(entry.file_date == date(2026, 11, 10) for entry in entries.values())


def test_skrs_later_date_wins_when_barcode_is_on_both_sheets_and_warns_before_passive():
    reactivated = PAROL[:11] + [46336]  # снова активен с 10.11.2026
    old_passive = PAROL[:7] + [None, 45000]
    entries = _by_barcode(
        SkrsSource().parse(
            skrs_xlsx(active=(reactivated,), passive=(old_passive, NEXIUM), changes=[], to_passive=[NEXIUM[:8]]),
            None,
        )
    )

    assert entries["8699717010093"].status == DrugReferenceEntry.Status.ACTIVE
    assert entries["8699717010093"].status_date == date(2026, 11, 10)
    # NEXIUM в списке «будут пассивными», но уже пассивен — пометка только у активных
    assert entries["8699786040021"].reason == ""


def test_skrs_without_passive_sheet_is_rejected():
    from .fixtures import make_xlsx

    with pytest.raises(XlsxError):
        SkrsSource().parse(make_xlsx({"AKTİF ÜRÜNLER LİSTESİ": [["x"]]}), None)
    with pytest.raises(XlsxError):
        SkrsSource().parse(b"not a zip", None)


def test_selcuk_parse_prices_and_not_produced_skips_test_rows():
    entries = _by_barcode(SelcukSource().parse(selcuk_xlsx(), date(2026, 10, 13)))

    assert set(entries) == {"8699717010093", "8699546093885", "8699593095085"}
    parol = entries["8699717010093"]
    assert parol.price == Decimal("105.16")
    assert parol.price_date == date(2026, 4, 21)
    assert parol.name == "PAROL 500 MG 30 TB."
    assert parol.status == DrugReferenceEntry.Status.LISTED
    assert entries["8699593095085"].status == DrugReferenceEntry.Status.NOT_PRODUCED


def test_file_links_found_on_source_pages():
    url, name, file_date = SkrsSource().find_file_url(TITCK_PAGE)
    assert url == TITCK_FILE_URL
    assert file_date == date(2026, 11, 10)
    assert name.startswith("AKLST0210.11.2026skrs")

    url, name, file_date = SelcukSource().find_file_url(SELCUK_PAGE)
    assert url == "/dosyalar/ilacfiyatvebarkod/WEBLISTE-13-10-2026.xlsx"
    assert (name, file_date) == ("WEBLISTE-13-10-2026.xlsx", date(2026, 10, 13))


def test_cell_helpers():
    assert barcode_from("8699786040021") == "8699786040021"
    assert barcode_from("8.699786040021E12") == "8699786040021"
    assert barcode_from("1234566541c") == ""
    assert excel_date("46336") == date(2026, 11, 10)
    assert excel_date("10.11.2026") == date(2026, 11, 10)
    assert excel_date("") is None


@pytest.mark.django_db
def test_load_replaces_rows_and_keeps_reason_from_earlier_week():
    source = SkrsSource()
    source.load_content(skrs_xlsx(), file_name="week1.xlsx", file_date=date(2026, 11, 10))
    # Через неделю: AKLAV остаётся пассивным с той же датой, но лист изменений уже другой
    load = source.load_content(
        skrs_xlsx(passive=(NEXIUM, AKLAV), changes=[]), file_name="week2.xlsx", file_date=date(2026, 11, 17)
    )

    assert load.result == DrugReferenceLoad.Result.LOADED
    assert load.rows == 4
    assert DrugReferenceEntry.objects.filter(source="skrs").count() == 4
    assert not DrugReferenceEntry.objects.filter(barcode="8699786090262").exists()
    assert DrugReferenceEntry.objects.get(barcode="8699591280063").reason == ITS_REASON


def _transport(responses, calls):
    def handler(request):
        calls.append(str(request.url))
        body = responses.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


@pytest.fixture
def fake_web(monkeypatch):
    calls = []
    responses = {}

    def client(timeout):
        return httpx.Client(transport=_transport(responses, calls), follow_redirects=True)

    monkeypatch.setattr(base, "http_client", client)
    return responses, calls


@pytest.mark.django_db
def test_download_loads_new_file_and_skips_the_same_file(fake_web):
    responses, calls = fake_web
    responses[SkrsSource.page_url] = TITCK_PAGE.encode()
    responses[TITCK_FILE_URL] = skrs_xlsx()

    first = SkrsSource().download_and_load()
    second = SkrsSource().download_and_load()

    assert first.result == DrugReferenceLoad.Result.LOADED
    assert first.file_date == date(2026, 11, 10)
    assert first.rows == 5
    assert second.result == DrugReferenceLoad.Result.UNCHANGED
    assert calls == [SkrsSource.page_url, TITCK_FILE_URL, SkrsSource.page_url]


@pytest.mark.django_db
def test_download_refuses_foreign_host_and_logs_failure(fake_web):
    responses, calls = fake_web
    responses[SkrsSource.page_url] = b'<a href="https://evil.example/AKLST0210.11.2026skrs.xlsx">x</a>'

    load = SkrsSource().download_and_load()

    assert load.result == DrugReferenceLoad.Result.FAILED
    assert "вне источника" in load.message
    assert calls == [SkrsSource.page_url]
    assert not DrugReferenceEntry.objects.exists()


@pytest.mark.django_db
def test_command_loads_local_file_with_date_from_name(tmp_path):
    path = tmp_path / "WEBLISTE-13-10-2026.xlsx"
    path.write_bytes(selcuk_xlsx())
    out = StringIO()

    call_command("load_drug_reference_files", "--source", "selcuk", "--file", str(path), stdout=out)

    load = DrugReferenceLoad.objects.get()
    assert load.file_date == date(2026, 10, 13)
    assert load.rows == 3
    assert "строк 3" in out.getvalue()


@pytest.mark.django_db
def test_weekly_task_loads_both_sources(fake_web):
    from apps.drug_check.tasks import load_reference_files

    responses, _calls = fake_web
    responses[SkrsSource.page_url] = TITCK_PAGE.encode()
    responses[TITCK_FILE_URL] = skrs_xlsx()
    responses[SelcukSource.page_url] = SELCUK_PAGE.encode()
    responses["https://selcukecza.com.tr/dosyalar/ilacfiyatvebarkod/WEBLISTE-13-10-2026.xlsx"] = selcuk_xlsx()

    summary = load_reference_files()

    assert summary["skrs"]["result"] == "loaded"
    assert summary["selcuk"] == {"result": "loaded", "rows": 3, "file": "WEBLISTE-13-10-2026.xlsx"}
