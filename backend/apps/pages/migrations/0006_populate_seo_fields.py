from django.db import migrations


def populate_seo_fields(apps, schema_editor):
    Page = apps.get_model('pages', 'Page')

    seo_data = {
        'about-us': {
            'meta_title_ru': 'О нас — Mudaroba | Товары из Турции',
            'meta_title_en': 'About Us — Mudaroba | Turkish Goods Export',
            'meta_description_ru': 'Mudaroba — сервис заказа товаров из Турции. Лекарства, БАДы, медицинские товары, одежда, электроника и многое другое. Доставляем по всей России и СНГ.',
            'meta_description_en': 'Mudaroba — a service for ordering goods from Turkey. Medicines, supplements, medical products, clothing, electronics and more. Delivery across Russia and CIS.',
        },
        'delivery': {
            'meta_title_ru': 'Доставка и оплата — Mudaroba',
            'meta_title_en': 'Delivery & Payment — Mudaroba',
            'meta_description_ru': 'Условия доставки и оплаты заказов из Турции. Международная доставка по России и СНГ. Банковский перевод, криптовалюта и другие способы оплаты.',
            'meta_description_en': 'Delivery and payment terms for orders from Turkey. International delivery to Russia and CIS. Bank transfer, cryptocurrency and other payment methods.',
        },
        'returns': {
            'meta_title_ru': 'Возврат товара — Mudaroba',
            'meta_title_en': 'Returns — Mudaroba',
            'meta_description_ru': 'Условия возврата и обмена товаров, заказанных через Mudaroba. Мы гарантируем качество каждого заказа и готовы решить любой вопрос.',
            'meta_description_en': 'Terms for returns and exchanges of goods ordered through Mudaroba. We guarantee the quality of every order.',
        },
        'privacy': {
            'meta_title_ru': 'Политика конфиденциальности — Mudaroba',
            'meta_title_en': 'Privacy Policy — Mudaroba',
            'meta_description_ru': 'Политика конфиденциальности Mudaroba. Мы защищаем ваши персональные данные и не передаём их третьим лицам.',
            'meta_description_en': 'Mudaroba Privacy Policy. We protect your personal data and do not share it with third parties.',
        },
    }

    for slug, fields in seo_data.items():
        Page.objects.filter(slug=slug).update(**fields)


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0005_page_meta_description_en_page_meta_description_ru_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_seo_fields, migrations.RunPython.noop),
    ]
