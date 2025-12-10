"""Модели для каталога товаров."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

CURRENCY_CHOICES = [
    ("RUB", "RUB"),
    ("USD", "USD"),
    ("EUR", "EUR"),
    ("TRY", "TRY"),
    ("GBP", "GBP"),
    ("USDT", "USDT"),
]

CARD_MEDIA_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm"]
CARD_MEDIA_MAX_SIZE_MB = 50

TOP_CATEGORY_SLUG_CHOICES = [
    ("medicines", "medicines"),
    ("supplements", "supplements"),
    ("medical-equipment", "medical-equipment"),
    ("clothing", "clothing"),
    ("shoes", "shoes"),
    ("electronics", "electronics"),
    ("furniture", "furniture"),
    ("tableware", "tableware"),
    ("accessories", "accessories"),
    ("jewelry", "jewelry"),
    ("underwear", "underwear"),
    ("headwear", "headwear"),
]


def validate_card_media_file_size(value):
    """Проверяет, что размер медиа-файла карточки не превышает допустимый лимит."""
    max_bytes = CARD_MEDIA_MAX_SIZE_MB * 1024 * 1024
    if value.size > max_bytes:
        raise ValidationError(
            _("Размер файла превышает %(size)s МБ"),
            params={"size": CARD_MEDIA_MAX_SIZE_MB},
        )


class Category(models.Model):
    """Категория товаров."""
    
    CATEGORY_TYPE_CHOICES = [
        ("medicines", _("Медицина")),
        ("supplements", _("БАДы")),
        ("medical_equipment", _("Медтехника")),
        ("clothing", _("Одежда")),
        ("underwear", _("Нижнее бельё")),
        ("headwear", _("Головные уборы")),
        ("shoes", _("Обувь")),
        ("electronics", _("Электроника")),
        ("furniture", _("Мебель")),
        ("tableware", _("Посуда")),
        ("accessories", _("Аксессуары")),
        ("jewelry", _("Украшения")),
    ]
    
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    category_type = models.CharField(
        _("Тип категории"),
        max_length=32,
        choices=CATEGORY_TYPE_CHOICES,
        default="medicines",
        db_index=True,
        help_text=_("Определяет домен: медицина, БАДы, медтехника, посуда, мебель, аксессуары, украшения и т.д.")
    )
    card_media = models.FileField(
        _("Медиа для карточки"),
        upload_to="marketing/cards/categories/",
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=CARD_MEDIA_ALLOWED_EXTENSIONS),
            validate_card_media_file_size,
        ],
        help_text=_("Изображение, GIF или видео для карточки категории (до 50 МБ)."),
    )
    card_media_external_url = models.URLField(
        _("Внешний URL медиа"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Ссылка на медиа (например, CDN или AWS S3). Если заполнено, приоритетнее файла."),
    )
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
        verbose_name = _("Категория (медицина/БАДы/медтехника/аксессуары)")
        verbose_name_plural = _("Категории (медицина/БАДы/медтехника/аксессуары)")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def get_card_media_url(self) -> str:
        """Возвращает URL медиа-файла карточки (или пустую строку)."""
        if self.card_media_external_url:
            return self.card_media_external_url
        if self.card_media:
            try:
                return self.card_media.url
            except ValueError:
                return self.card_media.name or ""
        return ""


class CategoryMedicines(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Медицина")
        verbose_name_plural = _("Категории — Медицина")


class CategorySupplements(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — БАДы")
        verbose_name_plural = _("Категории — БАДы")


class CategoryMedicalEquipment(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Медтехника")
        verbose_name_plural = _("Категории — Медтехника")


class CategoryTableware(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Посуда")
        verbose_name_plural = _("Категории — Посуда")


class CategoryFurniture(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Мебель")
        verbose_name_plural = _("Категории — Мебель")


class CategoryAccessories(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Аксессуары")
        verbose_name_plural = _("Категории — Аксессуары")


class CategoryJewelry(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Украшения")
        verbose_name_plural = _("Категории — Украшения")


class CategoryUnderwear(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Нижнее бельё")
        verbose_name_plural = _("Категории — Нижнее бельё")


class CategoryHeadwear(Category):
    class Meta:
        proxy = True
        verbose_name = _("Категория — Головные уборы")
        verbose_name_plural = _("Категории — Головные уборы")


class MarketingCategory(Category):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Категория товара")
        verbose_name_plural = _("Маркетинг — Категории товаров")


class MarketingRootCategory(Category):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Корневая категория")
        verbose_name_plural = _("Маркетинг — Корневые категории")


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
    primary_category_slug = models.CharField(
        _("Основная категория (slug)"),
        max_length=64,
        blank=True,
        choices=TOP_CATEGORY_SLUG_CHOICES,
        help_text=_("Явно укажите ключевой slug для бренда (clothing, shoes, electronics и т.д.)."),
    )
    card_media = models.FileField(
        _("Медиа для карточки"),
        upload_to="marketing/cards/brands/",
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=CARD_MEDIA_ALLOWED_EXTENSIONS),
            validate_card_media_file_size,
        ],
        help_text=_("Изображение, GIF или видео для карточки бренда (до 50 МБ)."),
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Бренд")
        verbose_name_plural = _("Бренды")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_card_media_url(self) -> str:
        """Возвращает URL медиа-файла карточки (или пустую строку)."""
        if self.card_media:
            try:
                return self.card_media.url
            except ValueError:
                return self.card_media.name or ""
        return ""


class MarketingBrand(Brand):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Популярный бренд")
        verbose_name_plural = _("Маркетинг — Популярные бренды")


class Product(models.Model):
    """Товар в каталоге."""

    PRODUCT_TYPE_CHOICES = [
        ("medicines", _("Медицина")),
        ("supplements", _("БАДы")),
        ("medical_equipment", _("Медтехника")),
        ("clothing", _("Одежда")),
        ("underwear", _("Нижнее бельё")),
        ("headwear", _("Головные уборы")),
        ("shoes", _("Обувь")),
        ("electronics", _("Электроника")),
        ("furniture", _("Мебель")),
        ("tableware", _("Посуда")),
        ("accessories", _("Аксессуары")),
        ("jewelry", _("Украшения")),
    ]

    AVAILABILITY_STATUS_CHOICES = [
        ("in_stock", _("В наличии")),
        ("backorder", _("Под заказ")),
        ("preorder", _("Предзаказ")),
        ("out_of_stock", _("Нет в наличии")),
        ("discontinued", _("Снят с производства")),
    ]
    
    # Основная информация
    name = models.CharField(_("Название"), max_length=500)
    slug = models.SlugField(_("Slug"), max_length=500, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    name_en = models.CharField(_("Название (англ.)"), max_length=500, blank=True)
    description_en = models.TextField(_("Описание (англ.)"), blank=True)
    product_type = models.CharField(
        _("Тип товара"),
        max_length=32,
        choices=PRODUCT_TYPE_CHOICES,
        default="medicines",
        db_index=True,
    )
    
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
    currency = models.CharField(
        _("Валюта"),
        max_length=5,
        choices=CURRENCY_CHOICES,
        default="RUB",
        help_text=_("Выбирается из списка расчётных валют, используемых в прайсах.")
    )
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
    availability_status = models.CharField(
        _("Статус доступности"),
        max_length=32,
        choices=AVAILABILITY_STATUS_CHOICES,
        default="in_stock",
        db_index=True,
    )
    min_order_quantity = models.PositiveIntegerField(
        _("Минимальное количество заказа"), default=1
    )
    pack_quantity = models.PositiveIntegerField(
        _("Количество в упаковке"), null=True, blank=True
    )
    country_of_origin = models.CharField(
        _("Страна происхождения"), max_length=100, blank=True, db_index=True
    )
    gtin = models.CharField(_("GTIN"), max_length=64, blank=True)
    mpn = models.CharField(_("MPN"), max_length=64, blank=True)
    weight_value = models.DecimalField(
        _("Вес"), max_digits=8, decimal_places=3, null=True, blank=True
    )
    weight_unit = models.CharField(_("Единица веса"), max_length=10, default="g")
    length = models.DecimalField(
        _("Длина"), max_digits=8, decimal_places=3, null=True, blank=True
    )
    width = models.DecimalField(
        _("Ширина"), max_digits=8, decimal_places=3, null=True, blank=True
    )
    height = models.DecimalField(
        _("Высота"), max_digits=8, decimal_places=3, null=True, blank=True
    )
    dimensions_unit = models.CharField(
        _("Единица размера"), max_length=10, default="cm"
    )
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(
        _("Главное изображение"),
        blank=True,
        help_text=_("URL основного изображения (ссылка на CDN или внутреннее хранилище).")
    )
    
    # Внешние данные
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    meta_title = models.CharField(
        _("Meta Title"),
        max_length=255,
        blank=True,
        help_text=_("Англоязычный SEO title, используется на всех фронтенд-страницах.")
    )
    meta_description = models.CharField(
        _("Meta Description"),
        max_length=500,
        blank=True,
        help_text=_("Англоязычный SEO description для карточки товара.")
    )
    meta_keywords = models.CharField(
        _("Meta Keywords"),
        max_length=500,
        blank=True,
        help_text=_("Ключевые слова для индексации (англ.).")
    )
    og_title = models.CharField(
        _("OG Title"),
        max_length=255,
        blank=True,
        help_text=_("OpenGraph title (англ.), если отличается от meta title.")
    )
    og_description = models.CharField(
        _("OG Description"),
        max_length=500,
        blank=True,
        help_text=_("OpenGraph description (англ.) для социальных сетей.")
    )
    og_image_url = models.URLField(
        _("OG Image URL"),
        blank=True,
        help_text=_("Ссылка на изображение для OpenGraph, если оно отличается от основного.")
    )
    
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
        verbose_name = _("Товар (медицина/БАДы/медтехника/аксессуары)")
        verbose_name_plural = _("Товары (медицина/БАДы/медтехника/аксессуары)")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
            models.Index(fields=["product_type"]),
            models.Index(fields=["availability_status"]),
            models.Index(fields=["country_of_origin"]),
        ]

    def __str__(self):
        return self.name


class ProductMedicines(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Медицина")
        verbose_name_plural = _("Товары — Медицина")


class ProductSupplements(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — БАДы")
        verbose_name_plural = _("Товары — БАДы")


class ProductMedicalEquipment(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Медтехника")
        verbose_name_plural = _("Товары — Медтехника")


class ProductTableware(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Посуда")
        verbose_name_plural = _("Товары — Посуда")


class ProductFurniture(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Мебель")
        verbose_name_plural = _("Товары — Мебель")


class ProductAccessories(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Аксессуары")
        verbose_name_plural = _("Товары — Аксессуары")


class ProductJewelry(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Украшения")
        verbose_name_plural = _("Товары — Украшения")


class ProductUnderwear(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Нижнее бельё")
        verbose_name_plural = _("Товары — Нижнее бельё")


class ProductHeadwear(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Головные уборы")
        verbose_name_plural = _("Товары — Головные уборы")


class ProductImage(models.Model):
    """Изображение товара."""
    
    product = models.ForeignKey(
        Product, 
        on_delete=models.CASCADE, 
        related_name="images",
        verbose_name=_("Товар")
    )
    image_url = models.URLField(
        _("URL изображения"),
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
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


class ClothingVariant(models.Model):
    """Вариант одежды (цвет, цены, остаток, галерея). Размеры хранятся отдельно."""

    product = models.ForeignKey(
        "ClothingProduct",
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Товар одежды (родитель)")
    )
    name = models.CharField(_("Название варианта"), max_length=500, blank=True)
    slug = models.SlugField(_("Slug варианта"), max_length=600, unique=True, help_text=_("Автогенерация по названию/цвету/размеру, можно переопределить."))
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    # size поле оставлено для обратной совместимости, но не используется как источник доступных размеров
    size = models.CharField(
        _("Размер (устарело)"),
        max_length=50,
        blank=True,
        help_text=_("Используйте таблицу размеров ниже; поле оставлено для совместимости.")
    )
    sku = models.CharField(_("SKU"), max_length=100, blank=True)
    barcode = models.CharField(_("Штрихкод"), max_length=100, blank=True)
    gtin = models.CharField(_("GTIN"), max_length=100, blank=True)
    mpn = models.CharField(_("MPN"), max_length=100, blank=True)
    price = models.DecimalField(_("Цена"), max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    currency = models.CharField(_("Валюта"), max_length=5, choices=CURRENCY_CHOICES, default="RUB")
    old_price = models.DecimalField(_("Старая цена"), max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    main_image = models.URLField(_("Главное изображение варианта"), blank=True)
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Вариант одежды")
        verbose_name_plural = _("Варианты одежды")
        ordering = ["product", "sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        base = self.name or self.product.name
        attrs = f"{self.color or ''} {self.size or ''}".strip()
        return f"{base} ({attrs})" if attrs else base

    def save(self, *args, **kwargs):
        """Автогенерация slug, если не заполнен."""
        if not self.slug:
            base_name = self.name or self.product.name
            composed = f"{base_name}-{self.color or ''}-{self.size or ''}".strip()
            self.slug = slugify(composed)[:580] or slugify(base_name)[:580]
        super().save(*args, **kwargs)


class ClothingVariantSize(models.Model):
    """Размер внутри цветового варианта одежды."""

    variant = models.ForeignKey(
        ClothingVariant,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name=_("Вариант одежды")
    )
    size = models.CharField(
        _("Размер"),
        max_length=50,
        blank=True,
        help_text=_("Например S, M, L или 48, 50.")
    )
    is_available = models.BooleanField(_("Доступен"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Остаток"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Размер варианта одежды")
        verbose_name_plural = _("Размеры варианта одежды")
        ordering = ["variant", "sort_order", "size"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
            models.Index(fields=["variant", "size"]),
        ]

    def __str__(self):
        return f"{self.variant} — {self.size}"


class ClothingVariantImage(models.Model):
    """Изображение варианта одежды."""

    variant = models.ForeignKey(
        ClothingVariant,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Вариант одежды")
    )
    image_url = models.URLField(_("URL изображения"), help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте."))
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение варианта одежды")
        verbose_name_plural = _("Изображения вариантов одежды")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение варианта {self.variant}"


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
    currency = models.CharField(
        _("Валюта"),
        max_length=5,
        choices=CURRENCY_CHOICES,
        default="RUB",
        help_text=_("Выбирается из списка расчётных валют, используемых в прайсах.")
    )
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
    currency = models.CharField(
        _("Валюта"),
        max_length=5,
        choices=CURRENCY_CHOICES,
        default="RUB",
        help_text=_("Выбирается из списка расчётных валют, используемых в прайсах.")
    )
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


class ClothingProductImage(models.Model):
    """Изображение товара одежды."""

    product = models.ForeignKey(
        ClothingProduct,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Товар одежды")
    )
    image_url = models.URLField(
        _("URL изображения"),
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение товара одежды")
        verbose_name_plural = _("Изображения товаров одежды")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение {self.product.name}"


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

    SHOE_SIZE_CHOICES = [
        ("35", "35"),
        ("36", "36"),
        ("37", "37"),
        ("38", "38"),
        ("39", "39"),
        ("40", "40"),
        ("41", "41"),
        ("42", "42"),
        ("43", "43"),
        ("44", "44"),
        ("45", "45"),
        ("46", "46"),
        ("47", "47"),
        ("48", "48"),
    ]
    
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
        verbose_name=_("Категория"),
        help_text=_("Выберите категорию из дерева обуви; при необходимости создайте новую в ShoeCategory.")
    )
    brand = models.ForeignKey(
        Brand, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="shoe_products",
        verbose_name=_("Бренд"),
        help_text=_("Если нет бренда в списке — создайте его в разделе брендов.")
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
    currency = models.CharField(
        _("Валюта"),
        max_length=5,
        choices=CURRENCY_CHOICES,
        default="RUB",
        help_text=_("Выбирается из списка расчётных валют, используемых в прайсах.")
    )
    old_price = models.DecimalField(
        _("Старая цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Специфичные для обуви поля
    size = models.CharField(
        _("Размер"),
        max_length=20,
        blank=True,
        choices=SHOE_SIZE_CHOICES,
        help_text=_("Выберите размер в EU-формате; при необходимости можно оставить пустым.")
    )
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    material = models.CharField(_("Материал"), max_length=100, blank=True)
    heel_height = models.CharField(_("Высота каблука"), max_length=50, blank=True)
    sole_type = models.CharField(_("Тип подошвы"), max_length=100, blank=True)
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(
        _("Главное изображение"),
        blank=True,
        help_text=_("URL главного фото; дополнительные фото задаются в галерее ниже.")
    )
    
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


class ShoeProductImage(models.Model):
    """Изображение товара обуви."""

    product = models.ForeignKey(
        ShoeProduct,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Товар обуви")
    )
    image_url = models.URLField(
        _("URL изображения"),
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение товара обуви")
        verbose_name_plural = _("Изображения товаров обуви")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение {self.product.name}"


class ShoeVariant(models.Model):
    """Вариант обуви (цвет, цены, остаток, галерея). Размеры хранятся отдельно."""

    product = models.ForeignKey(
        ShoeProduct,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Товар (родитель)")
    )
    name = models.CharField(_("Название варианта"), max_length=500, blank=True)
    slug = models.SlugField(_("Slug варианта"), max_length=600, unique=True, help_text=_("Автогенерация по названию/цвету/размеру, можно переопределить."))
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    # size поле оставлено для обратной совместимости, но не используется как источник доступных размеров
    size = models.CharField(
        _("Размер (устарело)"),
        max_length=20,
        blank=True,
        help_text=_("Используйте таблицу размеров ниже; поле оставлено для совместимости.")
    )
    sku = models.CharField(_("SKU"), max_length=100, blank=True)
    barcode = models.CharField(_("Штрихкод"), max_length=100, blank=True)
    gtin = models.CharField(_("GTIN"), max_length=100, blank=True)
    mpn = models.CharField(_("MPN"), max_length=100, blank=True)
    price = models.DecimalField(_("Цена"), max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    currency = models.CharField(_("Валюта"), max_length=5, choices=CURRENCY_CHOICES, default="RUB")
    old_price = models.DecimalField(_("Старая цена"), max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    main_image = models.URLField(_("Главное изображение варианта"), blank=True)
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Вариант обуви")
        verbose_name_plural = _("Варианты обуви")
        ordering = ["product", "sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        base = self.name or self.product.name
        attrs = f"{self.color or ''} {self.size or ''}".strip()
        return f"{base} ({attrs})" if attrs else base

    def save(self, *args, **kwargs):
        """Автогенерация slug, если не заполнен."""
        if not self.slug:
            base_name = self.name or self.product.name
            composed = f"{base_name}-{self.color or ''}-{self.size or ''}".strip()
            self.slug = slugify(composed)[:580] or slugify(base_name)[:580]
        super().save(*args, **kwargs)


class ShoeVariantSize(models.Model):
    """Размер внутри цветового варианта обуви."""

    variant = models.ForeignKey(
        ShoeVariant,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name=_("Вариант обуви")
    )
    size = models.CharField(
        _("Размер"),
        max_length=20,
        blank=True,
        help_text=_("EU размер, например 40, 41, 42.")
    )
    is_available = models.BooleanField(_("Доступен"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Остаток"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Размер варианта обуви")
        verbose_name_plural = _("Размеры варианта обуви")
        ordering = ["variant", "sort_order", "size"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
            models.Index(fields=["variant", "size"]),
        ]

    def __str__(self):
        return f"{self.variant} — {self.size}"


class ShoeVariantImage(models.Model):
    """Изображение варианта обуви."""

    variant = models.ForeignKey(
        ShoeVariant,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Вариант обуви")
    )
    image_url = models.URLField(_("URL изображения"), help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте."))
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение варианта обуви")
        verbose_name_plural = _("Изображения вариантов обуви")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение варианта {self.variant}"


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
    currency = models.CharField(
        _("Валюта"),
        max_length=5,
        choices=CURRENCY_CHOICES,
        default="RUB",
        help_text=_("Выбирается из списка расчётных валют, используемых в прайсах.")
    )
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


class ElectronicsProductImage(models.Model):
    """Изображение товара электроники."""

    product = models.ForeignKey(
        ElectronicsProduct,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Товар электроники")
    )
    image_url = models.URLField(
        _("URL изображения"),
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение товара электроники")
        verbose_name_plural = _("Изображения товаров электроники")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение {self.product.name}"


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
        verbose_name='Заголовок баннера',
        blank=True,
        help_text=_("Заголовок баннера (используется как fallback для медиа-файлов, если у них не указан свой заголовок)")
    )
    description = models.TextField(
        _("Описание баннера"),
        blank=True,
        help_text=_("Описание баннера (используется как fallback для медиа-файлов, если у них не указано свое описание)")
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


class MarketingBanner(Banner):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Баннер")
        verbose_name_plural = _("Маркетинг — Баннеры")


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
    title = models.CharField(
        _("Заголовок"),
        max_length=200,
        blank=True,
        help_text=_("Заголовок для этого медиа-элемента (H2). Если пусто, используется заголовок баннера.")
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Описание для этого медиа-элемента (H3). Если пусто, используется описание баннера.")
    )
    link_text = models.CharField(
        _("Текст кнопки"),
        max_length=100,
        blank=True,
        help_text=_("Текст для кнопки ссылки. Если пусто, используется текст ссылки баннера.")
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


class MarketingBannerMedia(BannerMedia):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Медиа баннеров")
        verbose_name_plural = _("Маркетинг — Медиа баннеров")
