from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_crypto_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="cryptopayment",
            name="invoice_code",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=128,
                verbose_name="Короткий ID инвойса",
            ),
        ),
    ]
