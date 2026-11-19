import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Выбор шкалы наценки в глобальных настройках и у категории (по умолчанию пусто)."""

    dependencies = [
        ('catalog', '0245_markup_scale'),
    ]

    operations = [
        migrations.AddField(
            model_name='globalcurrencysettings',
            name='markup_scale',
            field=models.ForeignKey(
                blank=True,
                help_text='Если выбрана — вместо глобального процента наценка берётся из шкалы по цене источника. На лекарства и услуги не действует: для них остаётся глобальный процент. Бренд и категория со своим процентом или шкалой по-прежнему сильнее.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='catalog.markupscale',
                verbose_name='Шкала наценки по цене',
            ),
        ),
        migrations.AddField(
            model_name='category',
            name='markup_scale',
            field=models.ForeignKey(
                blank=True,
                help_text='Если выбрана — действует вместо процента категории и наследуется подкатегориями. Наценка бренда по-прежнему сильнее.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to='catalog.markupscale',
                verbose_name='Шкала наценки по цене',
            ),
        ),
    ]
