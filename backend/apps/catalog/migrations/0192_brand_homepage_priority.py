from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0191_alter_serviceportfolioitem_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="brand",
            name="show_on_homepage",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Если включено, бренд получает ручной приоритет в блоке популярных брендов на главной.",
                verbose_name="Показывать на главной",
            ),
        ),
        migrations.AddField(
            model_name="brand",
            name="homepage_priority",
            field=models.PositiveIntegerField(
                db_index=True,
                default=100,
                help_text="Меньшее число показывается выше. Работает только если включено «Показывать на главной».",
                verbose_name="Приоритет на главной",
            ),
        ),
    ]
