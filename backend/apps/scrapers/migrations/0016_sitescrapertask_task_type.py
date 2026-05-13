from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0015_sitescrapertask_max_products_100k"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitescrapertask",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("catalog", "Парсинг каталога"),
                    ("stub_refresh", "Обновление заглушек"),
                ],
                default="catalog",
                max_length=20,
                verbose_name="Тип задачи",
            ),
        ),
        migrations.AlterField(
            model_name="sitescrapertask",
            name="start_url",
            field=models.URLField(blank=True, verbose_name="Начальный URL"),
        ),
    ]
