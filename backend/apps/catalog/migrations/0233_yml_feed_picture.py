from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0232_vk_category_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="YMLFeedPicture",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_key", models.CharField(max_length=64, unique=True, verbose_name="Хэш исходной ссылки")),
                ("file", models.FileField(blank=True, max_length=300, upload_to="feeds/pictures/", verbose_name="Копия")),
                ("checked_at", models.DateTimeField(auto_now_add=True, verbose_name="Проверено")),
            ],
            options={
                "verbose_name": "Фото YML-фида",
                "verbose_name_plural": "Фото YML-фидов",
            },
        ),
    ]
