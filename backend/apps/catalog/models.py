"""Модели для каталога товаров."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator


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
