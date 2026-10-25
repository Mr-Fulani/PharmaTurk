"""Режим «Только изменения» IlacFiyati: тип задачи и снимки строк листинга."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0027_remove_scraper_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitescrapertask',
            name='task_type',
            field=models.CharField(choices=[('catalog', 'Товар или категория по ссылке'), ('site', 'Весь сайт (все категории)'), ('changes', 'Только изменения (IlacFiyati)'), ('stub_refresh', 'Обновление заглушек')], default='catalog', max_length=20, verbose_name='Тип задачи'),
        ),
        migrations.CreateModel(
            name='SourceListingRow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('parser_key', models.CharField(max_length=50, verbose_name='Парсер')),
                ('url', models.CharField(max_length=500, verbose_name='Ссылка товара')),
                ('fingerprint', models.CharField(blank=True, max_length=64, verbose_name='Отпечаток строки')),
                ('source_status', models.CharField(blank=True, max_length=20, verbose_name='Статус у источника')),
                ('run_token', models.UUIDField(blank=True, null=True, verbose_name='ID прохода')),
                ('seen_at', models.DateTimeField(auto_now=True, verbose_name='Видели')),
            ],
            options={
                'verbose_name': 'Строка листинга источника',
                'verbose_name_plural': 'Строки листинга источника',
                'constraints': [models.UniqueConstraint(fields=('parser_key', 'url'), name='scrapers_listing_row_parser_url_uniq')],
            },
        ),
    ]
