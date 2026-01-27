"""Модели для системы парсеров."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator


class ScraperConfig(models.Model):
    """Конфигурация парсера сайта."""
    
    STATUS_CHOICES = [
        ('active', _('Активен')),
        ('inactive', _('Неактивен')),
        ('error', _('Ошибка')),
        ('maintenance', _('На обслуживании')),
    ]
    
    # Основная информация
    name = models.CharField(_('Название'), max_length=100, unique=True)
    parser_class = models.CharField(_('Класс парсера'), max_length=200)
    base_url = models.URLField(_('Базовый URL'))
    description = models.TextField(_('Описание'), blank=True)
    
    # Статус и настройки
    status = models.CharField(_('Статус'), max_length=20, choices=STATUS_CHOICES, default='active')
    is_enabled = models.BooleanField(_('Включен'), default=True)
    priority = models.PositiveIntegerField(_('Приоритет'), default=100, 
                                         help_text=_('Чем меньше число, тем выше приоритет'))
    
    # Настройки парсинга
    delay_min = models.FloatField(_('Минимальная задержка (сек)'), default=1.0,
                                validators=[MinValueValidator(0.1), MaxValueValidator(60.0)])
    delay_max = models.FloatField(_('Максимальная задержка (сек)'), default=3.0,
                                validators=[MinValueValidator(0.1), MaxValueValidator(60.0)])
    timeout = models.PositiveIntegerField(_('Таймаут запроса (сек)'), default=30,
                                        validators=[MinValueValidator(5), MaxValueValidator(300)])
    max_retries = models.PositiveIntegerField(_('Максимум повторов'), default=3,
                                            validators=[MinValueValidator(1), MaxValueValidator(10)])
    
    # Ограничения
    max_pages_per_run = models.PositiveIntegerField(_('Макс. страниц за запуск'), default=10,
                                                  validators=[MinValueValidator(1), MaxValueValidator(1000)])
    max_products_per_run = models.PositiveIntegerField(_('Макс. товаров за запуск'), default=100,
                                                     validators=[MinValueValidator(1), MaxValueValidator(10000)])
    
    # Расписание
    sync_enabled = models.BooleanField(_('Автосинхронизация'), default=True)
    sync_interval_hours = models.PositiveIntegerField(_('Интервал синхронизации (часы)'), default=24,
                                                    validators=[MinValueValidator(1), MaxValueValidator(168)])
    
    # Дополнительные настройки
    use_proxy = models.BooleanField(_('Использовать прокси'), default=False)
    user_agent = models.CharField(_('User-Agent'), max_length=500, blank=True)
    headers = models.JSONField(_('Дополнительные заголовки'), default=dict, blank=True)
    cookies = models.JSONField(_('Cookies'), default=dict, blank=True)
    
    # Статистика
    last_run_at = models.DateTimeField(_('Последний запуск'), null=True, blank=True)
    last_success_at = models.DateTimeField(_('Последний успешный запуск'), null=True, blank=True)
    last_error_at = models.DateTimeField(_('Последняя ошибка'), null=True, blank=True)
    last_error_message = models.TextField(_('Сообщение об ошибке'), blank=True)
    
    total_runs = models.PositiveIntegerField(_('Всего запусков'), default=0)
    successful_runs = models.PositiveIntegerField(_('Успешных запусков'), default=0)
    total_products_scraped = models.PositiveIntegerField(_('Всего товаров спаршено'), default=0)
    
    # Временные метки
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Конфигурация парсера')
        verbose_name_plural = _('Конфигурации парсеров')
        ordering = ['priority', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    @property
    def success_rate(self) -> float:
        """Возвращает процент успешных запусков."""
        if self.total_runs == 0:
            return 0.0
        return (self.successful_runs / self.total_runs) * 100
    
    def clean(self):
        """Валидация модели."""
        from django.core.exceptions import ValidationError
        
        if self.delay_min > self.delay_max:
            raise ValidationError(_('Минимальная задержка не может быть больше максимальной'))


class ScrapingSession(models.Model):
    """Сессия парсинга - один запуск парсера."""
    
    STATUS_CHOICES = [
        ('pending', _('Ожидает')),
        ('running', _('Выполняется')),
        ('completed', _('Завершено')),
        ('failed', _('Ошибка')),
        ('cancelled', _('Отменено')),
    ]
    
    # Связи
    scraper_config = models.ForeignKey(ScraperConfig, on_delete=models.CASCADE,
                                     related_name='sessions', verbose_name=_('Конфигурация парсера'))
    
    # Основная информация
    status = models.CharField(_('Статус'), max_length=20, choices=STATUS_CHOICES, default='pending')
    task_id = models.CharField(_('ID задачи Celery'), max_length=100, blank=True)
    
    # Параметры запуска
    start_url = models.URLField(_('Начальный URL'), blank=True)
    max_pages = models.PositiveIntegerField(_('Макс. страниц'), default=10)
    max_products = models.PositiveIntegerField(_('Макс. товаров'), default=100)
    
    # Результаты
    pages_processed = models.PositiveIntegerField(_('Обработано страниц'), default=0)
    products_found = models.PositiveIntegerField(_('Найдено товаров'), default=0)
    products_created = models.PositiveIntegerField(_('Создано товаров'), default=0)
    products_updated = models.PositiveIntegerField(_('Обновлено товаров'), default=0)
    products_skipped = models.PositiveIntegerField(_('Пропущено товаров'), default=0)
    errors_count = models.PositiveIntegerField(_('Количество ошибок'), default=0)
    
    # Временные метки
    started_at = models.DateTimeField(_('Начало'), null=True, blank=True)
    finished_at = models.DateTimeField(_('Окончание'), null=True, blank=True)
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    
    # Логи и ошибки
    log_messages = models.JSONField(_('Сообщения лога'), default=list, blank=True)
    error_message = models.TextField(_('Сообщение об ошибке'), blank=True)
    
    class Meta:
        verbose_name = _('Сессия парсинга')
        verbose_name_plural = _('Сессии парсинга')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.scraper_config.name} - {self.get_status_display()} ({self.created_at})"
    
    @property
    def duration(self):
        """Возвращает продолжительность сессии."""
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None
    
    @property
    def success_rate(self) -> float:
        """Возвращает процент успешно обработанных товаров."""
        if self.products_found == 0:
            return 0.0
        successful = self.products_created + self.products_updated
        return (successful / self.products_found) * 100


class CategoryMapping(models.Model):
    """Маппинг категорий с внешнего сайта на внутренние категории."""
    
    # Связи
    scraper_config = models.ForeignKey(ScraperConfig, on_delete=models.CASCADE,
                                     related_name='category_mappings', 
                                     verbose_name=_('Конфигурация парсера'))
    internal_category = models.ForeignKey('catalog.Category', on_delete=models.CASCADE,
                                        verbose_name=_('Внутренняя категория'))
    
    # Маппинг
    external_category_name = models.CharField(_('Внешнее название категории'), max_length=200)
    external_category_url = models.URLField(_('URL внешней категории'), blank=True)
    external_category_id = models.CharField(_('ID внешней категории'), max_length=100, blank=True)
    
    # Настройки
    is_active = models.BooleanField(_('Активно'), default=True)
    priority = models.PositiveIntegerField(_('Приоритет'), default=100)
    
    # Временные метки
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Маппинг категории')
        verbose_name_plural = _('Маппинги категорий')
        unique_together = ['scraper_config', 'external_category_name']
        ordering = ['priority', 'external_category_name']
    
    def __str__(self):
        return f"{self.external_category_name} → {self.internal_category.name}"


class BrandMapping(models.Model):
    """Маппинг брендов с внешнего сайта на внутренние бренды."""
    
    # Связи
    scraper_config = models.ForeignKey(ScraperConfig, on_delete=models.CASCADE,
                                     related_name='brand_mappings', 
                                     verbose_name=_('Конфигурация парсера'))
    internal_brand = models.ForeignKey('catalog.Brand', on_delete=models.CASCADE,
                                     verbose_name=_('Внутренний бренд'))
    
    # Маппинг
    external_brand_name = models.CharField(_('Внешнее название бренда'), max_length=200)
    external_brand_url = models.URLField(_('URL внешнего бренда'), blank=True)
    external_brand_id = models.CharField(_('ID внешнего бренда'), max_length=100, blank=True)
    
    # Настройки
    is_active = models.BooleanField(_('Активно'), default=True)
    priority = models.PositiveIntegerField(_('Приоритет'), default=100)
    
    # Временные метки
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('Маппинг бренда')
        verbose_name_plural = _('Маппинги брендов')
        unique_together = ['scraper_config', 'external_brand_name']
        ordering = ['priority', 'external_brand_name']
    
    def __str__(self):
        return f"{self.external_brand_name} → {self.internal_brand.name}"


class ScrapedProductLog(models.Model):
    """Лог спарсенных товаров для отслеживания изменений."""
    
    ACTION_CHOICES = [
        ('created', _('Создан')),
        ('updated', _('Обновлен')),
        ('skipped', _('Пропущен')),
        ('error', _('Ошибка')),
        ('duplicate', _('Дубликат')),
    ]
    
    # Связи
    session = models.ForeignKey(ScrapingSession, on_delete=models.CASCADE,
                              related_name='product_logs', verbose_name=_('Сессия'))
    product = models.ForeignKey('catalog.Product', on_delete=models.SET_NULL,
                              null=True, blank=True, verbose_name=_('Товар'))
    
    # Информация о товаре
    external_id = models.CharField(_('Внешний ID'), max_length=200)
    external_url = models.URLField(_('Внешний URL'))
    product_name = models.CharField(_('Название товара'), max_length=500)
    
    # Действие
    action = models.CharField(_('Действие'), max_length=20, choices=ACTION_CHOICES)
    message = models.TextField(_('Сообщение'), blank=True)
    
    # Данные товара (для отладки)
    scraped_data = models.JSONField(_('Спарсенные данные'), default=dict, blank=True)
    
    # Временная метка
    created_at = models.DateTimeField(_('Дата создания'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('Лог товара')
        verbose_name_plural = _('Логи товаров')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session', 'action']),
            models.Index(fields=['external_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.product_name} - {self.get_action_display()}"


class InstagramScraperTask(models.Model):
    """Задача для парсинга Instagram аккаунта."""
    
    STATUS_CHOICES = [
        ('pending', _('Ожидает')),
        ('running', _('Выполняется')),
        ('completed', _('Завершено')),
        ('failed', _('Ошибка')),
    ]
    
    CATEGORY_CHOICES = [
        ('books', _('Книги')),
        ('clothing', _('Одежда')),
        ('shoes', _('Обувь')),
        ('electronics', _('Электроника')),
        ('supplements', _('Добавки')),
        ('medical-equipment', _('Медицинское оборудование')),
        ('furniture', _('Мебель')),
        ('tableware', _('Посуда')),
        ('accessories', _('Аксессуары')),
        ('jewelry', _('Ювелирные изделия')),
        ('underwear', _('Нижнее белье')),
        ('headwear', _('Головные уборы')),
    ]
    
    # Параметры парсинга
    instagram_username = models.CharField(
        _('Instagram username'),
        max_length=100,
        help_text=_('Введите username без @ (например: book.warrior)')
    )
    category = models.CharField(
        _('Категория товаров'),
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='books'
    )
    max_posts = models.PositiveIntegerField(
        _('Максимум постов'),
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text=_('Количество постов для парсинга (не критично если больше чем есть)')
    )
    
    # Статус и результаты
    status = models.CharField(_('Статус'), max_length=20, choices=STATUS_CHOICES, default='pending')
    products_created = models.PositiveIntegerField(_('Создано товаров'), default=0)
    products_updated = models.PositiveIntegerField(_('Обновлено товаров'), default=0)
    products_skipped = models.PositiveIntegerField(_('Пропущено товаров'), default=0)
    
    # Логи
    log_output = models.TextField(_('Лог выполнения'), blank=True)
    error_message = models.TextField(_('Сообщение об ошибке'), blank=True)
    
    # Временные метки
    created_at = models.DateTimeField(_('Создано'), auto_now_add=True)
    started_at = models.DateTimeField(_('Начало выполнения'), null=True, blank=True)
    finished_at = models.DateTimeField(_('Завершено'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('Задача парсинга Instagram')
        verbose_name_plural = _('Задачи парсинга Instagram')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"@{self.instagram_username} ({self.get_category_display()}) - {self.get_status_display()}"
    
    @property
    def duration(self):
        """Возвращает продолжительность выполнения."""
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None
