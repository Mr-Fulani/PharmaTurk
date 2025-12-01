# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_add_social_auth_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="whatsapp_phone",
            field=models.CharField(
                blank=True, max_length=17, verbose_name="WhatsApp"
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="telegram_username",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="Telegram"
            ),
        ),
    ]

