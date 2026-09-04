from django.contrib import admin
from .models import CryptoInvoiceRequest, CryptoPayment


@admin.register(CryptoPayment)
class CryptoPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_id",
        "invoice_code",
        "order",
        "status",
        "amount_fiat",
        "currency",
        "expires_at",
        "created_at",
    )
    list_filter = ("status", "provider")
    search_fields = ("invoice_id", "invoice_code", "address", "order__number")
    raw_id_fields = ("order",)
    readonly_fields = ("created_at",)


@admin.register(CryptoInvoiceRequest)
class CryptoInvoiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "provider",
        "status",
        "amount_fiat",
        "fiat_currency",
        "attempt_count",
        "last_enqueued_at",
        "last_error_code",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "provider")
    search_fields = (
        "order__number",
        "provider_invoice_id",
        "provider_invoice_code",
    )
    raw_id_fields = ("order",)
    readonly_fields = (
        "idempotency_key",
        "amount_fiat",
        "fiat_currency",
        "attempt_count",
        "processing_started_at",
        "last_enqueued_at",
        "completed_at",
        "last_error_code",
        "provider_invoice_id",
        "provider_invoice_code",
        "created_at",
        "updated_at",
    )
