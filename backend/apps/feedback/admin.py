from django.contrib import admin
from .models import Testimonial


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'rating', 'media_type', 'is_active', 'created_at')
    list_filter = ('is_active', 'media_type', 'rating', 'created_at')
    search_fields = ('author_name', 'text')
    list_editable = ('is_active',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('author_name', 'author_avatar', 'text', 'rating', 'is_active')
        }),
        ('Медиа контент', {
            'fields': ('media_type', 'image', 'video_url', 'video_file'),
            'description': 'Выберите тип медиа и загрузите соответствующий файл или укажите URL.'
        }),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Динамически скрываем/показываем поля в зависимости от media_type
        if obj:
            if obj.media_type == 'image':
                fieldsets[1][1]['fields'] = ('media_type', 'image')
            elif obj.media_type == 'video':
                fieldsets[1][1]['fields'] = ('media_type', 'video_url', 'video_file')
            else: # 'none'
                fieldsets[1][1]['fields'] = ('media_type',)
        return fieldsets
