"""IndexNow: что уходит Bing и Яндексу, а что нет (docs/INDEXNOW.md). Сеть замокана."""
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import requests
from django.conf import settings as django_settings
from django.db import connection

from apps.catalog.models import (
    IndexNowUrlState,
    MedicineProduct,
    MedicineProductTranslation,
    Product,
)
from apps.catalog.services import indexnow
from apps.catalog.tasks import indexnow_submit_task

SITE = "https://mudaroba.com"


class Sent(list):
    status = 200


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = "" if status_code < 300 else "error body"


@pytest.fixture
def posts(settings, monkeypatch):
    settings.INDEXNOW_ENABLED = True
    settings.INDEXNOW_DAILY_URL_LIMIT = 10_000
    settings.FRONTEND_SITE_URL = SITE
    monkeypatch.setattr(Product, "update_currency_prices", lambda *args, **kwargs: None)
    sent = Sent()

    def fake_post(url, json, headers, timeout):
        sent.append({"url": url, **json})
        if isinstance(sent.status, Exception):
            raise sent.status
        return FakeResponse(sent.status)

    monkeypatch.setattr(indexnow.requests, "post", fake_post)
    return sent


def _medicine(name="Aspirin", **extra) -> MedicineProduct:
    base = Product.objects.create(
        name=name,
        slug=f"indexnow-{uuid4().hex[:10]}",
        product_type="medicines",
        price=Decimal("10.00"),
        currency="TRY",
        is_active=True,
        **extra,
    )
    return MedicineProduct.objects.get(base_product=base)


def _urls(medicine):
    return [f"{SITE}/product/{medicine.slug}", f"{SITE}/en/product/{medicine.slug}"]


def _sent_urls(sent):
    return [url for request in sent for url in request["urlList"]]


def _baseline():
    _medicine("Catalog filler")  # пустая таблица состояния = первый запуск
    result = indexnow.submit_changed_products()
    assert result["status"] == "baseline"


@pytest.mark.django_db
def test_disabled_does_nothing(posts, settings):
    settings.INDEXNOW_ENABLED = False
    _medicine()

    assert indexnow_submit_task() == {"status": "disabled"}
    assert posts == []
    assert not IndexNowUrlState.objects.exists()


@pytest.mark.django_db
def test_first_run_remembers_catalog_without_sending(posts):
    medicine = _medicine()

    result = indexnow.submit_changed_products()

    assert result["status"] == "baseline"
    assert posts == []
    state = IndexNowUrlState.objects.get(path=f"/product/{medicine.slug}")
    assert state.is_public and state.fingerprint and state.submitted_at is None


@pytest.mark.django_db
def test_price_change_is_not_sent_but_new_and_renamed_are(posts):
    renamed = _medicine("Old name")
    repriced = _medicine("Stable name")
    _baseline()

    MedicineProduct.objects.filter(pk=repriced.pk).update(price=Decimal("99.00"), old_price=Decimal("120"))
    assert indexnow.submit_changed_products()["submitted_urls"] == 0
    assert posts == []

    MedicineProduct.objects.filter(pk=renamed.pk).update(name="New name")
    added = _medicine("Brand new")
    result = indexnow.submit_changed_products()

    assert result["new"] == 1 and result["changed"] == 1
    assert sorted(_sent_urls(posts)) == sorted(_urls(renamed) + _urls(added))
    request = posts[0]
    assert request["url"] == "https://api.indexnow.org/indexnow"
    assert request["host"] == "mudaroba.com"
    key = django_settings.INDEXNOW_KEY
    assert request["key"] == key
    assert request["keyLocation"] == f"{SITE}/{key}.txt"
    assert IndexNowUrlState.objects.get(path=f"/product/{added.slug}").submitted_at is not None

    posts.clear()
    assert indexnow.submit_changed_products()["submitted_urls"] == 0
    assert posts == []


@pytest.mark.django_db
def test_availability_and_translation_changes_are_sent(posts):
    sold_out = _medicine()
    translated = _medicine()
    _baseline()

    MedicineProduct.objects.filter(pk=sold_out.pk).update(is_available=False)
    MedicineProductTranslation.objects.create(
        product=translated, locale="ru", name="Аспирин", description="Описание"
    )
    indexnow.submit_changed_products()

    assert sorted(_sent_urls(posts)) == sorted(_urls(sold_out) + _urls(translated))


