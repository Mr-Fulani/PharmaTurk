"""
Модель маппинга типов товаров на категории ВК Маркета.
Хранится отдельно от основного models.py для удобства поддержки.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class VKCategoryMapping(models.Model):
    """
    Маппинг (product_type, пол) → путь категории ВК Маркета.

    Управляется через Django Admin — без изменений кода при добавлении новых типов.
    Названия — из дерева категорий ВК (market.getCategories), см. docs/VK_YML_FEED.md.

    Пример vk_category_path:
      'Гардероб > Женщинам > Обувь'
      'Дом и дача > Мебель'
      'Витамины, БАДы и пищевые добавки'
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

    GENDER_CHOICES = [
        ("", "Любой пол"),
        ("men", "Мужское"),
        ("women", "Женское"),
        ("kids", "Детское"),
    ]

    product_type = models.CharField(
        _("Тип товара (product_type)"),
        max_length=60,
        choices=PRODUCT_TYPE_CHOICES,
        help_text=_("Значение product_type товара (из поля Product.product_type)."),
    )
    gender = models.CharField(
        _("Пол"),
        max_length=10,
        blank=True,
        default="",
        choices=GENDER_CHOICES,
        help_text=_(
            "Пол товара (товар или его категория). «Любой пол» — для товаров без пола, "
            "унисекс и типов, где ВК не делит по полу."
        ),
    )
    vk_category_path = models.CharField(
        _("Путь категории ВК"),
        max_length=500,
        help_text=_(
            "Полный путь категории через ' > '. "
            "Пример: 'Дом и дача > Мебель'"
        ),
    )
    vk_category_id = models.PositiveIntegerField(
        _("ID категории ВК"),
        null=True,
        blank=True,
        help_text=_(
            "Нужен, чтобы добавлять товары через API (market.add). Пусто — новые товары "
            "этой категории не добавляются, в отчёте синхронизации они указаны отдельно."
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
        ordering = ["product_type", "gender"]
        constraints = [
            models.UniqueConstraint(fields=["product_type", "gender"], name="catalog_vk_mapping_type_gender_uniq"),
        ]

    def __str__(self) -> str:
        suffix = f" ({self.gender})" if self.gender else ""
        return f"{self.product_type}{suffix} → {self.vk_category_path}"


class YMLFeedSnapshot(models.Model):
    """
    Готовый файл YML-фида: полный каталог (пустой slug) или корневая категория.

    Фид больше лимита ВК делится на части (part = 1, 2, …). Собирает задача
    catalog.generate_yml_feeds, эндпоинт фида отдаёт файл как есть.
    """

    category_slug = models.CharField(
        _("Slug категории"),
        max_length=200,
        blank=True,
        help_text=_("Пусто — полный каталог."),
    )
    part = models.PositiveSmallIntegerField(_("Часть"), default=1)
    file = models.FileField(_("Файл фида"), upload_to="feeds/yml/", max_length=300, blank=True)
    generated_at = models.DateTimeField(_("Собран"), null=True, blank=True)
    offers_count = models.PositiveIntegerField(_("Офферов"), default=0)
    size_bytes = models.PositiveBigIntegerField(_("Размер, байт"), default=0)

    class Meta:
        verbose_name = _("Готовый YML-фид")
        verbose_name_plural = _("Готовые YML-фиды")
        ordering = ["category_slug", "part"]
        constraints = [
            models.UniqueConstraint(fields=["category_slug", "part"], name="catalog_yml_feed_slug_part_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.category_slug or 'catalog'} #{self.part}"
