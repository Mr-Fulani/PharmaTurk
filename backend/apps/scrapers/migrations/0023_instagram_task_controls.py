# Generated manually: asynchronous Instagram task controls and live progress.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0022_analog_processing_stats"),
    ]

    operations = [
        migrations.AlterField(
            model_name="instagramscrapertask",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Ожидает"),
                    ("running", "Выполняется"),
                    ("paused", "На паузе"),
                    ("cancelled", "Остановлено"),
                    ("completed", "Завершено"),
                    ("failed", "Ошибка"),
                ],
                default="pending",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.AddField(
            model_name="instagramscrapertask",
            name="task_id",
            field=models.CharField(blank=True, max_length=100, verbose_name="ID задачи Celery"),
        ),
        migrations.AddField(
            model_name="instagramscrapertask",
            name="run_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text="Технический идентификатор для безопасного продолжения задачи без повторного сохранения постов.",
                verbose_name="ID запуска",
            ),
        ),
        migrations.AddField(
            model_name="instagramscrapertask",
            name="session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="instagram_tasks",
                to="scrapers.scrapingsession",
                verbose_name="Сессия парсинга",
            ),
        ),
        migrations.AddField(
            model_name="instagramscrapertask",
            name="posts_processed",
            field=models.PositiveIntegerField(default=0, verbose_name="Обработано постов"),
        ),
        migrations.AddField(
            model_name="instagramscrapertask",
            name="products_found",
            field=models.PositiveIntegerField(default=0, verbose_name="Найдено товаров"),
        ),
        migrations.AddField(
            model_name="instagramscrapertask",
            name="errors_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Количество ошибок"),
        ),
    ]
