"""Админка «Память переводов AI»: поиск по исходнику и ручная правка RU/EN.

Правка сохраняется обычным ``save()`` (сигналы потребителей, например
разнос МНН по лекарствам, срабатывают) и отвязывает запись от AI-лога:
исправленный менеджером перевод переиспользуется везде.
"""

from django.contrib import admin
from django.utils.text import Truncator

from apps.ai.models import AITranslationMemory


@admin.register(AITranslationMemory)
class AITranslationMemoryAdmin(admin.ModelAdmin):
    list_display = ("namespace", "short_source", "short_ru", "hits", "updated_at")
    list_filter = ("namespace",)
    search_fields = ("source_text", "ru_text", "en_text", "=source_hash")
    readonly_fields = ("namespace", "source_hash", "source_text", "source_log", "hits", "created_at", "updated_at")
    fields = readonly_fields[:3] + ("ru_text", "en_text") + readonly_fields[3:]
    ordering = ("-updated_at",)
    list_per_page = 50

    def has_add_permission(self, request):
        return False  # записи создаёт только пайплайн

    @admin.display(description="Исходный текст")
    def short_source(self, obj):
        return Truncator(obj.source_text).chars(90)

    @admin.display(description="RU")
    def short_ru(self, obj):
        return Truncator(obj.ru_text).chars(90)

    def save_model(self, request, obj, form, change):
        if change and form.has_changed():
            obj.source_log = None  # ручная правка: перевод больше не зависит от статуса лога
        super().save_model(request, obj, form, change)
