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

from apps.orders.admin import OrderAdmin, OrderItemAdmin
from apps.orders.models import Order, OrderItem, OrderProcessingEvent
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
    migration = importlib.import_module("apps.orders.migrations.0021_mark_existing_orders_processing")
    now = timezone.now()
    fresh = _order()
    old = _order()
    cancelled = _order(status=Order.OrderStatus.CANCELLED)
    delivered = _order(status=Order.OrderStatus.DELIVERED)
    touched = _order(status=Order.OrderStatus.PROCESSING)
    Order.objects.filter(pk__in=[old.pk, cancelled.pk]).update(created_at=now - timedelta(days=30))

    migration.mark_existing_orders(django_apps, None)

    statuses = dict(Order.objects.values_list("pk", "processing_status"))
    assert statuses[fresh.pk] == PS.NEW
    assert statuses[old.pk] == PS.DONE
    assert statuses[cancelled.pk] == PS.CANCELLED
    assert statuses[delivered.pk] == PS.DONE
    assert statuses[touched.pk] == PS.IN_PROGRESS


def _change_form_data(page):
    """Данные формы так, как их отправит браузер со страницы, открытой в момент GET."""
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
    return data


@pytest.mark.django_db
def test_stale_change_page_does_not_undo_colleagues_action(client, rf, plain_static):
    """Страница открыта до «Взять в работу» коллеги; её сохранение не откатывает отметку коллеги."""
    me, colleague = _staff("op-stale-me"), _staff("op-stale-colleague")
    order = _order()
    client.force_login(me)
    url = f"/admin/orders/order/{order.pk}/change/"
    data = _change_form_data(client.get(url))  # «Новая», без ответственного

    _admin().take_in_work(_request(rf, colleague), Order.objects.filter(pk=order.pk))
    data["comment"] = "уточнить адрес"
    response = client.post(url, data)

    assert response.status_code == 302, response.context["adminform"].form.errors
    order.refresh_from_db()
    assert (order.processing_status, order.assigned_to, order.comment) == (PS.IN_PROGRESS, colleague, "уточнить адрес")
    assert order.processing_events.count() == 1


@pytest.mark.django_db
def test_change_page_post_sets_processing_and_logs(client, plain_static):
    me = _staff("op-post-me")
    order = _order()
    client.force_login(me)
    url = f"/admin/orders/order/{order.pk}/change/"
    data = _change_form_data(client.get(url))
    data["processing_status"] = PS.WAITING_CLIENT

    response = client.post(url, data)

    assert response.status_code == 302, response.context["adminform"].form.errors
    order.refresh_from_db()
    assert (order.processing_status, order.assigned_to) == (PS.WAITING_CLIENT, me)
    assert order.processing_events.get().new_status == PS.WAITING_CLIENT


@pytest.mark.django_db
def test_admin_created_order_is_logged(rf):
    me = _staff("op-creator")
    obj = Order(number="OP-CREATE", total_amount=Decimal("1"), currency="RUB", contact_name="К", contact_phone="1",
                processing_status=PS.IN_PROGRESS)
    _admin().save_model(_request(rf, me), obj, SimpleNamespace(changed_data=["processing_status"]), change=False)

    event = obj.processing_events.get()
    assert (event.old_status, event.new_status, event.new_assigned_to) == (PS.NEW, PS.IN_PROGRESS, me)


@pytest.mark.django_db
def test_view_only_staff_has_no_processing_actions(rf):
    from django.contrib.auth.models import Permission

    viewer = User.objects.create_user(username="op-viewer", email="op-viewer@example.test", password="x", is_staff=True)
    viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
    actions = _admin().get_actions(_request(rf, viewer))
    assert not {"take_in_work", "mark_waiting_client", "mark_done"} & set(actions)


@pytest.mark.django_db
def test_assignee_choices_keep_current_even_without_staff_access(rf):
    me = _staff("op-form-me")
    former = User.objects.create_user(username="op-former", email="op-former@example.test", password="x")
    outsider = User.objects.create_user(username="op-outsider", email="op-outsider@example.test", password="x")
    order = _order(assigned_to=former)

    form_class = _admin().get_form(_request(rf, me), order)
    choices = set(form_class.base_fields["assigned_to"].queryset)
    assert me in choices and former in choices and outsider not in choices


@pytest.mark.django_db
def test_odd_assigned_filter_value_does_not_crash(rf):
    me = _staff("op-odd")
    _order()
    request = _request(rf, me, data={"assigned": "²"})
    cl = _admin().get_changelist_instance(request)
    assert cl.get_queryset(request).count() == 1


@pytest.mark.django_db
def test_other_admins_with_order_link_still_open(client, rf, plain_static):
    """Сортировка заказов по «Обработке» не ломает формы, где выбирают заказ (позиции, криптоплатежи)."""
    me = _staff("op-related")
    order = _order()
    item = OrderItem.objects.create(order=order, product_name="Товар", price=Decimal("1"), quantity=1, total=Decimal("1"))

    field = OrderItemAdmin(OrderItem, AdminSite()).formfield_for_foreignkey(
        OrderItem._meta.get_field("order"), _request(rf, me)
    )
    assert list(field.queryset) == [order]

    client.force_login(me)
    assert client.get(f"/admin/orders/orderitem/{item.pk}/change/").status_code == 200
    assert client.get("/admin/orders/order/?o=2").status_code == 200
    assert client.get("/admin/payments/cryptopayment/add/").status_code == 200
