"""Модели для каталога товаров."""

import uuid
from urllib.parse import urlparse, urlunparse
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from .currency_models import CurrencyRate, MarginSettings, ProductPrice, CurrencyUpdateLog
from .utils.storage_paths import (
    detect_media_type,
    get_category_card_upload_path,
    get_brand_card_upload_path,
    get_product_image_upload_path,
    get_product_upload_path,
    get_banner_image_upload_path,
    get_banner_video_upload_path,
    get_banner_gif_upload_path,
)

CURRENCY_CHOICES = [
    ("RUB", "RUB"),
    ("USD", "USD"),
    ("EUR", "EUR"),
    ("TRY", "TRY"),
    ("KZT", "KZT"),
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
    ("books", "books"),
]


def _card_media_folder_from_filename(filename: str) -> str:
    media_type = detect_media_type(filename)
    return {"image": "images", "video": "videos", "gif": "gifs"}.get(media_type, "images")


def _normalize_card_media_path(path: str, category_base: str | None = None) -> str:
    if not path:
        return path

    raw_path = path if path.startswith("/") else f"/{path}"
    parts = raw_path.lstrip("/").split("/")
    if len(parts) < 4:
        return path

    if parts[:3] == ["marketing", "cards", "brands"]:
        if len(parts) >= 5 and parts[3] in {"images", "videos", "gifs"}:
            return path
        filename = "/".join(parts[3:])
        if not filename:
            return path
        folder = _card_media_folder_from_filename(filename)
        new_parts = parts[:3] + [folder] + parts[3:]
        return "/" + "/".join(new_parts)

    if parts[:3] == ["marketing", "cards", "categories"]:
        if len(parts) >= 6 and parts[4] in {"images", "videos", "gifs"}:
            return path
        if len(parts) >= 5 and parts[3] in {"images", "videos", "gifs"}:
            base = category_base or "other"
            filename = "/".join(parts[4:])
            if not filename:
                return path
            new_parts = parts[:3] + [base, parts[3]] + parts[4:]
            return "/" + "/".join(new_parts)

        if "." in parts[3]:
            base = category_base or "other"
            filename = "/".join(parts[3:])
        else:
            base = parts[3]
            filename = "/".join(parts[4:])
        if not filename:
            return path
        folder = _card_media_folder_from_filename(filename)
        new_parts = parts[:3] + [base, folder] + filename.split("/")
        return "/" + "/".join(new_parts)

    return path


def _normalize_card_media_url(url: str, category_base: str | None = None) -> str:
    if not url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        parsed = urlparse(url)
        new_path = _normalize_card_media_path(parsed.path, category_base=category_base)
        if new_path == parsed.path:
            return url
        return urlunparse(parsed._replace(path=new_path))
    return _normalize_card_media_path(url, category_base=category_base)


def _resolve_category_card_base(category) -> str:
    category_slug = (getattr(category, "slug", "") or "").lower()
    category_type = getattr(category, "category_type", None)
    type_slug = (getattr(category_type, "slug", "") or "").lower()

    if "medic" in type_slug or "medic" in category_slug or type_slug == "medicines":
        return "medicines"
    if "supplement" in type_slug or "supplement" in category_slug or "bad" in category_slug:
        return "supplements"
    if "equipment" in type_slug or "equipment" in category_slug or "medical-equipment" in type_slug:
        return "medical-equipment"
    if type_slug == "clothing" or "clothing" in category_slug:
        return "clothing"
    if type_slug == "shoes" or "shoes" in category_slug:
        return "shoes"
    if type_slug == "jewelry" or "jewelry" in category_slug:
        return "jewelry"
    if type_slug == "electronics" or "electronics" in category_slug:
        return "electronics"
    if type_slug == "furniture" or "furniture" in category_slug:
        return "furniture"
    return "other"


def validate_card_media_file_size(value):
    """Проверяет, что размер медиа-файла карточки не превышает допустимый лимит."""
    max_bytes = CARD_MEDIA_MAX_SIZE_MB * 1024 * 1024
    if value.size > max_bytes:
        raise ValidationError(
            _("Размер файла превышает %(size)s МБ"),
            params={"size": CARD_MEDIA_MAX_SIZE_MB},
        )


