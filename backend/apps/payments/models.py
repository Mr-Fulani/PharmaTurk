"""Модели для платежей (крипто и др.)."""
from django.db import models
from django.utils.translation import gettext_lazy as _


class CryptoPaymentStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает")
    CONFIRMED = "confirmed", _("Подтверждён")
    EXPIRED = "expired", _("Истёк")


class CryptoInvoiceRequestStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает отправки")
    PROCESSING = "processing", _("Отправляется провайдеру")
    SUCCEEDED = "succeeded", _("Инвойс создан")
    FAILED = "failed", _("Отклонён до создания")
    UNCERTAIN = "uncertain", _("Результат требует сверки")


class CryptoPayment(models.Model):
    """Криптоплатёж (инвойс провайдера) для заказа."""

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="crypto_payment",
        verbose_name=_("Заказ"),
    )
    provider = models.CharField(_("Провайдер"), max_length=32, default="coinremitter")
    # Historical rows store CoinRemitter's long ``id`` in invoice_id. Keep the
    # field stable and persist the provider's short ``invoice_id`` separately.
    invoice_id = models.CharField(_("ID инвойса"), max_length=128, db_index=True)
    invoice_code = models.CharField(
        _("Короткий ID инвойса"),
        max_length=128,
        blank=True,
        db_index=True,
    )
    address = models.CharField(_("Адрес для оплаты"), max_length=256)
    amount_crypto = models.DecimalField(
        _("Сумма в крипте"), max_digits=20, decimal_places=8, default=0
    )
    amount_fiat = models.DecimalField(
        _("Сумма в фиате"), max_digits=12, decimal_places=2, default=0
    )
    currency = models.CharField(_("Валюта фиата"), max_length=3, default="USD")
    status = models.CharField(
        _("Статус"),
        max_length=32,
        choices=CryptoPaymentStatus.choices,
        default=CryptoPaymentStatus.PENDING,
    )
    qr_code_url = models.URLField(_("URL QR-кода"), blank=True)
    invoice_url = models.URLField(_("URL инвойса"), blank=True)
    expires_at = models.DateTimeField(_("Истекает"))
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Криптоплатёж")
        verbose_name_plural = _("Криптоплатежи")

    def __str__(self) -> str:
        return f"{self.invoice_id} ({self.status})"


class CryptoInvoiceRequest(models.Model):
    """Durable outbox intent for one external crypto-invoice creation call.

    CoinRemitter does not expose an idempotency-key parameter for invoice/create.
    The row therefore guarantees one local claim and deliberately quarantines an
    ambiguous attempt instead of automatically issuing a second provider call.
    """

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="crypto_invoice_request",
        verbose_name=_("Заказ"),
    )
    idempotency_key = models.CharField(
        _("Хэш ключа идемпотентности"),
        max_length=64,
        unique=True,
    )
    provider = models.CharField(_("Провайдер"), max_length=32, default="coinremitter")
    status = models.CharField(
        _("Статус"),
        max_length=20,
        choices=CryptoInvoiceRequestStatus.choices,
        default=CryptoInvoiceRequestStatus.PENDING,
        db_index=True,
    )
    amount_fiat = models.DecimalField(
        _("Сумма запроса в фиате"),
        max_digits=12,
        decimal_places=2,
    )
    fiat_currency = models.CharField(_("Валюта запроса"), max_length=3)
    locale = models.CharField(_("Язык возврата"), max_length=2, default="ru")
    attempt_count = models.PositiveIntegerField(_("Количество попыток"), default=0)
    processing_started_at = models.DateTimeField(
        _("Начало обращения к провайдеру"),
        null=True,
        blank=True,
    )
    last_enqueued_at = models.DateTimeField(
        _("Последняя публикация в очередь"),
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField(_("Завершено"), null=True, blank=True)
    last_error_code = models.CharField(
        _("Безопасный код последней ошибки"),
        max_length=64,
        blank=True,
    )
    provider_invoice_id = models.CharField(
        _("ID инвойса провайдера"),
        max_length=128,
        blank=True,
    )
    provider_invoice_code = models.CharField(
        _("Короткий ID инвойса провайдера"),
        max_length=128,
        blank=True,
    )
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Запрос криптоинвойса")
        verbose_name_plural = _("Запросы криптоинвойсов")
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="pay_invreq_status_created",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_id} ({self.status})"
