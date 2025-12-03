from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_add_whatsapp_telegram_to_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="middle_name",
            field=models.CharField(blank=True, max_length=150, verbose_name="отчество"),
        ),
        migrations.AddField(
            model_name="user",
            name="country",
            field=models.CharField(blank=True, max_length=100, verbose_name="страна"),
        ),
        migrations.AddField(
            model_name="user",
            name="city",
            field=models.CharField(blank=True, max_length=100, verbose_name="город"),
        ),
        migrations.AddField(
            model_name="user",
            name="postal_code",
            field=models.CharField(blank=True, max_length=20, verbose_name="почтовый индекс"),
        ),
        migrations.AddField(
            model_name="user",
            name="address",
            field=models.TextField(blank=True, verbose_name="адрес"),
        ),
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.ImageField(blank=True, null=True, upload_to="avatars/", verbose_name="аватар"),
        ),
        migrations.AddField(
            model_name="user",
            name="bio",
            field=models.TextField(blank=True, verbose_name="о себе"),
        ),
        migrations.AddField(
            model_name="user",
            name="whatsapp_phone",
            field=models.CharField(blank=True, max_length=17, verbose_name="WhatsApp"),
        ),
        migrations.AddField(
            model_name="user",
            name="is_public_profile",
            field=models.BooleanField(default=False, verbose_name="публичный профиль"),
        ),
        migrations.AddField(
            model_name="user",
            name="show_email",
            field=models.BooleanField(default=False, verbose_name="показывать email"),
        ),
        migrations.AddField(
            model_name="user",
            name="show_phone",
            field=models.BooleanField(default=False, verbose_name="показывать телефон"),
        ),
    ]

