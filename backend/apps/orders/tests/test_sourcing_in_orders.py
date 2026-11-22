"""Заявка «Найдём товар» ведётся в общем списке «Заказы» (docs/ORDER_PROCESSING.md)."""

import importlib
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from rest_framework.test import APIClient

from apps.orders.admin import OrderAdmin
from apps.orders.models import Order, SourcingRequest
from apps.orders.sourcing import create_order_for_sourcing_request
from apps.orders.tasks import notify_sourcing_request_telegram
from apps.users.models import User

URL = "/api/orders/sourcing-requests/"
PS = Order.ProcessingStatus


def _payload(**overrides):
    data = {
        "source_url": "https://www.trendyol.com/abc/product-p-123",
        "comment": "Нужен размер M",
        "quantity": 2,
        "contact_name": "Анна",
        "contact_phone": "+79990001122",
        "contact_channel": "telegram",
        "contact_username": "@anna_test",
        "locale": "en",
    }
    data.update(overrides)
    return data


def _request_with_order(**extra):
    data = dict(
        source_url="https://example.com/item_1", comment="Кроссовки 42", quantity=2,
        contact_name="Анна", contact_phone="+79990001122", contact_channel="whatsapp",
    )
    data.update(extra)
    req = SourcingRequest.objects.create(**data)
    return req, create_order_for_sourcing_request(req)


def _staff(name):
    return User.objects.create_user(
        username=name, email=f"{name}@example.test", password="x", is_staff=True, is_superuser=True,
    )


@pytest.fixture(autouse=True)
def _no_notifications():
    with patch("apps.orders.views.notify_sourcing_request_telegram.delay") as delay:
        yield delay


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def _change_form_data(page):
    """Данные формы со страницы заявки вместе со строками позиций — как отправит браузер."""
    form = page.context["adminform"].form
    data = {"_save": "Сохранить"}
    for name, field in form.fields.items():
        value = form[name].value()
        data[name] = "" if value is None else value
        if field.show_hidden_initial:
            data[f"initial-{name}"] = data[name]
    for inline in page.context["inline_admin_formsets"]:
        management = inline.formset.management_form
        for name in management.fields:
            data[management.add_prefix(name)] = management[name].value()
        for row in inline.formset.initial_forms:
            for name in row.fields:
                value = row[name].value()
                data[row.add_prefix(name)] = "" if value is None else value
    return data


@pytest.mark.django_db(transaction=True)
def test_form_creates_request_in_orders(_no_notifications):
    response = APIClient().post(URL, _payload(), format="multipart")

    assert response.status_code == 201, response.data
    req = SourcingRequest.objects.get()
    order = Order.objects.get()
    assert response.data == {"id": req.pk}
    assert req.order == order
    assert (order.kind, order.processing_status, order.status) == (Order.Kind.SOURCING, PS.NEW, Order.OrderStatus.NEW)
    assert (order.contact_name, order.contact_phone, order.contact_channel, order.contact_username) == (
        "Анна", "+79990001122", "telegram", "anna_test",
    )
    assert (order.comment, order.locale, order.total_amount) == ("Нужен размер M", "en", Decimal("0"))
    item = order.items.get()
    assert (item.product, item.product_name, item.quantity, item.price, item.source_url) == (
        None, "Нужен размер M", 2, Decimal("0"), "https://www.trendyol.com/abc/product-p-123",
    )
    _no_notifications.assert_called_once_with(req.pk)


@pytest.mark.django_db(transaction=True)
def test_request_without_phone_and_comment_still_gets_into_orders():
    response = APIClient().post(URL, _payload(contact_phone="", comment=""), format="multipart")

    assert response.status_code == 201, response.data
    order = Order.objects.get()
    assert order.contact_phone == ""
    assert order.items.get().product_name == "Товар по ссылке"


@pytest.mark.django_db
def test_repeat_call_does_not_create_second_order():
    req, order = _request_with_order()

    assert create_order_for_sourcing_request(req) == order
    assert Order.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_buyer_profile_does_not_show_sourcing_requests():
    """Для покупателя ничего не меняется: заявки на поиск нет ни в списке заказов, ни в счётчиках."""
    from apps.users.serializers import UserSerializer

    user = User.objects.create_user(username="sourcing-buyer", email="sb@example.test", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.post(URL, _payload(), format="multipart").status_code == 201
    order = Order.objects.get()
    assert order.user == user

    assert client.get("/api/orders/orders").data == []
    assert client.get(f"/api/orders/orders/{order.pk}").status_code == 404
    assert client.get(f"/api/orders/orders/by-number/{order.number}").status_code == 404
    assert UserSerializer().get_total_orders(user) == 0


@pytest.mark.django_db
def test_telegram_notification_links_to_the_request_in_orders(settings):
    settings.TELEGRAM_BOT_TOKEN = "token"
    settings.TELEGRAM_CHAT_ID = "admin-chat"
    req, order = _request_with_order()

    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(ok=True, status_code=200)) as post:
        notify_sourcing_request_telegram.run(req.pk)

    text = post.call_args.kwargs["json"]["text"]
    assert text.startswith(f"🔎 <b>Новая заявка на поиск товара</b> <code>{order.number}</code>\n")
    assert reverse("admin:orders_order_change", args=[order.pk]) in text
    assert "sourcingrequest" not in text
    # В черновике сообщения покупателю — тот же номер, что в «Заказах»
    assert order.number in text.split("wa.me/")[1]


