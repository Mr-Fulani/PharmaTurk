from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scrapers", "0021_sitescrapertask_target_brand"),
    ]

    operations = [
        migrations.AddField(
            model_name="scrapingsession",
            name="analog_errors",
            field=models.PositiveIntegerField(default=0, verbose_name="Ошибки обработки аналогов"),
        ),
        migrations.AddField(
            model_name="scrapingsession",
            name="analog_links_saved",
            field=models.PositiveIntegerField(default=0, verbose_name="Сохранено связей аналогов"),
        ),
        migrations.AddField(
            model_name="scrapingsession",
            name="analog_stubs_created",
            field=models.PositiveIntegerField(default=0, verbose_name="Создано заглушек аналогов"),
        ),
        migrations.AddField(
            model_name="scrapingsession",
            name="analog_stubs_upgraded",
            field=models.PositiveIntegerField(default=0, verbose_name="Заполнено заглушек аналогов"),
        ),
        migrations.AddField(
            model_name="scrapingsession",
            name="analogs_found",
            field=models.PositiveIntegerField(default=0, verbose_name="Найдено аналогов"),
        ),
        migrations.AddField(
            model_name="sitescrapertask",
            name="analog_errors",
            field=models.PositiveIntegerField(default=0, verbose_name="Ошибки обработки аналогов"),
        ),
        migrations.AddField(
            model_name="sitescrapertask",
            name="analog_links_saved",
            field=models.PositiveIntegerField(default=0, verbose_name="Сохранено связей аналогов"),
        ),
        migrations.AddField(
            model_name="sitescrapertask",
            name="analog_stubs_created",
            field=models.PositiveIntegerField(default=0, verbose_name="Создано заглушек аналогов"),
        ),
        migrations.AddField(
            model_name="sitescrapertask",
            name="analog_stubs_upgraded",
            field=models.PositiveIntegerField(default=0, verbose_name="Заполнено заглушек аналогов"),
        ),
        migrations.AddField(
            model_name="sitescrapertask",
            name="analogs_found",
            field=models.PositiveIntegerField(default=0, verbose_name="Найдено аналогов"),
        ),
    ]
