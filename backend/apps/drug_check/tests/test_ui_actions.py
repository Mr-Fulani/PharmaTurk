"""Заметная проверка в админке и ручные действия: принять цену IlacFiyati, сменить наличие (TD-044, шаг 3)."""

import re
import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.catalog.models import MedicineProduct, PriceHistory, Product
from apps.drug_check.actions import PRICE_HISTORY_SOURCE
from apps.drug_check.sources.selcuk import SelcukSource
from apps.drug_check.sources.skrs import SkrsSource
from apps.scrapers.parsers.ilacfiyati import IlacFiyatiParser

from .fixtures import ilacfiyati_card, selcuk_xlsx, skrs_xlsx

NEXIUM_URL = "https://ilacfiyati.com/ilaclar/nexium-40-mg-enterik-kapli-14-pellet-tablet"


@pytest.fixture(autouse=True)
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def lists(db):
    SkrsSource().load_content(skrs_xlsx(), file_name="skrs.xlsx", file_date=date(2026, 11, 10))
    SelcukSource().load_content(selcuk_xlsx(), file_name="WEBLISTE-13-10-2026.xlsx", file_date=date(2026, 10, 13))


@pytest.fixture
def web(monkeypatch):
    """IlacFiyati без сети: у источника цена 210,00 TL (у нас 202,15)."""
    pages, calls = {NEXIUM_URL: ilacfiyati_card(price="210,00 TL")}, []

    def fake_request(self, url, **kwargs):
        calls.append(url)
        return pages.get(url)

    monkeypatch.setattr(IlacFiyatiParser, "_make_request", fake_request)
    return pages, calls


@pytest.fixture
def nexium(db):
    medicine = MedicineProduct.objects.create(
        name="NEXIUM (эзомепразол) 40 мг, 14 таб.",
        slug=f"nexium-{time.monotonic_ns()}",
        barcode="8699786040021",
        price=Decimal("202.15"),
        old_price=Decimal("250.00"),
        currency="TRY",
        is_active=True,
        is_available=True,
        external_url=NEXIUM_URL,
    )
    medicine.refresh_from_db()
    return medicine


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("dc-ui-admin", "dc-ui@example.com", "x" * 20))
    return client


def _viewer(client, django_user_model, *codenames):
    user = django_user_model.objects.create_user(
        username=f"viewer-{time.monotonic_ns()}", email="v@example.com", password="x" * 20, is_staff=True
    )
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="catalog", codename__in=codenames))
    client.force_login(user)
    return client


def _offer_token(admin_client, nexium):
    html = admin_client.get(reverse("admin:drug_check_medicine", args=[nexium.pk])).content.decode()
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match, "в окне проверки нет кнопки «Принять цену»"
    return match.group(1)


# ── заметность ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_change_form_has_panel_above_fields_without_external_requests(admin_client, lists, web, nexium):
    _pages, calls = web

    html = admin_client.get(reverse("admin:catalog_medicineproduct_change", args=[nexium.pk])).content.decode()

    assert "Наличие и цена: проверка по источникам" in html
    assert html.index("dc-panel") < html.index('name="name"')  # панель над полями
    assert reverse("admin:drug_check_medicine", args=[nexium.pk]) in html
    assert "dc-panel--alert" in html  # SKRS: пассивен, а у нас «в наличии»
    assert "пассивен с 15.04.2025" in html
    assert calls == []  # карточка открывается без запросов к источнику


@pytest.mark.django_db
def test_add_form_has_no_panel(admin_client, lists):
    html = admin_client.get(reverse("admin:catalog_medicineproduct_add")).content.decode()

    assert "Наличие и цена: проверка по источникам" not in html


@pytest.mark.django_db
def test_changelist_row_has_check_link(admin_client, lists, nexium):
    html = admin_client.get(reverse("admin:catalog_medicineproduct_changelist")).content.decode()

    assert reverse("admin:drug_check_medicine", args=[nexium.pk]) in html
    assert ">Проверить</a>" in html


@pytest.mark.django_db
def test_admin_index_has_search_box_and_menu_item(admin_client):
    html = admin_client.get(reverse("admin:index")).content.decode()
    lookup = reverse("admin:drug_check_lookup")

    assert "Проверить лекарство: продаётся ли и какая цена" in html
    assert f'action="{lookup}"' in html
    assert "Проверить лекарство (название или штрихкод)" in html  # пункт меню группы
    assert html.index("Проверка лекарств") < html.index("Заказы и корзины")


@pytest.mark.django_db
def test_index_hides_search_without_medicine_permission(client, django_user_model):
    _viewer(client, django_user_model)

    html = client.get(reverse("admin:index")).content.decode()

    assert "Проверить лекарство: продаётся ли и какая цена" not in html


# ── принять цену ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_check_offers_ilacfiyati_price_and_confirm_page_changes_nothing(admin_client, lists, web, nexium):
    page = admin_client.get(reverse("admin:drug_check_medicine", args=[nexium.pk])).content.decode()
    assert "Принять цену 210,00 TL (IlacFiyati, цена от 01.04.2026)" in page
    assert "Отметить: нет в наличии" in page
    assert "в карточку её не принимаем" in page

    token = _offer_token(admin_client, nexium)
    confirm = admin_client.get(reverse("admin:drug_check_price", args=[nexium.pk]), {"token": token})

    html = confirm.content.decode()
    assert confirm.status_code == 200
    assert "202,15 TL" in html and "210,00 TL" in html
    assert "csrfmiddlewaretoken" in html
    nexium.refresh_from_db()
    assert nexium.price == Decimal("202.15")