class CategoryType(models.Model):
    """Тип категории товаров (можно добавлять через админку)."""
    
    name = models.CharField(_("Название"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Тип категории")
        verbose_name_plural = _("Типы категорий")
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Category(models.Model):
    """Единая модель категорий товаров (медицина, БАДы, одежда, обувь, электроника и т.д.)."""
    
    GENDER_CHOICES = [
        ('men', _('Мужская')),
        ('women', _('Женская')),
        ('unisex', _('Унисекс')),
        ('kids', _('Детская')),
    ]
    
    # Основные поля
    name = models.CharField(_("Название"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    
    # Тип категории (для медицины, БАДов, медтехники и т.д.)
    category_type = models.ForeignKey(
        CategoryType,
        on_delete=models.PROTECT,
        related_name="categories",
        verbose_name=_("Тип категории"),
        db_index=True,
        null=True,
        blank=True,
        help_text=_("Выберите тип категории для медицины/БАДов/медтехники. Для одежды/обуви/электроники не обязательно.")
    )
    
    # Медиа для карточки
    card_media = models.FileField(
        _("Медиа для карточки"),
        upload_to=get_category_card_upload_path,
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
    
    # Иерархия
    parent = models.ForeignKey(
        "self", 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="children",
        verbose_name=_("Родительская категория")
    )
    
    # Специфичные поля для одежды и обуви
    gender = models.CharField(
        _("Пол"), 
        max_length=10, 
        choices=GENDER_CHOICES, 
        blank=True,
        null=True,
        help_text=_("Для категорий одежды и обуви: мужская, женская, унисекс, детская")
    )
    clothing_type = models.CharField(
        _("Тип одежды"), 
        max_length=100, 
        blank=True,
        help_text=_("Для категорий одежды: платья, блузки, джинсы и т.д.")
    )
    shoe_type = models.CharField(
        _("Тип обуви"), 
        max_length=100, 
        blank=True,
        help_text=_("Для категорий обуви: туфли, кроссовки, сапоги и т.д.")
    )
    device_type = models.CharField(
        _("Тип устройства"), 
        max_length=100, 
        blank=True,
        help_text=_("Для категорий электроники: телефоны, ноутбуки, планшеты и т.д.")
    )
    
    # Общие поля
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
        unique_together = [['name', 'parent']]
        indexes = [
            models.Index(fields=['name', 'parent']),
        ]

    def __str__(self):
        return self.name

    def get_translated_name(self, locale: str = 'ru') -> str:
        """Получает переведенное название категории."""
        translation = self.translations.filter(locale=locale).first()
        if translation:
            return translation.name
        return self.name

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание категории."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''

    def get_card_media_url(self) -> str:
        """Возвращает URL медиа-файла карточки (или пустую строку)."""
        if self.card_media_external_url:
            return _normalize_card_media_url(
                self.card_media_external_url,
                category_base=_resolve_category_card_base(self),
            )
        if self.card_media:
            try:
                return _normalize_card_media_url(
                    self.card_media.url,
                    category_base=_resolve_category_card_base(self),
                )
            except ValueError:
                return _normalize_card_media_url(
                    self.card_media.name or "",
                    category_base=_resolve_category_card_base(self),
                )
        return ""


class CategoryTranslation(models.Model):
    """Переводы для категорий товаров."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Категория")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    name = models.CharField(
        _("Название"),
        max_length=200,
        help_text=_("Переведенное название категории")
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание категории")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод категории")
        verbose_name_plural = _("Переводы категорий")
        unique_together = [['category', 'locale']]
        ordering = ['category', 'locale']
        indexes = [
            models.Index(fields=['category', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.category.name} ({self.get_locale_display()})"


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


class CategoryBooks(Category):
    """Прокси-модель для категорий книг (жанров)."""
    class Meta:
        proxy = True
        verbose_name = _("Категория — Книги")
        verbose_name_plural = _("Категории — Книги (Жанры)")


class CategoryServices(Category):
    """Прокси-модель для категорий услуг."""
    class Meta:
        proxy = True
        verbose_name = _("Категория — Услуги")
        verbose_name_plural = _("Категории — Услуги")


class MarketingCategory(Category):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Подкатегория товара")
        verbose_name_plural = _("Маркетинг — Подкатегории товаров")


class MarketingRootCategory(Category):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Корневая категория")
        verbose_name_plural = _("Маркетинг — Корневые категории")


class CategoryClothing(Category):
    """Прокси-модель для категорий одежды."""
    class Meta:
        proxy = True
        verbose_name = _("Категория — Одежда")
        verbose_name_plural = _("Категории — Одежда")


class CategoryShoes(Category):
    """Прокси-модель для категорий обуви."""
    class Meta:
        proxy = True
        verbose_name = _("Категория — Обувь")
        verbose_name_plural = _("Категории — Обувь")


class CategoryElectronics(Category):
    """Прокси-модель для категорий электроники."""
    class Meta:
        proxy = True
        verbose_name = _("Категория — Электроника")
        verbose_name_plural = _("Категории — Электроника")


class BrandTranslation(models.Model):
    """Переводы для брендов."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    brand = models.ForeignKey(
        'Brand',
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Бренд")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    name = models.CharField(
        _("Название"),
        max_length=200,
        help_text=_("Переведенное название бренда")
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание бренда")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод бренда")
        verbose_name_plural = _("Переводы брендов")
        unique_together = [['brand', 'locale']]
        ordering = ['brand', 'locale']
        indexes = [
            models.Index(fields=['brand', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.brand.name} ({self.get_locale_display()})"


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
        upload_to=get_brand_card_upload_path,
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=CARD_MEDIA_ALLOWED_EXTENSIONS),
            validate_card_media_file_size,
        ],
        help_text=_("Изображение, GIF или видео для карточки бренда (до 50 МБ)."),
    )
    card_media_external_url = models.URLField(
        _("Внешний URL медиа"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Ссылка на медиа (например, CDN или AWS S3). Если заполнено, приоритетнее файла."),
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
        if self.card_media_external_url:
            return _normalize_card_media_url(self.card_media_external_url)
        if self.card_media:
            try:
                return _normalize_card_media_url(self.card_media.url)
            except ValueError:
                return _normalize_card_media_url(self.card_media.name or "")
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
        ("books", _("Книги")),
        # Добавьте здесь новые типы товаров по необходимости (должны совпадать с CATEGORY_TYPE_CHOICES)
        # Пример: ("cosmetics", _("Косметика")),
        # Пример: ("toys", _("Игрушки")),
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
    
    # SEO
    seo_title = models.CharField(_("SEO заголовок"), max_length=70, blank=True, null=True)
    seo_description = models.CharField(_("SEO описание"), max_length=160, blank=True, null=True)
    keywords = models.JSONField(_("Ключевые слова"), default=list, blank=True)

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
        max_length=2000,
        blank=True,
        help_text=_("URL основного изображения (ссылка на CDN или внутреннее хранилище).")
    )
    main_image_file = models.ImageField(
        _("Главное изображение (файл)"),
        upload_to=get_product_upload_path,
        blank=True,
        null=True,
    )
    video_url = models.URLField(
        _("URL видео"),
        max_length=2000,
        blank=True,
        help_text=_("URL видео для товара (например, из Instagram постов).")
    )
    main_video_file = models.FileField(
        _("Главное видео (файл)"),
        upload_to=get_product_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["mp4", "mov", "webm", "avi", "mkv"]),
        ],
        help_text=_("Видео-файл товара (загружается в R2/локальное хранилище).")
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
    
    # Специфичные поля для книг
    isbn = models.CharField(_("ISBN"), max_length=20, blank=True, help_text=_("ISBN книги"))
    publisher = models.CharField(_("Издательство"), max_length=200, blank=True)
    publication_date = models.DateField(_("Дата публикации"), null=True, blank=True)
    pages = models.PositiveIntegerField(_("Количество страниц"), null=True, blank=True)
    language = models.CharField(_("Язык"), max_length=50, blank=True, default="Русский")
    cover_type = models.CharField(_("Тип обложки"), max_length=50, blank=True, help_text=_("Твердая, мягкая и т.д."))
    rating = models.DecimalField(_("Рейтинг"), max_digits=3, decimal_places=2, default=0.00, help_text=_("Рейтинг книги от 0 до 5"))
    reviews_count = models.PositiveIntegerField(_("Количество отзывов"), default=0)
    is_bestseller = models.BooleanField(_("Бестселлер"), default=False)
    is_new = models.BooleanField(_("Новинка"), default=False)
    
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

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание товара."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''
    
    # Методы для работы с системой ценообразования
    def update_currency_prices(self, target_currencies=None):
        """Обновляет цены товара в разных валютах"""
        if target_currencies is None:
            target_currencies = ['RUB', 'USD', 'KZT', 'EUR', 'TRY']
        
        try:
            from apps.catalog.utils.currency_converter import currency_converter
        except ImportError:
            # Если конвертер недоступен, пропускаем обновление
            return
        
        if not self.price or not self.currency:
            return
        
        try:
            # Конвертируем в целевые валюты
            results = currency_converter.convert_to_multiple_currencies(
                self.price, self.currency, target_currencies, apply_margin=True
            )
            
            # Обновляем поля в модели
            if 'RUB' in results and results['RUB']:
                self.converted_price_rub = results['RUB']['converted_price']
                self.final_price_rub = results['RUB']['price_with_margin']
            
            if 'USD' in results and results['USD']:
                self.converted_price_usd = results['USD']['converted_price']
                self.final_price_usd = results['USD']['price_with_margin']
            
            # Создаем или обновляем запись в ProductPrice
            from .currency_models import ProductPrice
            
            price_info, created = ProductPrice.objects.get_or_create(
                product=self,
                defaults={
                    'base_currency': self.currency,
                    'base_price': self.price
                }
            )
            
            # Обновляем базовые данные
            price_info.base_currency = self.currency
            price_info.base_price = self.price
            
            # Обновляем цены в разных валютах
            if 'RUB' in results and results['RUB']:
                price_info.rub_price = results['RUB']['converted_price']
                price_info.rub_price_with_margin = results['RUB']['price_with_margin']
            
            if 'USD' in results and results['USD']:
                price_info.usd_price = results['USD']['converted_price']
                price_info.usd_price_with_margin = results['USD']['price_with_margin']
            
            if 'KZT' in results and results['KZT']:
                price_info.kzt_price = results['KZT']['converted_price']
                price_info.kzt_price_with_margin = results['KZT']['price_with_margin']
            
            if 'EUR' in results and results['EUR']:
                price_info.eur_price = results['EUR']['converted_price']
                price_info.eur_price_with_margin = results['EUR']['price_with_margin']
            
            if 'TRY' in results and results['TRY']:
                price_info.try_price = results['TRY']['converted_price']
                price_info.try_price_with_margin = results['TRY']['price_with_margin']
            
            price_info.save()
            # Не вызываем self.save() чтобы избежать бесконечной рекурсии
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating currency prices for product {self.id}: {str(e)}")
    
    def _get_variant_price_info(self):
        ext = self.external_data or {}
        source_variant_id = ext.get("source_variant_id")
        if not source_variant_id:
            return None
        product_type = (ext.get("effective_type") or ext.get("source_type") or self.product_type or "").lower()
        variant_model_map = {
            "clothing": ClothingVariant,
            "shoes": ShoeVariant,
            "jewelry": JewelryVariant,
            "furniture": FurnitureVariant,
            "books": BookVariant,
        }
        variant_model = variant_model_map.get(product_type)
        if not variant_model:
            return None
        try:
            from django.contrib.contenttypes.models import ContentType
            from .currency_models import ProductVariantPrice

            content_type = ContentType.objects.get_for_model(variant_model)
            return ProductVariantPrice.objects.filter(
                content_type=content_type,
                object_id=source_variant_id
            ).first()
        except Exception:
            return None

    def get_price_in_currency(self, target_currency):
        """Получает цену в указанной валюте"""
        try:
            from .currency_models import ProductPrice

            variant_price = self._get_variant_price_info()
            if variant_price:
                base_currency = (variant_price.base_currency or '').upper()
                target_currency = (target_currency or '').upper()
                if target_currency == base_currency:
                    return variant_price.base_price
                currency_map = {
                    'RUB': variant_price.rub_price_with_margin,
                    'USD': variant_price.usd_price_with_margin,
                    'KZT': variant_price.kzt_price_with_margin,
                    'EUR': variant_price.eur_price_with_margin,
                    'TRY': variant_price.try_price_with_margin,
                }
                price = currency_map.get(target_currency)
                if price is not None:
                    return price
            
            # Пробуем получить из новой структуры
            try:
                price_info = self.price_info
                
                if target_currency == 'RUB' and price_info.rub_price_with_margin:
                    return price_info.rub_price_with_margin
                elif target_currency == 'USD' and price_info.usd_price_with_margin:
                    return price_info.usd_price_with_margin
                elif target_currency == 'KZT' and price_info.kzt_price_with_margin:
                    return price_info.kzt_price_with_margin
                elif target_currency == 'EUR' and price_info.eur_price_with_margin:
                    return price_info.eur_price_with_margin
                elif target_currency == 'TRY' and price_info.try_price_with_margin:
                    return price_info.try_price_with_margin
                elif target_currency == self.currency:
                    return price_info.base_price
                    
            except ProductPrice.DoesNotExist:
                pass
            
            # Если цены нет в базе, пробуем конвертировать на лету
            from .utils.currency_converter import currency_converter
            
            if self.price and self.currency:
                _, _, price_with_margin = currency_converter.convert_price(
                    self.price, self.currency, target_currency, apply_margin=True
                )
                return price_with_margin
            
        except Exception:
            pass
    
        return None
    
    def get_all_prices(self):
        """Получает цены во всех валютах"""
        from .currency_models import ProductPrice
        
        prices = {}
        
        try:
            variant_price = self._get_variant_price_info()
            if variant_price:
                base_currency = (variant_price.base_currency or 'TRY').upper()
                prices[base_currency] = {
                    'original_price': variant_price.base_price,
                    'converted_price': variant_price.base_price,
                    'price_with_margin': variant_price.base_price,
                    'is_base_price': True
                }
                if variant_price.rub_price_with_margin:
                    prices['RUB'] = {
                        'original_price': variant_price.rub_price,
                        'converted_price': variant_price.rub_price,
                        'price_with_margin': variant_price.rub_price_with_margin,
                        'is_base_price': False
                    }
                if variant_price.usd_price_with_margin:
                    prices['USD'] = {
                        'original_price': variant_price.usd_price,
                        'converted_price': variant_price.usd_price,
                        'price_with_margin': variant_price.usd_price_with_margin,
                        'is_base_price': False
                    }
                if variant_price.kzt_price_with_margin:
                    prices['KZT'] = {
                        'original_price': variant_price.kzt_price,
                        'converted_price': variant_price.kzt_price,
                        'price_with_margin': variant_price.kzt_price_with_margin,
                        'is_base_price': False
                    }
                if variant_price.eur_price_with_margin:
                    prices['EUR'] = {
                        'original_price': variant_price.eur_price,
                        'converted_price': variant_price.eur_price,
                        'price_with_margin': variant_price.eur_price_with_margin,
                        'is_base_price': False
                    }
                if variant_price.try_price_with_margin:
                    prices['TRY'] = {
                        'original_price': variant_price.try_price,
                        'converted_price': variant_price.try_price,
                        'price_with_margin': variant_price.try_price_with_margin,
                        'is_base_price': False
                    }
                return prices

            price_info = self.price_info
            
            # Базовая цена
            prices[self.currency] = {
                'original_price': price_info.base_price,
                'converted_price': price_info.base_price,
                'price_with_margin': price_info.base_price,
                'is_base_price': True
            }
            
            # RUB
            if price_info.rub_price_with_margin:
                prices['RUB'] = {
                    'original_price': price_info.rub_price,
                    'converted_price': price_info.rub_price,
                    'price_with_margin': price_info.rub_price_with_margin,
                    'is_base_price': False
                }
            
            # USD
            if price_info.usd_price_with_margin:
                prices['USD'] = {
                    'original_price': price_info.usd_price,
                    'converted_price': price_info.usd_price,
                    'price_with_margin': price_info.usd_price_with_margin,
                    'is_base_price': False
                }
            
            # KZT
            if price_info.kzt_price_with_margin:
                prices['KZT'] = {
                    'original_price': price_info.kzt_price,
                    'converted_price': price_info.kzt_price,
                    'price_with_margin': price_info.kzt_price_with_margin,
                    'is_base_price': False
                }
            
            # EUR
            if price_info.eur_price_with_margin:
                prices['EUR'] = {
                    'original_price': price_info.eur_price,
                    'converted_price': price_info.eur_price,
                    'price_with_margin': price_info.eur_price_with_margin,
                    'is_base_price': False
                }
            
            # TRY
            if price_info.try_price_with_margin:
                prices['TRY'] = {
                    'original_price': price_info.try_price,
                    'converted_price': price_info.try_price,
                    'price_with_margin': price_info.try_price_with_margin,
                    'is_base_price': False
                }
                
        except ProductPrice.DoesNotExist:
            # Если цен нет, возвращаем базовую цену
            if self.price and self.currency:
                prices[self.currency] = {
                    'original_price': self.price,
                    'converted_price': self.price,
                    'price_with_margin': self.price,
                    'is_base_price': True
                }
        
        return prices
    
    def get_current_price(self, preferred_currency='RUB'):
        """Получает текущую цену в предпочитаемой валюте"""
        # Сначала пробуем получить цену в предпочитаемой валюте
        price = self.get_price_in_currency(preferred_currency)
        if price:
            return price, preferred_currency
        
        # Если нет, пробуем базовую валюту товара
        price = self.get_price_in_currency(self.currency)
        if price:
            return price, self.currency
        
        # Если нет ни чего, возвращаем оригинальную цену
        if self.price:
            return self.price, self.currency
        
        return None, None
    
    def get_price_breakdown(self, target_currency):
        """Получает детализацию цены для указанной валюты"""
        from .utils.currency_converter import currency_converter
        
        if not self.price or not self.currency:
            return None
        
        try:
            return currency_converter.get_price_breakdown(
                self.price, self.currency, target_currency
            )
        except Exception:
            return None
    
    def save(self, *args, **kwargs):
        """Переопределенный метод save с автоматическим обновлением цен."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Если у товара есть цена и валюта, обновляем цены в разных валютах
        if self.price and self.currency:
            try:
                self.update_currency_prices()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error updating currency prices for product {self.id}: {str(e)}")


class ProductTranslation(models.Model):
    """Переводы для товаров."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Товар")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание товара")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод товара")
        verbose_name_plural = _("Переводы товаров")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']
        indexes = [
            models.Index(fields=['product', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.product.name} ({self.get_locale_display()})"


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


class ProductBooks(Product):
    class Meta:
        proxy = True
        verbose_name = _("Товар — Книги")
        verbose_name_plural = _("Товары — Книги")


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
        max_length=2000,
        blank=True,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to=get_product_image_upload_path,
        blank=True,
        null=True,
    )
    video_url = models.URLField(
        _("URL видео"),
        max_length=2000,
        blank=True,
        help_text=_("URL видео (Instagram, YouTube и т.д.).")
    )
    video_file = models.FileField(
        _("Видео (файл)"),
        upload_to=get_product_image_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["mp4", "mov", "webm", "avi", "mkv"]),
        ],
        help_text=_("Видео-файл (загружается в R2/локальное хранилище).")
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
    main_image_file = models.ImageField(
        _("Главное изображение варианта (файл)"),
        upload_to="products/variants/",
        blank=True,
        null=True,
    )
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
            base_slug = (slugify(composed)[:580] or slugify(base_name)[:580]).strip('-')
            if not base_slug:
                base_slug = f"v-{uuid.uuid4().hex[:12]}"
            slug = base_slug
            i = 2
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix = f"-{i}"
                slug = f"{base_slug[:580 - len(suffix)]}{suffix}"
                i += 1
            self.slug = slug
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
    image_url = models.URLField(
        _("URL изображения"),
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/variants/gallery/",
        blank=True,
        null=True,
    )
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
# МОДЕЛИ ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

class ClothingProduct(models.Model):
    """Товар одежды."""
    
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
        related_name="clothing_products",
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
    
    # Изображения и видео
    main_image = models.URLField(_("Главное изображение"), blank=True)
    main_image_file = models.ImageField(
        _("Главное изображение (файл)"),
        upload_to="products/clothing/main/",
        blank=True,
        null=True,
    )
    video_url = models.URLField(
        _("URL видео"),
        max_length=2000,
        blank=True,
        help_text=_("URL видео для товара (например, из Instagram). При сохранении скачивается в хранилище."),
    )
    main_video_file = models.FileField(
        _("Главное видео (файл)"),
        upload_to="products/clothing/main/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["mp4", "mov", "webm", "avi", "mkv"]),
        ],
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

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание товара одежды."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''


class ClothingProductSize(models.Model):
    product = models.ForeignKey(
        ClothingProduct,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name=_("Товар одежды")
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
        verbose_name = _("Размер товара одежды")
        verbose_name_plural = _("Размеры товара одежды")
        ordering = ["product", "sort_order", "size"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["product", "size"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.size}"


class ClothingProductTranslation(models.Model):
    """Переводы для товаров одежды."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    product = models.ForeignKey(
        ClothingProduct,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Товар одежды")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание товара одежды")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод товара одежды")
        verbose_name_plural = _("Переводы товаров одежды")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']
        indexes = [
            models.Index(fields=['product', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.product.name} ({self.get_locale_display()})"


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
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/clothing/gallery/",
        blank=True,
        null=True,
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
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="shoe_products",
        verbose_name=_("Категория"),
        help_text=_("Выберите категорию обуви.")
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
    main_image_file = models.ImageField(
        _("Главное изображение (файл)"),
        upload_to="products/shoes/main/",
        blank=True,
        null=True,
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

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание товара обуви."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''


class ShoeProductSize(models.Model):
    product = models.ForeignKey(
        ShoeProduct,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name=_("Товар обуви")
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
        verbose_name = _("Размер товара обуви")
        verbose_name_plural = _("Размеры товара обуви")
        ordering = ["product", "sort_order", "size"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["product", "size"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.size}"


class ShoeProductTranslation(models.Model):
    """Переводы для товаров обуви."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    product = models.ForeignKey(
        ShoeProduct,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Товар обуви")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание товара обуви")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод товара обуви")
        verbose_name_plural = _("Переводы товаров обуви")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']
        indexes = [
            models.Index(fields=['product', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.product.name} ({self.get_locale_display()})"


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
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/shoes/gallery/",
        blank=True,
        null=True,
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
    main_image_file = models.ImageField(
        _("Главное изображение варианта (файл)"),
        upload_to="products/shoes/variants/",
        blank=True,
        null=True,
    )
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
            base_slug = (slugify(composed)[:580] or slugify(base_name)[:580]).strip('-')
            if not base_slug:
                base_slug = f"v-{uuid.uuid4().hex[:12]}"
            slug = base_slug
            i = 2
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix = f"-{i}"
                slug = f"{base_slug[:580 - len(suffix)]}{suffix}"
                i += 1
            self.slug = slug
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
    image_url = models.URLField(
        _("URL изображения"),
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/shoes/variants/gallery/",
        blank=True,
        null=True,
    )
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


class JewelryProduct(models.Model):
    """Товар украшений."""

    JEWELRY_TYPE_CHOICES = [
        ("ring", _("Кольцо")),
        ("bracelet", _("Браслет")),
        ("necklace", _("Цепь/ожерелье")),
        ("earrings", _("Серьги")),
        ("pendant", _("Подвеска")),
    ]

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
        related_name="jewelry_products",
        verbose_name=_("Категория")
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jewelry_products",
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

    # Специфичные поля для украшений
    jewelry_type = models.CharField(
        _("Тип украшения"),
        max_length=32,
        choices=JEWELRY_TYPE_CHOICES,
        blank=True,
        help_text=_("ring, bracelet, necklace, earrings, pendant")
    )
    material = models.CharField(_("Материал"), max_length=100, blank=True)
    metal_purity = models.CharField(_("Проба металла"), max_length=50, blank=True)
    stone_type = models.CharField(_("Тип камня"), max_length=100, blank=True)
    carat_weight = models.DecimalField(
        _("Вес камней, карат"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)

    # Изображения
    main_image = models.URLField(_("Главное изображение"), blank=True)
    main_image_file = models.ImageField(
        _("Главное изображение (файл)"),
        upload_to="products/jewelry/main/",
        blank=True,
        null=True,
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
        verbose_name = _("Товар — Украшения")
        verbose_name_plural = _("Товары — Украшения")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
            models.Index(fields=["jewelry_type"]),
        ]

    def __str__(self):
        return self.name

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание товара украшений."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''


class JewelryProductTranslation(models.Model):
    """Переводы для товаров украшений."""

    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]

    product = models.ForeignKey(
        JewelryProduct,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Товар украшений")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание товара украшений")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Перевод товара украшений")
        verbose_name_plural = _("Переводы товаров украшений")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']
        indexes = [
            models.Index(fields=['product', 'locale']),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.get_locale_display()})"


class JewelryProductImage(models.Model):
    """Изображение товара украшений."""

    product = models.ForeignKey(
        JewelryProduct,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Товар украшений")
    )
    image_url = models.URLField(
        _("URL изображения"),
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/jewelry/gallery/",
        blank=True,
        null=True,
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение товара украшений")
        verbose_name_plural = _("Изображения товаров украшений")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение {self.product.name}"


class JewelryVariant(models.Model):
    """Вариант украшения (цвет/материал + цены и остаток)."""

    product = models.ForeignKey(
        JewelryProduct,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Товар украшений (родитель)")
    )
    name = models.CharField(_("Название варианта"), max_length=500, blank=True)
    slug = models.SlugField(_("Slug варианта"), max_length=600, unique=True, help_text=_("Автогенерация по названию/цвету/материалу, можно переопределить."))
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    material = models.CharField(_("Материал варианта"), max_length=100, blank=True)
    # size поле оставлено для совместимости с фронтом, но реальные размеры в таблице sizes
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
    main_image_file = models.ImageField(
        _("Главное изображение варианта (файл)"),
        upload_to="products/jewelry/variants/",
        blank=True,
        null=True,
    )
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Вариант украшения")
        verbose_name_plural = _("Варианты украшений")
        ordering = ["product", "sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        base = self.name or self.product.name
        attrs = f"{self.color or ''} {self.material or ''}".strip()
        return f"{base} ({attrs})" if attrs else base

    def save(self, *args, **kwargs):
        """Автогенерация slug, если не заполнен."""
        if not self.slug:
            base_name = self.name or self.product.name
            composed = f"{base_name}-{self.color or ''}-{self.material or ''}".strip()
            base_slug = (slugify(composed)[:580] or slugify(base_name)[:580]).strip('-')
            if not base_slug:
                base_slug = f"v-{uuid.uuid4().hex[:12]}"
            slug = base_slug
            i = 2
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix = f"-{i}"
                slug = f"{base_slug[:580 - len(suffix)]}{suffix}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class JewelryVariantSize(models.Model):
    """Размер внутри варианта украшения."""

    SIZE_UNIT_CHOICES = [
        ("mm", _("Миллиметры")),
        ("cm", _("Сантиметры")),
        ("standard", _("Стандарт")),
    ]

    SIZE_TYPE_CHOICES = [
        ("ring_size", _("Размер кольца")),
        ("bracelet_length", _("Длина браслета")),
        ("necklace_length", _("Длина цепи/ожерелья")),
        ("standard", _("Стандарт")),
    ]

    variant = models.ForeignKey(
        JewelryVariant,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name=_("Вариант украшения")
    )
    size_value = models.DecimalField(
        _("Значение размера"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Числовое значение (например 16.5).")
    )
    size_unit = models.CharField(
        _("Единица"),
        max_length=16,
        choices=SIZE_UNIT_CHOICES,
        default="standard"
    )
    size_type = models.CharField(
        _("Тип размера"),
        max_length=32,
        choices=SIZE_TYPE_CHOICES,
        default="standard"
    )
    size_display = models.CharField(
        _("Отображаемый размер"),
        max_length=50,
        blank=True,
        help_text=_("Например: '16 мм', 'US 7', '18 см', 'Стандарт'.")
    )
    is_available = models.BooleanField(_("Доступен"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Остаток"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Размер варианта украшения")
        verbose_name_plural = _("Размеры варианта украшения")
        ordering = ["variant", "sort_order", "size_display"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
            models.Index(fields=["variant", "size_display"]),
        ]

    def __str__(self):
        return f"{self.variant} — {self.size_display or self.size_value or ''}".strip()

    def save(self, *args, **kwargs):
        """Автогенерация человекочитаемого отображения размера."""
        if not self.size_display:
            parts = []
            if self.size_value is not None:
                parts.append(f"{self.size_value}")
            unit_map = {"mm": "мм", "cm": "см", "standard": ""}
            unit = unit_map.get(self.size_unit, "")
            if unit:
                parts.append(unit)
            self.size_display = " ".join([p for p in parts if p]).strip() or _("Стандарт")
        super().save(*args, **kwargs)


class JewelryVariantImage(models.Model):
    """Изображение варианта украшения."""

    variant = models.ForeignKey(
        JewelryVariant,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Вариант украшения")
    )
    image_url = models.URLField(
        _("URL изображения"),
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/jewelry/variants/gallery/",
        blank=True,
        null=True,
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение варианта украшения")
        verbose_name_plural = _("Изображения вариантов украшений")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение варианта {self.variant}"


class ElectronicsProduct(models.Model):
    """Товар электроники."""
    
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
        related_name="electronics_products",
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
    main_image_file = models.ImageField(
        _("Главное изображение (файл)"),
        upload_to="products/electronics/main/",
        blank=True,
        null=True,
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

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание товара электроники."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''


class ElectronicsProductTranslation(models.Model):
    """Переводы для товаров электроники."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    product = models.ForeignKey(
        ElectronicsProduct,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Товар электроники")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание товара электроники")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод товара электроники")
        verbose_name_plural = _("Переводы товаров электроники")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']
        indexes = [
            models.Index(fields=['product', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.product.name} ({self.get_locale_display()})"


class Service(models.Model):
    """Услуга (не товар, а услуга)."""
    
    # Основная информация
    name = models.CharField(_("Название услуги"), max_length=500)
    slug = models.SlugField(_("Slug"), max_length=500, unique=True)
    description = models.TextField(_("Описание"), blank=True)
    
    # Категоризация
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="services",
        verbose_name=_("Категория")
    )
    
    # Цена и валюта
    price = models.DecimalField(
        _("Цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)],
        help_text=_("Стоимость услуги")
    )
    currency = models.CharField(
        _("Валюта"),
        max_length=5,
        choices=CURRENCY_CHOICES,
        default="RUB",
    )
    
    # Специфичные для услуг поля
    duration = models.CharField(
        _("Длительность"),
        max_length=100,
        blank=True,
        help_text=_("Например: '1 час', '30 минут', '1 день'")
    )
    service_type = models.CharField(
        _("Тип услуги"),
        max_length=100,
        blank=True,
        help_text=_("Например: 'Консультация', 'Диагностика', 'Лечение'")
    )
    
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
    
    # Статус
    is_active = models.BooleanField(_("Активна"), default=True)
    is_featured = models.BooleanField(_("Рекомендуемая"), default=False)
    
    # Временные метки
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Услуга")
        verbose_name_plural = _("Услуги")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["category"]),
            models.Index(fields=["price"]),
        ]
    
    def __str__(self):
        return self.name

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание услуги."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''


class ServiceTranslation(models.Model):
    """Переводы для услуг."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Услуга")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание услуги")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод услуги")
        verbose_name_plural = _("Переводы услуг")
        unique_together = [['service', 'locale']]
        ordering = ['service', 'locale']
        indexes = [
            models.Index(fields=['service', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.service.name} ({self.get_locale_display()})"


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
        max_length=2000,
        help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте.")
    )
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/electronics/gallery/",
        blank=True,
        null=True,
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


class FurnitureProduct(models.Model):
    """Товар мебели."""
    
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
        related_name="furniture_products",
        verbose_name=_("Категория")
    )
    brand = models.ForeignKey(
        Brand, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="furniture_products",
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
    )
    old_price = models.DecimalField(
        _("Старая цена"), 
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Специфичные для мебели поля
    material = models.CharField(_("Материал"), max_length=100, blank=True)
    furniture_type = models.CharField(_("Тип мебели"), max_length=100, blank=True, help_text=_("Например: диван, стол, стул"))
    dimensions = models.CharField(_("Размеры"), max_length=200, blank=True, help_text=_("Например: 200x100x80 см"))
    
    # Наличие и статус
    is_available = models.BooleanField(_("В наличии"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Количество на складе"), null=True, blank=True)
    
    # Изображения
    main_image = models.URLField(_("Главное изображение"), blank=True)
    main_image_file = models.ImageField(
        _("Главное изображение (файл)"),
        upload_to="products/furniture/main/",
        blank=True,
        null=True,
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
        verbose_name = _("Товар мебели")
        verbose_name_plural = _("Товары мебели")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return self.name

    def get_translated_description(self, locale: str = 'ru') -> str:
        """Получает переведенное описание товара мебели."""
        translation = self.translations.filter(locale=locale).first()
        if translation and translation.description:
            return translation.description
        return self.description or ''


class FurnitureProductTranslation(models.Model):
    """Переводы для товаров мебели."""
    
    LOCALE_CHOICES = [
        ('ru', _('Русский')),
        ('en', _('Английский')),
    ]
    
    product = models.ForeignKey(
        FurnitureProduct,
        on_delete=models.CASCADE,
        related_name='translations',
        verbose_name=_("Товар мебели")
    )
    locale = models.CharField(
        _("Язык"),
        max_length=10,
        choices=LOCALE_CHOICES,
        default='ru',
        db_index=True
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
        help_text=_("Переведенное описание товара мебели")
    )
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод товара мебели")
        verbose_name_plural = _("Переводы товаров мебели")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']
        indexes = [
            models.Index(fields=['product', 'locale']),
        ]
    
    def __str__(self):
        return f"{self.product.name} ({self.get_locale_display()})"


class FurnitureVariant(models.Model):
    """Вариант мебели (цвет, цены, остаток, галерея)."""
    
    product = models.ForeignKey(
        FurnitureProduct,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Товар мебели (родитель)")
    )
    name = models.CharField(_("Название варианта"), max_length=500, blank=True)
    slug = models.SlugField(_("Slug варианта"), max_length=600, unique=True, help_text=_("Автогенерация по названию/цвету, можно переопределить."))
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
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
    main_image_file = models.ImageField(
        _("Главное изображение варианта (файл)"),
        upload_to="products/furniture/variants/",
        blank=True,
        null=True,
    )
    external_id = models.CharField(_("Внешний ID"), max_length=100, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Вариант мебели")
        verbose_name_plural = _("Варианты мебели")
        ordering = ["product", "sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        base = self.name or self.product.name
        attrs = f"{self.color or ''}".strip()
        return f"{base} ({attrs})" if attrs else base

    def save(self, *args, **kwargs):
        """Автогенерация slug, если не заполнен."""
        if not self.slug:
            base_name = self.name or self.product.name
            composed = f"{base_name}-{self.color or ''}".strip()
            base_slug = (slugify(composed)[:580] or slugify(base_name)[:580]).strip('-')
            if not base_slug:
                base_slug = f"v-{uuid.uuid4().hex[:12]}"
            slug = base_slug
            i = 2
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix = f"-{i}"
                slug = f"{base_slug[:580 - len(suffix)]}{suffix}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class FurnitureVariantImage(models.Model):
    """Изображение варианта мебели."""
    
    variant = models.ForeignKey(
        FurnitureVariant,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Вариант мебели")
    )
    image_url = models.URLField(_("URL изображения"), help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте."))
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/furniture/variants/gallery/",
        blank=True,
        null=True,
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение варианта мебели")
        verbose_name_plural = _("Изображения вариантов мебели")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение варианта {self.variant}"


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
        upload_to=get_banner_image_upload_path,
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
        upload_to=get_banner_video_upload_path,
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
        upload_to=get_banner_gif_upload_path,
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
        # ВАЖНО: порядок должен быть детерминированным и совпадать в админке и API.
        # Сначала сортируем по баннеру, затем по sort_order, затем по id по возрастанию.
        # Так при одинаковом sort_order медиа идут в том порядке, в каком были созданы.
        ordering = ['banner', 'sort_order', 'id']
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


class Author(models.Model):
    """Автор книг."""
    
    first_name = models.CharField(_("Имя"), max_length=100)
    last_name = models.CharField(_("Фамилия"), max_length=100)
    bio = models.TextField(_("Биография"), blank=True)
    photo = models.URLField(_("Фото"), blank=True, help_text=_("URL фотографии автора"))
    birth_date = models.DateField(_("Дата рождения"), null=True, blank=True)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Автор")
        verbose_name_plural = _("Авторы")
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class BookVariant(models.Model):
    """Вариант книги (обложка, формат, цена)."""
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="book_variants",
        verbose_name=_("Книга (родитель)")
    )
    name = models.CharField(_("Название варианта"), max_length=500, blank=True)
    slug = models.SlugField(_("Slug варианта"), max_length=600, unique=True, help_text=_("Автогенерация по названию/формату"))
    cover_type = models.CharField(_("Тип обложки"), max_length=50, blank=True, help_text=_("Твердая, мягкая, суперобложка"))
    format_type = models.CharField(_("Формат"), max_length=50, blank=True, help_text=_("Твердый, мягкий, электронный"))
    isbn = models.CharField(_("ISBN"), max_length=20, blank=True, help_text=_("ISBN для конкретного варианта"))
    sku = models.CharField(_("SKU"), max_length=100, blank=True)
    barcode = models.CharField(_("Штрихкод"), max_length=100, blank=True)
    price = models.DecimalField(_("Цена"), max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    old_price = models.DecimalField(_("Старая цена"), max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    currency = models.CharField(_("Валюта"), max_length=5, choices=CURRENCY_CHOICES, default="RUB")
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
        verbose_name = _("Вариант книги")
        verbose_name_plural = _("Варианты книг")
        ordering = ["product", "sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        base = self.name or self.product.name
        attrs = f"{self.cover_type or ''} {self.format_type or ''}".strip()
        return f"{base} ({attrs})" if attrs else base

    def save(self, *args, **kwargs):
        """Автогенерация slug, если не заполнен."""
        if not self.slug:
            base_name = self.name or self.product.name
            composed = f"{base_name}-{self.cover_type or ''}-{self.format_type or ''}".strip()
            base_slug = (slugify(composed)[:580] or slugify(base_name)[:580]).strip('-')
            if not base_slug:
                base_slug = f"v-{uuid.uuid4().hex[:12]}"
            slug = base_slug
            i = 2
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix = f"-{i}"
                slug = f"{base_slug[:580 - len(suffix)]}{suffix}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class BookVariantSize(models.Model):
    """Формат/размер внутри варианта книги."""
    
    variant = models.ForeignKey(
        BookVariant,
        on_delete=models.CASCADE,
        related_name="sizes",
        verbose_name=_("Вариант книги")
    )
    size = models.CharField(
        _("Формат/размер"),
        max_length=50,
        blank=True,
        help_text=_("Например: Твердая, Мягкая, Электронная, 130x200, 140x215")
    )
    is_available = models.BooleanField(_("Доступен"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Остаток"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    class Meta:
        verbose_name = _("Формат варианта книги")
        verbose_name_plural = _("Форматы вариантов книг")
        ordering = ["variant", "sort_order", "size"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
            models.Index(fields=["variant", "size"]),
        ]

    def __str__(self):
        return f"{self.variant} — {self.size}"


class BookVariantImage(models.Model):
    """Изображение варианта книги."""
    
    variant = models.ForeignKey(
        BookVariant,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Вариант книги")
    )
    image_url = models.URLField(_("URL изображения"), help_text=_("Ссылка на изображение (CDN или медиа-хостинг); файл не сохраняется в проекте."))
    image_file = models.ImageField(
        _("Изображение (файл)"),
        upload_to="products/books/variants/gallery/",
        blank=True,
        null=True,
    )
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение варианта книги")
        verbose_name_plural = _("Изображения вариантов книг")
        ordering = ["sort_order", "created_at"]
        indexes = [
            models.Index(fields=["variant", "sort_order"]),
        ]

    def __str__(self):
        return f"Изображение варианта {self.variant}"


class ProductAuthor(models.Model):
    """Связь товара с авторами (для книг)."""
    
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="book_authors",
        verbose_name=_("Товар")
    )
    author = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name="books",
        verbose_name=_("Автор")
    )
    sort_order = models.IntegerField(_("Порядок сортировки"), default=0, help_text=_("Порядок отображения авторов"))
    created_at = models.DateTimeField(_("Дата создания"), auto_now_add=True)

    class Meta:
        verbose_name = _("Автор книги")
        verbose_name_plural = _("Авторы книг")
        unique_together = [['product', 'author']]
        ordering = ['sort_order', 'created_at']
        indexes = [
            models.Index(fields=['product', 'author']),
            models.Index(fields=['sort_order']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.author.full_name}"


class MarketingBannerMedia(BannerMedia):
    class Meta:
        proxy = True
        app_label = "marketing"
        verbose_name = _("Медиа баннеров")
        verbose_name_plural = _("Маркетинг — Медиа баннеров")


def _cleanup_variant_products(variant):
    external = variant.external_data or {}
    base_product_id = external.get("base_product_id")
    q = Q(external_data__source_variant_id=variant.id) | Q(external_data__source_variant_slug=variant.slug)
    if base_product_id:
        q |= Q(id=base_product_id, external_data__source_variant_id=variant.id)
    Product.objects.filter(q).delete()


@receiver(post_delete, sender=ClothingVariant)
def cleanup_clothing_variant_products(sender, instance, **kwargs):
    _cleanup_variant_products(instance)


@receiver(post_save, sender=ClothingVariant)
def cleanup_clothing_variant_products_on_deactivate(sender, instance, **kwargs):
    if not instance.is_active:
        _cleanup_variant_products(instance)


# Сигналы для автоматического создания цен вариантов
@receiver(post_save, sender=ClothingVariant)
def create_clothing_variant_price(sender, instance, created, **kwargs):
    """Создать цену для варианта одежды при его создании или обновлении"""
    from apps.catalog.utils.currency_converter import currency_converter
    
    # Если у варианта есть цена, создаем запись о цене
    if instance.price is not None and instance.price > 0:
        try:
            currency_converter.update_or_create_variant_price(
                variant_instance=instance,
                base_price=instance.price,
                base_currency=instance.currency or 'TRY'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating ClothingVariant price for {instance}: {str(e)}")


@receiver(post_save, sender=ShoeVariant)
def create_shoe_variant_price(sender, instance, created, **kwargs):
    """Создать цену для варианта обуви при его создании или обновлении"""
    from apps.catalog.utils.currency_converter import currency_converter
    
    # Если у варианта есть цена, создаем запись о цене
    if instance.price is not None and instance.price > 0:
        try:
            currency_converter.update_or_create_variant_price(
                variant_instance=instance,
                base_price=instance.price,
                base_currency=instance.currency or 'TRY'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating ShoeVariant price for {instance}: {str(e)}")


@receiver(post_save, sender=JewelryVariant)
def create_jewelry_variant_price(sender, instance, created, **kwargs):
    """Создать цену для варианта украшений при его создании или обновлении"""
    from apps.catalog.utils.currency_converter import currency_converter
    
    # Если у варианта есть цена, создаем запись о цене
    if instance.price is not None and instance.price > 0:
        try:
            currency_converter.update_or_create_variant_price(
                variant_instance=instance,
                base_price=instance.price,
                base_currency=instance.currency or 'TRY'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating JewelryVariant price for {instance}: {str(e)}")


@receiver(post_save, sender=FurnitureVariant)
def create_furniture_variant_price(sender, instance, created, **kwargs):
    """Создать цену для варианта мебели при его создании или обновлении"""
    from apps.catalog.utils.currency_converter import currency_converter
    
    # Если у варианта есть цена, создаем запись о цене
    if instance.price is not None and instance.price > 0:
        try:
            currency_converter.update_or_create_variant_price(
                variant_instance=instance,
                base_price=instance.price,
                base_currency=instance.currency or 'TRY'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating FurnitureVariant price for {instance}: {str(e)}")


@receiver(post_save, sender=BookVariant)
def create_book_variant_price(sender, instance, created, **kwargs):
    """Создать цену для варианта книг при его создании или обновлении"""
    from apps.catalog.utils.currency_converter import currency_converter
    
    # Если у варианта есть цена, создаем запись о цене
    if instance.price is not None and instance.price > 0:
        try:
            currency_converter.update_or_create_variant_price(
                variant_instance=instance,
                base_price=instance.price,
                base_currency=instance.currency or 'TRY'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating BookVariant price for {instance}: {str(e)}")


# Сигнал для очистки цен при удалении вариантов
@receiver(post_delete, sender=ClothingVariant)
@receiver(post_delete, sender=ShoeVariant)
@receiver(post_delete, sender=JewelryVariant)
@receiver(post_delete, sender=FurnitureVariant)
@receiver(post_delete, sender=BookVariant)
def cleanup_variant_prices(sender, instance, **kwargs):
    """Удалить цену варианта при удалении самого варианта"""
    from ..currency_models import ProductVariantPrice
    from django.contrib.contenttypes.models import ContentType
    
    try:
        content_type = ContentType.objects.get_for_model(instance)
        ProductVariantPrice.objects.filter(
            content_type=content_type,
            object_id=instance.id
        ).delete()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error cleaning up variant price for {instance}: {str(e)}")


@receiver(post_delete, sender=ShoeVariant)
def cleanup_shoe_variant_products(sender, instance, **kwargs):
    _cleanup_variant_products(instance)


@receiver(post_save, sender=ShoeVariant)
def cleanup_shoe_variant_products_on_deactivate(sender, instance, **kwargs):
    if not instance.is_active:
        _cleanup_variant_products(instance)
