import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0013_supplement_pending_items_payable"),
        ("payments", "0002_cryptopayment_invoice_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="CryptoInvoiceRequest",
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
                    "idempotency_key",
                    models.CharField(
                        max_length=64,
                        unique=True,
                        verbose_name="Хэш ключа идемпотентности",
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        default="coinremitter",
                        max_length=32,
                        verbose_name="Провайдер",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Ожидает отправки"),
                            ("processing", "Отправляется провайдеру"),
                            ("succeeded", "Инвойс создан"),
                            ("failed", "Отклонён до создания"),
                            ("uncertain", "Результат требует сверки"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "amount_fiat",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        verbose_name="Сумма запроса в фиате",
                    ),
                ),
                (
                    "fiat_currency",
                    models.CharField(max_length=3, verbose_name="Валюта запроса"),
                ),
                (
                    "locale",
                    models.CharField(
                        default="ru",
                        max_length=2,
                        verbose_name="Язык возврата",
                    ),
                ),
                (
                    "attempt_count",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="Количество попыток",
                    ),
                ),
                (
                    "processing_started_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Начало обращения к провайдеру",
                    ),
                ),
                (
                    "last_enqueued_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Последняя публикация в очередь",
                    ),
                ),
                (
                    "completed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Завершено",
                    ),
                ),
                (
                    "last_error_code",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="Безопасный код последней ошибки",
                    ),
                ),
                (
                    "provider_invoice_id",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="ID инвойса провайдера",
                    ),
                ),
                (
                    "provider_invoice_code",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="Короткий ID инвойса провайдера",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crypto_invoice_request",
                        to="orders.order",
                        verbose_name="Заказ",
                    ),
                ),
            ],
            options={
                "verbose_name": "Запрос криптоинвойса",
                "verbose_name_plural": "Запросы криптоинвойсов",
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="pay_invreq_status_created",
                    )
                ],
            },
        ),
    ]
