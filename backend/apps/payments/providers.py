"""Интерфейсы и заглушки платёжных провайдеров.

Реализация конкретных провайдеров (ЮKassa, CloudPayments, крипто) будет добавлена позже.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PaymentInitResult:
    """Результат инициализации платежа."""

    payment_id: str
    redirect_url: str | None
    extra: dict


class PaymentProvider(Protocol):
    """Контракт платёжного провайдера."""

    def create_payment(self, *, amount_minor: int, currency: str, description: str, metadata: dict) -> PaymentInitResult:  # noqa: E501
        """Инициализирует платёж и возвращает данные для редиректа/виджета."""

    def capture_payment(self, payment_id: str) -> bool:
        """Подтверждает платёж (если требуется двухстадийная оплата)."""

    def refund_payment(self, payment_id: str, *, amount_minor: int | None = None) -> bool:
        """Возвращает средства полностью/частично."""


class DummyProvider:
    """Заглушка провайдера для разработки без реальных оплат."""

    def create_payment(self, *, amount_minor: int, currency: str, description: str, metadata: dict) -> PaymentInitResult:  # noqa: E501
        return PaymentInitResult(payment_id="dummy-123", redirect_url=None, extra={"status": "created"})

    def capture_payment(self, payment_id: str) -> bool:
        return True

    def refund_payment(self, payment_id: str, *, amount_minor: int | None = None) -> bool:
        return True

