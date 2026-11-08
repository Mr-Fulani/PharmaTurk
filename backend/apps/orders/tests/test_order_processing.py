"""Отметка «Обработка» заявки в админке: статус для менеджеров, ответственный, журнал, список."""

import importlib
from datetime import timedelta
from decimal import Decimal
from itertools import count
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils import timezone

from apps.orders.admin import OrderAdmin
from apps.orders.models import Order, OrderProcessingEvent
from apps.users.models import User

PS = Order.ProcessingStatus
_seq = count(1)


def _staff(name):
    return User.objects.create_user(username=name, email=f"{name}@example.test", password="x", is_staff=True, is_superuser=True)


def _order(**extra):
    n = next(_seq)
    data = dict(
        number=f"OP{n:06d}",
        total_amount=Decimal("1000.00"),
        currency="RUB",
        contact_name="Клиент",
        contact_phone="+79990001122",
        payment_method="manager",
    )
    data.update(extra)
    return Order.objects.create(**data)


def _request(rf, user, path="/admin/orders/order/", data=None):
    request = rf.get(path, data or {})
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def _admin():
    return OrderAdmin(Order, AdminSite())


@pytest.mark.django_db
def test_new_order_is_new_and_unassigned():
    order = _order()
    assert order.processing_status == PS.NEW
    assert order.assigned_to is None


@pytest.mark.django_db
def test_take_in_work_assigns_me_logs_and_does_not_notify_client(rf):
    me = _staff("op-me")
    order = _order()
    admin = _admin()
    with patch("apps.orders.admin.notify_order_status_changed.delay") as delay:
        admin.take_in_work(_request(rf, me), Order.objects.filter(pk=order.pk))

    order.refresh_from_db()
    assert order.processing_status == PS.IN_PROGRESS
    assert order.assigned_to == me
    assert order.status == Order.OrderStatus.NEW  # клиентский статус не тронут
    delay.assert_not_called()
    event = OrderProcessingEvent.objects.get(order=order)
    assert (event.actor, event.old_status, event.new_status) == (me, PS.NEW, PS.IN_PROGRESS)
    assert (event.old_assigned_to, event.new_assigned_to) == (None, me)


@pytest.mark.django_db
def test_mark_done_keeps_existing_assignee_and_logs_who_did_it(rf):
    owner, colleague = _staff("op-owner"), _staff("op-colleague")
    order = _order(processing_status=PS.IN_PROGRESS, assigned_to=owner)

    _admin().mark_done(_request(rf, colleague), Order.objects.filter(pk=order.pk))

    order.refresh_from_db()
    assert order.processing_status == PS.DONE
    assert order.assigned_to == owner
    event = order.processing_events.get()
    assert event.actor == colleague
    assert (event.old_status, event.new_status) == (PS.IN_PROGRESS, PS.DONE)


@pytest.mark.django_db
def test_action_without_assignee_assigns_actor_and_repeat_is_not_logged(rf):
    me = _staff("op-waiter")
    order = _order()
    admin = _admin()

    admin.mark_waiting_client(_request(rf, me), Order.objects.filter(pk=order.pk))
    admin.mark_waiting_client(_request(rf, me), Order.objects.filter(pk=order.pk))

    order.refresh_from_db()
    assert order.processing_status == PS.WAITING_CLIENT
    assert order.assigned_to == me
    assert order.processing_events.count() == 1


@pytest.mark.django_db
def test_edit_form_change_is_logged_auto_assigned_and_silent_for_client(rf):
    me = _staff("op-editor")
    order = _order()
    obj = Order.objects.get(pk=order.pk)
    obj.processing_status = PS.IN_PROGRESS
    form = SimpleNamespace(changed_data=["processing_status"])
    with patch("apps.orders.admin.notify_order_status_changed.delay") as delay, \
            patch("apps.orders.admin.transaction.on_commit", side_effect=lambda fn: fn()):
        _admin().save_model(_request(rf, me), obj, form, change=True)

    order.refresh_from_db()
    assert order.processing_status == PS.IN_PROGRESS
    assert order.assigned_to == me
    delay.assert_not_called()
    event = order.processing_events.get()
    assert (event.actor, event.old_status, event.new_status, event.new_assigned_to) == (me, PS.NEW, PS.IN_PROGRESS, me)


