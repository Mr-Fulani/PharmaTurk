"""Celery-задачи для заказов, чеков и уведомлений."""
from __future__ import annotations

import base64
import logging
import re
import socket
from datetime import timedelta
from html import escape, unescape
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _

from config.celery import app
from apps.catalog.utils.r2_utils import get_r2_client

logger = logging.getLogger(__name__)

MAX_RECEIPT_PDF_BYTES = 5 * 1024 * 1024
# Паузы удваиваются от 30 с: всего около получаса, короткий сбой Telegram переживается
TELEGRAM_MAX_RETRIES = 6
TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096
# Около 20 тысяч знаков: комментарий заказа не ограничен, а одна заявка не должна завалить чат
TELEGRAM_MAX_MESSAGE_PARTS = 5
TELEGRAM_CUT_NOTICE = "\n\n… Дальше текст обрезан, полностью он в заявке в админке."
SOURCING_LOOKUP_QUERY_LIMIT = 100

from .contacts import contact_links, contact_message, order_item_names
from .models import Cart, CartItem, Order
from .services import (
    build_order_receipt_payload,
    render_receipt_html,
    generate_and_save_receipt,
    get_receipt_filename,
    get_receipt_storage_key,
    get_order_customer_email,
)


def _stale_anonymous_carts(cutoff):
    """Anonymous carts with no cart/item write at or after the cutoff."""
    recent_items = CartItem.objects.filter(
        cart_id=OuterRef("pk"),
        updated_at__gte=cutoff,
    )
    return Cart.objects.filter(
        user__isnull=True,
        updated_at__lt=cutoff,
    ).filter(~Exists(recent_items))


