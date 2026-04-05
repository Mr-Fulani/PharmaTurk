import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0165_rename_catalog_ban_banner_m_8b2c_idx_catalog_ban_banner__0b3ee2_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="globalcurrencysettings",
            name="default_air_shipping_usd",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Пустое поле на товаре/варианте — подставляется это значение. 0 на карточке — явная бесплатная доставка.",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Дефолт: авиадоставка (USD)",
            ),
        ),
        migrations.AddField(
            model_name="globalcurrencysettings",
            name="default_sea_shipping_usd",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Аналогично авиадоставке.",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Дефолт: морская доставка (USD)",
            ),
        ),
        migrations.AddField(
            model_name="globalcurrencysettings",
            name="default_ground_shipping_usd",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Пустое поле на товаре/варианте — подставляется это значение.",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Дефолт: наземная доставка (USD)",
            ),
        ),
        migrations.AddField(
            model_name="globalcurrencysettings",
            name="free_shipping_min_subtotal_usd",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Субтотал корзины без доставки. Пусто — правило отключено. При достижении порога все способы доставки в ответе API обнуляются.",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Бесплатная доставка от суммы заказа (USD)",
            ),
        ),
    ]
