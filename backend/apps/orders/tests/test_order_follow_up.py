"""Сопровождение заявки: уведомления о статусе, трек-номер (напоминания о Списке заявки — test_cart_reminders.py)."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.orders.models import Order
from apps.users.models import User


def _user(**extra):
    defaults = dict(username=f"fu-{timezone.now().timestamp()}", email="client@example.test", password="x")
    defaults.update(extra)
    return User.objects.create_user(**defaults)


def _order(user, **extra):
    data = dict(
        user=user,
        number=f"FU{int(timezone.now().timestamp() * 1000)}",
        status=Order.OrderStatus.NEW,
        total_amount=Decimal("1500.00"),
        currency="RUB",
        contact_name="Клиент",
        contact_phone="+79990001122",
        contact_email="client@example.test",
        payment_method="manager",
    )
    data.update(extra)
    return Order.objects.create(**data)


@pytest.mark.django_db
def test_shipped_status_message_contains_tracking(settings):
    from apps.orders.tasks import notify_order_status_changed

    settings.TELEGRAM_BOT_TOKEN = "token"
    user = _user(telegram_id="777", telegram_notifications=True)
    order = _order(
        user,
        status=Order.OrderStatus.SHIPPED,
        tracking_number="RB123456789TR",
        tracking_url="https://track.example/RB123456789TR",
    )
    with patch("apps.orders.tasks.requests.post", return_value=SimpleNamespace(ok=True, status_code=200)) as post, \
            patch("apps.orders.tasks.EmailMultiAlternatives.send", return_value=1) as send:
        notify_order_status_changed.run(order.pk)

    text = post.call_args.kwargs["json"]["text"]
    assert post.call_args.kwargs["json"]["chat_id"] == "777"
    assert order.number in text
    assert "RB123456789TR" in text
    send.assert_called_once()


@pytest.mark.django_db
def test_delivered_status_asks_for_review(settings):
    from apps.orders.tasks import build_order_status_message

    user = _user()
    order = _order(user, status=Order.OrderStatus.DELIVERED)

    text = build_order_status_message(order, "ru")

    assert "отзыв" in text.lower()
    assert "/testimonials" in text


@pytest.mark.django_db
def test_status_without_message_sends_nothing(settings):
    from apps.orders.tasks import notify_order_status_changed

    settings.TELEGRAM_BOT_TOKEN = "token"
    user = _user(telegram_id="777", telegram_notifications=True)
    order = _order(user, status=Order.OrderStatus.NEW)
    with patch("apps.orders.tasks.requests.post") as post, \
            patch("apps.orders.tasks.EmailMultiAlternatives.send") as send:
        notify_order_status_changed.run(order.pk)

    post.assert_not_called()
    send.assert_not_called()


@pytest.mark.django_db
def test_admin_status_change_schedules_notification(rf):
    from django.contrib.admin.sites import AdminSite

    from apps.orders.admin import OrderAdmin

    order = _order(_user())
    order.status = Order.OrderStatus.PROCESSING
    form = SimpleNamespace(changed_data=["status"])
    request = rf.post("/admin/")
    request.user = _user(username="fu-admin", email="admin@example.test", is_staff=True, is_superuser=True)
    with patch("apps.orders.admin.notify_order_status_changed.delay") as delay, \
            patch("apps.orders.admin.transaction.on_commit", side_effect=lambda fn: fn()):
        OrderAdmin(Order, AdminSite()).save_model(request, order, form, change=True)

    delay.assert_called_once_with(order.pk)
