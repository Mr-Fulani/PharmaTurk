"""Models for the recommendation system (vector RecSys on Qdrant)."""
from django.db import models
from django.conf import settings


class ProductVector(models.Model):
    """
    Link between Django Product and Qdrant.
    Stores vector id and metadata for fast filtering.
    """
    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="vector_data",
    )
    qdrant_id = models.CharField(max_length=50, unique=True, db_index=True)

    VECTOR_TYPES = [
        ("text", "Текстовый"),
        ("image", "Изображение"),
        ("combined", "Комбинированный"),
    ]
    vector_type = models.CharField(
        max_length=20, choices=VECTOR_TYPES, default="combined"
    )

    category_id = models.IntegerField(null=True, db_index=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    brand_id = models.IntegerField(null=True, db_index=True)
    color = models.CharField(max_length=50, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    vector_quality_score = models.FloatField(
        null=True, blank=True, help_text="Уверенность энкодера"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced = models.DateTimeField(
        null=True, blank=True,
        help_text="Последняя синхронизация с Qdrant",
    )

    class Meta:
        indexes = [
            models.Index(fields=["category_id", "is_active"]),
            models.Index(fields=["price", "is_active"]),
            models.Index(fields=["color", "is_active"]),
        ]
        verbose_name = "Вектор товара"
        verbose_name_plural = "Векторы товаров"

    def __str__(self):
        title = (self.product.name[:30] + "…") if len(self.product.name) > 30 else self.product.name
        return f"Vector for {title}"


class RecommendationEvent(models.Model):
    """Analytics for recommendations (impressions, clicks, cart, purchase)."""
    EVENT_TYPES = [
        ("impression", "Показ"),
        ("click", "Клик"),
        ("cart_add", "В корзину"),
        ("purchase", "Покупка"),
    ]
    ALGORITHMS = [
        ("vector_text", "Векторный (текст)"),
        ("vector_image", "Векторный (изображение)"),
        ("vector_combined", "Векторный (комбинированный)"),
        ("collaborative", "Коллаборативный"),
        ("trending", "Тренды"),
        ("hybrid", "Гибрид"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    session_id = models.CharField(max_length=100, db_index=True, blank=True)
    source_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="recommendation_sources",
    )
    recommended_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="recommendation_targets",
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    algorithm = models.CharField(max_length=20, choices=ALGORITHMS)
    position = models.PositiveSmallIntegerField(
        help_text="Позиция в списке (1-20)",
    )
    filters_applied = models.JSONField(
        default=dict,
        blank=True,
        help_text="Примененные фильтры",
    )
    similarity_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["session_id", "created_at"]),
            models.Index(fields=["algorithm", "event_type"]),
            models.Index(fields=["source_product", "event_type"]),
        ]
        verbose_name = "Событие рекомендации"
        verbose_name_plural = "События рекомендаций"


class UserEmbedding(models.Model):
    """User preference vector for personalized recommendations."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    preference_vector = models.JSONField(null=True, blank=True)
    category_weights = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"medicines": 0.8, "supplements": 0.3}',
    )
    avg_price_viewed = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    price_sensitivity = models.CharField(
        max_length=20,
        choices=[
            ("low", "Низкая"),
            ("medium", "Средняя"),
            ("high", "Высокая"),
        ],
        default="medium",
    )
    last_updated = models.DateTimeField(auto_now=True)

    def update_from_behavior(self):
        """Update vector from view/purchase history. Stub for first phase."""
        pass

    class Meta:
        verbose_name = "Эмбеддинг пользователя"
        verbose_name_plural = "Эмбеддинги пользователей"
