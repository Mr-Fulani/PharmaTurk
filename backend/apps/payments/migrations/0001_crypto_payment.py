# Generated manually for CryptoPayment model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("orders", "0005_alter_promocode_max_discount_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CryptoPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="coinremitter", max_length=32, verbose_name="Провайдер")),
                ("invoice_id", models.CharField(db_index=True, max_length=128, verbose_name="ID инвойса")),
                ("address", models.CharField(max_length=256, verbose_name="Адрес для оплаты")),
                ("amount_crypto", models.DecimalField(decimal_places=8, default=0, max_digits=20, verbose_name="Сумма в крипте")),
                ("amount_fiat", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Сумма в фиате")),
                ("currency", models.CharField(default="USD", max_length=3, verbose_name="Валюта фиата")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Ожидает"), ("confirmed", "Подтверждён"), ("expired", "Истёк")],
                        default="pending",
                        max_length=32,
                        verbose_name="Статус",
                    ),
                ),
                ("qr_code_url", models.URLField(blank=True, verbose_name="URL QR-кода")),
                ("invoice_url", models.URLField(blank=True, verbose_name="URL инвойса")),
                ("expires_at", models.DateTimeField(verbose_name="Истекает")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crypto_payment",
                        to="orders.order",
                        verbose_name="Заказ",
                    ),
                ),
            ],
            options={
                "verbose_name": "Криптоплатёж",
                "verbose_name_plural": "Криптоплатежи",
            },
        ),
    ]
