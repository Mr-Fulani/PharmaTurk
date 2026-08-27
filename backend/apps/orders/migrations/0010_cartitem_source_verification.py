from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0202_productsourceoffer"),
        ("orders", "0009_cart_identity_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="observed_public_currency",
            field=models.CharField(
                blank=True,
                default="",
                max_length=10,
                verbose_name="Валюта проверенной цены для покупателя",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="observed_public_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Проверенная цена для покупателя",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="observed_source_currency",
            field=models.CharField(
                blank=True, default="", max_length=10, verbose_name="Валюта проверенной цены"
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="observed_source_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Проверенная цена источника",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="observed_stock_precision",
            field=models.CharField(
                choices=[
                    ("exact", "Точный остаток"),
                    ("boolean", "Только наличие"),
                    ("unknown", "Неизвестно"),
                ],
                default="unknown",
                max_length=16,
                verbose_name="Точность проверенного остатка",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="observed_stock_quantity",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Проверенный остаток источника"
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="price_acknowledged_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Изменение цены подтверждено"
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="price_acknowledged_currency",
            field=models.CharField(
                blank=True, default="", max_length=10, verbose_name="Валюта подтверждённой цены"
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="price_acknowledged_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Подтверждённая цена",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="price_change_state",
            field=models.CharField(
                choices=[
                    ("none", "Без изменения"),
                    ("decreased", "Цена снизилась"),
                    ("increased", "Цена повысилась"),
                ],
                default="none",
                max_length=16,
                verbose_name="Изменение цены",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="source_availability_status",
            field=models.CharField(
                blank=True, default="", max_length=32, verbose_name="Наличие по источнику"
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="source_checked_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Источник проверен"),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="source_offer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cart_items",
                to="catalog.productsourceoffer",
                verbose_name="Предложение источника",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="verification_issues",
            field=models.JSONField(blank=True, default=list, verbose_name="Проблемы проверки"),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("not_checked", "Не проверено"),
                    ("verified", "Проверено"),
                    ("blocked", "Покупка заблокирована"),
                    ("retryable_error", "Источник временно недоступен"),
                    ("unsupported", "Проверка не поддерживается"),
                ],
                db_index=True,
                default="not_checked",
                max_length=32,
                verbose_name="Статус проверки источника",
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="verified_quantity",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Количество позиции при проверке",
            ),
        ),
        migrations.AddIndex(
            model_name="cartitem",
            index=models.Index(
                fields=["verification_status", "source_checked_at"],
                name="orders_ci_verify_checked_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("observed_stock_precision", "exact"),
                        ("observed_stock_quantity__isnull", False),
                    ),
                    models.Q(
                        ("observed_stock_precision__in", ["boolean", "unknown"]),
                        ("observed_stock_quantity__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="orders_cartitem_observed_stock",
            ),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("price_acknowledged_at__isnull", True),
                        ("price_acknowledged_currency", ""),
                        ("price_acknowledged_value__isnull", True),
                    ),
                    models.Q(
                        ("price_acknowledged_at__isnull", False),
                        ("price_acknowledged_value__isnull", False),
                        models.Q(("price_acknowledged_currency", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="orders_cartitem_price_ack_complete",
            ),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("observed_public_currency", ""),
                        ("observed_public_price__isnull", True),
                    ),
                    models.Q(
                        ("observed_public_price__isnull", False),
                        models.Q(("observed_public_currency", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="orders_cartitem_public_observation",
            ),
        ),
    ]
