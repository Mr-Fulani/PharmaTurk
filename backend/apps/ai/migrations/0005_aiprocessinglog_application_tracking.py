# Generated manually for the backwards-compatible AI moderation workflow.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0004_alter_aiprocessinglog_image_analysis_and_more"),
    ]

    operations = [
        # Existing approved/moderation rows cannot be classified reliably: the
        # old admin action could change status without applying anything, while
        # auto-apply could partially update a moderation row. Mark historical
        # records as unknown and use not_applied as the default for new logs.
        migrations.AddField(
            model_name="aiprocessinglog",
            name="application_status",
            field=models.CharField(
                choices=[
                    ("unknown", "Неизвестно (старый лог)"),
                    ("not_applied", "Не применено"),
                    ("partial", "Применено частично"),
                    ("applied", "Применено"),
                    ("failed", "Ошибка применения"),
                ],
                db_index=True,
                default="unknown",
                max_length=20,
                verbose_name="Применение к товару",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="aiprocessinglog",
            name="application_status",
            field=models.CharField(
                choices=[
                    ("unknown", "Неизвестно (старый лог)"),
                    ("not_applied", "Не применено"),
                    ("partial", "Применено частично"),
                    ("applied", "Применено"),
                    ("failed", "Ошибка применения"),
                ],
                db_index=True,
                default="not_applied",
                max_length=20,
                verbose_name="Применение к товару",
            ),
        ),
        migrations.AddField(
            model_name="aiprocessinglog",
            name="application_report",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Итог применения: изменён ли товар, отклонённые поля и причины.",
                verbose_name="Отчёт применения",
            ),
        ),
        migrations.AddField(
            model_name="aiprocessinglog",
            name="applied_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Дата применения",
            ),
        ),
    ]
