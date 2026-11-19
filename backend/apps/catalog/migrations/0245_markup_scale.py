import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0244_remove_product_margin_percent_applied'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarkupScale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Название')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
            ],
            options={
                'verbose_name': '💰 Шкала наценки',
                'verbose_name_plural': '💰 Наценки — Шкалы по цене',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='MarkupScaleStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price_from', models.DecimalField(decimal_places=2, help_text='Цена источника в лирах до наценок. Первая ступень начинается с 0.', max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name='От, лир')),
                ('percent', models.DecimalField(decimal_places=2, max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(500)], verbose_name='Наценка, %')),
                ('scale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='steps', to='catalog.markupscale', verbose_name='Шкала')),
            ],
            options={
                'verbose_name': 'ступень шкалы',
                'verbose_name_plural': 'ступени шкалы',
                'ordering': ['price_from'],
                'unique_together': {('scale', 'price_from')},
            },
        ),
    ]
