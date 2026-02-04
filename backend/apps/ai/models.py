from django.db import models
from django.conf import settings
from apps.catalog.models import Product, Category

class AIProcessingStatus(models.TextChoices):
    PENDING = 'pending', 'В очереди'
    PROCESSING = 'processing', 'Обработка'
    COMPLETED = 'completed', 'Завершено'
    FAILED = 'failed', 'Ошибка'
    MODERATION = 'moderation', 'На модерации'
    APPROVED = 'approved', 'Одобрено'
    REJECTED = 'rejected', 'Отклонено'

class AIProcessingLog(models.Model):
    """
    Полный лог AI обработки товара.
    Хранит входные данные, результаты, метрики для аудита.
    """
    PROCESSING_TYPES = [
        ('description_only', 'Только описание'),
        ('categorization_only', 'Только категоризация'),
        ('full', 'Полная обработка'),
        ('image_analysis', 'Анализ изображений'),
    ]

    # Связи
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='ai_logs',
        verbose_name='Товар'
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_processed',
        verbose_name='Обработал (модератор)'
    )

    # Тип и статус обработки
    processing_type = models.CharField(
        max_length=20,
        choices=PROCESSING_TYPES,
        default='full',
        verbose_name='Тип обработки'
    )
    status = models.CharField(
        max_length=20,
        choices=AIProcessingStatus.choices,
        default=AIProcessingStatus.PENDING,
        verbose_name='Статус'
    )

    # Входные данные (сохраняем полностью для воспроизводимости)
    input_data = models.JSONField(
        verbose_name='Входные данные',
        help_text='Сырые данные от парсера: title, description, specs, images_urls и т.д.'
    )
    input_images_urls = models.JSONField(
        default=list,
        verbose_name='URL изображений (вход)',
        help_text='Ссылки на R2 или оригинальные URL'
    )

    # Результаты генерации описания
    generated_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Сгенерированный заголовок'
    )
    generated_description = models.TextField(
        null=True,
        blank=True,
        verbose_name='Сгенерированное описание'
    )
    generated_seo_title = models.CharField(
        max_length=70,
        null=True,
        blank=True,
        verbose_name='SEO заголовок'
    )
    generated_seo_description = models.CharField(
        max_length=160,
        null=True,
        blank=True,
        verbose_name='SEO описание'
    )
    generated_keywords = models.JSONField(
        default=list,
        verbose_name='Ключевые слова'
    )

    # Результаты категоризации
    suggested_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_suggestions',
        verbose_name='Предложенная категория'
    )
    category_confidence = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Уверенность в категории',
        help_text='0.0 - 1.0'
    )
    category_alternatives = models.JSONField(
        default=list,
        verbose_name='Альтернативные категории',
        help_text='Топ-3 альтернативы с confidence score'
    )

    # Атрибуты, извлеченные AI
    extracted_attributes = models.JSONField(
        default=dict,
        verbose_name='Извлеченные атрибуты',
        help_text='{"color": "красный", "material": "хлопок", "size": "M-L"}'
    )

    # Анализ изображений (если применялся)
    image_analysis = models.JSONField(
        default=dict,
        verbose_name='Анализ изображений',
        help_text='{"dominant_colors": ["#FF0000"], "detected_objects": ["dress"], "quality_score": 0.85}'
    )

    # Технические метаданные
    llm_model = models.CharField(
        max_length=50,
        default='gpt-4o-mini',
        verbose_name='Использованная модель'
    )
    tokens_used = models.JSONField(
        default=dict,
        verbose_name='Использовано токенов',
        help_text='{"prompt": 150, "completion": 200, "total": 350}'
    )
    processing_time_ms = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Время обработки (мс)'
    )
    cost_usd = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name='Стоимость ($)'
    )

    # Полный raw response для отладки
    raw_llm_response = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Полный ответ LLM'
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name='Сообщение об ошибке'
    )
    stack_trace = models.TextField(
        null=True,
        blank=True,
        verbose_name='Stack trace (при ошибке)'
    )

    # Модерация
    moderation_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name='Заметки модератора'
    )
    moderation_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата модерации'
    )

    # Таймстампы
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Лог AI обработки'
        verbose_name_plural = 'Логи AI обработки'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['product', 'created_at']),
            models.Index(fields=['suggested_category', 'category_confidence']),
        ]

    def __str__(self):
        return f"#{self.id} {self.product.name[:30]} - {self.status}"

class AITemplate(models.Model):
    """
    Шаблоны для few-shot learning и промптов
    """
    TEMPLATE_TYPES = [
        ('description', 'Описание товара'),
        ('category_example', 'Пример категории'),
        ('attribute_extraction', 'Извлечение атрибутов'),
        ('image_prompt', 'Анализ изображения'),
    ]

    name = models.CharField(max_length=100, unique=True)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_templates'
    )

    # Контент для RAG
    content = models.TextField(help_text='Текст шаблона или примера')
    embedding_vector = models.JSONField(
        null=True,
        blank=True,
        help_text='Кеш эмбеддинга (опционально)'
    )

    # Метаданные
    language = models.CharField(max_length=10, default='ru')
    is_active = models.BooleanField(default=True)
    usage_count = models.PositiveIntegerField(default=0)
    success_rate = models.FloatField(default=0.0)  # На основе модерации

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AI шаблон'
        verbose_name_plural = 'AI шаблоны'

class AIModerationQueue(models.Model):
    """
    Очередь на модерацию для сомнительных результатов
    """
    PRIORITY_CHOICES = [
        (1, 'Низкий'),
        (2, 'Средний'),
        (3, 'Высокий'),
    ]

    log_entry = models.OneToOneField(
        AIProcessingLog,
        on_delete=models.CASCADE,
        related_name='moderation_queue'
    )
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, default=2)
    reason = models.CharField(
        max_length=100,
        help_text='Причина отправки на модерацию: low_confidence, sensitive_content и т.д.'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_moderation_tasks'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-priority', 'created_at']
