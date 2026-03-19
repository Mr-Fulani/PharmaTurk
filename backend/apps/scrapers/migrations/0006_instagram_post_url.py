# Generated manually for Instagram post_url and optional username

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0005_scraperconfig_ai_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="instagramscrapertask",
            name="post_url",
            field=models.URLField(
                blank=True,
                help_text="Опционально: URL конкретного поста для парсинга одного поста (например: https://www.instagram.com/p/ABC123/). Если задан, парсится только этот пост; иначе — профиль по username.",
                max_length=500,
                null=True,
                verbose_name="Ссылка на пост",
            ),
        ),
        migrations.AlterField(
            model_name="instagramscrapertask",
            name="instagram_username",
            field=models.CharField(
                blank=True,
                help_text="Введите username без @ (например: book.warrior). Не нужен, если указана ссылка на пост.",
                max_length=100,
                verbose_name="Instagram username",
            ),
        ),
    ]
