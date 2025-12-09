from django.db import migrations, models
from django.core.exceptions import ValidationError
import django.core.validators


CARD_MEDIA_ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm"]
CARD_MEDIA_MAX_SIZE_MB = 50


def validate_card_media_file_size(value):
    """Проверяет, что размер медиа-файла карточки не превышает допустимый лимит."""
    max_bytes = CARD_MEDIA_MAX_SIZE_MB * 1024 * 1024
    if value.size > max_bytes:
        raise ValidationError(
            "Размер файла превышает %(size)s МБ",
            params={"size": CARD_MEDIA_MAX_SIZE_MB},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0030_rename_catalog_clothin_vari_492d2c_idx_catalog_clo_variant_080b88_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="brand",
            name="card_media",
            field=models.FileField(
                blank=True,
                help_text="Изображение, GIF или видео для карточки бренда (до 50 МБ).",
                null=True,
                upload_to="marketing/cards/brands/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=CARD_MEDIA_ALLOWED_EXTENSIONS
                    ),
                    validate_card_media_file_size,
                ],
                verbose_name="Медиа для карточки",
            ),
        ),
        migrations.AddField(
            model_name="category",
            name="card_media",
            field=models.FileField(
                blank=True,
                help_text="Изображение, GIF или видео для карточки категории (до 50 МБ).",
                null=True,
                upload_to="marketing/cards/categories/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=CARD_MEDIA_ALLOWED_EXTENSIONS
                    ),
                    validate_card_media_file_size,
                ],
                verbose_name="Медиа для карточки",
            ),
        ),
    ]

