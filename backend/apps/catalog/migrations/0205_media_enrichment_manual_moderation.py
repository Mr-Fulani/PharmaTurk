import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.catalog.utils.storage_paths


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0204_quarantine_ilacfiyati_fake_stock"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicineproduct",
            name="media_enrichment_status",
            field=models.CharField(
                choices=[
                    ("pending", "В очереди"),
                    ("processing", "Обработка"),
                    ("moderation", "На модерации"),
                    ("completed", "Завершено"),
                    ("failed", "Ошибка"),
                ],
                default="pending",
                max_length=20,
                verbose_name="Статус медиа",
            ),
        ),
        migrations.AlterField(
            model_name="supplementproduct",
            name="media_enrichment_status",
            field=models.CharField(
                choices=[
                    ("pending", "В очереди"),
                    ("processing", "Обработка"),
                    ("moderation", "На модерации"),
                    ("completed", "Завершено"),
                    ("failed", "Ошибка"),
                ],
                default="pending",
                max_length=20,
                verbose_name="Статус медиа",
            ),
        ),
        migrations.CreateModel(
            name="MediaEnrichmentCandidate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "candidate_key",
                    models.CharField(
                        editable=False,
                        max_length=64,
                        unique=True,
                        verbose_name="Ключ кандидата",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        verbose_name="Источник поиска",
                    ),
                ),
                (
                    "source_host",
                    models.CharField(
                        blank=True,
                        max_length=253,
                        verbose_name="Домен изображения",
                    ),
                ),
                (
                    "source_url",
                    models.URLField(
                        max_length=2000,
                        verbose_name="Исходный URL изображения",
                    ),
                ),
                (
                    "search_query",
                    models.CharField(
                        blank=True,
                        max_length=1000,
                        verbose_name="Поисковый запрос",
                    ),
                ),
                (
                    "image_file",
                    models.ImageField(
                        max_length=500,
                        upload_to=apps.catalog.utils.storage_paths.get_media_enrichment_candidate_upload_path,
                        verbose_name="Файл-кандидат",
                    ),
                ),
                (
                    "content_hash",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        verbose_name="SHA-256 файла",
                    ),
                ),
                (
                    "image_hash",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=64,
                        null=True,
                        verbose_name="Перцептивный хэш",
                    ),
                ),
                ("width", models.PositiveIntegerField(verbose_name="Ширина")),
                ("height", models.PositiveIntegerField(verbose_name="Высота")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Ожидает модерации"),
                            ("approved", "Одобрено"),
                            ("rejected", "Отклонено"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="Статус модерации",
                    ),
                ),
                (
                    "moderation_note",
                    models.TextField(blank=True, verbose_name="Комментарий модератора"),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Дата модерации",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                (
                    "medicine_product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media_enrichment_candidates",
                        to="catalog.medicineproduct",
                        verbose_name="Препарат",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requested_media_enrichment_candidates",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Инициатор поиска",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_media_enrichment_candidates",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Модератор",
                    ),
                ),
                (
                    "supplement_product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media_enrichment_candidates",
                        to="catalog.supplementproduct",
                        verbose_name="БАД",
                    ),
                ),
            ],
            options={
                "verbose_name": "Кандидат изображения",
                "verbose_name_plural": "Модерация изображений",
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["status", "created_at"],
                        name="catalog_mec_status_created_idx",
                    ),
                    models.Index(
                        fields=["medicine_product", "status"],
                        name="catalog_mec_med_status_idx",
                    ),
                    models.Index(
                        fields=["supplement_product", "status"],
                        name="catalog_mec_sup_status_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                medicine_product__isnull=False,
                                supplement_product__isnull=True,
                            )
                            | models.Q(
                                medicine_product__isnull=True,
                                supplement_product__isnull=False,
                            )
                        ),
                        name="catalog_media_candidate_one_product",
                    ),
                ],
            },
        ),
    ]
