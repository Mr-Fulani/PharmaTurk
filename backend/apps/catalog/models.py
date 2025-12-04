"""Модели для каталога товаров."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class Category(models.Model):
    """Категория товаров."""
    
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    parent = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="children",
        verbose_name=_("Родительская категория")
    )
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)
    margin_percent = models.DecimalField(
        _("Маржа, %"), max_digits=5, decimal_places=2, default=0,
        help_text=_("Процент наценки для категории; перекрывается на уровне бренда/товара")
    )
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Категория")
        verbose_name_plural = _("Категории")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Brand(models.Model):
    """Бренд товаров."""
    
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    logo = models.URLField(_("Логотип"), blank=True)
    website = models.URLField(_("Сайт"), blank=True)
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    margin_percent = models.DecimalField(
        _("Маржа, %"), max_digits=5, decimal_places=2, default=0,
        help_text=_("Процент наценки для бренда; перекрывает категорию и наследуется товарами")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Бренд")
        verbose_name_plural = _("Бренды")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """Товар в каталоге."""
    
    # Основная информация
    name = models.CharField(_("Название"), max_length=500)
    slug = models.SlugField(_("Slug"), max_length=500, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    
    # Категоризация
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="products",
        verbose_name=_("Категория")
    )
    brand = models.ForeignKey(
        Brand, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="products",
        verbose_name=_("Бренд")
    )
    
    # Цена и валюта
    # Базовая цена и валюта из внешнего API
    price = models.DecimalField(
        _("Цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    old_price = models.DecimalField(
        _("Старая цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )

    # Конвертированные и финальные цены
    converted_price_rub = models.DecimalField(
        _("Цена в RUB (конверт.)"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    converted_price_usd = models.DecimalField(
        _("Цена в USD (конверт.)"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    final_price_rub = models.DecimalField(
        _("Итоговая цена RUB"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    final_price_usd = models.DecimalField(
        _("Итоговая цена USD"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    margin_percent_applied = models.DecimalField(
        _("Применённая маржа, %"), max_digits=5, decimal_places=2, default=0
    )
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(_("Главное изображение"), blank=True)
    
    # Внешние данные
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    
    # Метаданные
    sku = models.CharField(_("SKU"), max_length=100, blank=True)
    barcode = models.CharField(_("Штрихкод"), max_length=50, blank=True)
    
    # Статус
    is_active = models.BooleanField(_("Активен"), default=True)
    is_featured = models.BooleanField(_("Рекомендуемый"), default=False)
    
    # Временные метки
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    last_synced_at = models.DateTimeField(_("Последняя синхронизация"), null=True, blank=True)
    last_external_updated_at = models.DateTimeField(_("Изменён во внешнем API"), null=True, blank=True)

    class Meta:
        verbose_name = _("Товар")
        verbose_name_plural = _("Товары")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    """Изображение товара."""
    
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name="images",
        verbose_name=_("Товар")
    )
    image_url = models.URLField(_("URL изображения"))
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение товара")
        verbose_name_plural = _("Изображения товаров")
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"Изображение {self.product.name}"


class ProductAttribute(models.Model):
    """Атрибут товара (состав, показания, противопоказания и т.д.)."""
    
    ATTRIBUTE_TYPES = [
        ("composition", _("Состав")),
        ("indications", _("Показания")),
        ("contraindications", _("Противопоказания")),
        ("side_effects", _("Побочные эффекты")),
        ("dosage", _("Дозировка")),
        ("storage", _("Условия хранения")),
        ("expiry", _("Срок годности")),
        ("manufacturer", _("Производитель")),
        ("country", _("Страна производства")),
        ("form", _("Форма выпуска")),
        ("weight", _("Вес/объем")),
        ("other", _("Другое")),
    ]
    
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name="attributes",
        verbose_name=_("Товар")
    )
    attribute_type = models.CharField(_("Тип атрибута"), max_length=50, choices=ATTRIBUTE_TYPES)
    name = models.CharField(_("Название"), max_length=200)
    value = models.TextField(_("Значение"))
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Атрибут товара")
        verbose_name_plural = _("Атрибуты товаров")
        ordering = ["sort_order", "name"]
        unique_together = ["product", "attribute_type", "name"]

    def __str__(self):
        return f"{self.product.name} - {self.get_attribute_type_display()}: {self.name}"


class PriceHistory(models.Model):
    """История изменения цен товара."""
    
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name="price_history",
        verbose_name=_("Товар")
    )
    price = models.DecimalField(_("Цена"), max_digits=10, decimal_places=2)
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    recorded_at = models.DateTimeField(_("Дата записи"), auto_now_add=True)
    source = models.CharField(_("Источник"), max_length=50, default="api")

    class Meta:
        verbose_name = _("История цен")
        verbose_name_plural = _("История цен")
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"{self.product.name} - {self.price} {self.currency} ({self.recorded_at})"


class Favorite(models.Model):
    """Избранное пользователя."""
    
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='favorites',
        null=True,
        blank=True,
        verbose_name=_("Пользователь")
    )
    
    # GenericForeignKey для поддержки всех типов товаров
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("Тип товара")
    )
    object_id = models.PositiveIntegerField(verbose_name=_("ID товара"))
    product = GenericForeignKey('content_type', 'object_id')
    
    session_key = models.CharField(
        _("Ключ сессии"),
        max_length=100,
        null=True,
        blank=True,
        help_text=_("Для анонимных пользователей")
    )
    created_at = models.DateTimeField(_("Дата добавления"), auto_now_add=True)

    class Meta:
        verbose_name = _("Избранное")
        verbose_name_plural = _("Избранное")
        unique_together = [
            ('user', 'content_type', 'object_id'),
            ('session_key', 'content_type', 'object_id'),
        ]
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['session_key', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        user_str = self.user.email if self.user else f"Session: {self.session_key}"
        product_name = getattr(self.product, 'name', 'Unknown')
        return f"{user_str} - {product_name}"


# ============================================================================
# НОВЫЕ МОДЕЛИ ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

class ClothingCategory(models.Model):
    """Категория одежды."""
    
    GENDER_CHOICES = [
        ('men', _('Мужская')),
        ('women', _('Женская')),
        ('unisex', _('Унисекс')),
        ('kids', _('Детская')),
    ]
    
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    parent = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="children",
        verbose_name=_("Родительская категория")
    )
    gender = models.CharField(_("Пол"), max_length=10, choices=GENDER_CHOICES, default='unisex')
    clothing_type = models.CharField(_("Тип одежды"), max_length=100, blank=True)  # платья, блузки, джинсы
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Категория одежды")
        verbose_name_plural = _("Категории одежды")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ClothingProduct(models.Model):
    """Товар одежды."""
    
    # Основная информация
    name = models.CharField(_("Название"), max_length=500)
    slug = models.SlugField(_("Slug"), max_length=500, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    
    # Категоризация
    category = models.ForeignKey(
        ClothingCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="products",
        verbose_name=_("Категория")
    )
    brand = models.ForeignKey(
        Brand, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="clothing_products",
        verbose_name=_("Бренд")
    )
    
    # Цена
    price = models.DecimalField(
        _("Цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    old_price = models.DecimalField(
        _("Старая цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Специфичные для одежды поля
    size = models.CharField(_("Размер"), max_length=20, blank=True)
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    material = models.CharField(_("Материал"), max_length=100, blank=True)
    season = models.CharField(_("Сезон"), max_length=50, blank=True)  # лето, зима, демисезон
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(_("Главное изображение"), blank=True)
    
    # Внешние данные
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    
    # Статус
    is_active = models.BooleanField(_("Активен"), default=True)
    is_featured = models.BooleanField(_("Рекомендуемый"), default=False)
    
    # Временные метки
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Товар одежды")
        verbose_name_plural = _("Товары одежды")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name


class ShoeCategory(models.Model):
    """Категория обуви."""
    
    GENDER_CHOICES = [
        ('men', _('Мужская')),
        ('women', _('Женская')),
        ('unisex', _('Унисекс')),
        ('kids', _('Детская')),
    ]
    
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    parent = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="children",
        verbose_name=_("Родительская категория")
    )
    gender = models.CharField(_("Пол"), max_length=10, choices=GENDER_CHOICES, default='unisex')
    shoe_type = models.CharField(_("Тип обуви"), max_length=100, blank=True)  # туфли, кроссовки, сапоги
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Категория обуви")
        verbose_name_plural = _("Категории обуви")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ShoeProduct(models.Model):
    """Товар обуви."""
    
    # Основная информация
    name = models.CharField(_("Название"), max_length=500)
    slug = models.SlugField(_("Slug"), max_length=500, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    
    # Категоризация
    category = models.ForeignKey(
        ShoeCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="products",
        verbose_name=_("Категория")
    )
    brand = models.ForeignKey(
        Brand, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="shoe_products",
        verbose_name=_("Бренд")
    )
    
    # Цена
    price = models.DecimalField(
        _("Цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    old_price = models.DecimalField(
        _("Старая цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Специфичные для обуви поля
    size = models.CharField(_("Размер"), max_length=20, blank=True)
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    material = models.CharField(_("Материал"), max_length=100, blank=True)
    heel_height = models.CharField(_("Высота каблука"), max_length=50, blank=True)
    sole_type = models.CharField(_("Тип подошвы"), max_length=100, blank=True)
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(_("Главное изображение"), blank=True)
    
    # Внешние данные
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    
    # Статус
    is_active = models.BooleanField(_("Активен"), default=True)
    is_featured = models.BooleanField(_("Рекомендуемый"), default=False)
    
    # Временные метки
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Товар обуви")
        verbose_name_plural = _("Товары обуви")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name


class ElectronicsCategory(models.Model):
    """Категория электроники."""
    
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    parent = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="children",
        verbose_name=_("Родительская категория")
    )
    device_type = models.CharField(_("Тип устройства"), max_length=100, blank=True)  # телефоны, ноутбуки, планшеты
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активна"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Категория электроники")
        verbose_name_plural = _("Категории электроники")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ElectronicsProduct(models.Model):
    """Товар электроники."""
    
    # Основная информация
    name = models.CharField(_("Название"), max_length=500)
    slug = models.SlugField(_("Slug"), max_length=500, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    
    # Категоризация
    category = models.ForeignKey(
        ElectronicsCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="products",
        verbose_name=_("Категория")
    )
    brand = models.ForeignKey(
        Brand, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="electronics_products",
        verbose_name=_("Бренд")
    )
    
    # Цена
    price = models.DecimalField(
        _("Цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(_("Валюта"), max_length=3, default="RUB")
    old_price = models.DecimalField(
        _("Старая цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Специфичные для электроники поля
    model = models.CharField(_("Модель"), max_length=100, blank=True)
    specifications = models.JSONField(_("Характеристики"), default=dict, blank=True)
    warranty = models.CharField(_("Гарантия"), max_length=100, blank=True)
    power_consumption = models.CharField(_("Потребление энергии"), max_length=50, blank=True)
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(_("Главное изображение"), blank=True)
    
    # Внешние данные
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    
    # Статус
    is_active = models.BooleanField(_("Активен"), default=True)
    is_featured = models.BooleanField(_("Рекомендуемый"), default=False)
    
    # Временные метки
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Товар электроники")
        verbose_name_plural = _("Товары электроники")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name


class Banner(models.Model):
    """Баннер для главной страницы."""
    
    POSITION_CHOICES = [
        ('main', _('Главный баннер (вверху страницы)')),
        ('after_brands', _('После блока "Популярные бренды"')),
        ('before_footer', _('Перед футером')),
        ('after_popular_products', _('После популярных товаров')),
    ]
    
    title = models.CharField(
        max_length=200,
        verbose_name='Заголовок баннера'
    )
    position = models.CharField(
        max_length=50,
        choices=POSITION_CHOICES,
        default='main',
        verbose_name='Позиция баннера',
        db_index=True
    )
    
    # Ссылка при клике
    link_url = models.URLField(
        _("Ссылка при клике"),
        blank=True,
        help_text=_("URL для перехода при клике на баннер")
    )
    link_text = models.CharField(
        _("Текст кнопки"),
        max_length=100,
        blank=True,
        help_text=_("Текст кнопки, отображаемой поверх медиа-контента")
    )
    
    # Настройки отображения
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(
        _("Порядок сортировки"),
        default=0,
        help_text=_("Чем меньше число, тем выше баннер в карусели")
    )
    
    # Метаданные
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Баннер")
        verbose_name_plural = _("Баннеры")
        ordering = ['position', 'sort_order', '-created_at']
        indexes = [
            models.Index(fields=['position', 'is_active', 'sort_order']),
        ]
    
    def __str__(self):
        position_display = dict(self.POSITION_CHOICES).get(self.position, self.position)
        title_part = f" - {self.title}" if self.title else ""
        return f"{position_display}{title_part}"


class BannerMedia(models.Model):
    """Медиа-файл для баннера (изображение, видео или GIF)."""
    
    CONTENT_TYPE_CHOICES = [
        ('image', _('Изображение')),
        ('video', _('Видео')),
        ('gif', _('GIF анимация')),
    ]
    
    banner = models.ForeignKey(
        Banner,
        on_delete=models.CASCADE,
        related_name='media_files',
        verbose_name=_("Баннер")
    )
    link_url = models.URLField(
        _("Ссылка при клике на медиа"),
        blank=True,
        help_text=_("URL для перехода при клике на этот конкретный медиа-элемент. Если пусто, используется ссылка баннера.")
    )
    content_type = models.CharField(
        _("Тип контента"),
        max_length=10,
        choices=CONTENT_TYPE_CHOICES,
        default='image',
        help_text=_("Тип медиа-контента")
    )
    
    # Поля для изображения
    image = models.ImageField(
        _("Изображение"),
        upload_to='banners/',
        blank=True,
        null=True,
        help_text=_("Изображение для баннера (JPG, PNG)")
    )
    image_url = models.URLField(
        _("URL изображения"),
        blank=True,
        help_text=_("Внешний URL изображения (если не загружено локально)")
    )
    
    # Поля для видео
    video_url = models.URLField(
        _("URL видео"),
        blank=True,
        help_text=_("URL видео (YouTube, Vimeo или прямой ссылка на видеофайл)")
    )
    video_file = models.FileField(
        _("Видеофайл"),
        upload_to='banners/videos/',
        blank=True,
        null=True,
        help_text=_("Локальный видеофайл (MP4, WebM)")
    )
    
    # Поля для GIF
    gif_url = models.URLField(
        _("URL GIF"),
        blank=True,
        help_text=_("Внешний URL GIF анимации")
    )
    gif_file = models.FileField(
        _("GIF файл"),
        upload_to='banners/gifs/',
        blank=True,
        null=True,
        help_text=_("Локальный GIF файл")
    )
    
    # Порядок отображения в карусели
    sort_order = models.PositiveIntegerField(
        _("Порядок сортировки"),
        default=0,
        help_text=_("Чем меньше число, тем раньше отображается в карусели")
    )
    
    # Метаданные
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    
    class Meta:
        verbose_name = _("Медиа баннера")
        verbose_name_plural = _("Медиа баннеров")
        ordering = ['banner', 'sort_order', '-created_at']
        indexes = [
            models.Index(fields=['banner', 'sort_order']),
        ]
    
    def __str__(self):
        content_type_display = dict(self.CONTENT_TYPE_CHOICES).get(self.content_type, self.content_type)
        return f"{self.banner} - {content_type_display} (#{self.sort_order})"
    
    def get_content_url(self):
        """Получить URL контента в зависимости от типа."""
        if self.content_type == 'image':
            if self.image:
                return self.image.url
            return self.image_url or ''
        elif self.content_type == 'video':
            if self.video_file:
                return self.video_file.url
            return self.video_url or ''
        elif self.content_type == 'gif':
            if self.gif_file:
                return self.gif_file.url
            return self.gif_url or ''
        return ''
    
    def get_content_type_for_html(self):
        """Определить MIME-тип для HTML-тега."""
        if self.content_type == 'image':
            if self.image:
                ext = self.image.name.split('.')[-1].lower()
                return f'image/{ext if ext in ["jpg", "jpeg", "png", "webp"] else "jpeg"}'
            return 'image/jpeg'
        elif self.content_type == 'video':
            if self.video_file:
                ext = self.video_file.name.split('.')[-1].lower()
                return f'video/{ext if ext in ["mp4", "webm", "ogg"] else "mp4"}'
            return 'video/mp4'
        elif self.content_type == 'gif':
            return 'image/gif'
        return ''
