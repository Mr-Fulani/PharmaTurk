"""Флаг «Мультибрендовый магазин»: бренд со страницы товара вместо бренда настроек.

FLO и akakce продают товары разных брендов — флаг включается у них сразу.
"""

from django.db import migrations, models

MULTIBRAND_PARSERS = ("flo", "akakce")


def enable_multibrand(apps, schema_editor):
    ScraperConfig = apps.get_model("scrapers", "ScraperConfig")
    for parser in MULTIBRAND_PARSERS:
        ScraperConfig.objects.filter(parser_class__iexact=parser).update(is_multibrand=True)


class Migration(migrations.Migration):

    dependencies = [
        ('scrapers', '0029_listing_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='scraperconfig',
            name='is_multibrand',
            field=models.BooleanField(default=False, help_text='Включите для магазинов с товарами разных брендов (FLO, akakce): бренд берётся со страницы каждого товара, а «Бренд по умолчанию» — только если на странице его нет. Выключено — «Бренд по умолчанию» ставится всем товарам.', verbose_name='Мультибрендовый магазин'),
        ),
        migrations.AlterField(
            model_name='scraperconfig',
            name='default_brand',
            field=models.ForeignKey(blank=True, help_text='Для магазина одного бренда (IKEA, LC Waikiki): ставится всем товарам и приоритетнее бренда со страницы. У мультибрендового магазина — только запасной, если на странице товара бренда нет.', null=True, on_delete=models.deletion.SET_NULL, to='catalog.brand', verbose_name='Бренд по умолчанию'),
        ),
        migrations.RunPython(enable_multibrand, migrations.RunPython.noop),
    ]
