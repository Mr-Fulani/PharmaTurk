from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Cart, CartItem, Order, OrderItem


class CartItemInline(admin.TabularInline):
    """Инлайн для позиций корзины."""
    model = CartItem
    extra = 0
    readonly_fields = ('price', 'currency', 'created_at', 'updated_at')
    fields = ('product', 'quantity', 'price', 'currency')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """Админка для корзин."""
    list_display = ('id', 'user', 'session_key', 'currency', 'items_count', 'total_amount', 'created_at')
    list_filter = ('currency', 'created_at')
    search_fields = ('user__email', 'session_key')
    ordering = ('-created_at',)
    readonly_fields = ('items_count', 'total_amount', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('user', 'session_key', 'currency')}),
        (_('Statistics'), {'fields': ('items_count', 'total_amount')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    """Админка для позиций корзины."""
    list_display = ('cart', 'product', 'quantity', 'price', 'currency', 'created_at')
    list_filter = ('currency', 'created_at')
    search_fields = ('cart__user__email', 'product__name')
    ordering = ('-created_at',)
    readonly_fields = ('price', 'currency', 'created_at', 'updated_at')


class OrderItemInline(admin.TabularInline):
    """Инлайн для позиций заказа."""
    model = OrderItem
    extra = 0
    readonly_fields = ('price', 'total')
    fields = ('product', 'product_name', 'price', 'quantity', 'total')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Админка для заказов."""
    list_display = ('number', 'user', 'status', 'total_amount', 'currency', 'payment_method', 'created_at')
    list_filter = ('status', 'currency', 'payment_method', 'payment_status', 'created_at')
    search_fields = ('number', 'user__email', 'contact_name', 'contact_phone')
    ordering = ('-created_at',)
    readonly_fields = ('number', 'user', 'subtotal_amount', 'total_amount', 'currency', 'created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('number', 'user', 'status')}),
        (_('Amounts'), {'fields': ('subtotal_amount', 'shipping_amount', 'discount_amount', 'total_amount', 'currency')}),
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
    list_display = ('order', 'product', 'product_name', 'price', 'quantity', 'total')
    search_fields = ('order__number', 'product__name', 'product_name')
    ordering = ('order',)
    readonly_fields = ('price', 'total')
