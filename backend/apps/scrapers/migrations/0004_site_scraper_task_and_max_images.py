from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0003_scraperconfig_scraper_password_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='scraperconfig',
            name='max_images_per_product',
            field=models.PositiveIntegerField(
                default=5,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)],
                verbose_name='Макс. медиа на товар'
            ),
        ),
        migrations.AddField(
            model_name='scrapingsession',
            name='max_images_per_product',
            field=models.PositiveIntegerField(
                default=5,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)],
                verbose_name='Макс. медиа на товар'
            ),
        ),
        migrations.CreateModel(
            name='SiteScraperTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_url', models.URLField(verbose_name='Начальный URL')),
                ('max_pages', models.PositiveIntegerField(default=10, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(1000)], verbose_name='Макс. страниц')),
                ('max_products', models.PositiveIntegerField(default=100, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10000)], verbose_name='Макс. товаров')),
                ('max_images_per_product', models.PositiveIntegerField(default=5, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(20)], verbose_name='Макс. медиа на товар')),
                ('status', models.CharField(choices=[('pending', 'Ожидает'), ('running', 'Выполняется'), ('completed', 'Завершено'), ('failed', 'Ошибка')], default='pending', max_length=20, verbose_name='Статус')),
                ('task_id', models.CharField(blank=True, max_length=100, verbose_name='ID задачи Celery')),
                ('products_found', models.PositiveIntegerField(default=0, verbose_name='Найдено товаров')),
                ('products_created', models.PositiveIntegerField(default=0, verbose_name='Создано товаров')),
                ('products_updated', models.PositiveIntegerField(default=0, verbose_name='Обновлено товаров')),
                ('products_skipped', models.PositiveIntegerField(default=0, verbose_name='Пропущено товаров')),
                ('pages_processed', models.PositiveIntegerField(default=0, verbose_name='Обработано страниц')),
                ('errors_count', models.PositiveIntegerField(default=0, verbose_name='Количество ошибок')),
                ('log_output', models.TextField(blank=True, verbose_name='Лог выполнения')),
                ('error_message', models.TextField(blank=True, verbose_name='Сообщение об ошибке')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('started_at', models.DateTimeField(blank=True, null=True, verbose_name='Начало выполнения')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='Завершено')),
                ('scraper_config', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='site_tasks', to='scrapers.scraperconfig', verbose_name='Конфигурация парсера')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='site_tasks', to='scrapers.scrapingsession', verbose_name='Сессия парсинга')),
            ],
            options={
                'verbose_name': 'Задача парсинга сайта',
                'verbose_name_plural': 'Задачи парсинга сайтов',
                'ordering': ['-created_at'],
            },
        ),
    ]
