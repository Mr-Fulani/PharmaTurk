"""Celery-задачи для платежей (крипто и др.)."""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.db import utils as django_db_utils
from django.utils import timezone

from config.celery import app

from .models import CryptoPayment

logger = logging.getLogger(__name__)


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
    if user:
        utg = getattr(user, "telegram_chat_id", None) or getattr(user, "tg_chat_id", None)
        if utg:
            user_chat_id = str(utg)

    amount_info = ""
    try:
        cp = CryptoPayment.objects.get(order=order)
        amount_info = f"\n💰 Оплачено: {cp.amount_crypto} USDT (≈ {cp.amount_fiat} {cp.currency})"
    except CryptoPayment.DoesNotExist:
        pass

    def _send_tg(chat_id: str, text: str):
        if not bot_token or not chat_id:
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Telegram notification failed for order %s: %s", order.number, resp.text)
            else:
                logger.info("Telegram notification sent for order %s → chat_id=%s", order.number, chat_id)
        except requests.RequestException as e:
            logger.warning("Telegram send error for order %s: %s", order.number, e)

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
        user_email = getattr(order, 'contact_email', None) or (order.user.email if order.user else None)
        if user_email:
            # Отправка чека по email
            send_order_receipt_task.delay(order_id=order.id, email=user_email)
            logger.info("Triggered order receipt email for order %s to %s", order.number, user_email)
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
    if user:
        utg = getattr(user, "telegram_chat_id", None) or getattr(user, "tg_chat_id", None)
        if utg:
            user_chat_id = str(utg)

    def _send_tg(chat_id: str, text: str):
        if not bot_token or not chat_id:
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            if not resp.ok:
                logger.warning("Telegram notification failed for order %s: %s", order.number, resp.text)
            else:
                logger.info("Telegram notification sent for order %s → chat_id=%s", order.number, chat_id)
        except requests.RequestException as e:
            logger.warning("Telegram send error for order %s: %s", order.number, e)

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
