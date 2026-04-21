"""Модель статических страниц с простым механизмом локализации.

Модель хранит заголовки и HTML-контент для двух языков (en/ru).
Вариант реализован без сторонних библиотек -- простые поля `title_en/title_ru` и `content_en/content_ru`.
Методы `get_title` и `get_content` возвращают значение для запрошенного языка с fallback'ом.
"""

from django.db import models
from django.utils.text import slugify


class Page(models.Model):
    """Статическая страница с локализованными полями.

    Поля:
    - slug: уникальный идентификатор страницы (используется в URL)
    - title_en/title_ru, content_en/content_ru: переводимые поля
    - is_active: флаг публикации
    - created_at/updated_at: временные метки
    """

    slug = models.SlugField(max_length=150, unique=True, help_text="Канонический slug, общий для всех локалей")

    # Заголовки по языкам
    title_en = models.CharField(max_length=255, blank=True, verbose_name="Title (EN)")
    title_ru = models.CharField(max_length=255, blank=True, verbose_name="Title (RU)")

    # Контент (HTML) по языкам
    content_en = models.TextField(blank=True, verbose_name="Content (EN)")
    content_ru = models.TextField(blank=True, verbose_name="Content (RU)")

    is_active = models.BooleanField(default=True, verbose_name="Опубликовано")
    footer_order = models.PositiveIntegerField(default=0, verbose_name="Порядок в футере")

    # SEO / Open Graph
    meta_title_en = models.CharField(max_length=255, blank=True, verbose_name="SEO Title (EN)")
    meta_title_ru = models.CharField(max_length=255, blank=True, verbose_name="SEO Title (RU)")
    meta_description_en = models.TextField(blank=True, verbose_name="SEO Description (EN)")
    meta_description_ru = models.TextField(blank=True, verbose_name="SEO Description (RU)")
    og_image = models.ImageField(
        upload_to="pages/og/", 
        blank=True, 
        null=True, 
        verbose_name="OG Image",
        help_text="Изображение для превью в соцсетях (1200x630px)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "📄 Статическая страница"
        verbose_name_plural = "📄 Контент — Статические страницы"
        ordering = ("footer_order", "-updated_at",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.title_ru or self.title_en or self.slug

    def save(self, *args, **kwargs):
        """При сохранении, если slug не задан, генерируем его из доступного заголовка."""
        if not self.slug:
            # генерируем slug из русского или английского заголовка
            base = self.title_ru or self.title_en or "page"
            self.slug = slugify(base)[:150]
        super().save(*args, **kwargs)

    def get_title(self, lang: str = "ru") -> str:
        """Возвращает заголовок для заданного языка."""
        return getattr(self, f"title_{lang}", None) or getattr(self, "title_en") or getattr(self, "title_ru") or ""

    def get_content(self, lang: str = "ru") -> str:
        """Возвращает HTML-контент для заданного языка с fallback'ом."""
        return getattr(self, f"content_{lang}", None) or getattr(self, "content_en") or getattr(self, "content_ru") or ""

    def get_meta_title(self, lang: str = "ru") -> str:
        """Возвращает SEO заголовок с fallback'ом на обычный заголовок."""
        return (getattr(self, f"meta_title_{lang}", None) or 
                getattr(self, "meta_title_en") or 
                getattr(self, "meta_title_ru") or 
                self.get_title(lang))

    def get_meta_description(self, lang: str = "ru") -> str:
        """Возвращает SEO описание."""
        return (getattr(self, f"meta_description_{lang}", None) or 
                getattr(self, "meta_description_en") or 
                getattr(self, "meta_description_ru") or "")
