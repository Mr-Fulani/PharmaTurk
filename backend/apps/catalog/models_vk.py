"""
Модель маппинга типов товаров на категории ВК Маркета.
Хранится отдельно от основного models.py для удобства поддержки.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class VKCategoryMapping(models.Model):
    """
    Маппинг product_type → путь категории ВК Маркета.

    Управляется через Django Admin — без изменений кода при добавлении новых типов.

    Пример vk_category_path:
      'Одежда, обувь и аксессуары > Мужская одежда > Головные уборы > Кепки и бейсболки'
      'Электроника > Смартфоны и гаджеты'
      'Здоровье > Витамины и БАД'
      'Мебель и интерьер > Мебель'
      'Запчасти и автотовары'
    """

    PRODUCT_TYPE_CHOICES = [
        ("clothing",          "Одежда"),
        ("shoes",             "Обувь"),
        ("jewelry",           "Ювелирные украшения"),
        ("electronics",       "Электроника"),
        ("furniture",         "Мебель"),
        ("books",             "Книги"),
        ("perfumery",         "Парфюмерия"),
        ("medicines",         "Лекарства"),
        ("supplements",       "БАДы"),
        ("medical_equipment", "Медицинская техника"),
        ("tableware",         "Посуда"),
        ("accessories",       "Аксессуары"),
        ("incense",           "Благовония"),
        ("sports",            "Спортивные товары"),
        ("auto_parts",        "Автозапчасти"),
        ("headwear",          "Головные уборы"),
        ("underwear",         "Нижнее бельё"),
        ("islamic_clothing",  "Исламская одежда"),
    ]

    product_type = models.CharField(
        _("Тип товара (product_type)"),
        max_length=60,
        unique=True,
        choices=PRODUCT_TYPE_CHOICES,
        help_text=_("Значение product_type товара (из поля Product.product_type)."),
    )
    vk_category_path = models.CharField(
        _("Путь категории ВК"),
        max_length=500,
        help_text=_(
            "Полный путь категории через ' > '. "
            "Пример: 'Здоровье > Витамины и БАД'"
        ),
    )
    notes = models.TextField(
        _("Примечания"),
        blank=True,
        help_text=_("Необязательное поле: откуда взят путь, особенности."),
    )
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Маппинг категории ВК")
        verbose_name_plural = _("Маппинги категорий ВК")
        ordering = ["product_type"]

    def __str__(self) -> str:
        return f"{self.product_type} → {self.vk_category_path}"


class YMLFeedSnapshot(models.Model):
    """
    Готовый файл YML-фида: полный каталог (пустой slug) или корневая категория.

    Собирает задача catalog.generate_yml_feeds, эндпоинт фида отдаёт файл как есть.
    """

    category_slug = models.CharField(
        _("Slug категории"),
        max_length=200,
        unique=True,
        blank=True,
        help_text=_("Пусто — полный каталог."),
    )
    file = models.FileField(_("Файл фида"), upload_to="feeds/yml/", max_length=300, blank=True)
    generated_at = models.DateTimeField(_("Собран"), null=True, blank=True)
    offers_count = models.PositiveIntegerField(_("Офферов"), default=0)
    size_bytes = models.PositiveBigIntegerField(_("Размер, байт"), default=0)

    class Meta:
        verbose_name = _("Готовый YML-фид")
        verbose_name_plural = _("Готовые YML-фиды")
        ordering = ["category_slug"]

    def __str__(self) -> str:
        return self.category_slug or "catalog"
