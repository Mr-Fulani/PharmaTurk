import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0006_alter_aiprocessinglog_category_alternatives"),
    ]

    operations = [
        migrations.CreateModel(
            name="AITranslationMemory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("namespace", models.CharField(max_length=50, verbose_name="Пространство")),
                ("source_hash", models.CharField(max_length=64, verbose_name="Хэш источника")),
                ("ru_text", models.TextField(blank=True, default="", verbose_name="Текст RU")),
                ("en_text", models.TextField(blank=True, default="", verbose_name="Текст EN")),
                ("hits", models.PositiveIntegerField(default=0, verbose_name="Повторных использований")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "source_log",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ai.aiprocessinglog",
                        verbose_name="Исходный AI-лог",
                    ),
                ),
            ],
            options={
                "verbose_name": "Память переводов AI",
                "verbose_name_plural": "Память переводов AI",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("namespace", "source_hash"), name="ai_translation_memory_unique_source"
                    )
                ],
            },
        ),
    ]