def _orders_chat_id() -> str:
    """Куда слать заявки менеджерам: TELEGRAM_ORDERS_CHAT_ID (канал/группа), иначе TELEGRAM_CHAT_ID."""
    return (
        str(getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", "") or "").strip()
        or str(getattr(settings, "TELEGRAM_CHAT_ID", "") or "").strip()
    )


@app.task(name="orders.cleanup_stale_anonymous_carts")
def cleanup_stale_anonymous_carts(
    days: int | None = None,
    batch_size: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Delete inactive anonymous carts in bounded batches; never user carts."""
    retention_days = int(
        days
        if days is not None
        else getattr(settings, "ANONYMOUS_CART_TTL_DAYS", 30)
    )
    cleanup_batch_size = int(
        batch_size
        if batch_size is not None
        else getattr(settings, "ANONYMOUS_CART_CLEANUP_BATCH_SIZE", 500)
    )
    if retention_days < 1:
        raise ValueError("days must be at least 1")
    if cleanup_batch_size < 1 or cleanup_batch_size > 10_000:
        raise ValueError("batch_size must be between 1 and 10000")

    cutoff = timezone.now() - timedelta(days=retention_days)
    matched = _stale_anonymous_carts(cutoff).count()
    result = {
        "matched": matched,
        "deleted": 0,
        "dry_run": bool(dry_run),
        "retention_days": retention_days,
    }
    if dry_run or matched == 0:
        return result

    deleted = 0
    while True:
        with transaction.atomic():
            cart_ids = list(
                _stale_anonymous_carts(cutoff)
                .select_for_update(skip_locked=True)
                .order_by("pk")
                .values_list("pk", flat=True)[:cleanup_batch_size]
            )
            if not cart_ids:
                break
            _cascade_count, deleted_by_model = Cart.objects.filter(
                user__isnull=True,
                pk__in=cart_ids,
            ).delete()
            deleted += deleted_by_model.get(Cart._meta.label, 0)

    result["deleted"] = deleted
    logger.info(
        "Anonymous cart cleanup matched=%s deleted=%s retention_days=%s",
        matched,
        deleted,
        retention_days,
    )
    return result


def _load_receipt_pdf_from_storage(order: Order) -> bytes | None:
    """Read the deterministic receipt object directly from trusted R2 storage."""
    bucket_name = (getattr(settings, "R2_CONFIG", {}) or {}).get("bucket_name")
    if not bucket_name:
        return None
    # Never fall back to the legacy predictable ``receipts/{order.number}.pdf``
    # namespace. Missing receipts are regenerated under the HMAC namespace.
    keys = [get_receipt_storage_key(order)]
    client = get_r2_client()
    last_error_name = ""
    for key in dict.fromkeys(keys):
        body_stream = None
        try:
            response = client.get_object(Bucket=bucket_name, Key=key)
            body_stream = response.get("Body")
            declared_size = int(response.get("ContentLength") or 0)
            if declared_size < 0 or declared_size > MAX_RECEIPT_PDF_BYTES:
                continue
            if body_stream is None:
                continue
            data = body_stream.read(MAX_RECEIPT_PDF_BYTES + 1)
            if len(data) > MAX_RECEIPT_PDF_BYTES or not data.startswith(b"%PDF-"):
                continue
            return data
        except Exception as exc:
            last_error_name = type(exc).__name__
        finally:
            if body_stream is not None and hasattr(body_stream, "close"):
                body_stream.close()

    if last_error_name:
        logger.warning(
            "Could not load receipt PDF from storage for order %s: %s",
            order.number,
            last_error_name,
        )
    return None


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
        except Exception as exc:
            if not self.fail_silently:
                raise
            logger.warning("IPv4 SMTP connection to %s failed: %s", self.host, type(exc).__name__)
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
    # Например List-Unsubscribe у напоминаний о Списке заявки
    if getattr(message, "extra_headers", None):
        payload["headers"] = dict(message.extra_headers)

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

    logger.info("Sending receipt email for order %s", order.number)

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
        logger.info("Sending email via Django (HOST: %s)", settings.EMAIL_HOST)
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


class TelegramTemporaryError(Exception):
    """Telegram не принял сообщение, но повтор может помочь: сеть, 429, 5xx.

    В тексте нет адреса запроса: в нём токен бота, а исключение попадает в журнал Celery.
    """


def _post_telegram(bot_token: str, method: str, **kwargs):
    """POST в Bot API. Ответ 4xx возвращает вызывающему: повтор его не исправит."""
    try:
        resp = requests.post(f"https://api.telegram.org/bot{bot_token}/{method}", **kwargs)
    except requests.RequestException as exc:
        raise TelegramTemporaryError(type(exc).__name__) from None
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TelegramTemporaryError(f"HTTP {resp.status_code}")
    return resp


def _tg_markdown_escape(value) -> str:
    """Пользовательский ввод не должен ломать parse_mode=Markdown."""
    text = str(value or "-")
    for ch in ("\\", "_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def _tg_length(text: str) -> int:
    """Длина с запасом: эмодзи идёт за две единицы, как в UTF-16, символы экранирования считаются."""
    return len(text.encode("utf-16-le")) // 2


def _tg_fitting_end(text: str, limit: int) -> int:
    """Сколько первых символов text укладывается в limit единиц `_tg_length`."""
    units = 0
    for index, ch in enumerate(text):
        units += _tg_length(ch)
        if units > limit:
            return index
    return len(text)


def _tg_html_escape(value) -> str:
    """Пользовательский ввод не должен ломать parse_mode=HTML."""
    return escape(str(value or "-"), quote=False)


def _tg_link(url: str, label: str) -> str:
    return f'<a href="{escape(url)}">{escape(label, quote=False)}</a>'


def _admin_url(name: str, *args, query: str = "") -> str:
    """Абсолютный адрес страницы админки; вход — по сессии менеджера, токенов в адресе нет."""
    url = settings.SITE_URL + reverse(name, args=args)
    return f"{url}?q={quote(query, safe='')}" if query else url


_TG_TAG_RE = re.compile(r"<(/?)\w+[^>]*>")


def _tg_html_safe_end(text: str, end: int) -> int:
    """Сдвигает разрез назад, если он попал в &-сущность, внутрь тега или между <b> и </b>."""
    head = text[:end]
    amp = head.rfind("&")
    if amp != -1 and ";" not in head[amp:]:
        head = head[:amp]
    tag = head.rfind("<")
    if tag != -1 and ">" not in head[tag:]:
        head = head[:tag]
    open_tags = []
    for match in _TG_TAG_RE.finditer(head):
        if not match.group(1):
            open_tags.append(match.start())
        elif open_tags:
            open_tags.pop()
    if open_tags:
        head = head[:open_tags[0]]
    # Пустая часть зациклила бы деление: тег длиннее сообщения шаблон не создаёт
    return len(head) or end


def _split_tg_text(text: str) -> list[str]:
    """Делит текст на сообщения Telegram, не ломая parse_mode=HTML.

    Ввод покупателя экранирован, теги ставит только шаблон. Разрез не должен попасть в
    «&amp;», внутрь тега или ссылки: следующее сообщение открыло бы разметку без конца, и
    Telegram ответил бы 400. Чистые пробелы Telegram тоже не принимает. Длина считается по
    тексту с тегами — с запасом: Telegram считает её уже без них.
    """
    parts = []
    rest = text.strip()
    while rest:
        is_last = len(parts) == TELEGRAM_MAX_MESSAGE_PARTS - 1
        limit = TELEGRAM_MESSAGE_LIMIT - (_tg_length(TELEGRAM_CUT_NOTICE) if is_last else 0)
        end = _tg_fitting_end(rest, limit)
        if end < len(rest):
            cut = rest.rfind("\n", end // 2, end)
            if cut == -1:
                cut = rest.rfind(" ", end // 2, end)
            if cut != -1:
                end = cut
            end = _tg_html_safe_end(rest, end)
        parts.append(rest[:end].rstrip())
        rest = rest[end:].lstrip()
        if is_last and rest:
            parts[-1] += TELEGRAM_CUT_NOTICE
            break
    return parts


def _tg_delivery_steps(text: str, attachment: bytes | None, short_caption: str) -> list[tuple[str, bytes | None]]:
    """Что отправить менеджеру, по порядку: пары (текст, вложение).

    Текст, который влезает в подпись, идёт подписью к вложению. Длинный — отдельными
    сообщениями, вложение с short_caption следом: подпись длиннее предела Telegram отвергает
    ответом 400, и пропало бы всё. Предел подписи Telegram считает по тексту без тегов.
    На повторе шаги те же, отправленные пропускаются по счётчику.
    """
    if attachment and _tg_length(unescape(_TG_TAG_RE.sub("", text))) <= TELEGRAM_CAPTION_LIMIT:
        return [(text, attachment)]
    steps = [(part, None) for part in _split_tg_text(text)]
    if attachment:
        steps.append((short_caption, attachment))
    return steps


def _tg_write_line(obj, number, item_names=(), sourcing: bool = False, locale: str = "ru") -> str:
    """Строка «Написать» со ссылками на чат покупателя; в чате уже набран черновик на языке заявки."""
    hrefs = dict(
        contact_links(
            obj.contact_channel, obj.contact_username, obj.contact_phone, "",
            contact_message(obj.contact_name, number, item_names, sourcing=sourcing, locale=locale), "",
        )
    )
    # mailto: Telegram ссылкой не делает; письмо с черновиком открывается из админки
    links = [_tg_link(hrefs[key], label) for key, label in (("telegram", "Telegram"), ("whatsapp", "WhatsApp")) if key in hrefs]
    return "✍️ Написать: " + " · ".join(links) if links else ""


def _item_medicine(item):
    product = item.product
    if product is None or product.product_type != "medicines":
        return None
    return getattr(product, "medicine_item", None)


def _order_item_links(items) -> list[str]:
    """Строка ссылок каждой позиции: «В админке · На сайте · Источник» (HTML); без товара — пусто.

    Запросы — на заявку, а не на позицию: товары, их записи разделов и недостающие адреса продавцов.
    """
    from django.db.models import prefetch_related_objects

    from apps.catalog.admin_links import domain_record_prefetches, product_admin_url, product_site_url
    from apps.catalog.models import Product, ProductSourceOffer
    from apps.catalog.services.product_resolve import build_canonical_path

    products = {
        product.pk: product
        for product in Product.objects.filter(pk__in={item.product_id for item in items if item.product_id}).only(
            "product_type", "slug", "is_active", "external_url", "external_data"
        )
    }
    prefetch_related_objects(
        list(products.values()),
        *domain_record_prefetches(product_types={product.product_type for product in products.values()}),
    )
    # Адрес продавца из предложений источников — только товарам без своей ссылки, одним запросом
    without_source = {
        item.product_id
        for item in items
        if item.product_id in products and not (item.source_url or products[item.product_id].external_url)
    }
    offer_urls = {}
    if without_source:
        # Обратный порядок: в словаре остаётся первый по алфавиту адрес, как у кнопки в админке
        offers = ProductSourceOffer.objects.filter(product_id__in=without_source).order_by("-canonical_url")
        offer_urls = dict(offers.values_list("product_id", "canonical_url"))

    lines = []
    for item in items:
        product = products.get(item.product_id)
        if product is None:
            lines.append("")
            continue
        links = [_tg_link(settings.SITE_URL + product_admin_url(product), "В админке")]
        site_url = product_site_url(product)
        variant_slug = (product.external_data or {}).get("source_variant_slug")
        if not site_url and product.is_active and product.slug and product.product_type != "medicines":
            # Заказанная расцветка — служебный товар: карточка открывается по slug варианта,
            # у украшений — по своему slug (как «На сайте» в позициях заказа админки)
            slug = product.slug if product.product_type == "jewelry" else variant_slug or product.slug
            site_url = _site_url() + build_canonical_path(product.product_type, slug)
        if site_url:
            links.append(_tg_link(site_url, "На сайте"))
        # Ссылка, сохранённая при оформлении; у старых позиций — текущая ссылка товара
        source = item.source_url or product.external_url or offer_urls.get(product.pk, "")
        if source.startswith(("https://", "http://")):
            links.append(_tg_link(source, "Источник"))
        lines.append("🔗 " + " · ".join(links))
    return lines


def _order_item_blocks(order, drug_checks: dict, with_links: bool = True) -> tuple[list[str], list[str]]:
    """Позиции заявки абзацами (HTML) и названия позиций без цены."""
    from apps.drug_check.service import lookup_query

    h = _tg_html_escape
    blocks, on_request = [], []
    items = list(order.items.all())
    link_lines = [""] * len(items)
    if with_links:
        try:
            link_lines = _order_item_links(items)
        except Exception:
            # Сбой ссылок не убирает позиции из сообщения
            logger.warning("order_telegram_item_links_failed", exc_info=True)
    for index, (item, link_line) in enumerate(zip(items, link_lines), start=1):
        lines = [f"{index}. <b>{h(item.product_name)}</b>"]
        if item.chosen_size:
            lines.append(f"Размер: {h(item.chosen_size)}")
        if not item.price:
            on_request.append(item.product_name)
            lines.append(f"{item.quantity} шт. · цена по запросу")
        elif item.quantity == 1:
            lines.append(f"1 шт. · {item.price} {order.currency}")
        else:
            lines.append(f"{item.quantity} шт. × {item.price} {order.currency} = {item.total} {order.currency}")
        medicine = _item_medicine(item)
        if medicine is not None:
            labels = []
            if medicine.is_hospital:
                labels.append("🏥 Больничный препарат")
            if medicine.import_restricted_countries:
                countries = ", ".join(medicine.import_restricted_countries.split(","))
                labels.append(f"⛔ Ввоз ограничен: {h(countries)}")
            if labels:
                lines.append(" · ".join(labels))
            check = drug_checks.get(str(medicine.pk))
            if check:
                lines.append(h(check))
            query = lookup_query(medicine)
            lines.append(
                "🔎 "
                + _tg_link(_admin_url("admin:drug_check_medicine", medicine.pk), "Проверить по источникам")
                + " · "
                + _tg_link(
                    _admin_url("admin:drug_check_lookup", query=query),
                    "Поиск по штрихкоду" if query.isdigit() else "Поиск по названию",
                )
            )
        if link_line:
            lines.append(link_line)
        blocks.append("\n".join(lines))
    return blocks, on_request


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=TELEGRAM_MAX_RETRIES)
def notify_new_order_telegram(
    self,
    _email_result=None,
    order_id: int = None,
    locale: str = 'ru',
    customer_notified: bool = False,
    admin_steps_sent: int = 0,
    drug_checks: dict | None = None,
    drug_check_text: str | None = None,
) -> None:
    """Уведомляет (Telegram) о создании нового заказа.
    Может запускаться как Celery link после send_order_receipt_task — тогда первым аргументом
    приходит результат предыдущей задачи (_email_result), который игнорируется.
    PDF чека читается напрямую из доверенного R2 bucket либо генерируется заново.
    При временном сбое Telegram повторяется только сообщение менеджеру: покупателю задача
    пишет один раз (customer_notified), иначе после обрыва связи он получил бы дубль.
    Длинный текст менеджеру уходит по шагам, повтор продолжает с шага admin_steps_sent.
    Итог проверки лекарств заявки (TD-044, ≤ 15 с) считается один раз и передаётся в повтор
    (drug_checks): текст и шаги на повторе те же. drug_check_text — прежний аргумент, его могут
    нести повторы, поставленные до выкатки; не используется.
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
    admin_chat_id = _orders_chat_id()

    user = order.user
    user_chat_id = ""
    if user and getattr(user, "telegram_notifications", False):
        utg = getattr(user, "telegram_id", None) or ""
        if utg:
            user_chat_id = str(utg).strip()

    is_ru = locale != "en"

    # Не загружаем order.receipt_url через HTTP: поле/redirect не должны становиться SSRF.
    pdf_bytes = _load_receipt_pdf_from_storage(order)

    # Если прочитать объект не удалось, генерируем PDF заново.
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

    def _send_tg(
        chat_id: str,
        text: str,
        document: bytes | None = None,
        filename: str = "receipt.pdf",
        parse_mode: str = "Markdown",
    ):
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not set!")
            return
        if not chat_id:
            logger.warning("Telegram chat_id is missing, skipping notification")
            return
        if document:
            files = {"document": (filename, document, "application/pdf")}
            data = {"chat_id": chat_id, "caption": text, "parse_mode": parse_mode}
            resp = _post_telegram(bot_token, "sendDocument", data=data, files=files, timeout=20)
        else:
            # Без предпросмотра: у ссылки в админку им стала бы страница входа
            json_data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            resp = _post_telegram(bot_token, "sendMessage", json=json_data, timeout=10)

        if not resp.ok:
            logger.warning(
                "Telegram notification failed for order %s: HTTP %s",
                order.number,
                resp.status_code,
            )
        else:
            logger.info("Telegram notification sent for order %s", order.number)

    from .services import (
        CONTACT_CHANNEL_TRANSLATIONS,
        PAYMENT_METHOD_TRANSLATIONS,
        SHIPPING_METHOD_TRANSLATIONS,
        translate_method,
    )

    h = _tg_html_escape

    is_request = order.payment_method == "manager"

    filename = get_receipt_filename(order)
    admin_error = None

    # Уведомление админу
    if admin_chat_id:
        payment_info = translate_method(order.payment_method, PAYMENT_METHOD_TRANSLATIONS, "ru")
        delivery_info = translate_method(order.shipping_method, SHIPPING_METHOD_TRANSLATIONS, "ru")
        channel_info = translate_method(order.contact_channel, CONTACT_CHANNEL_TRANSLATIONS, "ru")
        if not isinstance(drug_checks, dict):
            from apps.drug_check.service import order_checks

            drug_checks = order_checks(order)
        # Больничные препараты и товары без цены: сумму называет менеджер (docs/HOSPITAL_MEDICINES.md)
        try:
            item_blocks, on_request = _order_item_blocks(order, drug_checks)
            item_names = order_item_names(order.items.all(), locale)
        except Exception:
            # Как у проверки лекарств: сбой списка позиций не держит уведомление менеджеру.
            logger.warning("order_telegram_items_failed", exc_info=True)
            item_blocks, on_request, item_names = [], [], []

        buyer = [
            "👤 <b>Покупатель</b>",
            f"Имя: {h(order.contact_name)}",
            f"Телефон: {h(order.contact_phone)}",
            f"Email: {h(order.contact_email)}",
            f"Связаться через: {h(channel_info)}",
        ]
        if order.contact_username:
            is_phone = order.contact_username.lstrip("+").isdigit()
            handle = order.contact_username if is_phone else f"@{order.contact_username}"
            buyer.append(f"{h(channel_info)}: {h(handle)}")
        write_line = _tg_write_line(order, order.number, item_names, locale=locale)
        if write_line:
            buyer.append(write_line)
        total = [f"💰 <b>Итого: {order.total_amount} {order.currency}</b>"]
        if on_request:
            total.append("Цена по запросу (в сумму не вошли): " + h("; ".join(on_request)))
        total.append(f"Оплата: {h(payment_info)}")
        total.append(f"Доставка: {h(delivery_info)}")

        def _admin_text(blocks):
            sections = [
                f"{'📝 <b>Новая заявка</b>' if is_request else '📦 <b>Новый заказ</b>'} <code>{h(order.number)}</code>\n"
                + _tg_link(_admin_url("admin:orders_order_change", order.id), "Открыть заявку в админке"),
                "\n".join(buyer),
            ]
            if blocks:
                sections += ["🛒 <b>Позиции</b>", *blocks]
            sections.append("\n".join(total))
            if order.comment:
                sections.append(f"💬 <b>Комментарий</b>\n{h(order.comment)}")
            return "\n\n".join(sections)

        admin_text = _admin_text(item_blocks)
        if item_blocks and _split_tg_text(admin_text)[-1].endswith(TELEGRAM_CUT_NOTICE):
            # Не помещается: сначала уходят строки ссылок позиций, потом режется текст заявки
            try:
                admin_text = _admin_text(_order_item_blocks(order, drug_checks, with_links=False)[0])
            except Exception:
                logger.warning("order_telegram_items_failed", exc_info=True)
        admin_steps = _tg_delivery_steps(admin_text, pdf_bytes, f"🧾 Чек к заказу <code>{h(order.number)}</code>")
        try:
            for step_text, step_document in admin_steps[admin_steps_sent:]:
                _send_tg(admin_chat_id, step_text, document=step_document, filename=filename, parse_mode="HTML")
                admin_steps_sent += 1
        except TelegramTemporaryError as exc:
            logger.warning("Telegram send error for order %s: %s", order.number, exc)
            admin_error = exc

    # Уведомление покупателю
    if user_chat_id and user_chat_id != admin_chat_id and not customer_notified:
        delivery_info_user = translate_method(order.shipping_method, SHIPPING_METHOD_TRANSLATIONS, locale)

        if is_ru:
            user_text = (
                f"{'✅ *Ваша заявка принята!*' if is_request else '✅ *Ваш заказ успешно оформлен!*'}\n"
                f"Заказ: `{order.number}`\n"
                f"Сумма: {order.total_amount} {order.currency}\n"
                f"Способ доставки: {delivery_info_user}\n\n"
                + (
                    "Менеджер свяжется с вами, чтобы подтвердить заказ и согласовать способ оплаты."
                    if is_request
                    else "Мы уже занимаемся его сборкой!"
                )
            )
        else:
            user_text = (
                f"{'✅ *Your request has been received!*' if is_request else '✅ *Your order has been placed successfully!*'}\n"
                f"Order: `{order.number}`\n"
                f"Amount: {order.total_amount} {order.currency}\n"
                f"Shipping method: {delivery_info_user}\n\n"
                + (
                    "A manager will contact you to confirm the order and agree on payment."
                    if is_request
                    else "We are already assembling it!"
                )
            )
        try:
            _send_tg(user_chat_id, user_text, document=pdf_bytes, filename=filename)
        except TelegramTemporaryError as exc:
            logger.warning("Telegram send error for order %s (customer): %s", order.number, exc)

    if admin_error:
        raise self.retry(
            exc=admin_error,
            args=(),
            kwargs={
                "order_id": order_id,
                "locale": locale,
                "customer_notified": True,
                "admin_steps_sent": admin_steps_sent,
                "drug_checks": drug_checks,
            },
            countdown=30 * 2 ** self.request.retries,
        )


@app.task(bind=True, max_retries=TELEGRAM_MAX_RETRIES)
def notify_sourcing_request_telegram(self, request_id: int, steps_sent: int = 0) -> None:
    """Уведомляет менеджеров (TELEGRAM_ORDERS_CHAT_ID, иначе TELEGRAM_CHAT_ID) о заявке «Найдём товар по ссылке или фото»."""
    from .models import SourcingRequest
    from .services import CONTACT_CHANNEL_TRANSLATIONS, translate_method

    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = _orders_chat_id()
    if not bot_token or not chat_id:
        return
    try:
        req = SourcingRequest.objects.get(pk=request_id)
    except SourcingRequest.DoesNotExist:
        return

    h = _tg_html_escape
    wanted = ["🛍 <b>Что ищем</b>"]
    if req.source_url:
        wanted.append(f"Ссылка: {h(req.source_url)}")
    if req.comment:
        wanted.append(f"Комментарий: {h(req.comment)}")
    wanted.append(f"Количество: {req.quantity}")
    buyer = ["👤 <b>Покупатель</b>", f"Имя: {h(req.contact_name)}"]
    if req.contact_phone:
        buyer.append(f"Телефон: {h(req.contact_phone)}")
    if req.contact_email:
        buyer.append(f"Email: {h(req.contact_email)}")
    channel_info = translate_method(req.contact_channel, CONTACT_CHANNEL_TRANSLATIONS, "ru")
    buyer.append(f"Связаться через: {h(channel_info)}")
    if req.contact_username:
        is_phone = req.contact_username.lstrip("+").isdigit()
        buyer.append(f"{h(channel_info)}: {h(req.contact_username if is_phone else '@' + req.contact_username)}")
    write_line = _tg_write_line(req, req.pk, sourcing=True, locale=req.locale)
    if write_line:
        buyer.append(write_line)
    # В окно поиска лекарств подставляется запрос покупателя — одной строкой, не длиннее поля поиска
    query = " ".join((req.comment or "").split())[:SOURCING_LOOKUP_QUERY_LIMIT]
    lookup = "💊 Если это лекарство: " + _tg_link(
        _admin_url("admin:drug_check_lookup", query=query), "проверить по источникам"
    )
    text = "\n\n".join(
        [
            f"🔎 <b>Новая заявка на поиск товара</b> <code>{req.pk}</code>\n"
            + _tg_link(_admin_url("admin:orders_sourcingrequest_change", req.pk), "Открыть заявку в админке"),
            "\n".join(wanted),
            "\n".join(buyer),
            lookup,
        ]
    )

    photo = b""
    if req.image:
        try:
            with req.image.open("rb") as fh:
                photo = fh.read(10 * 1024 * 1024)
        except Exception as exc:
            logger.warning(
                "Sourcing request %s: cannot read photo for Telegram: %s",
                req.pk, type(exc).__name__,
            )
    try:
        for step_text, step_photo in _tg_delivery_steps(text, photo, f"Фото к заявке <code>{req.pk}</code>")[steps_sent:]:
            if step_photo:
                resp = _post_telegram(
                    bot_token,
                    "sendPhoto",
                    data={"chat_id": chat_id, "caption": step_text, "parse_mode": "HTML"},
                    files={"photo": ("photo.jpg", step_photo, "image/jpeg")},
                    timeout=20,
                )
            else:
                resp = _post_telegram(
                    bot_token,
                    "sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": step_text,
                        "parse_mode": "HTML",
                        # Предпросмотр — только у ссылки покупателя, не у страницы входа в админку
                        "disable_web_page_preview": not req.source_url,
                    },
                    timeout=15,
                )
            if not resp.ok:
                logger.warning("Telegram sourcing notification failed for %s: HTTP %s", req.pk, resp.status_code)
            steps_sent += 1
    except TelegramTemporaryError as exc:
        raise self.retry(
            exc=exc,
            args=(),
            kwargs={"request_id": request_id, "steps_sent": steps_sent},
            countdown=30 * 2 ** self.request.retries,
        )


# ─── Сопровождение заявки: статусы и напоминания ─────────────────────────────


def _send_telegram_text(chat_id: str, text: str) -> bool:
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not bot_token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=15,
        )
    except requests.RequestException:
        logger.warning("Telegram send error to %s", chat_id)
        return False
    if not resp.ok:
        logger.warning("Telegram send failed to %s: HTTP %s", chat_id, resp.status_code)
    return bool(resp.ok)


