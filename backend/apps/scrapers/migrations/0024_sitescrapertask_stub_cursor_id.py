from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scrapers", "0023_instagram_task_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitescrapertask",
            name="stub_cursor_id",
            field=models.PositiveBigIntegerField(
                default=0,
                editable=False,
                help_text=(
                    "Последний полностью обработанный MedicineProduct в режиме обновления "
                    "заглушек. Используется только для безопасного продолжения фоновой задачи."
                ),
                verbose_name="ID заглушки для продолжения",
            ),
        ),
    ]
