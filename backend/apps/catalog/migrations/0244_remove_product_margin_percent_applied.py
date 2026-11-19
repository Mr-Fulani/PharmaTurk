from django.db import migrations, models


class Migration(migrations.Migration):
    """Убирает мёртвое поле товара «Применённая маржа, %»: его никто не читал и не писал."""

    dependencies = [
        ('catalog', '0243_deleted_product_slug'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='margin_percent_applied',
        ),
        migrations.AlterField(
            model_name='category',
            name='margin_percent',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Процент наценки для категории; перекрывается на уровне бренда',
                max_digits=5,
                verbose_name='Маржа, %',
            ),
        ),
    ]
