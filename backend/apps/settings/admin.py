"""Админ-интерфейс для настроек сайта."""

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import FooterSettings, HomeBlock, SiteAppearance


@admin.register(FooterSettings)
class FooterSettingsAdmin(admin.ModelAdmin):
    """Админка для настроек футера."""
    
    list_display = ('__str__', 'phone', 'email', 'location', 'updated_at')
    list_display_links = ('__str__',)
    
    def has_add_permission(self, request):
        """Запрещаем создание новых записей (singleton)."""
        return not FooterSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        """Запрещаем удаление единственной записи."""
        return False
    
    fieldsets = (
        (_("Контакты"), {
            "fields": ("phone", "email", "location"),
        }),
        (_("Социальные сети"), {
            "fields": ("telegram_url", "whatsapp_url", "vk_url", "instagram_url"),
        }),
        (_("Дополнительная информация"), {
            "fields": ("crypto_payment_text",),
        }),
        (_("Метаданные"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    
    readonly_fields = ("created_at", "updated_at")
    
    def changelist_view(self, request, extra_context=None):
        """При открытии списка создаем запись, если её нет."""
        try:
            FooterSettings.load()
        except Exception:
            # Игнорируем ошибки при миграциях
            pass
        return super().changelist_view(request, extra_context)
    
    def save_model(self, request, obj, form, change):
        """При сохранении убеждаемся, что запись имеет pk=1 (singleton)."""
        obj.pk = 1
        super().save_model(request, obj, form, change)


@admin.register(SiteAppearance)
class SiteAppearanceAdmin(admin.ModelAdmin):
    """Тема оформления сайта (одна запись)."""

    fields = ("theme", "updated_at")
    readonly_fields = ("updated_at",)
    radio_fields = {"theme": admin.VERTICAL}

    def has_add_permission(self, request):
        return not SiteAppearance.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SiteAppearance.load()
        return HttpResponseRedirect(
            reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
        )


@admin.register(HomeBlock)
class HomeBlockAdmin(admin.ModelAdmin):
    """Блоки главной: галочка «Показывать» и порядок прямо в списке."""

    list_display = ("block", "is_enabled", "sort_order")
    list_display_links = None
    list_editable = ("is_enabled", "sort_order")
    ordering = ("sort_order", "id")

    @admin.display(description=_("Блок"), ordering="sort_order")
    def block(self, obj):
        return obj.get_key_display()

    def has_add_permission(self, request):
        """Набор блоков задан кодом и заводится миграцией."""
        return False

    def has_delete_permission(self, request, obj=None):
        return False
