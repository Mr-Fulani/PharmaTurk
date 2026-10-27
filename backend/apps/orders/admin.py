from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from .models import (
    Cart,
    CartItem,
    CartReminderLog,
    CartReminderSettings,
    Order,
    OrderItem,
    PromoCode,
    SourcingRequest,
)
from .tasks import notify_order_status_changed


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
    list_display = ('id', 'user', 'session_key', 'currency', 'items_count', 'total_amount', 'promo_code', 'reminder_sent_at', 'created_at')
    list_filter = ('currency', 'created_at', 'promo_code')
    search_fields = ('user__email', 'session_key', 'promo_code__code')
    ordering = ('-created_at',)
    readonly_fields = ('items_count', 'total_amount', 'reminder_sent_at', 'reminder_count', 'locale', 'created_at', 'updated_at')
    actions = ('stop_cart_reminders',)
    
    fieldsets = (
        (None, {'fields': ('user', 'session_key', 'currency', 'promo_code')}),
        (_('Statistics'), {'fields': ('items_count', 'total_amount')}),
        (_('Напоминания о заявке'), {'fields': ('reminder_sent_at', 'reminder_count', 'locale')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    inlines = [CartItemInline]

    @admin.action(description=_("Клиент связался с менеджером — не напоминать о текущем Списке"))
    def stop_cart_reminders(self, request, queryset):
        from .cart_reminders import MAX_STEPS

        # Круг считается пройденным; если клиент снова изменит Список — напоминания начнутся заново
        updated = queryset.filter(user__isnull=False).update(reminder_sent_at=timezone.now(), reminder_count=MAX_STEPS)
        self.message_user(request, _("Напоминания остановлены для Списков: %(count)s") % {"count": updated})


@admin.register(CartReminderSettings)
class CartReminderSettingsAdmin(admin.ModelAdmin):
    """Одна запись настроек; на её странице — кнопки «Отправить тестовое мне»."""

    change_form_template = "admin/orders/cartremindersettings/change_form.html"
    readonly_fields = ("due_now", "updated_at")
    fieldsets = (
        (_("Включение"), {"fields": ("enabled", "email_enabled", "telegram_enabled", "due_now")}),
        (_("Когда напоминать"), {
            "fields": ("first_delay_hours", "second_delay_hours", "pause_days", "max_age_days"),
            "description": _(
                "Не больше двух напоминаний на одно состояние Списка заявки. Клиент, отправивший "
                "заявку или «Найдём товар» после изменения Списка, напоминаний не получает."
            ),
        }),
        (_("Служебное"), {"fields": ("updated_at",), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return not CartReminderSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = CartReminderSettings.load()
        return redirect(reverse("admin:orders_cartremindersettings_change", args=[obj.pk]))

    @admin.display(description=_("Подходят под напоминание сейчас"))
    def due_now(self, obj):
        from .cart_reminders import due_carts

        if obj is None or obj.pk is None:
            return "—"
        count = due_carts(obj).count()
        note = "" if obj.enabled else _(" (напоминания выключены — никому не уходит)")
        return f"{count}{note}"

    def get_urls(self):
        custom_urls = [
            path(
                "send-test/",
                self.admin_site.admin_view(self.send_test_view),
                name="orders_cartremindersettings_send_test",
            ),
        ]
        return custom_urls + super().get_urls()

    def send_test_view(self, request):
        """Тестовое напоминание текущему администратору: его email и Telegram, если привязан."""
        from .cart_reminders import send_test_reminder

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_change_permission(request):
            raise PermissionDenied
        locale = "en" if request.POST.get("locale") == "en" else "ru"
        logs = send_test_reminder(request.user, locale=locale)
        if not logs:
            self.message_user(
                request,
                _(
                    "Не отправлено: каналы с галочкой («Отправлять на email», «Отправлять в Telegram») "
                    "недоступны вашему аккаунту — нет email или привязанного Telegram — либо обе галочки сняты, "
                    "или в каталоге нет товаров с ценой."
                ),
                messages.WARNING,
            )
        for log in logs:
            if log.status == CartReminderLog.Status.SENT:
                self.message_user(request, _("Отправлено: %(channel)s → %(to)s") % {
                    "channel": log.get_channel_display(), "to": log.recipient,
                })
            else:
                self.message_user(request, _("Ошибка: %(channel)s → %(to)s: %(error)s") % {
                    "channel": log.get_channel_display(), "to": log.recipient, "error": log.error,
                }, messages.ERROR)
        obj = CartReminderSettings.load()
        return redirect(reverse("admin:orders_cartremindersettings_change", args=[obj.pk]))


@admin.register(CartReminderLog)
class CartReminderLogAdmin(admin.ModelAdmin):
    """Журнал напоминаний: только просмотр."""

    list_display = (
        "created_at", "user", "step", "channel", "status", "recipient",
        "items_count", "total_display", "clicked", "returned", "request_sent",
    )
    list_filter = ("status", "channel", "step", "created_at")
    search_fields = ("user__email", "recipient")
    list_select_related = ("user",)
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        # «Вернулся» — менял Список после напоминания; «Отправил заявку» — заявка после напоминания
        return super().get_queryset(request).annotate(
            returned_flag=Exists(Cart.objects.filter(pk=OuterRef("cart_id"), updated_at__gt=OuterRef("created_at"))),
            request_flag=Exists(Order.objects.filter(user_id=OuterRef("user_id"), created_at__gt=OuterRef("created_at"))),
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Сумма"), ordering="total")
    def total_display(self, obj):
        return f"{obj.total} {obj.currency}" if obj.total is not None else "—"

    @admin.display(description=_("Перешёл по ссылке"), boolean=True, ordering="clicked_at")
    def clicked(self, obj):
        return obj.clicked_at is not None

    @admin.display(description=_("Вернулся к Списку"), boolean=True)
    def returned(self, obj):
        return obj.returned_flag

    @admin.display(description=_("Отправил заявку"), boolean=True)
    def request_sent(self, obj):
        return obj.request_flag


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
    autocomplete_fields = ('product',)
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
    list_display = (
        'number', 'import_restriction_badge', 'user', 'status', 'total_amount', 'currency', 'contact_phone',
        'contact_channel', 'payment_method', 'created_at',
    )
    list_filter = ('status', 'currency', 'payment_method', 'payment_status', 'promo_code', 'created_at')
    search_fields = ('number', 'user__email', 'contact_name', 'contact_phone', 'promo_code__code')
    ordering = ('-created_at',)
    readonly_fields = (
        'number', 'user', 'subtotal_amount', 'total_amount', 'currency', 'created_at', 'updated_at', 'receipt_url',
        'import_restriction_banner',
    )
    
    fieldsets = (
        (None, {'fields': ('number', 'import_restriction_banner', 'user', 'status')}),
        (_('Amounts'), {'fields': ('subtotal_amount', 'shipping_amount', 'discount_amount', 'total_amount', 'currency', 'promo_code')}),
        (_('Contact'), {'fields': ('contact_name', 'contact_phone', 'contact_email', 'contact_channel', 'contact_username')}),
        (_('Shipping'), {'fields': ('shipping_address', 'shipping_address_text', 'shipping_method', 'tracking_number', 'tracking_url')}),
        (_('Payment & Documents'), {'fields': ('payment_method', 'payment_status', 'receipt_url')}),
        (_('Additional'), {'fields': ('comment',)}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    inlines = [OrderItemInline]

    @staticmethod
    def _restricted_items(obj):
        """Позиции с лекарствами, запрещёнными к ввозу в РФ/СНГ (TD-024): доставку решает менеджер."""
        return [
            item for item in obj.items.select_related('product__medicine_item')
            if item.product_id and getattr(getattr(item.product, 'medicine_item', None), 'import_restricted_countries', '')
        ]

    @admin.display(description=_('Ввоз'))
    def import_restriction_badge(self, obj):
        items = self._restricted_items(obj)
        if not items:
            return ''
        return format_html(
            '<span style="padding:2px 6px;border-radius:6px;background:#f8d7da;color:#842029;font-weight:700;">'
            '⛔ {} поз.</span>', len(items),
        )

    @admin.display(description=_('Ограничение ввоза'))
    def import_restriction_banner(self, obj):
        items = self._restricted_items(obj) if obj and obj.pk else []
        if not items:
            return '—'
        rows = format_html_join(
            '', '<li>{} — {}</li>',
            ((item.product_name, item.product.medicine_item.import_restricted_countries.replace(',', ', ')) for item in items),
        )
        return format_html(
            '<div style="padding:10px 14px;border-radius:8px;background:#f8d7da;color:#842029;">'
            '<b>⛔ В заявке препараты, запрещённые или ограниченные к ввозу.</b> Проверьте страну доставки: '
            'в страну из списка не отправлять без решения ответственного.<ul style="margin:6px 0 0 18px">{}</ul></div>',
            rows,
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Менеджер сменил статус — уведомляем клиента (Telegram/email) после коммита
        if change and 'status' in getattr(form, 'changed_data', []):
            order_id = obj.pk
            transaction.on_commit(lambda: notify_order_status_changed.delay(order_id))


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


@admin.register(SourcingRequest)
class SourcingRequestAdmin(admin.ModelAdmin):
    """Заявки «Найдём товар по ссылке или фото»."""

    list_display = ('id', 'status', 'contact_name', 'contact_phone', 'contact_channel', 'short_url', 'quantity', 'created_at')
    list_filter = ('status', 'contact_channel', 'created_at')
    list_editable = ('status',)
    search_fields = ('contact_name', 'contact_phone', 'contact_email', 'contact_username', 'source_url', 'comment')
    readonly_fields = ('user', 'image_preview', 'locale', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('status', 'manager_comment')}),
        (_('Request'), {'fields': ('source_url', 'image', 'image_preview', 'comment', 'quantity')}),
        (_('Contact'), {'fields': ('user', 'contact_name', 'contact_phone', 'contact_email', 'contact_channel', 'contact_username')}),
        (_('Timestamps'), {'fields': ('locale', 'created_at', 'updated_at')}),
    )

    @admin.display(description=_('Ссылка'))
    def short_url(self, obj):
        if not obj.source_url:
            return '—'
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', obj.source_url, obj.source_url[:50])

    @admin.display(description=_('Превью'))
    def image_preview(self, obj):
        if not obj.image:
            return '—'
        return format_html('<img src="{}" style="max-height:240px;max-width:320px" />', obj.image.url)