@pytest.mark.django_db
def test_post_applies_price_through_save_recalculates_and_logs(admin_client, lists, web, nexium):
    token = _offer_token(admin_client, nexium)
    _pages, calls = web
    calls.clear()

    response = admin_client.post(reverse("admin:drug_check_price", args=[nexium.pk]), {"token": token})

    assert response.status_code == 302
    assert calls == []  # цена из проверки, не новым запросом
    nexium.refresh_from_db()
    product = Product.objects.get(pk=nexium.base_product_id)
    assert (nexium.price, nexium.currency, nexium.old_price) == (Decimal("210.00"), "TRY", None)
    assert (product.price, product.old_price) == (Decimal("210.00"), None)
    assert product.price_info.base_price == Decimal("210.00")  # цены в валютах пересчитаны
    assert product.price_info.rub_price == Decimal("420.00")  # тестовый курс: 10 TRY = 20 RUB
    history = PriceHistory.objects.get(product=product, source=PRICE_HISTORY_SOURCE)
    assert history.price == Decimal("210.00")
    entry = LogEntry.objects.get(object_id=str(nexium.pk), action_flag=CHANGE)
    assert entry.user.username == "dc-ui-admin"
    assert "цена 202,15 TL → 210,00 TL" in entry.get_change_message()
    assert "IlacFiyati" in entry.get_change_message()


@pytest.mark.django_db
def test_forged_or_foreign_price_token_is_refused(admin_client, lists, web, nexium):
    other = MedicineProduct.objects.create(name="Другое", slug=f"other-{time.monotonic_ns()}", price=Decimal("5"),
                                           currency="TRY")
    token = _offer_token(admin_client, nexium)

    forged = admin_client.post(reverse("admin:drug_check_price", args=[nexium.pk]), {"token": token[:-2] + "xx"})
    foreign = admin_client.post(reverse("admin:drug_check_price", args=[other.pk]), {"token": token})

    assert forged.status_code == foreign.status_code == 302
    nexium.refresh_from_db()
    other.refresh_from_db()
    assert nexium.price == Decimal("202.15")
    assert other.price == Decimal("5.00")
    assert not LogEntry.objects.exists()


@pytest.mark.django_db
def test_hospital_medicine_gets_no_price_offer_and_post_is_refused(admin_client, lists, web, nexium):
    token = _offer_token(admin_client, nexium)
    MedicineProduct.objects.filter(pk=nexium.pk).update(is_hospital=True)

    page = admin_client.get(reverse("admin:drug_check_medicine", args=[nexium.pk])).content.decode()
    response = admin_client.post(reverse("admin:drug_check_price", args=[nexium.pk]), {"token": token})

    assert "цену не принимаем" in page
    assert 'name="token"' not in page
    assert response.status_code == 302
    nexium.refresh_from_db()
    assert nexium.price == Decimal("202.15")


@pytest.mark.django_db
def test_same_price_offers_nothing(admin_client, lists, web, nexium):
    web[0][NEXIUM_URL] = ilacfiyati_card(price="202,15 TL")

    page = admin_client.get(reverse("admin:drug_check_medicine", args=[nexium.pk])).content.decode()

    assert "совпадает с IlacFiyati" in page
    assert 'name="token"' not in page


# ── наличие ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_availability_confirm_then_post_syncs_product_and_logs(admin_client, lists, web, nexium):
    url = reverse("admin:drug_check_availability", args=[nexium.pk])

    confirm = admin_client.get(url, {"to": "0"}).content.decode()
    nexium.refresh_from_db()
    assert nexium.is_available is True
    assert "в наличии" in confirm and "нет в наличии" in confirm
    assert "пассивен с 15.04.2025" in confirm  # подсказка по спискам

    response = admin_client.post(url, {"to": "0"})

    assert response.status_code == 302
    nexium.refresh_from_db()
    assert nexium.is_available is False
    assert Product.objects.get(pk=nexium.base_product_id).is_available is False
    assert nexium.is_active is True  # видимость не трогаем
    message = LogEntry.objects.get(object_id=str(nexium.pk)).get_change_message()
    assert "наличие «в наличии» → «нет в наличии»" in message


# ── права и методы ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_view_only_user_sees_check_but_no_actions_and_cannot_post(client, django_user_model, lists, web, nexium):
    _viewer(client, django_user_model, "view_medicineproduct")

    page = client.get(reverse("admin:drug_check_medicine", args=[nexium.pk]))
    post = client.post(reverse("admin:drug_check_availability", args=[nexium.pk]), {"to": "0"})
    confirm = client.get(reverse("admin:drug_check_availability", args=[nexium.pk]), {"to": "0"})

    assert page.status_code == 200
    assert "Принять цену" not in page.content.decode()
    assert "Отметить:" not in page.content.decode()
    assert post.status_code == confirm.status_code == 403
    nexium.refresh_from_db()
    assert nexium.is_available is True


@pytest.mark.django_db
def test_post_without_csrf_is_rejected(client, django_user_model, lists, nexium):
    from django.test import Client

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(django_user_model.objects.create_superuser("dc-csrf", "csrf@example.com", "x" * 20))

    response = csrf_client.post(reverse("admin:drug_check_availability", args=[nexium.pk]), {"to": "0"})

    assert response.status_code == 403
    nexium.refresh_from_db()
    assert nexium.is_available is True
