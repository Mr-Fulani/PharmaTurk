from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Cart, CartItem, Order, OrderItem, PromoCode


class CartItemInline(admin.TabularInline):
    """Инлайн для позиций корзины."""

    model = CartItem
    extra = 0
    readonly_fields = (
        "price",
        "currency",
        "source_offer",
        "verification_status",
        "source_checked_at",
        "created_at",
        "updated_at",
    )
    fields = (
        "product",
        "chosen_size",
        "quantity",
        "price",
        "currency",
        "source_offer",
        "verification_status",
        "source_checked_at",
    )


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Админка для корзин."""
    list_display = ('id', 'user', 'session_key', 'currency', 'items_count', 'total_amount', 'promo_code', 'created_at')
    list_filter = ('currency', 'created_at', 'promo_code')
    search_fields = ('user__email', 'session_key', 'promo_code__code')
    ordering = ('-created_at',)
    readonly_fields = ('items_count', 'total_amount', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('user', 'session_key', 'currency', 'promo_code')}),
        (_('Statistics'), {'fields': ('items_count', 'total_amount')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Админка для позиций корзины."""

    list_display = (
        "cart",
        "product",
        "chosen_size",
        "quantity",
        "price",
        "currency",
        "verification_status",
        "source_offer",
        "source_checked_at",
        "created_at",
    )
    list_filter = ("verification_status", "currency", "source_checked_at", "created_at")
    search_fields = ("cart__user__email", "product__name")
    ordering = ("-created_at",)
    readonly_fields = (
        "price",
        "currency",
        "source_offer",
        "verification_status",
        "source_checked_at",
        "source_availability_status",
        "observed_source_price",
        "observed_source_currency",
        "observed_public_price",
        "observed_public_currency",
        "observed_stock_precision",
        "observed_stock_quantity",
        "verified_quantity",
        "verification_issues",
        "price_change_state",
        "price_acknowledged_at",
        "price_acknowledged_value",
        "price_acknowledged_currency",
        "created_at",
        "updated_at",
    )


class OrderItemInline(admin.TabularInline):
    """Инлайн для позиций заказа."""
    model = OrderItem
    extra = 0
    readonly_fields = (
        'price',
        'total',
        'source_parser',
        'source_external_sku',
        'source_checked_at',
        'supplier_confirmation_required',
    )
    fields = (
        'product',
        'product_name',
        'chosen_size',
        'price',
        'quantity',
        'total',
        'source_parser',
        'source_external_sku',
        'source_checked_at',
        'supplier_confirmation_required',
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Админка для заказов."""
    list_display = ('number', 'user', 'status', 'total_amount', 'currency', 'promo_code', 'payment_method', 'created_at')
    list_filter = ('status', 'currency', 'payment_method', 'payment_status', 'promo_code', 'created_at')
    search_fields = ('number', 'user__email', 'contact_name', 'contact_phone', 'promo_code__code')
    ordering = ('-created_at',)
    readonly_fields = ('number', 'user', 'subtotal_amount', 'total_amount', 'currency', 'created_at', 'updated_at', 'receipt_url')
    
    fieldsets = (
        (None, {'fields': ('number', 'user', 'status')}),
        (_('Amounts'), {'fields': ('subtotal_amount', 'shipping_amount', 'discount_amount', 'total_amount', 'currency', 'promo_code')}),
        (_('Contact'), {'fields': ('contact_name', 'contact_phone', 'contact_email')}),
        (_('Shipping'), {'fields': ('shipping_address', 'shipping_address_text', 'shipping_method')}),
        (_('Payment & Documents'), {'fields': ('payment_method', 'payment_status', 'receipt_url')}),
        (_('Additional'), {'fields': ('comment',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Админка для позиций заказа."""
    list_display = (
        'order',
        'product',
        'product_name',
        'chosen_size',
        'price',
        'quantity',
        'total',
        'source_parser',
        'supplier_confirmation_required',
    )
    search_fields = (
        'order__number',
        'product__name',
        'product_name',
        'source_external_sku',
        'source_url',
    )
    ordering = ('order',)
    readonly_fields = (
        'price',
        'total',
        'source_parser',
        'source_domain',
        'source_url',
        'source_external_product_id',
        'source_external_sku',
        'source_variant_key',
        'source_size_key',
        'source_selected_options',
        'source_price',
        'source_currency',
        'source_availability_status',
        'source_stock_precision',
        'source_stock_quantity',
        'source_checked_at',
        'supplier_confirmation_required',
    )


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    """Админка для промокодов."""
    list_display = ('code', 'discount_type', 'discount_value', 'min_amount', 'used_count', 'max_uses', 'is_active', 'valid_from', 'valid_to')
    list_filter = ('discount_type', 'is_active', 'valid_from', 'valid_to')
    search_fields = ('code', 'description')
    ordering = ('-created_at',)
    readonly_fields = ('used_count', 'created_at', 'updated_at', 'money_overview')
    
    fieldsets = (
        (None, {'fields': ('code', 'description', 'is_active')}),
        (_('Discount'), {'fields': ('discount_type', 'discount_value', 'max_discount', 'min_amount', 'money_overview')}),
        (_('Usage'), {'fields': ('max_uses', 'used_count')}),
        (_('Validity'), {'fields': ('valid_from', 'valid_to')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )

    def money_overview(self, obj: PromoCode):
        currencies = ['RUB', 'USD', 'EUR', 'TRY', 'KZT']
        lines = []

        for cur in currencies:
            try:
                min_amount = obj.get_min_amount(cur)
                max_discount = obj.get_max_discount(cur)
                fixed_value = obj.get_fixed_discount_value(cur)

                parts = [f"min: {min_amount:.2f} {cur}"]
                if obj.discount_type == PromoCode.DiscountType.FIXED and fixed_value is not None:
                    parts.append(f"fixed: {fixed_value:.2f} {cur}")
                if max_discount is not None:
                    parts.append(f"max: {max_discount:.2f} {cur}")
                lines.append(' / '.join(parts))
            except Exception:
                continue

        return "\n".join(lines) if lines else ""

    money_overview.short_description = _('Amounts (converted)')
    
    def get_readonly_fields(self, request, obj=None):
        """Сделать used_count редактируемым только при создании."""
        if obj:
            return self.readonly_fields
        return ('used_count', 'created_at', 'updated_at', 'money_overview')
