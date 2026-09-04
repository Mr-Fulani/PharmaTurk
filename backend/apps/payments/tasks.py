"""Celery-задачи для платежей (крипто и др.)."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction, utils as django_db_utils
from django.db.models import Count, Q
from django.utils import timezone

from config.celery import app

from .models import (
    CryptoInvoiceRequest,
    CryptoInvoiceRequestStatus,
    CryptoPayment,
    CryptoPaymentStatus,
)

logger = logging.getLogger(__name__)


def enqueue_crypto_invoice_request(request_id: int) -> bool:
    """Best-effort wake-up for a durable outbox row.

    Broker delivery is deliberately not the source of truth. A periodic
    dispatcher will find the still-pending row when this immediate publish
    fails after the database transaction has committed.
    """

    try:
        create_coinremitter_invoice_request.delay(request_id)
    except Exception:  # noqa: BLE001 - broker URLs may contain credentials
        logger.warning(
            "coinremitter_outbox_enqueue_failed",
            extra={"crypto_invoice_request_id": request_id},
        )
        return False
    try:
        now = timezone.now()
        CryptoInvoiceRequest.objects.filter(
            pk=request_id,
            status=CryptoInvoiceRequestStatus.PENDING,
        ).update(last_enqueued_at=now, updated_at=now)
    except Exception:  # noqa: BLE001 - publishing already succeeded
        logger.warning(
            "coinremitter_outbox_enqueue_timestamp_failed",
            extra={"crypto_invoice_request_id": request_id},
        )
    return True


def _mark_invoice_request(
    request_id: int,
    *,
    status: str,
    error_code: str,
) -> None:
    now = timezone.now()
    CryptoInvoiceRequest.objects.filter(
        pk=request_id,
        status=CryptoInvoiceRequestStatus.PROCESSING,
    ).update(
        status=status,
        last_error_code=error_code[:64],
        completed_at=now,
        updated_at=now,
    )


@app.task(bind=True, acks_late=True, reject_on_worker_lost=True)
def create_coinremitter_invoice_request(self, request_id: int) -> dict:
    """Claim and execute one provider call without holding a DB transaction.

    CoinRemitter invoice/create has no documented idempotency parameter. Once a
    call starts, an unavailable result is quarantined as ``uncertain`` and is
    never retried automatically. This favours a manual provider reconciliation
    over accidentally creating two payable invoices for one order.
    """

    with transaction.atomic():
        try:
            invoice_request = (
                CryptoInvoiceRequest.objects.select_for_update()
                .select_related("order")
                .get(pk=request_id)
            )
        except CryptoInvoiceRequest.DoesNotExist:
            return {"status": "missing"}

        if invoice_request.status == CryptoInvoiceRequestStatus.SUCCEEDED:
            return {"status": "already_succeeded"}
        if invoice_request.status == CryptoInvoiceRequestStatus.PROCESSING:
            return {"status": "already_processing"}
        if invoice_request.status != CryptoInvoiceRequestStatus.PENDING:
            return {"status": invoice_request.status}

        invoice_request.status = CryptoInvoiceRequestStatus.PROCESSING
        invoice_request.attempt_count += 1
        invoice_request.processing_started_at = timezone.now()
        invoice_request.last_error_code = ""
        invoice_request.save(
            update_fields=[
                "status",
                "attempt_count",
                "processing_started_at",
                "last_error_code",
                "updated_at",
            ]
        )
        order = invoice_request.order
        locale = invoice_request.locale

    if (
        not getattr(settings, "COINREMITTER_API_KEY", "")
        or not getattr(settings, "COINREMITTER_API_PASSWORD", "")
    ) and not getattr(settings, "CRYPTO_DUMMY_MODE", False):
        _mark_invoice_request(
            request_id,
            status=CryptoInvoiceRequestStatus.FAILED,
            error_code="provider_not_configured",
        )
        return {"status": "failed", "error_code": "provider_not_configured"}

    try:
        # Lazy import avoids the existing orders -> payments task dependency at
        # module import time while the orchestration code is migrated gradually.
        from apps.orders.views import _create_crypto_invoice

        invoice_data, _payment_data = _create_crypto_invoice(
            order.number,
            invoice_request.amount_fiat,
            invoice_request.fiat_currency,
            locale=locale,
        )
    except Exception as exc:  # noqa: BLE001 - never retry an ambiguous provider call
        error_code = f"exception_{type(exc).__name__}"[:64]
        _mark_invoice_request(
            request_id,
            status=CryptoInvoiceRequestStatus.UNCERTAIN,
            error_code=error_code,
        )
        logger.warning(
            "coinremitter_outbox_provider_result_uncertain",
            extra={
                "crypto_invoice_request_id": request_id,
                "order_id": order.pk,
                "error_code": error_code,
            },
        )
        return {"status": "uncertain", "error_code": error_code}

    if not invoice_data:
        _mark_invoice_request(
            request_id,
            status=CryptoInvoiceRequestStatus.UNCERTAIN,
            error_code="provider_result_unavailable",
        )
        logger.warning(
            "coinremitter_outbox_provider_result_uncertain",
            extra={
                "crypto_invoice_request_id": request_id,
                "order_id": order.pk,
                "error_code": "provider_result_unavailable",
            },
        )
        return {
            "status": "uncertain",
            "error_code": "provider_result_unavailable",
        }

    provider_invoice_id = str(invoice_data.get("invoice_id") or "").strip()
    try:
        amount_crypto = Decimal(str(invoice_data.get("amount")))
    except (InvalidOperation, TypeError, ValueError):
        amount_crypto = Decimal("0")
    has_payment_destination = bool(
        str(invoice_data.get("address") or "").strip()
        or str(invoice_data.get("invoice_url") or "").strip()
    )
    if (
        not provider_invoice_id
        or not amount_crypto.is_finite()
        or amount_crypto <= 0
        or not has_payment_destination
    ):
        _mark_invoice_request(
            request_id,
            status=CryptoInvoiceRequestStatus.UNCERTAIN,
            error_code="invalid_provider_result",
        )
        logger.warning(
            "coinremitter_outbox_provider_result_uncertain",
            extra={
                "crypto_invoice_request_id": request_id,
                "order_id": order.pk,
                "error_code": "invalid_provider_result",
            },
        )
        return {"status": "uncertain", "error_code": "invalid_provider_result"}

    with transaction.atomic():
        invoice_request = (
            CryptoInvoiceRequest.objects.select_for_update()
            .select_related("order")
            .get(pk=request_id)
        )
        if invoice_request.status == CryptoInvoiceRequestStatus.SUCCEEDED:
            return {"status": "already_succeeded"}
        if invoice_request.status != CryptoInvoiceRequestStatus.PROCESSING:
            return {"status": invoice_request.status}

        payment, created = CryptoPayment.objects.get_or_create(
            order=invoice_request.order,
            defaults={
                "provider": (
                    "dummy"
                    if str(invoice_data.get("invoice_id", "")).startswith("dummy-")
                    else "coinremitter"
                ),
                "invoice_id": provider_invoice_id,
                "invoice_code": invoice_data.get("invoice_code") or "",
                "address": invoice_data.get("address") or "",
                "amount_crypto": amount_crypto,
                "amount_fiat": invoice_request.amount_fiat,
                "currency": invoice_request.fiat_currency,
                "status": CryptoPaymentStatus.PENDING,
                "qr_code_url": invoice_data.get("qr_code") or "",
                "invoice_url": invoice_data.get("invoice_url") or "",
                "expires_at": invoice_data.get("expires_at")
                or (timezone.now() + timedelta(minutes=30)),
            },
        )
        if not created and (
            payment.invoice_id != provider_invoice_id
            or payment.invoice_code != (invoice_data.get("invoice_code") or "")
        ):
            invoice_request.status = CryptoInvoiceRequestStatus.UNCERTAIN
            invoice_request.last_error_code = "conflicting_local_payment"
            invoice_request.completed_at = timezone.now()
            invoice_request.save(
                update_fields=[
                    "status",
                    "last_error_code",
                    "completed_at",
                    "updated_at",
                ]
            )
            return {"status": "uncertain", "error_code": "conflicting_local_payment"}

        invoice_request.status = CryptoInvoiceRequestStatus.SUCCEEDED
        invoice_request.provider_invoice_id = provider_invoice_id
        invoice_request.provider_invoice_code = invoice_data.get("invoice_code") or ""
        invoice_request.last_error_code = ""
        invoice_request.completed_at = timezone.now()
        invoice_request.save(
            update_fields=[
                "status",
                "provider_invoice_id",
                "provider_invoice_code",
                "last_error_code",
                "completed_at",
                "updated_at",
            ]
        )

    logger.info(
        "coinremitter_outbox_succeeded",
        extra={
            "crypto_invoice_request_id": request_id,
            "order_id": order.pk,
        },
    )
    return {"status": "succeeded", "payment_id": payment.pk}


@app.task
def dispatch_pending_crypto_invoice_requests() -> int:
    """Republish durable pending rows missed by an on-commit broker wake-up."""

    limit = max(1, min(500, int(settings.COINREMITTER_OUTBOX_DISPATCH_BATCH_SIZE)))
    republish_cutoff = timezone.now() - timedelta(
        seconds=max(60, int(settings.COINREMITTER_OUTBOX_REPUBLISH_SECONDS))
    )
    request_ids = list(
        CryptoInvoiceRequest.objects.filter(
            status=CryptoInvoiceRequestStatus.PENDING,
        )
        .filter(
            Q(last_enqueued_at__isnull=True)
            | Q(last_enqueued_at__lte=republish_cutoff)
        )
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:limit]
    )
    published = sum(enqueue_crypto_invoice_request(pk) for pk in request_ids)
    logger.info(
        "coinremitter_outbox_dispatch_summary",
        extra={"outbox_candidates": len(request_ids), "outbox_published": published},
    )
    return published


@app.task
def reconcile_coinremitter_state() -> dict:
    """Quarantine stale claims and emit a read-only provider drift summary."""

    stale_cutoff = timezone.now() - timedelta(
        seconds=max(60, int(settings.COINREMITTER_OUTBOX_STALE_SECONDS))
    )
    now = timezone.now()
    stale_count = CryptoInvoiceRequest.objects.filter(
        status=CryptoInvoiceRequestStatus.PROCESSING,
        processing_started_at__lte=stale_cutoff,
    ).update(
        status=CryptoInvoiceRequestStatus.UNCERTAIN,
        last_error_code="stale_processing",
        completed_at=now,
        updated_at=now,
    )

    outbox_counts = {
        row["status"]: row["count"]
        for row in CryptoInvoiceRequest.objects.values("status").annotate(
            count=Count("id")
        )
    }
    limit = max(1, min(10, int(settings.COINREMITTER_RECONCILIATION_BATCH_SIZE)))
    cutoff = timezone.now() - timedelta(
        minutes=max(1, int(settings.COINREMITTER_RECONCILIATION_MIN_AGE_MINUTES))
    )
    payments = list(
        CryptoPayment.objects.select_related("order")
        .filter(
            provider="coinremitter",
            status=CryptoPaymentStatus.PENDING,
            created_at__lte=cutoff,
        )
        .order_by("created_at", "pk")[:limit]
    )

    from .providers.coinremitter import get_invoice
    from .reconciliation import classify_coinremitter_state

    categories: Counter[str] = Counter()
    drift = critical = unavailable = 0
    for payment in payments:
        provider_invoice = get_invoice(payment.invoice_code or payment.invoice_id)
        if provider_invoice is None:
            categories["provider_unavailable"] += 1
            unavailable += 1
            continue
        result = classify_coinremitter_state(payment, provider_invoice)
        categories[result.category] += 1
        drift += int(result.is_drift)
        critical += int(result.is_critical)

    summary = {
        "checked": len(payments),
        "drift": drift,
        "critical": critical,
        "provider_unavailable": unavailable,
        "stale_outbox_quarantined": stale_count,
        "outbox": outbox_counts,
        "categories": dict(categories),
    }
    unresolved_outbox = (
        outbox_counts.get(CryptoInvoiceRequestStatus.UNCERTAIN, 0)
        + outbox_counts.get(CryptoInvoiceRequestStatus.FAILED, 0)
    )
    log = (
        logger.warning
        if drift or unavailable or stale_count or unresolved_outbox
        else logger.info
    )
    log("coinremitter_reconciliation_summary", extra=summary)
    return summary


@app.task
def expire_pending_crypto_payments() -> int:
    """Пометить истёкшие крипто-инвойсы (status=pending, expires_at < now). Stock не трогали."""
    try:
        now = timezone.now()
        qs = CryptoPayment.objects.filter(status="pending", expires_at__lt=now)
        count = qs.update(status="expired")
        if count:
            logger.info("Expired %d pending crypto payment(s)", count)
        return count
    except django_db_utils.ProgrammingError as e:
        # Таблица может ещё не существовать при старте (миграции выполняются после запуска beat/worker).
        if "does not exist" in str(e):
            logger.debug("payments_cryptopayment table not ready yet, skipping expire task: %s", e)
            return 0
        raise


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=3)
def notify_crypto_payment_confirmed(self, order_id: int) -> None:
    """Уведомляет пользователя (Telegram) о подтверждении криптоплатежа.

    Работает gracefully: если Telegram не настроен — просто логирует без ошибки.
    """
    from apps.orders.models import Order
    from apps.orders.tasks import send_order_receipt_task

    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("notify_crypto_payment_confirmed: order %s not found", order_id)
        return

    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    admin_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""

    user = order.user
    user_chat_id = ""
    if user and getattr(user, "telegram_notifications", False):
        utg = getattr(user, "telegram_id", None) or ""
        if utg:
            user_chat_id = str(utg).strip()

    amount_info = ""
    try:
        cp = CryptoPayment.objects.get(order=order)
        coin_code = (getattr(settings, "COINREMITTER_COIN", "") or "crypto").upper()
        amount_info = (
            f"\n💰 Оплачено: {cp.amount_crypto} {coin_code} "
            f"(≈ {cp.amount_fiat} {cp.currency})"
        )
    except CryptoPayment.DoesNotExist:
        pass

    def _send_tg(chat_id: str, text: str):
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not set!")
            return
        if not chat_id:
            logger.warning("Telegram chat_id is missing, skipping notification")
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning(
                    "Telegram notification failed for order %s: HTTP %s",
                    order.number,
                    resp.status_code,
                )
            else:
                logger.info("Telegram notification sent for order %s", order.number)
        except requests.RequestException:
            logger.warning("Telegram send error for order %s", order.number)

    # Уведомление админу
    if admin_chat_id:
        admin_text = (
            f"🔔 *Новая оплата!*\n"
            f"Заказ: `{order.number}`"
            f"{amount_info}\n"
            f"Статус: *Оплачен*"
        )
        _send_tg(admin_chat_id, admin_text)

    # Уведомление покупателю
    if user_chat_id and user_chat_id != admin_chat_id:
        user_text = (
            f"✅ *Ваш заказ оплачен!*\n"
            f"Заказ: `{order.number}`"
            f"{amount_info}\n\n"
            f"Мы приняли его в обработку и скоро с вами свяжемся."
        )
        _send_tg(user_chat_id, user_text)

    # Отправляем чек на почту (и генерируем PDF)
    try:
        # Берём email покупателя и не отправляем на админские адреса
        from apps.orders.services import get_order_customer_email
        user_email = get_order_customer_email(order)
        if user_email:
            # Отправка чека по email
            send_order_receipt_task.delay(order_id=order.id, email=user_email)
            logger.info("Triggered order receipt email for order %s", order.number)
    except Exception as e:
        logger.error("Failed to trigger send_order_receipt_task for order %s: %s", order.number, e)


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=30, max_retries=3)
def notify_crypto_payment_expired(self, order_id: int) -> None:
    """Уведомляет пользователя (Telegram) об истечении времени крипто-инвойса."""
    from apps.orders.models import Order

    try:
        order = Order.objects.select_related("user").get(id=order_id)
    except Order.DoesNotExist:
        return

    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    admin_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""

    user = order.user
    user_chat_id = ""
    if user and getattr(user, "telegram_notifications", False):
        utg = getattr(user, "telegram_id", None) or ""
        if utg:
            user_chat_id = str(utg).strip()

    def _send_tg(chat_id: str, text: str):
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not set!")
            return
        if not chat_id:
            logger.warning("Telegram chat_id is missing, skipping notification")
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning(
                    "Telegram notification failed for order %s: HTTP %s",
                    order.number,
                    resp.status_code,
                )
            else:
                logger.info("Telegram notification sent for order %s", order.number)
        except requests.RequestException:
            logger.warning("Telegram send error for order %s", order.number)

    if admin_chat_id:
        admin_text = (
            f"⚠️ *Истекло время оплаты*\n"
            f"Заказ: `{order.number}`\n"
            f"Покупатель не успел оплатить крипто-инвойс."
        )
        _send_tg(admin_chat_id, admin_text)

    if user_chat_id and user_chat_id != admin_chat_id:
        user_text = (
            f"⏰ *Время оплаты истекло*\n"
            f"Заказ: `{order.number}`\n\n"
            f"К сожалению, время на оплату крипто-инвойса истекло. Вы можете создать новый заказ."
        )
        _send_tg(user_chat_id, user_text)
