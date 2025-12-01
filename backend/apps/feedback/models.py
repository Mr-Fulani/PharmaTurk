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
    media_type = models.CharField(
        max_length=10,
        choices=MEDIA_TYPE_CHOICES,
        default='none',
        verbose_name='Тип медиа'
    )
    image = models.ImageField(
        upload_to='testimonials/images/',
        blank=True,
        null=True,
        verbose_name='Изображение'
    )
    video_url = models.URLField(
        blank=True,
        null=True,
        verbose_name='URL видео (YouTube, Vimeo)'
    )
    video_file = models.FileField(
        upload_to='testimonials/videos/',
        blank=True,
        null=True,
        verbose_name='Файл видео'
    )
    is_active = models.BooleanField(
        default=True,
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
