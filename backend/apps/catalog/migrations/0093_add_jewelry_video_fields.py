# Generated manually for JewelryProduct video support (Reels from Instagram etc.)

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0092_add_sports_auto_parts_services_product_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="jewelryproduct",
            name="video_url",
            field=models.URLField(
                blank=True,
                help_text="URL видео (например, Reels из Instagram). При сохранении скачивается в хранилище.",
                max_length=2000,
                verbose_name="URL видео",
            ),
        ),
        migrations.AddField(
            model_name="jewelryproduct",
            name="main_video_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="products/jewelry/main/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["mp4", "mov", "webm", "avi", "mkv"]
                    )
                ],
                verbose_name="Главное видео (файл)",
            ),
        ),
    ]
