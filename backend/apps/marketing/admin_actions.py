"""Действие списка товаров админки для Telegram-канала (подключается в админках разделов каталога)."""

from django.contrib import admin, messages
from django.db.models import F
from django.utils import timezone
from django.utils.html import format_html


class TelegramChannelActionMixin:
    """Действие списка товаров «В очередь Telegram-канала» (лекарства, БАДы, эфирные масла)."""

    @admin.action(description="В очередь Telegram-канала")
    def add_to_telegram_channel(self, request, queryset):
        from .telegram_channel import enqueue

        added, skipped = 0, []
        for item in queryset.select_related("base_product"):
            product = item.base_product
            post, message = (
                enqueue(product) if product else (None, "У товара нет записи в «Товарах».")
            )
            if post is not None and message == "Поставлен в очередь.":
                added += 1
            else:
                skipped.append(f"{item.name}: {message}")
        self.message_user(request, f"Поставлено в очередь канала: {added}")
        for line in skipped[:20]:
            self.message_user(request, line, messages.WARNING)
        if len(skipped) > 20:
            self.message_user(
                request, f"…и ещё не поставлено: {len(skipped) - 20}", messages.WARNING
            )


class TelegramChannelStatusFilter(admin.SimpleListFilter):
    """Фильтр списка товаров по состоянию в Telegram-канале."""

    title = "Telegram-канал"
    parameter_name = "telegram_channel"

    def lookups(self, request, model_admin):
        return [
            ("none", "Не публиковался"),
            ("queued", "В очереди"),
            ("published", "Опубликован"),
            ("error", "Ошибка"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "none":
            return queryset.filter(base_product__telegram_channel_post__isnull=True)
        if value in ("queued", "published", "error"):
            return queryset.filter(base_product__telegram_channel_post__status=value)
        return queryset


class TelegramChannelListMixin(TelegramChannelActionMixin):
    """Список товаров раздела: действие «В очередь», колонка и фильтр «Telegram-канал»."""

    def get_queryset(self, request):
        # Пост канала — аннотациями (один JOIN со списком), без запроса на строку. Не select_related:
        # список админки при FK в колонках вызывает select_related() и сбросил бы его.
        post = "base_product__telegram_channel_post__"
        return (
            super()
            .get_queryset(request)
            .annotate(
                tg_status=F(post + "status"),
                tg_published_at=F(post + "published_at"),
                tg_post_url=F(post + "post_url"),
            )
        )

    def get_list_display(self, request):
        return [*super().get_list_display(request), "telegram_channel_status"]

    def get_list_filter(self, request):
        return [*super().get_list_filter(request), TelegramChannelStatusFilter]

    @admin.display(description="Telegram-канал")
    def telegram_channel_status(self, obj):
        from .models import TelegramChannelPost

        if not obj.tg_status:
            return "—"
        if obj.tg_status != TelegramChannelPost.Status.PUBLISHED:
            return TelegramChannelPost.Status(obj.tg_status).label
        published = obj.tg_published_at
        date = timezone.localtime(published).strftime("%d.%m.%Y") if published else ""
        label = f"Опубликован {date}".strip()
        if not obj.tg_post_url:
            return label
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', obj.tg_post_url, label
        )
