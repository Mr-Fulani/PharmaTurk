"""TD-023: флаги ``ai_on_create_enabled``/``ai_on_update_enabled`` никто не читает.

Поля уходят из модели. Сами столбцы остаются до следующего релиза с DEFAULT true:
новый код вставляет строки без них, а откат на предыдущий образ, который ещё
читает эти столбцы, не сломается (``rollback.sh`` миграции не откатывает).
Удалить столбцы — отдельной миграцией позже, как ``0031`` после ``0027``.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0031_drop_scraper_password_column'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='scraperconfig',
                    name='ai_on_create_enabled',
                ),
                migrations.RemoveField(
                    model_name='scraperconfig',
                    name='ai_on_update_enabled',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=[
                        "ALTER TABLE scrapers_scraperconfig "
                        "ALTER COLUMN ai_on_create_enabled SET DEFAULT true",
                        "ALTER TABLE scrapers_scraperconfig "
                        "ALTER COLUMN ai_on_update_enabled SET DEFAULT true",
                    ],
                    reverse_sql=[
                        "ALTER TABLE scrapers_scraperconfig "
                        "ALTER COLUMN ai_on_create_enabled DROP DEFAULT",
                        "ALTER TABLE scrapers_scraperconfig "
                        "ALTER COLUMN ai_on_update_enabled DROP DEFAULT",
                    ],
                ),
            ],
        ),
    ]
