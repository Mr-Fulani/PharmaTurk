"""TD-034: удаляет столбец scraper_password, оставленный в 0027 ради отката на старый образ."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0030_scraperconfig_is_multibrand'),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE scrapers_scraperconfig DROP COLUMN IF EXISTS scraper_password",
            reverse_sql=(
                "ALTER TABLE scrapers_scraperconfig "
                "ADD COLUMN IF NOT EXISTS scraper_password varchar(100) NOT NULL DEFAULT ''"
            ),
        ),
    ]
