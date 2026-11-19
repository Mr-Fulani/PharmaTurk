from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0007_seed_benefits_block'),
    ]

    operations = [
        migrations.AlterField(
            model_name='footersettings',
            name='crypto_payment_text',
            field=models.CharField(blank=True, default='Оплата — по согласованию с менеджером, возможна криптовалютой. Относится к товарам, кроме лекарств: сведения о лекарствах — справочные.', max_length=200, verbose_name='Текст про оплату криптовалютой'),
        ),
        migrations.AlterField(
            model_name='homeblock',
            name='key',
            field=models.CharField(choices=[('main_banner', 'Баннер 1 — главный, вверху страницы'), ('benefits', 'Строка преимуществ — заявка, доставка, поиск по ссылке, возврат'), ('brands', 'Популярные бренды'), ('banner_after_brands', 'Баннер 2 — после брендов'), ('categories', 'Категории товаров'), ('banner_before_footer', 'Баннер 3 — после категорий'), ('bestsellers', 'Хиты продаж'), ('medicine_reference', '«Часто ищут в справочнике лекарств» — лекарства с галочкой «Рекомендуемый»'), ('sourcing', '«Найдём любой товар» — заявка по ссылке или фото'), ('recommendations', '«Вам может понравиться» — по просмотрам покупателя'), ('banner_after_popular', 'Баннер 4 — после хитов'), ('testimonials', 'Отзывы покупателей'), ('facts', '«Как работает Mudaroba» — текст для поисковиков')], max_length=40, unique=True, verbose_name='Блок'),
        ),
    ]
