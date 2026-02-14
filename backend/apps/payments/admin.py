from django.contrib import admin
from .models import CryptoPayment


@admin.register(CryptoPayment)
class CryptoPaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice_id", "order", "status", "amount_fiat", "currency", "expires_at", "created_at")
    list_filter = ("status", "provider")
    search_fields = ("invoice_id", "address", "order__number")
    raw_id_fields = ("order",)
    readonly_fields = ("created_at",)
