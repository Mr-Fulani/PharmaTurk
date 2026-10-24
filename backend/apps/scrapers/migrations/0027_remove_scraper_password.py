"""TD-016: пароль парсера больше не хранится.

Пароли стираются сразу, поле уходит из модели. Сам столбец (пустой, с DEFAULT '')
остаётся до следующего релиза: откат на предыдущий образ, который ещё читает
``scraper_password``, не сломается. Удалить столбец — отдельной миграцией позже.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0026_site_mode_and_instagram_profile'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='scraperconfig',
                    name='scraper_password',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=[
                        "UPDATE scrapers_scraperconfig SET scraper_password = ''",
                        "ALTER TABLE scrapers_scraperconfig "
                        "ALTER COLUMN scraper_password SET DEFAULT ''",
                    ],
                    reverse_sql=[
                        "ALTER TABLE scrapers_scraperconfig "
                        "ALTER COLUMN scraper_password DROP DEFAULT",
                    ],
                ),
            ],
        ),
        migrations.AlterField(
            model_name='scraperconfig',
            name='scraper_username',
            field=models.CharField(blank=True, help_text='Логин бот-аккаунта Instagram — только подпись сессии в логах. Вход — по cookie sessionid в поле «Cookies», пароль не нужен.', max_length=100, verbose_name='Логин парсера'),
        ),
    ]
