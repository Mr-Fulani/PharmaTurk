"""Сообщение владельцу, когда Bright Data (прокси или Web Unlocker) отклоняет запросы.

Проверочных запросов нет: срабатывает только на отказ, полученный обычной работой
сайта (открытие карточки, Список заявки, сбор из админки). Не чаще раза в сутки.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.core.cache import cache

from apps.http_errors import ExternalAccessBlockedError, PaidAccessUnavailableError

logger = logging.getLogger(__name__)

CACHE_KEY = "monitoring:paid-access-alert:v1"
ALERT_INTERVAL_SECONDS = 24 * 3600
# Сообщение не ушло (Telegram недоступен) — следующая попытка через час, а не на каждом отказе.
RETRY_AFTER_FAILED_DELIVERY_SECONDS = 3600
_PROXY_STATUS_RE = re.compile(r"\b(402|407)\b")


def is_paid_access_failure(exc: BaseException | None) -> bool:
    """Отказ самого провайдера: нет оплаты, аккаунт или зона приостановлены, лимит исчерпан.

    Смотрит всю цепочку причин исключения. 407 отдаёт только прокси, магазин — никогда;
    402 считается отказом прокси, только когда об этом говорит сама ошибка прокси.
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, PaidAccessUnavailableError):
            return True
        if isinstance(exc, ExternalAccessBlockedError) and exc.status_code == 407:
            return True
        text = f"{type(exc).__name__} {exc}".lower()
        if ("proxy" in text or "tunnel" in text) and _PROXY_STATUS_RE.search(text):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def format_alert(source: str) -> str:
    return (
        "⚠️ Mudaroba: платный доступ Bright Data перестал работать\n"
        f"Где замечено: {source or 'источник не определён'}.\n"
        "Что случилось: Bright Data отклонил запрос — закончились деньги на балансе, "
        "аккаунт или зона приостановлены либо исчерпан месячный лимит.\n"
        "Что перестало обновляться: цены и наличие при открытии карточек и Списка заявки "
        "у Zara, Bershka, Pull&Bear, Massimo Dutti, FLO, Aloparça, поиск продавцов БАДов "
        "на Akakçe и сбор этих магазинов из админки. Сайт работает, покупатели видят "
        "последние сохранённые цены.\n"
        "Что сделать: зайти в кабинет Bright Data, проверить баланс и состояние зон.\n"
        "Повторное сообщение — не раньше чем через сутки."
    )


def report_paid_access_failure(source: str, exc: BaseException | None) -> bool:
    """Шлёт сообщение в чат ошибок, если ``exc`` — отказ провайдера. Никогда не падает."""
    try:
        if not getattr(settings, "PAID_ACCESS_ALERT_ENABLED", True):
            return False
        if not is_paid_access_failure(exc):
            return False
        if not cache.add(CACHE_KEY, 1, timeout=ALERT_INTERVAL_SECONDS):
            return False
        from apps.monitoring.watchdog import send_admin_telegram_notification

        delivered = send_admin_telegram_notification(format_alert(source))
        if not delivered:
            cache.set(CACHE_KEY, 1, timeout=RETRY_AFTER_FAILED_DELIVERY_SECONDS)
        logger.warning(
            "paid_access_alert", extra={"source": source, "delivered": delivered}
        )
        return delivered
    except Exception:
        logger.exception("paid_access_alert_failed", extra={"source": source})
        return False
