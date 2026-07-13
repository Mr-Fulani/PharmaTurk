from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0195_medicine_created_partial_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="globalcurrencysettings",
            name="default_margin_percentage",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("15.00"),
                help_text=(
                    "Используется только если у бренда и категории товара маржа равна 0. "
                    "Маржа валютных пар настраивается отдельно."
                ),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Глобальная товарная маржа (%)",
            ),
        ),
    ]
