from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0018_cart_reminders'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sourcingrequest',
            name='contact_phone',
            field=models.CharField(blank=True, max_length=32, verbose_name='Телефон'),
        ),
    ]
