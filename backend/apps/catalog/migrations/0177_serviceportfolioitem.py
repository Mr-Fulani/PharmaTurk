from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import FileExtensionValidator

import apps.catalog.models
import apps.catalog.utils.storage_paths


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0176_update_service_media_helptexts_and_video_limits"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServicePortfolioItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Заголовок кейса")),
                ("description", models.TextField(blank=True, verbose_name="Описание кейса")),
                (
                    "result_summary",
                    models.CharField(
                        blank=True,
                        help_text="Короткий итог работы, например: Ремонт ванной за 12 дней.",
                        max_length=255,
                        verbose_name="Краткий результат",
                    ),
                ),
                ("city", models.CharField(blank=True, max_length=120, verbose_name="Город")),
                (
                    "image_file",
                    models.ImageField(
                        blank=True,
                        help_text="Фото выполненной работы. Можно загрузить файл или указать внешний URL.",
                        null=True,
                        upload_to=apps.catalog.utils.storage_paths.get_service_image_upload_path,
                        verbose_name="Изображение (файл)",
                    ),
                ),
                (
                    "image_url",
                    models.URLField(
                        blank=True,
                        help_text="Внешняя ссылка на фото выполненной работы.",
                        max_length=2000,
                        verbose_name="URL изображения",
                    ),
                ),
                (
                    "video_file",
                    models.FileField(
                        blank=True,
                        help_text="Видео выполненной работы. Поддерживаются MP4, MOV, WEBM, M4V, AVI, MKV до 100 МБ.",
                        null=True,
                        upload_to=apps.catalog.utils.storage_paths.get_service_image_upload_path,
                        validators=[
                            FileExtensionValidator(allowed_extensions=apps.catalog.models.SERVICE_VIDEO_ALLOWED_EXTENSIONS),
                            apps.catalog.models.validate_service_video_file_size,
                        ],
                        verbose_name="Видео (файл)",
                    ),
                ),
                (
                    "video_url",
                    models.URLField(
                        blank=True,
                        help_text="Внешняя ссылка на видео выполненной работы.",
                        max_length=2000,
                        verbose_name="URL видео",
                    ),
                ),
                ("alt_text", models.CharField(blank=True, max_length=255, verbose_name="Alt текст")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активно")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_portfolio_items",
                        to="catalog.category",
                        verbose_name="Категория услуг",
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="portfolio_items",
                        to="catalog.service",
                        verbose_name="Связанная услуга",
                    ),
                ),
            ],
            options={
                "verbose_name": "Кейс / работа услуги",
                "verbose_name_plural": "Кейсы / работы услуг",
                "ordering": ["sort_order", "-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="serviceportfolioitem",
            index=models.Index(fields=["category", "is_active"], name="catalog_ser_categor_34033f_idx"),
        ),
        migrations.AddIndex(
            model_name="serviceportfolioitem",
            index=models.Index(fields=["service", "is_active"], name="catalog_ser_service_eb8300_idx"),
        ),
    ]
