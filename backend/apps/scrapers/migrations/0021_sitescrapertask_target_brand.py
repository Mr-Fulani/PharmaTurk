from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0199_refresh_currency_margin_snapshots"),
        ("scrapers", "0020_sitescrapertask_resume_page_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitescrapertask",
            name="target_brand",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Опционально. Проставит бренд всем товарам этой задачи. "
                    "Имеет приоритет над брендом из конфигурации парсера и данными страницы."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="site_scraper_tasks",
                to="catalog.brand",
                verbose_name="Бренд",
            ),
        ),
    ]
