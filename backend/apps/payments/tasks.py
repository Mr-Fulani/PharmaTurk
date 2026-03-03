"""Celery-задачи для платежей (крипто и др.)."""
from __future__ import annotations

import logging

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
