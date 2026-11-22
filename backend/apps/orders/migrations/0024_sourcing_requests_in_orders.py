import django.db.models.deletion
from django.db import migrations, models

REASON_CHOICES = [
    ('no_reply', 'Клиент не ответил'),
    ('expensive', 'Дорого'),
    ('slow', 'Долго'),
    ('out_of_stock', 'Нет в наличии'),
    ('not_found', 'Не нашли товар'),
    ('cannot_deliver', 'Не можем доставить (страна, ограничение на ввоз, рецепт)'),
    ('changed_mind', 'Передумал'),
    ('spam', 'Спам или тест'),
]


class Migration(migrations.Migration):
    """Заявки «Найдём товар» ведутся в общем списке «Заказы»: тип заявки, связь с заявкой на поиск
    и причина «Не нашли товар». Только схема: существующие записи не меняются (все заказы — «Из Списка»,
    у старых заявок на поиск пары нет)."""

    dependencies = [
        ('orders', '0023_order_processing_stages'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='kind',
            field=models.CharField(choices=[('cart', 'Из Списка'), ('sourcing', '🔎 Найти товар')], db_index=True, default='cart', max_length=16, verbose_name='Тип заявки'),
        ),
        migrations.AddField(
            model_name='sourcingrequest',
            name='order',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sourcing_request', to='orders.order', verbose_name='Заявка в «Заказах»'),
        ),
        migrations.AlterField(
            model_name='order',
            name='processing_fail_reason',
            field=models.CharField(blank=True, choices=REASON_CHOICES, default='', help_text='Только для отметки «Не состоялась»; при другой отметке очищается. Клиент не видит.', max_length=16, verbose_name='Почему не состоялась'),
        ),
        migrations.AlterField(
            model_name='orderprocessingevent',
            name='new_reason',
            field=models.CharField(blank=True, choices=REASON_CHOICES, default='', max_length=16, verbose_name='Стала причина'),
        ),
        migrations.AlterField(
            model_name='orderprocessingevent',
            name='old_reason',
            field=models.CharField(blank=True, choices=REASON_CHOICES, default='', max_length=16, verbose_name='Была причина'),
        ),
    ]
