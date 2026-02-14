"""
Celery-задачи для заказов.

TODO: Функционал чеков временно отключен. Будет доработан позже.
Включает: формирование чека, отправку по email, интеграцию с админкой.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

from config.celery import app

from .models import Order
from .services import build_order_receipt_payload, render_receipt_html


# TODO: Функционал чеков временно отключен. Будет доработан позже.
@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=3)
def send_order_receipt_task(
    self, order_id: int, email: str | None = None, locale: str = "ru"
) -> bool:
    """Отправляет чек по заказу на указанный email на языке locale (ru/en)."""
    order = Order.objects.select_related("user").prefetch_related("items").get(id=order_id)

    recipient = email or order.contact_email or (order.user.email if order.user else None)
    if not recipient:
        return False

    loc = "en" if (locale or "").strip().lower() == "en" else "ru"
    receipt = build_order_receipt_payload(order)
    html_body = render_receipt_html(order, receipt, locale=loc)
    text_body = strip_tags(html_body)

    subject = _("Чек по заказу %(number)s") % {"number": order.number}

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@pharmaturk.local"),
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")
    message.send()
    return True


