# Generated manually for R2: галерея книг с видео (ссылка на parsed/ без дубля в main/).

import apps.catalog.utils.storage_paths
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0163_imagefile_max_length_500"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookproductimage",
            name="video_url",
            field=models.URLField(
                blank=True,
                help_text="Видео в галерее (парсер кладёт ссылку на R2; без дублирования в main/).",
                max_length=2000,
                verbose_name="URL видео",
            ),
        ),
        migrations.AddField(
            model_name="bookproductimage",
            name="video_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_book_product_gallery_upload_path,
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["mp4", "mov", "webm", "avi", "mkv"]
                    )
                ],
                verbose_name="Видео (файл)",
                max_length=2000,
            ),
        ),
    ]
