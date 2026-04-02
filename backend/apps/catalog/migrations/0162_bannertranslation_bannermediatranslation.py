# Миграция: переводы текстов баннеров и слайдов

import django.db.models.deletion
from django.db import migrations, models


def copy_banner_texts_to_translations(apps, schema_editor):
    Banner = apps.get_model("catalog", "Banner")
    BannerMedia = apps.get_model("catalog", "BannerMedia")
    BannerTranslation = apps.get_model("catalog", "BannerTranslation")
    BannerMediaTranslation = apps.get_model("catalog", "BannerMediaTranslation")
    for loc in ("ru", "en"):
        for b in Banner.objects.all():
            BannerTranslation.objects.get_or_create(
                banner=b,
                locale=loc,
                defaults={
                    "title": b.title or "",
                    "description": b.description or "",
                    "link_text": b.link_text or "",
                },
            )
        for m in BannerMedia.objects.all():
            BannerMediaTranslation.objects.get_or_create(
                banner_media=m,
                locale=loc,
                defaults={
                    "title": m.title or "",
                    "description": m.description or "",
                    "link_text": m.link_text or "",
                },
            )


def noop_reverse(apps, schema_editor):
    BannerTranslation = apps.get_model("catalog", "BannerTranslation")
    BannerMediaTranslation = apps.get_model("catalog", "BannerMediaTranslation")
    BannerMediaTranslation.objects.all().delete()
    BannerTranslation.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0161_alter_headwearproduct_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BannerTranslation",
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
                    "locale",
                    models.CharField(
                        choices=[("ru", "Русский"), ("en", "Английский")],
                        db_index=True,
                        default="ru",
                        max_length=10,
                        verbose_name="Язык",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        blank=True,
                        help_text="Перевод заголовка баннера",
                        max_length=200,
                        verbose_name="Заголовок",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Перевод описания баннера",
                        verbose_name="Описание",
                    ),
                ),
                (
                    "link_text",
                    models.CharField(
                        blank=True,
                        help_text="Перевод текста кнопки",
                        max_length=100,
                        verbose_name="Текст кнопки",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Дата создания"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Дата обновления"),
                ),
                (
                    "banner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="catalog.banner",
                        verbose_name="Баннер",
                    ),
                ),
            ],
            options={
                "verbose_name": "Перевод баннера",
                "verbose_name_plural": "Переводы баннеров",
                "ordering": ["banner", "locale"],
                "indexes": [
                    models.Index(
                        fields=["banner", "locale"],
                        name="catalog_ban_banner__f3a1_idx",
                    )
                ],
                "unique_together": {("banner", "locale")},
            },
        ),
        migrations.CreateModel(
            name="BannerMediaTranslation",
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
                    "locale",
                    models.CharField(
                        choices=[("ru", "Русский"), ("en", "Английский")],
                        db_index=True,
                        default="ru",
                        max_length=10,
                        verbose_name="Язык",
                    ),
                ),
                (
                    "title",
                    models.CharField(blank=True, max_length=200, verbose_name="Заголовок"),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Описание"),
                ),
                (
                    "link_text",
                    models.CharField(
                        blank=True, max_length=100, verbose_name="Текст кнопки"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Дата создания"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Дата обновления"),
                ),
                (
                    "banner_media",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translations",
                        to="catalog.bannermedia",
                        verbose_name="Медиа баннера",
                    ),
                ),
            ],
            options={
                "verbose_name": "Перевод медиа баннера",
                "verbose_name_plural": "Переводы медиа баннеров",
                "ordering": ["banner_media", "locale"],
                "indexes": [
                    models.Index(
                        fields=["banner_media", "locale"],
                        name="catalog_ban_banner_m_8b2c_idx",
                    )
                ],
                "unique_together": {("banner_media", "locale")},
            },
        ),
        migrations.RunPython(copy_banner_texts_to_translations, noop_reverse),
    ]
