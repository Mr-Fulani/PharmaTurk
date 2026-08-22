from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0005_aiprocessinglog_application_tracking"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiprocessinglog",
            name="category_alternatives",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Топ-3 альтернативы с confidence score",
                verbose_name="Альтернативные категории",
            ),
        ),
    ]
