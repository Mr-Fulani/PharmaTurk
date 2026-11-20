from django.db import migrations, models


class Migration(migrations.Migration):
    """Язык оформления заявки. Только схема: старые заявки остаются с пустым значением (русский)."""

    dependencies = [
        ('orders', '0021_mark_existing_orders_processing'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='locale',
            field=models.CharField(blank=True, default='', max_length=8, verbose_name='Язык оформления'),
        ),
    ]