def _send_plain_email(recipient: str, subject: str, text: str) -> None:
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@mudaroba.local"),
        to=[recipient],
    )
    message.send()


def _site_url() -> str:
    return getattr(settings, "FRONTEND_SITE_URL", "") or getattr(settings, "SITE_URL", "")


def _user_locale(user) -> str:
    return "en" if (getattr(user, "language", "") or "").lower().startswith("en") else "ru"


def build_order_status_message(order, locale: str = "ru") -> str | None:
    """Текст для клиента о новом статусе заявки; None — статус не требует уведомления."""
    md = _tg_markdown_escape
    number = f"`{order.number}`"
    site = _site_url()
    status = order.status
    S = Order.OrderStatus
    if locale == "en":
        texts = {
            S.PENDING_PAYMENT: f"✅ Your request {number} is confirmed. Total: {order.total_amount} {order.currency}. A manager will contact you about payment.",
            S.PROCESSING: f"📦 Order {number} is being processed: we are collecting and preparing it for shipping.",
            S.SHIPPED: f"🚚 Order {number} has been shipped.",
            S.DELIVERED: f"🎉 Order {number} has been delivered. We would be grateful for a review: {site}/testimonials?action=add",
            S.CANCELLED: f"Order {number} has been cancelled. If this is a mistake, please contact us.",
        }
        tracking_label = "Tracking number"
    else:
        texts = {
            S.PENDING_PAYMENT: f"✅ Заявка {number} подтверждена. Сумма: {order.total_amount} {order.currency}. Менеджер свяжется с вами по оплате.",
            S.PROCESSING: f"📦 Заказ {number} в работе: собираем и готовим к отправке.",
            S.SHIPPED: f"🚚 Заказ {number} отправлен.",
            S.DELIVERED: f"🎉 Заказ {number} доставлен. Будем благодарны за отзыв: {site}/testimonials?action=add",
            S.CANCELLED: f"Заказ {number} отменён. Если это ошибка — свяжитесь с нами.",
        }
        tracking_label = "Трек-номер"
    text = texts.get(status)
    if not text:
        return None
    if status == S.SHIPPED and order.tracking_number:
        text += f"\n{tracking_label}: `{md(order.tracking_number)}`"
        if order.tracking_url:
            text += f"\n{order.tracking_url}"
    return text


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=3)
def notify_order_status_changed(self, order_id: int) -> None:
    """Уведомляет клиента о смене статуса заявки менеджером: Telegram (если включён) и email."""
    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        return
    user = order.user
    locale = _user_locale(user)
    text = build_order_status_message(order, locale)
    if not text:
        return
    if user and getattr(user, "telegram_notifications", False) and getattr(user, "telegram_id", ""):
        _send_telegram_text(str(user.telegram_id).strip(), text)
    recipient = get_order_customer_email(order)
    if recipient and (user is None or getattr(user, "email_notifications", True)):
        subject = (
            f"Order {order.number}: status update" if locale == "en" else f"Заказ {order.number}: новый статус"
        )
        _send_plain_email(recipient, subject, text.replace("`", ""))


@app.task(name="orders.remind_abandoned_carts")
def remind_abandoned_carts(batch_size: int = 50) -> int:
    """Напоминания о неотправленном Списке заявки (email/Telegram) по настройкам из админки.

    Пока в «Напоминания о заявке: настройки» не включено — ничего не делает.
    Отбор, частота и отписка — apps/orders/cart_reminders.py, docs/CART_REMINDERS.md.
    """
    from .cart_reminders import run_cart_reminders

    return run_cart_reminders(batch_size=batch_size)
