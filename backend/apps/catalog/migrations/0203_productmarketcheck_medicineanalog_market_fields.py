from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0202_productsourceoffer"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicineanalog",
            name="last_observed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Последнее наблюдение"),
        ),
        migrations.AddField(
            model_name="medicineanalog",
            name="reference_currency",
            field=models.CharField(
                blank=True, max_length=10, verbose_name="Валюта справочной цены"
            ),
        ),
        migrations.AddField(
            model_name="medicineanalog",
            name="reference_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Справочная цена источника",
            ),
        ),
        migrations.AddField(
            model_name="medicineanalog",
            name="source_url",
            field=models.URLField(
                blank=True, max_length=2000, verbose_name="URL аналога в источнике"
            ),
        ),
        migrations.CreateModel(
            name="ProductMarketCheck",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "source",
                    models.CharField(db_index=True, max_length=100, verbose_name="Источник"),
                ),
                ("source_url", models.URLField(max_length=2000, verbose_name="URL источника")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "В очереди"),
                            ("running", "Выполняется"),
                            ("succeeded", "Успешно"),
                            ("source_unavailable", "Источник недоступен"),
                            ("failed", "Ошибка"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=32,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "observed_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Последняя подтверждённая цена",
                    ),
                ),
                (
                    "observed_currency",
                    models.CharField(blank=True, max_length=10, verbose_name="Валюта"),
                ),
                (
                    "previous_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Цена до последнего изменения",
                    ),
                ),
                (
                    "analog_count",
                    models.PositiveIntegerField(default=0, verbose_name="Найдено аналогов"),
                ),
                (
                    "request_count",
                    models.PositiveIntegerField(default=0, verbose_name="Количество запросов"),
                ),
                (
                    "task_id",
                    models.CharField(blank=True, max_length=100, verbose_name="ID задачи Celery"),
                ),
                (
                    "error_code",
                    models.CharField(blank=True, max_length=64, verbose_name="Код ошибки"),
                ),
                (
                    "error_message",
                    models.CharField(
                        blank=True, max_length=500, verbose_name="Безопасное сообщение об ошибке"
                    ),
                ),
                (
                    "requested_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Последний запрос"),
                ),
                (
                    "started_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Начало проверки"),
                ),
                (
                    "finished_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Завершение проверки"),
                ),
                (
                    "last_success_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Последняя успешная проверка"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="market_checks",
                        to="catalog.product",
                        verbose_name="Товар",
                    ),
                ),
            ],
            options={
                "verbose_name": "Проверка справочной цены",
                "verbose_name_plural": "Проверки справочных цен",
                "ordering": ["-requested_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["status", "requested_at"], name="catalog_mc_status_req_idx"
                    ),
                    models.Index(
                        fields=["source", "last_success_at"], name="catalog_mc_source_ok_idx"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("product", "source"),
                        name="catalog_marketcheck_product_source_uniq",
                    ),
                ],
            },
        ),
    ]
