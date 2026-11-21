"""Админка Telegram-канала: настройки, очередь постов, предпросмотр поста товара."""

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import TelegramChannelPost, TelegramChannelSettings


@admin.register(TelegramChannelSettings)
class TelegramChannelSettingsAdmin(admin.ModelAdmin):
    """Одна запись настроек канала."""

    readonly_fields = ("bot_state", "queue_state", "updated_at")
    fieldsets = (
        ("Канал", {"fields": ("channel_id", "bot_state")}),
        ("Расписание", {"fields": ("enabled", "publish_times", "queue_state")}),
        ("Служебное", {"fields": ("updated_at",), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        return not TelegramChannelSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = TelegramChannelSettings.load()
        return redirect(reverse("admin:marketing_telegramchannelsettings_change", args=[obj.pk]))

    @admin.display(description="Бот сайта")
    def bot_state(self, obj):
        if not getattr(settings, "TELEGRAM_BOT_TOKEN", ""):
            return "Не подключён — публикация не сработает."
        username = getattr(settings, "TELEGRAM_BOT_USERNAME", "")
        return f"Подключён: @{username}" if username else "Подключён."

    @admin.display(description="Очередь")
    def queue_state(self, obj):
        count = TelegramChannelPost.objects.filter(status=TelegramChannelPost.Status.QUEUED).count()
        return format_html(
            '{} в очереди · <a href="{}">открыть очередь</a>',
            count,
            reverse("admin:marketing_telegramchannelpost_changelist"),
        )


@admin.register(TelegramChannelPost)
class TelegramChannelPostAdmin(admin.ModelAdmin):
    """Очередь канала. Товары добавляются со страницы товара или действием в списке товаров."""

    list_display = ("product_link", "status", "position", "queued_at", "published_at", "post_link", "error_short")
    list_editable = ("position",)
    list_filter = ("status", "by_schedule")
    search_fields = ("product__name", "product__slug")
    list_select_related = ("product",)
    readonly_fields = (
        "product", "status", "queued_at", "published_at", "by_schedule", "message_id", "post_url", "error",
    )
    fields = ("product", "position", *readonly_fields[1:])
    actions = ("publish_now", "return_to_queue")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Товар", ordering="product__name")
    def product_link(self, obj):
        url = reverse("admin:marketing_telegramchannelpost_product", args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description="Пост")
    def post_link(self, obj):
        if not obj.post_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">открыть</a>', obj.post_url)

    @admin.display(description="Ошибка")
    def error_short(self, obj):
        return obj.error[:120] or "—"

    @admin.action(description="Опубликовать сейчас")
    def publish_now(self, request, queryset):
        from .telegram_channel import publish

        for post in queryset.select_related("product"):
            error = publish(post)
            if error:
                self.message_user(request, f"{post.product.name}: {error}", messages.ERROR)
            else:
                self.message_user(request, f"Опубликовано: {post.product.name}")

    @admin.action(description="Вернуть в очередь (в том числе уже опубликованные)")
    def return_to_queue(self, request, queryset):
        from .telegram_channel import requeue

        count = 0
        for post in queryset.exclude(status=TelegramChannelPost.Status.QUEUED):
            requeue(post)
            count += 1
        self.message_user(request, f"Возвращено в очередь: {count}")

    def get_urls(self):
        custom_urls = [
            path(
                "product/<int:product_id>/",
                self.admin_site.admin_view(self.product_view),
                name="marketing_telegramchannelpost_product",
            ),
        ]
        return custom_urls + super().get_urls()

    def product_view(self, request, product_id: int):
        """Предпросмотр поста товара и кнопки «В очередь» / «Опубликовать сейчас»."""
        from apps.catalog.models import Product

        from .telegram_channel import block_reason, build_post, enqueue, publish

        if not self.has_change_permission(request):
            raise PermissionDenied
        product = get_object_or_404(Product, pk=product_id)
        here = reverse("admin:marketing_telegramchannelpost_product", args=[product.pk])
        if request.method == "POST":
            post, message = enqueue(product)
            if post is None:
                self.message_user(request, message, messages.ERROR)
            elif request.POST.get("action") == "publish":
                if post.status == TelegramChannelPost.Status.PUBLISHED:
                    self.message_user(request, message, messages.WARNING)
                else:
                    error = publish(post)
                    if error:
                        self.message_user(request, error, messages.ERROR)
                    else:
                        self.message_user(request, "Опубликовано в канале.")
            else:
                self.message_user(request, message)
            return redirect(here)

        reason = block_reason(product)
        content = None
        if not reason:
            try:
                content = build_post(product)
            except Exception as exc:  # предпросмотр не должен ронять страницу
                reason = f"Пост не собрался: {type(exc).__name__}"
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Пост в Telegram-канал",
            "product": product,
            "reason": reason,
            "content": content,
            "post_html": mark_safe(content["text"].replace("\n", "<br>")) if content else "",
            "post": TelegramChannelPost.objects.filter(product=product).first(),
            "settings_url": reverse("admin:marketing_telegramchannelsettings_changelist"),
            "queue_url": reverse("admin:marketing_telegramchannelpost_changelist"),
        }
        return render(request, "admin/marketing/telegramchannelpost/product.html", context)
