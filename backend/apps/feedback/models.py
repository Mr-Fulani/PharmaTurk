from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils.text import slugify
import os
import uuid


class Testimonial(models.Model):
    """
    Модель для хранения отзывов клиентов.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='testimonials',
        verbose_name='Пользователь'
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
    is_active = models.BooleanField(
        default=False,
        verbose_name='Активен'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = '💬 Отзыв'
        verbose_name_plural = '💬 Отзывы — Отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return f'Отзыв от {self.author_name}'

    @property
    def media_items(self):
        """Возвращает все медиа элементы отзыва."""
        return self.media.all().order_by('order')


class TestimonialSectionSettings(models.Model):
    """Singleton-настройки раздела отзывов."""
    show_on_homepage = models.BooleanField(
        default=False,
        verbose_name='Показывать блок отзывов на главной',
        help_text='Управляет показом карусели отзывов на главной странице сайта.'
    )

    class Meta:
        verbose_name = '💬 Настройки блока отзывов'
        verbose_name_plural = '💬 Отзывы — Настройки блока'

    def __str__(self):
        return 'Настройки блока отзывов'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


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
        verbose_name = '💬 Медиа отзыва'
        verbose_name_plural = '💬 Отзывы — Медиа отзывов'
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


def get_product_review_media_upload_path(instance, filename):
    """Readable R2 key: reviews/<type>/<product>/users/<username-id>/<media>/..."""
    review = instance.review
    product_type = slugify(review.product_type) or "product"
    product_slug = slugify(review.product_slug) or f"product-{review.pk or 'new'}"
    user = review.user
    user_label = slugify(getattr(user, "username", ""))
    if not user_label:
        user_label = slugify(str(getattr(user, "email", "")).split("@", 1)[0])
    user_segment = f"{user_label or 'user'}-{review.user_id or 'unknown'}"
    media_dir = "images" if instance.media_type == ProductReviewMedia.MediaType.IMAGE else "videos"
    extension = os.path.splitext(str(filename))[1].lower()
    return (
        f"reviews/{product_type}/{product_slug}/users/{user_segment}/{media_dir}/"
        f"{uuid.uuid4().hex}{extension}"
    )


class ProductReview(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает модерации"
        APPROVED = "approved", "Опубликован"
        REJECTED = "rejected", "Отклонён"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
        verbose_name="Пользователь",
    )
    product_type = models.CharField("Тип товара/услуги", max_length=64, db_index=True)
    product_slug = models.SlugField("Slug родительской карточки", max_length=600, db_index=True)
    product_name = models.CharField("Название товара/услуги", max_length=500)
    author_name = models.CharField("Имя автора", max_length=150)
    rating = models.PositiveSmallIntegerField(
        "Оценка",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    text = models.TextField("Текст отзыва")
    status = models.CharField(
        "Статус",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)
    published_at = models.DateTimeField("Опубликован", null=True, blank=True)

    class Meta:
        verbose_name = "⭐ Отзыв о товаре/услуге"
        verbose_name_plural = "⭐ Отзывы — Товары и услуги"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "product_type", "product_slug"),
                name="unique_product_review_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=("product_type", "product_slug", "status"), name="feedback_pr_target_idx"),
        ]

    def __str__(self):
        return f"{self.author_name}: {self.product_name} ({self.rating}/5)"


class ProductReviewMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Изображение"
        VIDEO = "video", "Видео"

    review = models.ForeignKey(
        ProductReview,
        on_delete=models.CASCADE,
        related_name="media",
        verbose_name="Отзыв",
    )
    media_type = models.CharField("Тип", max_length=10, choices=MediaType.choices)
    file = models.FileField("Файл", upload_to=get_product_review_media_upload_path, max_length=1000)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "⭐ Медиа отзыва о товаре/услуге"
        verbose_name_plural = "⭐ Отзывы — Медиа товаров и услуг"
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.review_id}: {self.media_type} #{self.order + 1}"
