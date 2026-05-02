from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0178_serviceportfolioitem_before_after"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="alt_text_en",
            field=models.CharField(blank=True, max_length=255, verbose_name="Alt текст (EN)"),
        ),
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="description_en",
            field=models.TextField(blank=True, verbose_name="Описание кейса (EN)"),
        ),
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="result_summary_en",
            field=models.CharField(
                blank=True,
                help_text="Короткий итог работы на английском языке.",
                max_length=255,
                verbose_name="Краткий результат (EN)",
            ),
        ),
        migrations.AddField(
            model_name="serviceportfolioitem",
            name="title_en",
            field=models.CharField(blank=True, max_length=255, verbose_name="Заголовок кейса (EN)"),
        ),
    ]
