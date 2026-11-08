# Разметка старых заявок отдельной миграцией (своя транзакция): в 0020 UPDATE заказов перед
# отложенным CREATE INDEX падал на проде с «pending trigger events» (08.11.2026, релиз откатился).

from datetime import timedelta

from django.db import migrations
from django.utils import timezone

# Заявки старше недели на момент выкатки считаем уже обработанными, иначе весь архив стал бы «Новой».
# Только база: без сети и R2 (у migrate на проде нет интернета).
OPEN_WINDOW = timedelta(days=7)


def mark_existing_orders(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    Order.objects.filter(status='cancelled').update(processing_status='cancelled')
    Order.objects.filter(status__in=('shipped', 'delivered')).update(processing_status='done')
    # Свежие, с которыми менеджер уже работал по клиентскому статусу
    Order.objects.filter(status__in=('pending_payment', 'paid', 'processing')).update(processing_status='in_progress')
    Order.objects.exclude(status='cancelled').filter(created_at__lt=timezone.now() - OPEN_WINDOW).update(
        processing_status='done'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0020_order_processing'),
    ]

    operations = [
        migrations.RunPython(mark_existing_orders, migrations.RunPython.noop),
    ]
