"""
Celery-задачи для заказов.

TODO: Функционал чеков временно отключен. Будет доработан позже.
Включает: формирование чека, отправку по email, интеграцию с админкой.
"""
from __future__ import annotations

import base64
import logging
import socket

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

from config.celery import app

logger = logging.getLogger(__name__)

from .models import Order
from .services import (
    build_order_receipt_payload,
    render_receipt_html,
    generate_and_save_receipt,
    get_receipt_filename,
    get_order_customer_email,
)


class IPv4EmailBackend(EmailBackend):
    # Используем IPv4-адреса, если окружение не умеет в IPv6
    def open(self):
        if self.connection:
            return False
        try:
            # Разрешаем хост только в IPv4, чтобы обойти проблемы IPv6 в контейнере
            addrinfo = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
            if not addrinfo:
                raise socket.error(f"Could not resolve IPv4 for {self.host}")
            # Пробуем несколько IPv4-адресов, если один из них не отвечает
            last_error = None
            per_attempt_timeout = min(self.timeout or 30, 8)
            for entry in addrinfo:
                ipv4_addr = entry[4][0]
                try:
                    logger.info(f"Connecting to {self.host} via IPv4: {ipv4_addr}")
                    self.connection = self.connection_class(ipv4_addr, self.port, timeout=per_attempt_timeout)
                    if self.use_tls and not self.use_ssl:
                        # Передаем исходный hostname для корректной TLS-валидации сертификата
                        self.connection.starttls(server_hostname=self.host)
                    if self.username and self.password:
                        self.connection.login(self.username, self.password)
                    return True
                except Exception as e:
                    last_error = e
                    logger.warning(f"IPv4 адрес недоступен: {ipv4_addr} ({str(e)})")
                    self.connection = None
            if last_error:
                raise last_error
            return False
        except Exception:
            if not self.fail_silently:
                raise
            return False


def _send_email_with_ipv4_fallback(message) -> None:
    # Сначала пытаемся отправить через API, если он настроен
    if _send_email_via_api(message):
        return

    # Дальше используем стандартную отправку Django
    try:
        message.send()
        return
    except (socket.gaierror, socket.error, OSError) as net_err:
        # При сетевой ошибке переключаемся на IPv4
        logger.warning(f"Network error detected ({str(net_err)}). Forcing IPv4 fallback...")

    connection = IPv4EmailBackend(
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        use_ssl=settings.EMAIL_USE_SSL,
        timeout=settings.EMAIL_TIMEOUT,
    )
    message.connection = connection
    message.send()


def _extract_message_parts(message):
    # Готовим единый набор данных для API‑провайдеров
    from_email = (getattr(settings, "EMAIL_API_FROM", "") or "").strip() or getattr(settings, "DEFAULT_FROM_EMAIL", "")
    to_emails = list(getattr(message, "to", []) or [])
    subject = getattr(message, "subject", "") or ""
    text_body = getattr(message, "body", "") or ""
    html_body = None
    for alt, mimetype in (getattr(message, "alternatives", []) or []):
        if mimetype == "text/html":
            html_body = alt
            break

    attachments = []
    for attachment in getattr(message, "attachments", []) or []:
        if not isinstance(attachment, tuple) or len(attachment) < 2:
            continue
        filename = attachment[0]
        raw_content = attachment[1]
        mimetype = attachment[2] if len(attachment) > 2 else "application/octet-stream"
        if raw_content is None:
            continue
        if isinstance(raw_content, str):
            raw_bytes = raw_content.encode("utf-8")
        elif isinstance(raw_content, (bytes, bytearray)):
            raw_bytes = bytes(raw_content)
        else:
            raw_bytes = bytes(raw_content)
        attachments.append(
            {
                "filename": filename,
                "mimetype": mimetype,
                "content_b64": base64.b64encode(raw_bytes).decode("ascii"),
            }
        )

    return from_email, to_emails, subject, text_body, html_body, attachments


