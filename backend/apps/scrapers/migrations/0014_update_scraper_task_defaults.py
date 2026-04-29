from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0013_alter_scraperconfig_default_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scrapingsession",
            name="max_pages",
            field=models.PositiveIntegerField(default=1, verbose_name="Макс. страниц"),
        ),
        migrations.AlterField(
            model_name="scrapingsession",
            name="max_products",
            field=models.PositiveIntegerField(default=50, verbose_name="Макс. товаров"),
        ),
        migrations.AlterField(
            model_name="scrapingsession",
            name="max_images_per_product",
            field=models.PositiveIntegerField(
                default=20,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)],
                verbose_name="Макс. медиа на товар",
            ),
        ),
        migrations.AlterField(
            model_name="sitescrapertask",
            name="max_pages",
            field=models.PositiveIntegerField(
                default=1,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(1000)],
                verbose_name="Макс. страниц",
            ),
        ),
        migrations.AlterField(
            model_name="sitescrapertask",
            name="max_products",
            field=models.PositiveIntegerField(
                default=50,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10000)],
                verbose_name="Макс. товаров",
            ),
        ),
        migrations.AlterField(
            model_name="sitescrapertask",
            name="max_images_per_product",
            field=models.PositiveIntegerField(
                default=20,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)],
                verbose_name="Макс. медиа на товар",
            ),
        ),
    ]