@pytest.mark.django_db
def test_deactivated_product_is_sent_once_and_again_when_back(posts):
    medicine = _medicine()
    _baseline()
    path = f"/product/{medicine.slug}"

    MedicineProduct.objects.filter(pk=medicine.pk).update(is_active=False)
    result = indexnow.submit_changed_products()

    assert result["gone"] == 1
    assert _sent_urls(posts) == _urls(medicine)
    assert IndexNowUrlState.objects.get(path=path).is_public is False

    posts.clear()
    indexnow.submit_changed_products()
    assert posts == []

    MedicineProduct.objects.filter(pk=medicine.pk).update(is_active=True)
    result = indexnow.submit_changed_products()
    assert result["new"] == 1
    assert _sent_urls(posts) == _urls(medicine)
    assert IndexNowUrlState.objects.get(path=path).is_public is True


@pytest.mark.django_db
def test_stub_and_variant_rows_are_not_tracked(posts):
    _baseline()
    stub = _medicine(external_data={"is_stub": True})
    variant = _medicine()
    variant_data = {"source_variant_id": f"variant-{uuid4().hex[:6]}"}
    MedicineProduct.objects.filter(pk=variant.pk).update(external_data=variant_data)

    indexnow.submit_changed_products()

    sent = _sent_urls(posts)
    assert not set(_urls(stub)) & set(sent)
    assert not set(_urls(variant)) & set(sent)


@pytest.mark.parametrize("status", [400, 403, 422, 429])
@pytest.mark.django_db
def test_error_response_is_logged_and_retried_next_run(posts, status, caplog):
    _baseline()
    medicine = _medicine()
    posts.status = status

    result = indexnow_submit_task()

    assert result["status"] == f"error_{status}"
    assert result["submitted_urls"] == 0
    assert f"ответ {status}" in caplog.text
    assert not IndexNowUrlState.objects.filter(path=f"/product/{medicine.slug}").exists()

    posts.clear()
    posts.status = 200
    indexnow.submit_changed_products()
    assert _sent_urls(posts) == _urls(medicine)


@pytest.mark.django_db
def test_network_error_does_not_fail_task(posts):
    _baseline()
    _medicine()
    posts.status = requests.ConnectionError("down")

    assert indexnow_submit_task()["status"] == "network_error"


@pytest.mark.django_db
def test_daily_limit_defers_the_rest(posts, settings):
    _baseline()
    first = _medicine()
    second = _medicine()
    settings.INDEXNOW_DAILY_URL_LIMIT = 3  # хватает на одну страницу (2 URL)

    result = indexnow.submit_changed_products()

    assert result["submitted_urls"] == 2
    assert result["deferred_pages"] == 1
    assert len(posts) == 1

    posts.clear()
    result = indexnow.submit_changed_products()
    assert result["status"] == "daily_limit"
    assert posts == []

    settings.INDEXNOW_DAILY_URL_LIMIT = 10_000
    indexnow.submit_changed_products()
    assert sorted(_sent_urls(posts)) in (sorted(_urls(first)), sorted(_urls(second)))


@pytest.mark.django_db
def test_requests_are_split_at_ten_thousand_urls(posts, monkeypatch):
    _baseline()
    for _ in range(3):
        _medicine()
    monkeypatch.setattr(indexnow, "MAX_URLS_PER_REQUEST", 4)

    result = indexnow.submit_changed_products()

    assert result["submitted_urls"] == 6
    assert [len(request["urlList"]) for request in posts] == [4, 2]


@pytest.mark.django_db
@pytest.mark.parametrize("model", indexnow._domain_models(), ids=lambda model: model.__name__)
def test_hourly_scan_uses_partial_indexes_not_external_data(model):
    """Каждый час по всему каталогу: служебные строки — только через индексы 0217."""
    sql, params = indexnow.fingerprint_rows(model).query.sql_with_params()

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(f"EXPLAIN {sql}", params)
        plan = "\n".join(row[0] for row in cursor.fetchall())

    assert f"{model._meta.db_table}_source_variant_idx" in plan
    assert "catalog_product_nonpublic_id_idx" in plan


def test_key_file_is_published_by_frontend():
    key = django_settings.INDEXNOW_KEY
    assert len(key) == 32 and int(key, 16) >= 0
    public = Path(__file__).resolve().parents[4] / "frontend" / "public"
    if not public.is_dir():
        pytest.skip("frontend/ нет рядом с backend/ (тесты в контейнере backend)")
    assert (public / f"{key}.txt").read_text().strip() == key


def test_beat_runs_hourly():
    entry = django_settings.CELERY_BEAT_SCHEDULE["catalog-indexnow-submit"]
    assert entry["task"] == "catalog.indexnow_submit"
    assert entry["schedule"].hour == set(range(24))
