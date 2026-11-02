from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0233_yml_feed_picture"),
    ]

    operations = [
        migrations.CreateModel(
            name="IndexNowUrlState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=700, unique=True, verbose_name="Путь")),
                (
                    "fingerprint",
                    models.CharField(
                        blank=True,
                        help_text="MD5 названия, описания, наличия и переводов RU/EN; цена не входит.",
                        max_length=32,
                        verbose_name="Отпечаток",
                    ),
                ),
                ("is_public", models.BooleanField(default=True, verbose_name="На витрине")),
                (
                    "submitted_at",
                    models.DateTimeField(
                        blank=True,
                        db_index=True,
                        help_text="Пусто — страница записана при первом запуске и ещё не отправлялась.",
                        null=True,
                        verbose_name="Отправлено в IndexNow",
                    ),
                ),
            ],
            options={
                "verbose_name": "Страница в IndexNow",
                "verbose_name_plural": "Страницы в IndexNow",
            },
        ),
    ]
