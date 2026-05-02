from django.db import migrations, models

import apps.catalog.utils.storage_paths


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0177_serviceportfolioitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="after_image_file",
            field=models.ImageField(
                blank=True,
                help_text="Фото объекта после завершения работ.",
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_service_image_upload_path,
                verbose_name="Фото после (файл)",
            ),
        ),
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="after_image_url",
            field=models.URLField(
                blank=True,
                help_text="Внешняя ссылка на фото объекта после завершения работ.",
                max_length=2000,
                verbose_name="URL фото после",
            ),
        ),
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="before_image_file",
            field=models.ImageField(
                blank=True,
                help_text="Фото объекта до начала работ.",
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_service_image_upload_path,
                verbose_name="Фото до (файл)",
            ),
        ),
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="before_image_url",
            field=models.URLField(
                blank=True,
                help_text="Внешняя ссылка на фото объекта до начала работ.",
                max_length=2000,
                verbose_name="URL фото до",
            ),
        ),
    ]
