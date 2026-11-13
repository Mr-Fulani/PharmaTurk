"""Кнопка «Проверить сейчас», окно поиска и итог проверки в сообщении о заявке."""

import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.catalog.models import MedicineProduct, Product
from apps.drug_check.service import order_check_text
from apps.drug_check.sources.selcuk import SelcukSource
from apps.drug_check.sources.skrs import SkrsSource
from apps.orders.models import Order, OrderItem
from apps.orders.tasks import notify_new_order_telegram
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser

from .fixtures import ilacfiyati_card, selcuk_xlsx, skrs_xlsx

NEXIUM_URL = "https://ilacfiyati.com/ilaclar/nexium-40-mg-enterik-kapli-14-pellet-tablet"


@pytest.fixture
def lists(db):
    SkrsSource().load_content(skrs_xlsx(), file_name="skrs.xlsx", file_date=date(2026, 11, 10))
    SelcukSource().load_content(selcuk_xlsx(), file_name="WEBLISTE-13-10-2026.xlsx", file_date=date(2026, 10, 13))


@pytest.fixture
def web(monkeypatch):
    pages, calls = {NEXIUM_URL: ilacfiyati_card()}, []

    def fake_request(self, url, **kwargs):
        calls.append(url)
        return pages.get(url)

    monkeypatch.setattr(IlacFiyatiParser, "_make_request", fake_request)
    return pages, calls


@pytest.fixture(autouse=True)
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("dc-admin", "dc-admin@example.com", "x" * 20))
    return client


@pytest.fixture
def nexium(db):
    medicine = MedicineProduct.objects.create(
        name="NEXIUM (эзомепразол) 40 мг, 14 таб.",
        slug=f"nexium-{time.monotonic_ns()}",
        barcode="8699786040021",
        price=Decimal("202.15"),
        currency="TRY",
        is_active=True,
        is_available=True,
        external_url=NEXIUM_URL,
    )
    medicine.refresh_from_db()
    return medicine


@pytest.mark.django_db
def test_medicine_card_has_check_button_and_check_page_shows_sources(admin_client, lists, web, nexium):
    change = admin_client.get(reverse("admin:catalog_medicineproduct_change", args=[nexium.pk]))
    check_url = reverse("admin:drug_check_medicine", args=[nexium.pk])

    assert change.status_code == 200
    assert check_url in change.content.decode()
    assert "Проверить сейчас" in change.content.decode()

    page = admin_client.get(check_url)
    html = page.content.decode()
    assert page.status_code == 200
    assert "Пассивен с 15.04.2025" in html
    assert 'class="dc-alert"' in html
    assert "202,15 TL" in html
    assert "01.04.2026" in html
    assert "Нет в прайсе" in html
    assert "ничего не меняет" in html or "не меняет" in html


@pytest.mark.django_db
def test_lookup_by_name_searches_lists_without_requests(admin_client, lists, web):
    _pages, calls = web

    page = admin_client.get(reverse("admin:drug_check_lookup"), {"q": "crestor"})

    html = page.content.decode()
    assert page.status_code == 200
    assert "CRESTOR 5 MG 28 FILM TABLET" in html
    assert "?q=8699786090262" in html
    assert calls == []


@pytest.mark.django_db
def test_lookup_by_barcode_runs_full_check(admin_client, lists, web, nexium):
    page = admin_client.get(reverse("admin:drug_check_lookup"), {"q": "8699786040021"})

    html = page.content.decode()
    assert "Пассивен с 15.04.2025" in html
    assert reverse("admin:drug_check_medicine", args=[nexium.pk]) in html


@pytest.mark.django_db
def test_check_page_requires_medicine_view_permission(client, django_user_model, nexium):
    staff = django_user_model.objects.create_user(username="staff", email="s@example.com", password="x" * 20,
                                                  is_staff=True)
    client.force_login(staff)

    response = client.get(reverse("admin:drug_check_medicine", args=[nexium.pk]))

    assert response.status_code == 403


def _order_with(*products):
    order = Order.objects.create(
        number=f"REQ{time.monotonic_ns() % 10**8}", total_amount=Decimal("100"), currency="RUB",
        contact_name="Клиент", contact_phone="+79990001122", payment_method="manager",
    )
    for product in products:
        OrderItem.objects.create(order=order, product=product, product_name=product.name, price=Decimal("100"),
                                 quantity=1, total=Decimal("100"))
    return order


@pytest.mark.django_db
def test_order_text_lists_each_medicine_and_skips_other_goods(lists, web, nexium):
    other = Product.objects.create(name="Кроссовки", slug=f"shoe-{time.monotonic_ns()}", product_type="shoes",
                                   price=Decimal("10"), currency="TRY")
    order = _order_with(nexium.base_product, other, nexium.base_product)

    text = order_check_text(order)

    lines = text.split("\n")
    assert lines[0].startswith("🔎 Проверка лекарств")
    assert len(lines) == 2
    assert lines[1].startswith("• NEXIUM (эзомепразол) 40 мг, 14 таб.: ⚠️ SKRS: пассивен с 15.04.2025")
    assert order_check_text(_order_with(other)) == ""


@pytest.mark.django_db
def test_order_text_stops_external_requests_after_time_budget(lists, web, nexium):
    _pages, calls = web

    text = order_check_text(_order_with(nexium.base_product), seconds=0)

    assert "IlacFiyati: не успели проверить" in text
    assert "SKRS: пассивен с 15.04.2025" in text  # своя таблица — без сети, всегда есть
    assert calls == []


def test_order_text_is_empty_when_items_cannot_be_read():
    assert order_check_text(SimpleNamespace(pk=1)) == ""


@pytest.mark.django_db
@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=None)
@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.orders.tasks.requests.post")
def test_manager_telegram_message_ends_with_drug_check(post, _gen, _load, settings, lists, web, nexium):
    settings.TELEGRAM_BOT_TOKEN = "test-token"
    settings.TELEGRAM_CHAT_ID = "admin-chat"
    settings.TELEGRAM_ORDERS_CHAT_ID = ""
    post.return_value = SimpleNamespace(status_code=200, ok=True)
    order = _order_with(nexium.base_product)

    notify_new_order_telegram.run(order_id=order.id)

    texts = [call.kwargs["json"]["text"] for call in post.call_args_list]
    assert len(texts) == 1
    assert "Новая заявка" in texts[0]
    assert "🔎 Проверка лекарств" in texts[0]
    assert "SKRS: пассивен с 15.04.2025" in texts[0]


@pytest.mark.django_db
@patch("apps.orders.tasks._load_receipt_pdf_from_storage", return_value=None)
@patch("apps.orders.tasks.generate_and_save_receipt", return_value=("", None))
@patch("apps.orders.tasks.requests.post")
def test_retry_reuses_drug_check_text_without_new_requests(post, _gen, _load, settings, web, nexium):
    settings.TELEGRAM_BOT_TOKEN = "test-token"
    settings.TELEGRAM_CHAT_ID = "admin-chat"
    settings.TELEGRAM_ORDERS_CHAT_ID = ""
    post.return_value = SimpleNamespace(status_code=200, ok=True)
    _pages, calls = web
    order = _order_with(nexium.base_product)

    notify_new_order_telegram.run(order_id=order.id, drug_check_text="🔎 готовый итог")

    assert "🔎 готовый итог" in post.call_args.kwargs["json"]["text"]
    assert calls == []