@pytest.mark.django_db
def test_orders_list_shows_type_and_filters_by_it(client, plain_static):
    client.force_login(_staff("so-list"))
    _req, sourcing = _request_with_order()
    cart = Order.objects.create(
        number="SO000001", total_amount=Decimal("10"), currency="RUB", contact_name="Клиент",
        contact_phone="+79990001122",
    )

    body = client.get("/admin/orders/order/").content.decode()
    assert "🔎 Найти товар" in body and "Из Списка" in body
    assert "Кроссовки 42" in body  # слова клиента — в колонке «Состав»

    listing = client.get("/admin/orders/order/?kind__exact=sourcing")
    assert [order.pk for order in listing.context["cl"].result_list] == [sourcing.pk]
    listing = client.get("/admin/orders/order/?kind__exact=cart")
    assert [order.pk for order in listing.context["cl"].result_list] == [cart.pk]


@pytest.mark.django_db
def test_order_page_shows_what_client_is_looking_for(client, plain_static):
    client.force_login(_staff("so-page"))
    _req, sourcing = _request_with_order()
    cart = Order.objects.create(
        number="SO000002", total_amount=Decimal("10"), currency="RUB", contact_name="Клиент",
        contact_phone="+79990001122",
    )

    body = client.get(f"/admin/orders/order/{sourcing.pk}/change/").content.decode()
    assert "Что ищет клиент" in body
    assert 'href="https://example.com/item_1"' in body
    assert "Кроссовки 42" in body
    # Черновик сообщения — с утверждённым текстом заявки на поиск
    assert "%D0%BF%D0%BE%D0%B8%D1%81%D0%BA" in body  # «поиск»

    assert "Что ищет клиент" not in client.get(f"/admin/orders/order/{cart.pk}/change/").content.decode()


@pytest.mark.django_db
def test_manager_enters_found_price_and_fail_reason_without_messages_to_client(client, plain_static):
    """Нашли товар: менеджер вписывает название и цену — суммы считаются; клиенту ничего не уходит."""
    me = _staff("so-price")
    client.force_login(me)
    _req, order = _request_with_order(contact_phone="", contact_channel="telegram", contact_username="anna_tg")
    url = f"/admin/orders/order/{order.pk}/change/"
    data = _change_form_data(client.get(url))
    data.update({
        "items-0-product_name": "Nike Air Max 42", "items-0-price": "1500.50", "currency": "TRY",
        "processing_status": PS.PRICE_SENT, "status": Order.OrderStatus.PROCESSING,
    })

    with patch("apps.orders.admin.notify_order_status_changed.delay") as delay:
        response = client.post(url, data)

    assert response.status_code == 302, response.context["adminform"].form.errors
    delay.assert_not_called()
    order.refresh_from_db()
    item = order.items.get()
    assert (item.product_name, item.price, item.total) == ("Nike Air Max 42", Decimal("1500.50"), Decimal("3001.00"))
    assert (order.subtotal_amount, order.total_amount, order.currency) == (Decimal("3001.00"), Decimal("3001.00"), "TRY")
    assert (order.processing_status, order.assigned_to) == (PS.PRICE_SENT, me)

    data = _change_form_data(client.get(url))
    data.update({"processing_status": PS.CANCELLED, "processing_fail_reason": Order.FailReason.NOT_FOUND})
    assert client.post(url, data).status_code == 302
    order.refresh_from_db()
    assert order.get_processing_fail_reason_display() == "Не нашли товар"


@pytest.mark.django_db
def test_price_of_cart_order_items_stays_read_only(rf):
    from apps.orders.admin import OrderItemInline

    inline = OrderItemInline(Order, AdminSite())
    _req, sourcing = _request_with_order()
    cart = Order(kind=Order.Kind.CART)

    assert "price" in inline.get_readonly_fields(rf.get("/"), cart)
    assert "price" not in inline.get_readonly_fields(rf.get("/"), sourcing)
    assert "currency" in OrderAdmin(Order, AdminSite()).get_readonly_fields(rf.get("/"), cart)


@pytest.mark.django_db
def test_old_section_points_to_orders(client, plain_static):
    client.force_login(_staff("so-old"))
    old = SourcingRequest.objects.create(
        source_url="https://example.com/old", contact_name="Старая", contact_phone="+79990001122",
        status=SourcingRequest.Status.DONE,
    )
    _req, order = _request_with_order()

    body = client.get("/admin/orders/sourcingrequest/").content.decode()
    assert f"Заказы: №{order.number}</a> — Новая" in body
    assert "Найден / оформлен" in body
    assert client.get(f"/admin/orders/sourcingrequest/{old.pk}/change/").status_code == 200


def test_migration_changes_schema_only():
    from django.db import migrations

    migration = importlib.import_module("apps.orders.migrations.0024_sourcing_requests_in_orders")
    kinds = {type(operation) for operation in migration.Migration.operations}
    assert kinds == {migrations.AddField, migrations.AlterField}
