import sys

domains = [
    {
        "Prefix": "Headwear",
        "type": "headwear",
        "related_name": "headwear_item",
        "category_folder": "headwear",
        "verbose_name_product": "Головной убор",
        "verbose_name_products": "Головные уборы",
    },
    {
        "Prefix": "Underwear",
        "type": "underwear",
        "related_name": "underwear_item",
        "category_folder": "underwear",
        "verbose_name_product": "Нижнее бельё (товар)",
        "verbose_name_products": "Нижнее бельё",
    },
    {
        "Prefix": "IslamicClothing",
        "type": "islamic_clothing",
        "related_name": "islamic_clothing_item",
        "category_folder": "islamic_clothing",
        "verbose_name_product": "Исламская одежда",
        "verbose_name_products": "Исламская одежда",
    },
]

template = """
# ============================================================================
# ДОМЕН {Prefix}
# ============================================================================

class {Prefix}Product(AbstractDomainProduct):
    \"\"\"{verbose_name_product}.\"\"\"
    _domain_product_type = "{type}"
    base_product = models.OneToOneField(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="{related_name}", verbose_name=_("Базовый товар (shadow)"))
    size = models.CharField(_("Размер"), max_length=20, blank=True)
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    video_url = models.URLField(_("URL видео"), max_length=2000, blank=True)
    main_video_file = models.FileField(_("Главное видео (файл)"), upload_to="products/{category_folder}/main/", blank=True, null=True)

    class Meta:
        verbose_name = _("{verbose_name_product}")
        verbose_name_plural = _("{verbose_name_products}")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["external_id"]),
            models.Index(fields=["is_active", "is_available"]),
            models.Index(fields=["category", "brand"]),
            models.Index(fields=["price"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_to_base_product()

class {Prefix}ProductSize(models.Model):
    product = models.ForeignKey({Prefix}Product, on_delete=models.CASCADE, related_name="sizes", verbose_name=_("{verbose_name_product}"))
    size = models.CharField(_("Размер"), max_length=50, blank=True)
    is_available = models.BooleanField(_("Доступен"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Остаток"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Размер товара: {verbose_name_product}")
        verbose_name_plural = _("Размеры: {verbose_name_products}")
        ordering = ["product", "sort_order", "size"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["product", "size"]),
        ]

class {Prefix}ProductTranslation(models.Model):
    product = models.ForeignKey({Prefix}Product, on_delete=models.CASCADE, related_name='translations', verbose_name=_("{verbose_name_product}"))
    locale = models.CharField(_("Язык"), max_length=10, choices=[('ru', _('Русский')), ('en', _('Английский'))], default='ru', db_index=True)
    name = models.CharField(_("Название"), max_length=500, blank=True)
    description = models.TextField(_("Описание"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("Перевод: {verbose_name_product}")
        verbose_name_plural = _("Переводы: {verbose_name_products}")
        unique_together = [['product', 'locale']]
        ordering = ['product', 'locale']

class {Prefix}ProductImage(models.Model):
    product = models.ForeignKey({Prefix}Product, on_delete=models.CASCADE, related_name="images", verbose_name=_("{verbose_name_product}"))
    image_url = models.URLField(_("URL изображения"), max_length=2000, blank=True)
    image_file = models.ImageField(_("Изображение (файл)"), upload_to="products/{category_folder}/gallery/", blank=True, null=True)
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение {verbose_name_product}")
        verbose_name_plural = _("Изображения {verbose_name_products}")
        ordering = ["sort_order", "created_at"]

class {Prefix}Variant(models.Model):
    product = models.ForeignKey({Prefix}Product, on_delete=models.CASCADE, related_name="variants", verbose_name=_("{verbose_name_product} (родитель)"))
    name = models.CharField(_("Название варианта"), max_length=500, blank=True)
    name_en = models.CharField(_("Название (англ.)"), max_length=500, blank=True)
    slug = models.SlugField(_("Slug варианта"), max_length=600, unique=True)
    color = models.CharField(_("Цвет"), max_length=50, blank=True)
    size = models.CharField(_("Размер (устарело)"), max_length=50, blank=True)
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
    main_image_file = models.ImageField(_("Главное изображение варианта (файл)"), upload_to="products/{category_folder}/variants/", blank=True, null=True)
    external_id = models.CharField(_("Внешний ID"), max_length=500, blank=True)
    external_url = models.URLField(_("Внешняя ссылка"), blank=True, max_length=2000)
    external_data = models.JSONField(_("Внешние данные"), default=dict, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Вариант: {verbose_name_product}")
        verbose_name_plural = _("Варианты: {verbose_name_products}")
        ordering = ["product", "sort_order", "-created_at"]
        indexes = [
            models.Index(fields=["product", "sort_order"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active", "is_available"]),
        ]

    def __str__(self):
        base = self.name or self.product.name
        attrs = f"{{self.color or ''}} {{self.size or ''}}".strip()
        return f"{{base}} ({{attrs}})" if attrs else base

    def save(self, *args, **kwargs):
        if not self.slug:
            base_name = self.name or self.product.name
            composed = f"{{base_name}}-{{self.color or ''}}-{{self.size or ''}}".strip()
            base_slug = (slugify(composed)[:580] or slugify(base_name)[:580]).strip('-')
            if not base_slug:
                base_slug = f"v-{{uuid.uuid4().hex[:12]}}"
            slug = base_slug
            i = 2
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                suffix = f"-{{i}}"
                slug = f"{{base_slug[:580 - len(suffix)]}}{{suffix}}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

class {Prefix}VariantSize(models.Model):
    variant = models.ForeignKey({Prefix}Variant, on_delete=models.CASCADE, related_name="sizes", verbose_name=_("Вариант"))
    size = models.CharField(_("Размер"), max_length=50, blank=True)
    is_available = models.BooleanField(_("Доступен"), default=True)
    stock_quantity = models.PositiveIntegerField(_("Остаток"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Размер варианта: {verbose_name_product}")
        verbose_name_plural = _("Размеры вариантов: {verbose_name_products}")
        ordering = ["variant", "sort_order", "size"]

class {Prefix}VariantImage(models.Model):
    variant = models.ForeignKey({Prefix}Variant, on_delete=models.CASCADE, related_name="images", verbose_name=_("Вариант"))
    image_url = models.URLField(_("URL изображения"), max_length=2000, blank=True)
    image_file = models.ImageField(_("Изображение (файл)"), upload_to="products/{category_folder}/variants/gallery/", blank=True, null=True)
    alt_text = models.CharField(_("Alt текст"), max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок сортировки"), default=0)
    is_main = models.BooleanField(_("Главное изображение"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Изображение варианта: {verbose_name_product}")
        verbose_name_plural = _("Изображения вариантов: {verbose_name_products}")
        ordering = ["sort_order", "created_at"]
"""

out = ""
for d in domains:
    out += template.format(**d)
    
with open("/Users/user/PharmaTurk/backend/apps/catalog/models.py", "a", encoding="utf-8") as f:
    f.write(out)
