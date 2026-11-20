from django.db import migrations, models

PROCESSING_CHOICES = [
    ('new', 'Новая'),
    ('in_progress', 'В работе'),
    ('waiting_client', 'Написали клиенту — ждём ответа'),
    ('price_sent', 'Назвали цену — ждём решения'),
    ('agreed', 'Клиент согласен — ждём оплату'),
    ('paid', 'Оплачено — закупаем'),
    ('shipped', 'Отправлено'),
    ('done', 'Завершена'),
    ('cancelled', 'Не состоялась'),
]
REASON_CHOICES = [
    ('no_reply', 'Клиент не ответил'),
    ('expensive', 'Дорого'),
    ('slow', 'Долго'),
    ('out_of_stock', 'Нет в наличии'),
    ('cannot_deliver', 'Не можем доставить (страна, ограничение на ввоз, рецепт)'),
    ('changed_mind', 'Передумал'),
    ('spam', 'Спам или тест'),
]


class Migration(migrations.Migration):
    """Шаги обработки заявки и причина «Не состоялась». Только схема: значения в базе не меняются
    (старые «Обработана» и «Отменена» — те же done и cancelled с новыми подписями), причина пустая."""

    dependencies = [
        ('orders', '0022_order_locale'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='processing_fail_reason',
            field=models.CharField(blank=True, choices=REASON_CHOICES, default='', help_text='Только для отметки «Не состоялась»; при другой отметке очищается. Клиент не видит.', max_length=16, verbose_name='Почему не состоялась'),
        ),
        migrations.AddField(
            model_name='orderprocessingevent',
            name='new_reason',
            field=models.CharField(blank=True, choices=REASON_CHOICES, default='', max_length=16, verbose_name='Стала причина'),
        ),
        migrations.AddField(
            model_name='orderprocessingevent',
            name='old_reason',
            field=models.CharField(blank=True, choices=REASON_CHOICES, default='', max_length=16, verbose_name='Была причина'),
        ),
        migrations.AlterField(
            model_name='order',
            name='processing_status',
            field=models.CharField(choices=PROCESSING_CHOICES, db_index=True, default='new', help_text='Для менеджеров: клиент эту отметку не видит и сообщений о ней не получает.', max_length=16, verbose_name='Обработка'),
        ),
        migrations.AlterField(
            model_name='orderprocessingevent',
            name='new_status',
            field=models.CharField(choices=PROCESSING_CHOICES, max_length=16, verbose_name='Стало'),
        ),
        migrations.AlterField(
            model_name='orderprocessingevent',
            name='old_status',
            field=models.CharField(choices=PROCESSING_CHOICES, max_length=16, verbose_name='Было'),
        ),
    ]
