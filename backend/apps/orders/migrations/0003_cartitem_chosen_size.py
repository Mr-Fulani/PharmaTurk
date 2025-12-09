from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_promocode_cart_promo_code_order_promo_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="chosen_size",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="Выбранный размер"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="chosen_size",
            field=models.CharField(blank=True, default="", max_length=50, verbose_name="Выбранный размер"),
        ),
        migrations.AlterUniqueTogether(
            name="cartitem",
            unique_together={("cart", "product", "chosen_size")},
        ),
    ]

