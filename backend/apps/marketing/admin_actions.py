"""Действие списка товаров админки для Telegram-канала (подключается в админках разделов каталога)."""

from django.contrib import admin, messages


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
