"""Длина путей фото шапок, белья и исламской одежды — 500, как у обуви и одежды.

С 100 символами путь вида products/headwear/hw-caps/hw-baseball-caps/… не
помещался: «Storage can not find an available filename», image_file пустой,
фото качались заново при каждом проходе парсера. Только схема, без сети.
"""

import apps.catalog.utils.storage_paths
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0235_cross_source_duplicates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="headwearproduct",
            name="main_video_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_main_upload_path,
                verbose_name="Главное видео (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="headwearproductimage",
            name="image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_gallery_upload_path,
                verbose_name="Изображение (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="headwearvariant",
            name="main_image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_variant_main_upload_path,
                verbose_name="Главное изображение варианта (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="headwearvariantimage",
            name="image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_variant_gallery_upload_path,
                verbose_name="Изображение (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="underwearproduct",
            name="main_video_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_main_upload_path,
                verbose_name="Главное видео (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="underwearproductimage",
            name="image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_gallery_upload_path,
                verbose_name="Изображение (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="underwearvariant",
            name="main_image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_variant_main_upload_path,
                verbose_name="Главное изображение варианта (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="underwearvariantimage",
            name="image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_variant_gallery_upload_path,
                verbose_name="Изображение (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="islamicclothingproduct",
            name="main_video_file",
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_main_upload_path,
                verbose_name="Главное видео (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="islamicclothingproductimage",
            name="image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_gallery_upload_path,
                verbose_name="Изображение (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="islamicclothingvariant",
            name="main_image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_variant_main_upload_path,
                verbose_name="Главное изображение варианта (файл)",
            ),
        ),
        migrations.AlterField(
            model_name="islamicclothingvariantimage",
            name="image_file",
            field=models.ImageField(
                blank=True,
                max_length=500,
                null=True,
                upload_to=apps.catalog.utils.storage_paths.get_domain_variant_gallery_upload_path,
                verbose_name="Изображение (файл)",
            ),
        ),
    ]
