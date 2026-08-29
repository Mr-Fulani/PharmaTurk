from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0011_orderitem_source_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cartitem",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("not_checked", "Не проверено"),
                    ("pending_confirmation", "Ожидает подтверждения поставщика"),
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
    ]
