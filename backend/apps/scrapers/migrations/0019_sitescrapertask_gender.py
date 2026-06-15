# Generated manually: add gender override to SiteScraperTask

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scrapers", "0018_alter_sitescrapertask_max_pages_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitescrapertask",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("men", "Мужской"),
                    ("women", "Женский"),
                    ("unisex", "Унисекс"),
                ],
                default="",
                help_text="Опционально. Проставит пол всем товарам задачи (для одежды/обуви/парфюмерии). Пусто — пол определяется автоматически.",
                max_length=10,
                verbose_name="Пол",
            ),
        ),
    ]
