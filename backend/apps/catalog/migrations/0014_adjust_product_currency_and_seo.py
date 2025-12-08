from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0013_manual_product_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="currency",
            field=models.CharField(
                choices=[
                    ("RUB", "RUB"),
                    ("USD", "USD"),
                    ("EUR", "EUR"),
                    ("TRY", "TRY"),
                    ("GBP", "GBP"),
                ],
                default="RUB",
                help_text=_("Выбирается из списка расчётных валют, используемых в прайсах."),
                max_length=3,
                verbose_name=_("Валюта"),
            ),
        ),
        migrations.RemoveField(
            model_name="product",
            name="meta_title_en",
        ),
        migrations.RemoveField(
            model_name="product",
            name="meta_description_en",
        ),
        migrations.RemoveField(
            model_name="product",
            name="meta_keywords_en",
        ),
        migrations.RemoveField(
            model_name="product",
            name="og_title_en",
        ),
        migrations.RemoveField(
            model_name="product",
            name="og_description_en",
        ),
    ]

