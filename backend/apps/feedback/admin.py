from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from .models import ProductReview, ProductReviewMedia, Testimonial, TestimonialMedia, TestimonialSectionSettings


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


class ProductReviewMediaInline(admin.TabularInline):
    model = ProductReviewMedia
    extra = 0
    fields = ("media_type", "file", "preview", "order")
    readonly_fields = ("preview",)

    @admin.display(description="Превью")
    def preview(self, obj):
        if not obj or not obj.file:
            return "—"
        if obj.media_type == ProductReviewMedia.MediaType.IMAGE:
            return format_html('<img src="{}" style="max-width:120px;max-height:90px;border-radius:8px" />', obj.file.url)
        return format_html('<a href="{}" target="_blank">Открыть видео</a>', obj.file.url)


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product_name", "author_name", "rating", "status", "media_count", "created_at")
    list_filter = ("status", "rating", "product_type", "created_at")
    search_fields = ("product_name", "product_slug", "author_name", "text", "user__username", "user__email")
    readonly_fields = ("user", "product_type", "product_slug", "product_name", "author_name", "created_at", "updated_at", "published_at")
    raw_id_fields = ()
    date_hierarchy = "created_at"
    inlines = (ProductReviewMediaInline,)
    actions = ("approve_reviews", "reject_reviews")
    fieldsets = (
        ("Товар или услуга", {"fields": ("product_name", "product_type", "product_slug")}),
        ("Автор", {"fields": ("user", "author_name")}),
        ("Отзыв", {"fields": ("rating", "text", "status")}),
        ("Даты", {"fields": ("created_at", "updated_at", "published_at")}),
    )

    @admin.display(description="Медиа")
    def media_count(self, obj):
        return obj.media.count() or "—"

    def save_model(self, request, obj, form, change):
        if obj.status == ProductReview.Status.APPROVED and not obj.published_at:
            obj.published_at = timezone.now()
        elif obj.status != ProductReview.Status.APPROVED:
            obj.published_at = None
        super().save_model(request, obj, form, change)

    @admin.action(description="Одобрить выбранные отзывы")
    def approve_reviews(self, request, queryset):
        count = queryset.update(status=ProductReview.Status.APPROVED, published_at=timezone.now())
        self.message_user(request, f"Опубликовано отзывов: {count}")

    @admin.action(description="Отклонить выбранные отзывы")
    def reject_reviews(self, request, queryset):
        count = queryset.update(status=ProductReview.Status.REJECTED, published_at=None)
        self.message_user(request, f"Отклонено отзывов: {count}")
