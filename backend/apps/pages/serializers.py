"""Сериализаторы DRF для модели Page.

Serializer возвращает локализованные поля `title` и `content` через SerializerMethodField.
Ожидает, что в `context` передан ключ `lang` для выбора языка.
"""

from rest_framework import serializers
from .models import Page


class PageSerializer(serializers.ModelSerializer):
    """Сериализатор, возвращающий локализованный заголовок и контент.

    Поля `title` и `content` вычисляются методами `get_title`/`get_content`, которые смотрят
    в `self.context.get('lang')` и выполняют fallback при отсутствии перевода.
    """
    title = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ("id", "slug", "title", "content", "is_active", "created_at", "updated_at")
        read_only_fields = ("created_at", "updated_at")

    def get_title(self, obj: Page) -> str:  # pragma: no cover - trivial
        lang = self.context.get("lang") or "ru"
        return obj.get_title(lang=lang)

    def get_content(self, obj: Page) -> str:  # pragma: no cover - trivial
        lang = self.context.get("lang") or "ru"
        return obj.get_content(lang=lang)
