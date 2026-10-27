from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0226_fix_non_antibiotics_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="YMLFeedSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "category_slug",
                    models.CharField(
                        blank=True,
                        help_text="Пусто — полный каталог.",
                        max_length=200,
                        unique=True,
                        verbose_name="Slug категории",
                    ),
                ),
                (
                    "file",
                    models.FileField(blank=True, max_length=300, upload_to="feeds/yml/", verbose_name="Файл фида"),
                ),
                ("generated_at", models.DateTimeField(blank=True, null=True, verbose_name="Собран")),
                ("offers_count", models.PositiveIntegerField(default=0, verbose_name="Офферов")),
                ("size_bytes", models.PositiveBigIntegerField(default=0, verbose_name="Размер, байт")),
            ],
            options={
                "verbose_name": "Готовый YML-фид",
                "verbose_name_plural": "Готовые YML-фиды",
                "ordering": ["category_slug"],
            },
        ),
    ]
