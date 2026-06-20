from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import apps.feedback.models


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0009_alter_testimonialsectionsettings_show_on_homepage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_type", models.CharField(db_index=True, max_length=64, verbose_name="Тип товара/услуги")),
                ("product_slug", models.SlugField(db_index=True, max_length=600, verbose_name="Slug родительской карточки")),
                ("product_name", models.CharField(max_length=500, verbose_name="Название товара/услуги")),
                ("author_name", models.CharField(max_length=150, verbose_name="Имя автора")),
                ("rating", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)], verbose_name="Оценка")),
                ("text", models.TextField(verbose_name="Текст отзыва")),
                ("status", models.CharField(choices=[("pending", "Ожидает модерации"), ("approved", "Опубликован"), ("rejected", "Отклонён")], db_index=True, default="pending", max_length=16, verbose_name="Статус")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменён")),
                ("published_at", models.DateTimeField(blank=True, null=True, verbose_name="Опубликован")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_reviews", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={"verbose_name": "⭐ Отзыв о товаре/услуге", "verbose_name_plural": "⭐ Отзывы — Товары и услуги", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ProductReviewMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("media_type", models.CharField(choices=[("image", "Изображение"), ("video", "Видео")], max_length=10, verbose_name="Тип")),
                ("file", models.FileField(max_length=1000, upload_to=apps.feedback.models.get_product_review_media_upload_path, verbose_name="Файл")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("review", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="media", to="feedback.productreview", verbose_name="Отзыв")),
            ],
            options={"verbose_name": "⭐ Медиа отзыва о товаре/услуге", "verbose_name_plural": "⭐ Отзывы — Медиа товаров и услуг", "ordering": ("order", "id")},
        ),
        migrations.AddConstraint(
            model_name="productreview",
            constraint=models.UniqueConstraint(fields=("user", "product_type", "product_slug"), name="unique_product_review_per_user"),
        ),
        migrations.AddIndex(
            model_name="productreview",
            index=models.Index(fields=["product_type", "product_slug", "status"], name="feedback_pr_target_idx"),
        ),
    ]
