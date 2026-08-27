from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0201_canonicalize_favorite_product_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductSourceOffer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "parser_key",
                    models.CharField(
                        db_index=True,
                        help_text="Стабильный ключ parser registry, например zara или flo.",
                        max_length=100,
                        verbose_name="Ключ парсера",
                    ),
                ),
                (
                    "parser_config",
                    models.JSONField(blank=True, default=dict, verbose_name="Конфигурация парсера"),
                ),
                (
                    "source_domain",
                    models.CharField(db_index=True, max_length=255, verbose_name="Домен источника"),
                ),
                (
                    "canonical_url",
                    models.URLField(max_length=2000, verbose_name="Канонический URL"),
                ),
                (
                    "offer_key",
                    models.CharField(
                        editable=False, max_length=64, verbose_name="Ключ предложения"
                    ),
                ),
                (
                    "external_product_id",
                    models.CharField(blank=True, max_length=500, verbose_name="Внешний ID товара"),
                ),
                (
                    "external_sku",
                    models.CharField(blank=True, max_length=500, verbose_name="Внешний SKU"),
                ),
                (
                    "variant_key",
                    models.CharField(blank=True, max_length=500, verbose_name="Ключ варианта"),
                ),
                (
                    "size_key",
                    models.CharField(blank=True, max_length=100, verbose_name="Ключ размера"),
                ),
                (
                    "selected_options",
                    models.JSONField(blank=True, default=dict, verbose_name="Выбранные опции"),
                ),
                (
                    "source_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Цена источника",
                    ),
                ),
                (
                    "source_currency",
                    models.CharField(blank=True, max_length=10, verbose_name="Валюта источника"),
                ),
                (
                    "availability_status",
                    models.CharField(
                        choices=[
                            ("in_stock", "В наличии"),
                            ("out_of_stock", "Нет в наличии"),
                            ("limited", "Ограниченный остаток"),
                            ("discontinued", "Снят с продажи"),
                            ("unknown", "Неизвестно"),
                            ("source_unreachable", "Источник недоступен"),
                            ("unsupported", "Проверка не поддерживается"),
                        ],
                        db_index=True,
                        default="unknown",
                        max_length=32,
                        verbose_name="Статус источника",
                    ),
                ),
                (
                    "stock_precision",
                    models.CharField(
                        choices=[
                            ("exact", "Точный остаток"),
                            ("boolean", "Только наличие"),
                            ("unknown", "Неизвестно"),
                        ],
                        default="unknown",
                        max_length=16,
                        verbose_name="Точность остатка",
                    ),
                ),
                (
                    "stock_quantity",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="Остаток источника"
                    ),
                ),
                (
                    "priority",
                    models.PositiveSmallIntegerField(
                        default=100,
                        help_text="Меньшее значение выбирается первым.",
                        verbose_name="Приоритет",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Активно")),
                (
                    "last_checked_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Последняя проверка"),
                ),
                (
                    "last_successful_check_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Последняя успешная проверка"
                    ),
                ),
                (
                    "last_error_code",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="Код последней ошибки"
                    ),
                ),
                (
                    "last_error_message",
                    models.TextField(blank=True, verbose_name="Последняя ошибка"),
                ),
                (
                    "consecutive_failures",
                    models.PositiveIntegerField(default=0, verbose_name="Ошибок подряд"),
                ),
                (
                    "response_metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="Диагностика ответа"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="source_offers",
                        to="catalog.product",
                        verbose_name="Товар",
                    ),
                ),
            ],
            options={
                "verbose_name": "Предложение источника",
                "verbose_name_plural": "Предложения источников",
                "ordering": ["product_id", "priority", "id"],
                "indexes": [
                    models.Index(
                        fields=["product", "is_active", "priority"],
                        name="catalog_so_prod_active_pri",
                    ),
                    models.Index(
                        fields=["source_domain", "is_active"], name="catalog_so_source_active_idx"
                    ),
                    models.Index(
                        fields=["availability_status", "last_checked_at"],
                        name="catalog_so_status_checked_idx",
                    ),
                    models.Index(
                        fields=["parser_key", "last_checked_at"],
                        name="catalog_so_parser_checked_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("product", "parser_key", "offer_key"),
                        name="catalog_sourceoffer_identity_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("offer_key", ""), _negated=True),
                        name="catalog_sourceoffer_key_nonempty",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("stock_precision", "exact"), ("stock_quantity__isnull", False)
                            )
                            | models.Q(
                                ("stock_precision__in", ["boolean", "unknown"]),
                                ("stock_quantity__isnull", True),
                            )
                        ),
                        name="catalog_sourceoffer_stock_precision",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("availability_status", "in_stock"),
                            ("stock_precision", "exact"),
                            ("stock_quantity", 0),
                            _negated=True,
                        ),
                        name="catalog_sourceoffer_instock_nonzero",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("availability_status", "out_of_stock"),
                                ("stock_precision", "exact"),
                                _negated=True,
                            )
                            | models.Q(("stock_quantity", 0))
                        ),
                        name="catalog_sourceoffer_outstock_zero",
                    ),
                ],
            },
        ),
    ]
