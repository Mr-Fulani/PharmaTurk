from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0014_update_scraper_task_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitescrapertask",
            name="max_products",
            field=models.PositiveIntegerField(
                default=50,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100000),
                ],
                verbose_name="Макс. товаров",
            ),
        ),
    ]
