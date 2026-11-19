from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0242_thermoses_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeletedProductSlug',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(max_length=500, unique=True, verbose_name='Внешний ID')),
                ('slug', models.CharField(max_length=600, verbose_name='Адрес (slug)')),
                ('old_slugs', models.JSONField(blank=True, default=list, verbose_name='Прежние адреса')),
                ('created_at', models.DateTimeField(auto_now=True, verbose_name='Удалён')),
            ],
            options={
                'verbose_name': 'Адрес удалённого товара',
                'verbose_name_plural': 'Адреса удалённых товаров',
            },
        ),
    ]
