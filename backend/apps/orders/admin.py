from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Cart, CartItem, Order, OrderItem, PromoCode


class CartItemInline(admin.TabularInline):
    """Инлайн для позиций корзины."""
    model = CartItem
    extra = 0
    readonly_fields = ('price', 'currency', 'created_at', 'updated_at')
    fields = ('product', 'chosen_size', 'quantity', 'price', 'currency')


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
    list_display = ('cart', 'product', 'chosen_size', 'quantity', 'price', 'currency', 'created_at')
    list_filter = ('currency', 'created_at')
    search_fields = ('cart__user__email', 'product__name')
    ordering = ('-created_at',)
    readonly_fields = ('price', 'currency', 'created_at', 'updated_at')


class OrderItemInline(admin.TabularInline):
    """Инлайн для позиций заказа."""
    model = OrderItem
    extra = 0
    readonly_fields = ('price', 'total')
    fields = ('product', 'product_name', 'chosen_size', 'price', 'quantity', 'total')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Админка для заказов."""
    list_display = ('number', 'user', 'status', 'total_amount', 'currency', 'promo_code', 'payment_method', 'created_at')
    list_filter = ('status', 'currency', 'payment_method', 'payment_status', 'promo_code', 'created_at')
    search_fields = ('number', 'user__email', 'contact_name', 'contact_phone', 'promo_code__code')
    ordering = ('-created_at',)
    readonly_fields = ('number', 'user', 'subtotal_amount', 'total_amount', 'currency', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('number', 'user', 'status')}),
        (_('Amounts'), {'fields': ('subtotal_amount', 'shipping_amount', 'discount_amount', 'total_amount', 'currency', 'promo_code')}),
        (_('Contact'), {'fields': ('contact_name', 'contact_phone', 'contact_email')}),
        (_('Shipping'), {'fields': ('shipping_address', 'shipping_address_text', 'shipping_method')}),
        (_('Payment'), {'fields': ('payment_method', 'payment_status')}),
        (_('Additional'), {'fields': ('comment',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Админка для позиций заказа."""
    list_display = ('order', 'product', 'product_name', 'chosen_size', 'price', 'quantity', 'total')
    search_fields = ('order__number', 'product__name', 'product_name')
    ordering = ('order',)
    readonly_fields = ('price', 'total')


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    """Админка для промокодов."""
    list_display = ('code', 'discount_type', 'discount_value', 'min_amount', 'used_count', 'max_uses', 'is_active', 'valid_from', 'valid_to')
    list_filter = ('discount_type', 'is_active', 'valid_from', 'valid_to')
    search_fields = ('code', 'description')
    ordering = ('-created_at',)
    readonly_fields = ('used_count', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('code', 'description', 'is_active')}),
        (_('Discount'), {'fields': ('discount_type', 'discount_value', 'max_discount', 'min_amount')}),
        (_('Usage'), {'fields': ('max_uses', 'used_count')}),
        (_('Validity'), {'fields': ('valid_from', 'valid_to')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    def get_readonly_fields(self, request, obj=None):
        """Сделать used_count редактируемым только при создании."""
        if obj:
            return self.readonly_fields
        return ('used_count', 'created_at', 'updated_at')
