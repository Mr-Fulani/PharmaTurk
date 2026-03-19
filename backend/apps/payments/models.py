"""Модели для платежей (крипто и др.)."""
from django.db import models
from django.utils.translation import gettext_lazy as _


class CryptoPaymentStatus(models.TextChoices):
    PENDING = "pending", _("Ожидает")
    CONFIRMED = "confirmed", _("Подтверждён")
    EXPIRED = "expired", _("Истёк")


class CryptoPayment(models.Model):
    """Криптоплатёж (инвойс провайдера) для заказа."""

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="crypto_payment",
        verbose_name=_("Заказ"),
    )
    provider = models.CharField(_("Провайдер"), max_length=32, default="coinremitter")
    invoice_id = models.CharField(_("ID инвойса"), max_length=128, db_index=True)
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
