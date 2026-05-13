from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import Testimonial, TestimonialMedia, TestimonialSectionSettings


class TestimonialMediaInline(admin.TabularInline):
    """Inline для управления медиа отзывов."""
    model = TestimonialMedia
    extra = 1
    fields = ('media_type', 'image', 'video_url', 'video_file', 'order')
    ordering = ('order',)


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'user', 'rating', 'media_count', 'is_active', 'created_at')
    list_filter = ('is_active', 'rating', 'created_at', 'user')
    search_fields = ('author_name', 'text', 'user__username', 'user__email')
    list_editable = ('is_active',)
    date_hierarchy = 'created_at'
    inlines = [TestimonialMediaInline]
    raw_id_fields = ('user',)  # Для удобного выбора пользователя
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'author_name', 'author_avatar', 'text', 'rating', 'is_active')
        }),
    )

    def media_count(self, obj):
        """Показывает количество медиа элементов."""
        count = obj.media.count()
        return count if count > 0 else '—'
    media_count.short_description = 'Медиа'


@admin.register(TestimonialMedia)
class TestimonialMediaAdmin(admin.ModelAdmin):
    list_display = ('testimonial', 'media_type', 'preview', 'order', 'created_at')
    list_filter = ('media_type', 'created_at')
    search_fields = ('testimonial__author_name', 'testimonial__text')
    ordering = ('testimonial', 'order', 'created_at')

    def preview(self, obj):
        """Показывает превью медиа."""
        if obj.media_type == 'image' and obj.image:
            return format_html('<img src="{}" style="max-width: 100px; max-height: 100px;" />', obj.image.url)
        elif obj.media_type == 'video_file' and obj.video_file:
            return format_html('<span>📹 Видео файл</span>')
        elif obj.media_type == 'video' and obj.video_url:
            return format_html('<span>🔗 {}...</span>', obj.video_url[:30])
        return '—'
    preview.short_description = 'Превью'


@admin.register(TestimonialSectionSettings)
class TestimonialSectionSettingsAdmin(admin.ModelAdmin):
    list_display = ('show_on_homepage',)
    readonly_fields = ()

    fieldsets = (
        ('Главная страница', {
            'description': 'Включает или скрывает блок отзывов на главной странице без правок в коде.',
            'fields': ('show_on_homepage',),
        }),
    )

    def has_add_permission(self, request):
        return not TestimonialSectionSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        settings_obj = TestimonialSectionSettings.load()
        change_url = reverse(
            f'admin:{settings_obj._meta.app_label}_{settings_obj._meta.model_name}_change',
            args=[settings_obj.pk],
        )
        return HttpResponseRedirect(change_url)
