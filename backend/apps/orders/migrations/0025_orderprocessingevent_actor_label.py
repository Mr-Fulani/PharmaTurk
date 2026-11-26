from django.db import migrations, models


class Migration(migrations.Migration):
    """Кто нажал кнопку под уведомлением о заявке в Telegram. Только схема, без сети."""

    dependencies = [
        ('orders', '0024_sourcing_requests_in_orders'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderprocessingevent',
            name='actor_label',
            field=models.CharField(blank=True, default='', max_length=150, verbose_name='Кто изменил (Telegram)'),
        ),
    ]
