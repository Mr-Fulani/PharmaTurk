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

import requests
import logging

from config.celery import app

logger = logging.getLogger(__name__)

from .models import Order
from .services import build_order_receipt_payload, render_receipt_html, generate_and_save_receipt, get_receipt_filename


# TODO: Функционал чеков временно отключен. Будет доработан позже.
@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=3)
def send_order_receipt_task(
    self, order_id: int, email: str | None = None, locale: str = "ru"
) -> bool:
    """Отправляет чек по заказу на указанный email на языке locale (ru/en)."""
    order = Order.objects.select_related("user").prefetch_related("items").get(id=order_id)

    recipient = email or order.contact_email or (order.user.email if order.user else None)
    if not recipient:
        logger.warning("No recipient email found for order %s", order.number)
        return False

    logger.info("Sending receipt email for order %s to %s", order.number, recipient)
    
    loc = "en" if (locale or "").strip().lower() == "en" else "ru"
    receipt = build_order_receipt_payload(order, locale=loc)
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

    # Call the service to generate the PDF and upload to R2
    # It will also update the order.receipt_url
    try:
        receipt_url, pdf_content = generate_and_save_receipt(order, locale=loc)
        if pdf_content:
            message.attach(get_receipt_filename(order), pdf_content, "application/pdf")
            logger.info("PDF receipt attached to email for order %s", order.number)
    except Exception as e:
        logger.error("Failed to generate/attach PDF receipt for order %s: %s", order.number, e)

    try:
        message.send()
        logger.info("Receipt email successfully sent for order %s to %s", order.number, recipient)
    except Exception as e:
        logger.error("SMTP error sending receipt for order %s to %s: %s", order.number, recipient, e)
        raise  # Retry via Celery

    return True

@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=3)
def notify_new_order_telegram(self, _email_result=None, order_id: int = None, locale: str = 'ru') -> None:
    """Уведомляет (Telegram) о создании нового заказа.
    Может запускаться как Celery link после send_order_receipt_task — тогда первым аргументом
    приходит результат предыдущей задачи (_email_result), который игнорируется.
    PDF чека берётся из order.receipt_url (уже загружен в R2 email-задачей).
    """
    if order_id is None:
        logger.warning("notify_new_order_telegram: order_id not provided")
        return
    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("notify_new_order_telegram: order %s not found", order_id)
        return

    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    admin_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""

    user = order.user
    user_chat_id = ""
    if user:
        utg = getattr(user, "telegram_id", None) or ""
        if utg:
            user_chat_id = str(utg).strip()

    is_ru = locale != "en"

    # Получаем PDF-чек (если он уже был сгенерирован email-задачей или генерируем сейчас)
    pdf_bytes: bytes | None = None
    receipt_url = getattr(order, "receipt_url", None)
    
    if not receipt_url:
        # Если URL еще нет (задачи запущены параллельно), попробуем сгенерировать сами
        receipt_url, pdf_bytes = generate_and_save_receipt(order, locale=locale)
    
    if receipt_url and not pdf_bytes:
        try:
            r = requests.get(receipt_url, timeout=15)
            if r.ok:
                pdf_bytes = r.content
            else:
                logger.warning("Could not download receipt PDF for order %s: %s", order.number, r.status_code)
        except Exception as dl_err:
            logger.warning("Error downloading receipt PDF for order %s: %s", order.number, dl_err)

    def _send_tg(chat_id: str, text: str, document: bytes | None = None, filename: str = "receipt.pdf"):
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not set!")
            return
        if not chat_id:
            logger.warning("Telegram chat_id is missing, skipping notification")
            return
        try:
            base_url = f"https://api.telegram.org/bot{bot_token}/"
            if document:
                files = {"document": (filename, document, "application/pdf")}
                data = {"chat_id": chat_id, "caption": text, "parse_mode": "Markdown"}
                resp = requests.post(base_url + "sendDocument", data=data, files=files, timeout=20)
            else:
                json_data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
                resp = requests.post(base_url + "sendMessage", json=json_data, timeout=10)

            if not resp.ok:
                logger.warning("Telegram notification failed for order %s: %s", order.number, resp.text)
            else:
                logger.info("Telegram notification sent for order %s → chat_id=%s", order.number, chat_id)
        except requests.RequestException as e:
            logger.warning("Telegram send error for order %s: %s", order.number, e)

    from .services import translate_method, PAYMENT_METHOD_TRANSLATIONS, SHIPPING_METHOD_TRANSLATIONS

    filename = get_receipt_filename(order)

    # Уведомление админу
    if admin_chat_id:
        payment_info = translate_method(order.payment_method, PAYMENT_METHOD_TRANSLATIONS, "ru")
        delivery_info = translate_method(order.shipping_method, SHIPPING_METHOD_TRANSLATIONS, "ru")
        admin_text = (
            f"📦 *Новый заказ!*\n"
            f"Заказ: `{order.number}`\n"
            f"Сумма: {order.total_amount} {order.currency}\n"
            f"Оплата: {payment_info}\n"
            f"Доставка: {delivery_info}"
        )
        _send_tg(admin_chat_id, admin_text, document=pdf_bytes, filename=filename)

    # Уведомление покупателю
    if user_chat_id and user_chat_id != admin_chat_id:
        payment_info_user = translate_method(order.payment_method, PAYMENT_METHOD_TRANSLATIONS, locale)
        delivery_info_user = translate_method(order.shipping_method, SHIPPING_METHOD_TRANSLATIONS, locale)

        if is_ru:
            user_text = (
                f"✅ *Ваш заказ успешно оформлен!*\n"
                f"Заказ: `{order.number}`\n"
                f"Сумма: {order.total_amount} {order.currency}\n"
                f"Способ доставки: {delivery_info_user}\n\n"
                f"Мы уже занимаемся его сборкой!"
            )
        else:
            user_text = (
                f"✅ *Your order has been placed successfully!*\n"
                f"Order: `{order.number}`\n"
                f"Amount: {order.total_amount} {order.currency}\n"
                f"Shipping method: {delivery_info_user}\n\n"
                f"We are already assembling it!"
            )
        _send_tg(user_chat_id, user_text, document=pdf_bytes, filename=filename)
