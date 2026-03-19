from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    dependencies = [
        ("scrapers", "0004_site_scraper_task_and_max_images"),
    ]

    operations = [
        migrations.AddField(
            model_name="scraperconfig",
            name="ai_on_create_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name=_("AI для новых товаров"),
            ),
        ),
        migrations.AddField(
            model_name="scraperconfig",
            name="ai_on_update_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name=_("AI для обновлений товаров"),
            ),
        ),
    ]
