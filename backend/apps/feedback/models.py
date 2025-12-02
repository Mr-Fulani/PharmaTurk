from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Testimonial(models.Model):
    """
    Модель для хранения отзывов клиентов.
    """
    MEDIA_TYPE_CHOICES = (
        ('none', 'Нет'),
        ('image', 'Изображение'),
        ('video', 'Видео'),
    )

    author_name = models.CharField(
        max_length=100,
        verbose_name='Имя автора'
    )
    author_avatar = models.ImageField(
        upload_to='testimonials/avatars/',
        blank=True,
        null=True,
        verbose_name='Аватар автора'
    )
    text = models.TextField(
        verbose_name='Текст отзыва'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        blank=True,
        null=True,
        verbose_name='Рейтинг (1-5)'
    )
    # Старые поля для обратной совместимости
    media_type = models.CharField(
        max_length=10,
        choices=MEDIA_TYPE_CHOICES,
        default='none',
        verbose_name='Тип медиа (устаревшее)'
    )
    image = models.ImageField(
        upload_to='testimonials/images/',
        blank=True,
        null=True,
        verbose_name='Изображение (устаревшее)'
    )
    video_url = models.URLField(
        blank=True,
        null=True,
        verbose_name='URL видео (YouTube, Vimeo) (устаревшее)'
    )
    video_file = models.FileField(
        upload_to='testimonials/videos/',
        blank=True,
        null=True,
        verbose_name='Файл видео (устаревшее)'
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Активен'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return f'Отзыв от {self.author_name}'

    @property
    def media_items(self):
        """Возвращает все медиа элементы отзыва."""
        return self.media.all().order_by('order')


class TestimonialMedia(models.Model):
    """
    Модель для хранения медиа файлов отзывов (поддержка нескольких медиа).
    """
    MEDIA_TYPE_CHOICES = (
        ('image', 'Изображение'),
        ('video', 'Видео (YouTube/Vimeo URL)'),
        ('video_file', 'Видео файл'),
    )

    testimonial = models.ForeignKey(
        Testimonial,
        on_delete=models.CASCADE,
        related_name='media',
        verbose_name='Отзыв'
    )
    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        verbose_name='Тип медиа'
    )
    image = models.ImageField(
        upload_to='testimonials/images/',
        blank=True,
        null=True,
        verbose_name='Изображение'
    )
    video_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='URL видео (YouTube/Vimeo)'
    )
    video_file = models.FileField(
        upload_to='testimonials/videos/',
        blank=True,
        null=True,
        verbose_name='Видео файл'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок отображения'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = 'Медиа отзыва'
        verbose_name_plural = 'Медиа отзывов'
        ordering = ['order', 'created_at']

    def __str__(self):
        return f'Медиа для отзыва {self.testimonial.id} ({self.media_type})'

    @property
    def image_url(self):
        """Возвращает URL изображения."""
        if self.image and hasattr(self.image, 'url'):
            return self.image.url
        return None

    @property
    def video_file_url(self):
        """Возвращает URL видео файла."""
        if self.video_file and hasattr(self.video_file, 'url'):
            return self.video_file.url
        return None