@pytest.mark.django_db
def test_edit_form_client_status_change_still_notifies_without_processing_log(rf):
    me = _staff("op-client-status")
    order = _order()
    obj = Order.objects.get(pk=order.pk)
    obj.status = Order.OrderStatus.PROCESSING
    form = SimpleNamespace(changed_data=["status"])
    with patch("apps.orders.admin.notify_order_status_changed.delay") as delay, \
            patch("apps.orders.admin.transaction.on_commit", side_effect=lambda fn: fn()):
        _admin().save_model(_request(rf, me), obj, form, change=True)

    delay.assert_called_once_with(order.pk)
    assert not order.processing_events.exists()


@pytest.mark.django_db
def test_changelist_puts_open_orders_first_and_filters(rf):
    me, other = _staff("op-list-me"), _staff("op-list-other")
    now = timezone.now()
    done = _order(processing_status=PS.DONE, assigned_to=me)
    new_old = _order()
    new_fresh = _order()
    waiting = _order(processing_status=PS.WAITING_CLIENT, assigned_to=other)
    in_work = _order(processing_status=PS.IN_PROGRESS, assigned_to=me)
    Order.objects.filter(pk=new_old.pk).update(created_at=now - timedelta(days=2))
    Order.objects.filter(pk=done.pk).update(created_at=now + timedelta(minutes=5))

    admin = _admin()

    def numbers(params=None):
        request = _request(rf, me, data=params)
        cl = admin.get_changelist_instance(request)
        return [o.number for o in cl.get_queryset(request)]

    assert numbers() == [new_fresh.number, new_old.number, in_work.number, waiting.number, done.number]
    assert set(numbers({"processing": "open"})) == {new_fresh.number, new_old.number, in_work.number, waiting.number}
    assert set(numbers({"processing": PS.DONE})) == {done.number}
    assert set(numbers({"assigned": "me"})) == {done.number, in_work.number}
    assert set(numbers({"assigned": "none"})) == {new_fresh.number, new_old.number}
    assert set(numbers({"assigned": str(other.pk)})) == {waiting.number}


@pytest.fixture
def plain_static(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.mark.django_db
def test_changelist_and_change_page_render(client, rf, plain_static):
    me = _staff("op-render")
    order = _order()
    client.force_login(me)
    _admin().take_in_work(_request(rf, me), Order.objects.filter(pk=order.pk))

    listing = client.get("/admin/orders/order/")
    assert listing.status_code == 200
    assert "В работе" in listing.content.decode()

    page = client.get(f"/admin/orders/order/{order.pk}/change/")
    body = page.content.decode()
    assert page.status_code == 200
    assert "История обработки" in body
    assert "Новая → В работе" in body


@pytest.mark.django_db
def test_migration_marks_existing_orders():
    migration = importlib.import_module("apps.orders.migrations.0020_order_processing")
    now = timezone.now()
    fresh = _order()
    old = _order()
    cancelled = _order(status=Order.OrderStatus.CANCELLED)
    delivered = _order(status=Order.OrderStatus.DELIVERED)
    Order.objects.filter(pk__in=[old.pk, cancelled.pk]).update(created_at=now - timedelta(days=30))

    migration.mark_existing_orders(django_apps, None)

    statuses = dict(Order.objects.values_list("pk", "processing_status"))
    assert statuses[fresh.pk] == PS.NEW
    assert statuses[old.pk] == PS.DONE
    assert statuses[cancelled.pk] == PS.CANCELLED
    assert statuses[delivered.pk] == PS.DONE
