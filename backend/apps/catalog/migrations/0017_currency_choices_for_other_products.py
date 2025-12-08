from django.db import migrations, models
from django.utils.translation import gettext_lazy as _

COMMON_CURRENCY_CHOICES = [
    ("RUB", "RUB"),
    ("USD", "USD"),
    ("EUR", "EUR"),
    ("TRY", "TRY"),
    ("GBP", "GBP"),
    ("USDT", "USDT"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0016_shoe_gallery_and_size_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clothingproduct",
            name="currency",
            field=models.CharField(
                choices=COMMON_CURRENCY_CHOICES,
                default="RUB",
                help_text=_("Выбирается из списка расчётных валют, используемых в прайсах."),
                max_length=5,
                verbose_name=_("Валюта"),
            ),
        ),
        migrations.AlterField(
            model_name="shoeproduct",
            name="currency",
            field=models.CharField(
                choices=COMMON_CURRENCY_CHOICES,
                default="RUB",
                help_text=_("Выбирается из списка расчётных валют, используемых в прайсах."),
                max_length=5,
                verbose_name=_("Валюта"),
            ),
        ),
        migrations.AlterField(
            model_name="electronicsproduct",
            name="currency",
            field=models.CharField(
                choices=COMMON_CURRENCY_CHOICES,
                default="RUB",
                help_text=_("Выбирается из списка расчётных валют, используемых в прайсах."),
                max_length=5,
                verbose_name=_("Валюта"),
            ),
        ),
    ]

