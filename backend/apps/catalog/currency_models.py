import uuid
from decimal import Decimal
from django.db import models
from django.db.models import JSONField
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class CurrencyRate(models.Model):
    """Модель для хранения курсов валют"""
    
    CURRENCY_CHOICES = [
        ('TRY', 'Турецкая лира'),
        ('RUB', 'Российский рубль'),
        ('KZT', 'Казахстанский тенге'),
        ('USD', 'Доллар США'),
        ('EUR', 'Евро'),
        ('USDT', 'Tether (USDT)'),
    ]
    
    SOURCE_CHOICES = [
        ('centralbank_rf', 'Центробанк РФ'),
        ('nationalbank_kz', 'Нацбанк Казахстана'),
        ('centralbank_tr', 'Центробанк Турции'),
        ('openexchangerates', 'OpenExchangeRates API'),
        ('manual', 'Ручной ввод'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_currency = models.CharField(max_length=4, choices=CURRENCY_CHOICES, verbose_name='Из валюты')
    to_currency = models.CharField(max_length=4, choices=CURRENCY_CHOICES, verbose_name='В валюту')
    rate = models.DecimalField(max_digits=10, decimal_places=6, validators=[MinValueValidator(0)], verbose_name='Курс')
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, verbose_name='Источник')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        unique_together = ['from_currency', 'to_currency']
        ordering = ['-updated_at']
        verbose_name = '💰 Курс валют'
        verbose_name_plural = '💰 Валюты — Курсы валют'
    
    def __str__(self):
        return f"{self.from_currency} → {self.to_currency}: {self.rate}"


class GlobalCurrencySettings(models.Model):
    """
    Глобальные настройки валют и маржи для интернет-магазина (Singleton).
    """
    
    default_margin_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('15.00'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Маржа по умолчанию (%)',
        help_text="Используется если для конкретной пары валют не задана своя маржа (по умолчанию 15%)."
    )
    
    usdt_markup_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('3.00'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Наценка USDT (%)',
        help_text="На сколько процентов USDT дороже базового USD (по умолчанию 3%)."
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'глобальная настройка валют'
        verbose_name_plural = '🌐 Настройки: Валюты и Маржа'

    def __str__(self):
        return f"Глобальные настройки валют (Маржа: {self.default_margin_percentage}%, USDT наценка: {self.usdt_markup_percentage}%)"
        
    def save(self, *args, **kwargs):
        """Гарантирует существование только одной записи (Singleton) и очищает кэш при сохранении."""
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete("global_currency_settings")

    def delete(self, *args, **kwargs):
        """Предотвращает удаление единственной записи."""
        pass

    @classmethod
    def load(cls):
        """
        Загружает настройки из кэша. Если в кэше нет — берет из БД (или создает дефолтные).
        """
        if obj := cache.get("global_currency_settings"):
            return obj
            
        obj, created = cls.objects.get_or_create(pk=1)
        cache.set("global_currency_settings", obj, timeout=60 * 60 * 24)  # Кэшируем на сутки
        return obj


class MarginSettings(models.Model):
    """Модель для хранения настроек маржи"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    currency_pair = models.CharField(
        max_length=10, 
        verbose_name='Пара валют',
        help_text="Формат: ИЗ-В (например, TRY-RUB)"
    )
    margin_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100)
        ],
        verbose_name='Маржа (%)',
        help_text="Процент маржи (например, 15 для 15%)"
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    description = models.TextField(blank=True, verbose_name='Описание', help_text="Описание настройки маржи")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        unique_together = ['currency_pair']
        ordering = ['currency_pair']
        verbose_name = '💰 Настройка маржи'
        verbose_name_plural = '💰 Валюты — Настройки маржи'
    
    def __str__(self):
        return f"{self.currency_pair}: {self.margin_percentage}%"


class ProductPrice(models.Model):
    """Модель для хранения цен товара с конвертацией во все валюты"""
    
    CURRENCY_CHOICES = [
        ('TRY', 'Турецкая лира'),
        ('RUB', 'Российский рубль'),
        ('KZT', 'Казахстанский тенге'),
        ('USD', 'Доллар США'),
        ('EUR', 'Евро'),
        ('USDT', 'Tether (USDT)'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(
        'catalog.Product', 
        on_delete=models.CASCADE, 
        related_name='price_info',
        verbose_name='Товар'
    )
    
    # Базовая цена товара
    base_currency = models.CharField(max_length=4, choices=CURRENCY_CHOICES, default='TRY', verbose_name='Базовая валюта')
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
        verbose_name='Базовая цена',
        help_text="Цена в исходной валюте"
    )
    
    # Цены в разных валютах
    rub_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в RUB',
        help_text="Конвертированная цена в рублях"
    )
    rub_price_with_margin = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в RUB с маржой'
    )
    
    usd_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USD',
        help_text="Конвертированная цена в долларах"
    )
    usd_price_with_margin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USD с маржой'
    )
    
    kzt_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в KZT',
        help_text="Конвертированная цена в тенге"
    )
    kzt_price_with_margin = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в KZT с маржой'
    )
    
    eur_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в EUR',
        help_text="Конвертированная цена в евро"
    )
    eur_price_with_margin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в EUR с маржой'
    )
    
    try_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в TRY',
        help_text="Конвертированная цена в турецких лирах"
    )
    try_price_with_margin = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в TRY с маржой'
    )
    
    usdt_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USDT',
        help_text="Конвертированная цена в USDT"
    )
    usdt_price_with_margin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USDT с маржой'
    )
    
    # Будущие поля для доставки
    air_shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Стоимость авиадоставки',
        help_text="Фиксированная стоимость доставки в валюте продажи (не в процентах)"
    )
    sea_shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Стоимость морской доставки',
        help_text="Фиксированная стоимость доставки в валюте продажи (не в процентах)"
    )
    ground_shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Стоимость наземной доставки',
        help_text="Фиксированная стоимость доставки в валюте продажи (не в процентах)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        verbose_name = '💰 Цены товара'
        verbose_name_plural = '💰 Валюты — Цены товаров'
    
    def __str__(self):
        return f"{self.product.name} - {self.base_price} {self.base_currency}"


class CurrencyUpdateLog(models.Model):
    """Лог обновления курсов валют"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=50, verbose_name='Источник')
    success = models.BooleanField(default=True, verbose_name='Успешно')
    rates_updated = models.PositiveIntegerField(default=0, verbose_name='Обновлено курсов')
    error_message = models.TextField(blank=True, verbose_name='Ошибка')
    execution_time_seconds = models.FloatField(null=True, blank=True, verbose_name='Время выполнения (сек)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = '💰 Лог обновления курсов'
        verbose_name_plural = '💰 Валюты — Логи обновления курсов'
    
    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.source} - {status} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ProductVariantPrice(models.Model):
    """Модель для хранения цен вариантов товаров с конвертацией во все валюты"""
    
    CURRENCY_CHOICES = [
        ('TRY', 'Турецкая лира'),
        ('RUB', 'Российский рубль'),
        ('KZT', 'Казахстанский тенге'),
        ('USD', 'Доллар США'),
        ('EUR', 'Евро'),
        ('USDT', 'Tether (USDT)'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Полиморфная связь с вариантами разных типов
    content_type = models.ForeignKey('contenttypes.ContentType', on_delete=models.CASCADE, verbose_name='Тип варианта')
    object_id = models.UUIDField(verbose_name='ID варианта')
    variant = GenericForeignKey('content_type', 'object_id')
    
    # Базовая цена варианта
    base_currency = models.CharField(max_length=4, choices=CURRENCY_CHOICES, default='TRY', verbose_name='Базовая валюта')
    base_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
        verbose_name='Базовая цена',
        help_text="Цена в исходной валюте"
    )
    
    # Цены в разных валютах
    rub_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в RUB',
        help_text="Конвертированная цена в рублях"
    )
    rub_price_with_margin = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в RUB с маржой'
    )
    
    usd_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USD',
        help_text="Конвертированная цена в долларах"
    )
    usd_price_with_margin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USD с маржой'
    )
    
    kzt_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в KZT',
        help_text="Конвертированная цена в тенге"
    )
    kzt_price_with_margin = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в KZT с маржой'
    )
    
    eur_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в EUR',
        help_text="Конвертированная цена в евро"
    )
    eur_price_with_margin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в EUR с маржой'
    )
    
    try_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в TRY',
        help_text="Конвертированная цена в турецких лирах"
    )
    try_price_with_margin = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в TRY с маржой'
    )
    
    usdt_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USDT',
        help_text="Конвертированная цена в USDT"
    )
    usdt_price_with_margin = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Цена в USDT с маржой'
    )
    
    # Стоимость доставки для варианта
    air_shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Стоимость авиадоставки',
        help_text="Фиксированная стоимость доставки в валюте продажи (не в процентах)"
    )
    sea_shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Стоимость морской доставки',
        help_text="Фиксированная стоимость доставки в валюте продажи (не в процентах)"
    )
    ground_shipping_cost = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True, blank=True,
        verbose_name='Стоимость наземной доставки',
        help_text="Фиксированная стоимость доставки в валюте продажи (не в процентах)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    
    class Meta:
        verbose_name = '💰 Цены варианта товара'
        verbose_name_plural = '💰 Валюты — Цены вариантов товаров'
        unique_together = ['content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        try:
            return f"{self.variant} - {self.base_price} {self.base_currency}"
        except:
            return f"Вариант {self.object_id} - {self.base_price} {self.base_currency}"