def _send_email_via_sendgrid(message) -> bool:
    # Надежная отправка через SendGrid API
    api_key = getattr(settings, "SENDGRID_API_KEY", "") or ""
    if not api_key:
        return False

    from_email, to_emails, subject, text_body, html_body, attachments = _extract_message_parts(message)
    if not to_emails:
        return False

    content = [{"type": "text/plain", "value": text_body}]
    if html_body:
        content.append({"type": "text/html", "value": html_body})

    payload = {
        "personalizations": [{"to": [{"email": e} for e in to_emails]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": content,
    }
    if attachments:
        payload["attachments"] = [
            {
                "content": item["content_b64"],
                "type": item["mimetype"],
                "filename": item["filename"],
                "disposition": "attachment",
            }
            for item in attachments
        ]

    timeout = getattr(settings, "EMAIL_API_TIMEOUT", 15)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers, timeout=timeout)
        if resp.status_code in (200, 202):
            logger.info("Email sent via SendGrid API")
            return True
        logger.error("SendGrid API failed: %s %s", resp.status_code, resp.text[:500])
        return False
    except Exception as e:
        logger.error("SendGrid API error: %s", str(e))
        return False


def _send_email_via_smtp2go(message) -> bool:
    # Отправка через SMTP2GO API — устойчиво к блокировкам SMTP‑портов
    api_key = getattr(settings, "SMTP2GO_API_KEY", "") or ""
    if not api_key:
        return False

    from_email, to_emails, subject, text_body, html_body, attachments = _extract_message_parts(message)
    if not to_emails:
        return False

    payload = {
        "api_key": api_key,
        "sender": from_email,
        "to": to_emails,
        "subject": subject,
        "text_body": text_body,
    }
    if html_body:
        payload["html_body"] = html_body
    if attachments:
        payload["attachments"] = [
            {
                "filename": item["filename"],
                "fileblob": item["content_b64"],
                "mimetype": item["mimetype"],
            }
            for item in attachments
        ]

    base_url = (getattr(settings, "SMTP2GO_API_URL", "") or "https://api.smtp2go.com/v3").rstrip("/")
    timeout = getattr(settings, "EMAIL_API_TIMEOUT", 15)
    headers = {"X-Smtp2go-Api-Key": api_key, "Content-Type": "application/json", "Accept": "application/json"}
    try:
        resp = requests.post(f"{base_url}/email/send", json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            logger.info("Email sent via SMTP2GO API")
            return True
        logger.error("SMTP2GO API failed: %s %s", resp.status_code, resp.text[:500])
        return False
    except Exception as e:
        logger.error("SMTP2GO API error: %s", str(e))
        return False


def _send_email_via_resend(message) -> bool:
    # Отправка через Resend API (HTTP), без зависимости от SMTP‑портов
    api_key = getattr(settings, "RESEND_API_KEY", "") or ""
    if not api_key:
        return False

    from_email, to_emails, subject, text_body, html_body, attachments = _extract_message_parts(message)
    if not to_emails:
        return False

    payload = {
        "from": from_email,
        "to": to_emails,
        "subject": subject,
    }
    if text_body:
        payload["text"] = text_body
    if html_body:
        payload["html"] = html_body
    if attachments:
        payload["attachments"] = [
            {
                "filename": item["filename"],
                "content": item["content_b64"],
                "content_type": item["mimetype"],
            }
            for item in attachments
        ]

    base_url = (getattr(settings, "RESEND_API_URL", "") or "https://api.resend.com").rstrip("/")
    user_agent = getattr(settings, "RESEND_USER_AGENT", "") or "mudaroba/1.0"
    timeout = getattr(settings, "EMAIL_API_TIMEOUT", 15)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }
    try:
        resp = requests.post(f"{base_url}/emails", json=payload, headers=headers, timeout=timeout)
        if resp.status_code in (200, 201):
            logger.info("Email sent via Resend API")
            return True
        logger.error("Resend API failed: %s %s", resp.status_code, resp.text[:500])
        return False
    except Exception as e:
        logger.error("Resend API error: %s", str(e))
        return False


def _send_email_via_api(message) -> bool:
    # Выбор провайдера API отправки
    provider = (getattr(settings, "EMAIL_API_PROVIDER", "") or "").strip().lower()
    if provider:
        logger.info("Email API provider enabled: %s", provider)
    if provider == "sendgrid":
        return _send_email_via_sendgrid(message)
    if provider == "smtp2go":
        return _send_email_via_smtp2go(message)
    if provider == "resend":
        return _send_email_via_resend(message)
    return False


# TODO: Функционал чеков временно отключен. Будет доработан позже.
@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=60, max_retries=3)
def send_order_receipt_task(
    self, order_id: int, email: str | None = None, locale: str = "ru"
) -> bool:
    """Отправляет чек по заказу на указанный email на языке locale (ru/en)."""
    order = Order.objects.select_related("user").prefetch_related("items").get(id=order_id)

    # Выбираем email покупателя, избегая отправки на админские адреса
    recipient = email or get_order_customer_email(order)
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
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@mudaroba.local"),
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")

    # Генерируем PDF и сохраняем в R2, а также обновляем order.receipt_url
    try:
        receipt_url, pdf_content = generate_and_save_receipt(order, locale=loc)
        if pdf_content:
            message.attach(get_receipt_filename(order), pdf_content, "application/pdf")
            logger.info("PDF receipt attached to email for order %s", order.number)
        else:
            # Если PDF не сгенерирован, считаем это ошибкой задачи, чтобы она ушла в ретрай
            error_msg = f"PDF content is empty for order {order.number}. This is critical, retrying task."
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as e:
        logger.critical("Failed to generate/attach PDF receipt for order %s: %s. The task will retry.", order.number, str(e))
        raise  # Перевыбрасываем исключение, чтобы задача провалилась и была перезапущена

    # --- SMTP SENDING ---
    logger.info("--- SMTP START ---")
    try:
        # Пытаемся отправить через Django. При сетевой ошибке делаем IPv4-фоллбек.
        logger.info(f"Sending email via Django to {recipient} (HOST: {settings.EMAIL_HOST})")
        logger.info("Configured EMAIL_API_PROVIDER: %s", getattr(settings, "EMAIL_API_PROVIDER", ""))
        _send_email_with_ipv4_fallback(message)

        logger.info("SUCCESS: Email sent successfully!")
    except Exception as e:
        logger.error(f"FAILED: Django could not send email: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise
    logger.info("--- SMTP END ---")
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

    # Получаем PDF-чек. Логика устойчива к race-condition с удалением старых файлов.
    pdf_bytes: bytes | None = None
    receipt_url = getattr(order, "receipt_url", None)

    # 1. Сначала пытаемся скачать по существующему URL
    if receipt_url:
        try:
            r = requests.get(receipt_url, timeout=15)
            if r.ok:
                pdf_bytes = r.content
            else:
                logger.warning(
                    "Could not download receipt PDF for order %s (status: %s). It might have been deleted. Will try to regenerate.",
                    order.number, r.status_code
                )
                # Если файл не найден (404) или доступ запрещен (403), сбрасываем pdf_bytes, чтобы сгенерировать заново
                if r.status_code in [404, 403]:
                    pdf_bytes = None
        except Exception as dl_err:
            logger.warning("Error downloading receipt PDF for order %s: %s. Will try to regenerate.", order.number, dl_err)
            pdf_bytes = None

    # 2. Если скачать не удалось (или URL не было), генерируем PDF заново.
    if not pdf_bytes:
        logger.info("Generating PDF receipt on-the-fly for Telegram task (order: %s)", order.number)
        try:
            # Эта функция сама сохранит новый URL в заказ
            _url, pdf_bytes = generate_and_save_receipt(order, locale=locale)
            if not pdf_bytes:
                logger.error("Failed to regenerate PDF for order %s. Telegram notification will be sent without attachment.", order.number)
        except Exception as gen_err:
            logger.error("Critical error during PDF regeneration for order %s: %s", order.number, gen_err)
            pdf_bytes = None

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
