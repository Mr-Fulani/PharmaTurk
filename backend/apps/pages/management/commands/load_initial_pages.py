from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Load initial static pages: delivery, returns, privacy (with en/ru content)'

    def handle(self, *args, **options):
        from apps.pages.models import Page

        now = timezone.now()

        pages = [
            {
                'slug': 'delivery',
                'title_en': 'Delivery and Payment',
                'title_ru': 'Доставка и оплата',
                'content_en': (
                    '<div class="prose max-w-none">'
                    '<h2>Delivery</h2>'
                    '<p>We deliver orders to customers using trusted courier services. Delivery times depend on the destination and selected shipping method. Typical delivery times are 3–7 business days within the country and 7–21 business days for international orders.</p>'
                    '<h2>Payment</h2>'
                    '<p>We accept online payments via major credit cards and payment providers. For specific payment options available in your region, please check the checkout page.</p>'
                    '<h3>Shipping Costs</h3>'
                    '<p>Shipping costs are calculated at checkout based on weight, dimensions and destination. Free shipping promotions may apply.</p>'
                    '</div>'
                ),
                'content_ru': (
                    '<div class="prose max-w-none">'
                    '<h2>Доставка</h2>'
                    '<p>Мы доставляем заказы с помощью надёжных курьерских служб. Сроки доставки зависят от региона и выбранного способа доставки. Обычно это 3–7 рабочих дней по стране и 7–21 рабочий день для международных отправлений.</p>'
                    '<h2>Оплата</h2>'
                    '<p>Мы принимаем онлайн-платежи банковскими картами и через популярных платёжных провайдеров. Доступные способы оплаты зависят от вашей страны и указываются на странице оформления заказа.</p>'
                    '<h3>Стоимость доставки</h3>'
                    '<p>Стоимость доставки рассчитывается при оформлении заказа в зависимости от веса, габаритов и адреса. Могут действовать акции с бесплатной доставкой.</p>'
                    '</div>'
                ),
            },
            {
                'slug': 'returns',
                'title_en': 'Return Policy',
                'title_ru': 'Возврат товара',
                'content_en': (
                    '<div class="prose max-w-none">'
                    '<h2>Returns and Exchanges</h2>'
                    '<p>If you are not satisfied with your purchase, you may return the item within 14 days of receipt, subject to our return rules. Items must be in original condition and packaging.</p>'
                    '<h3>How to start a return</h3>'
                    '<p>Contact our support team with your order number and reason for return. We will provide instructions and a return authorization if the return is accepted.</p>'
                    '<h3>Refunds</h3>'
                    '<p>Refunds are processed to the original payment method after we receive and inspect the returned items. Processing typically takes 5–10 business days.</p>'
                    '</div>'
                ),
                'content_ru': (
                    '<div class="prose max-w-none">'
                    '<h2>Возврат и обмен</h2>'
                    '<p>Если вы не удовлетворены покупкой, вы можете вернуть товар в течение 14 дней с момента получения при соблюдении правил возврата. Товар должен быть в оригинальном состоянии и упаковке.</p>'
                    '<h3>Как оформить возврат</h3>'
                    '<p>Свяжитесь со службой поддержки, укажите номер заказа и причину возврата. Мы пришлём инструкции и авторизацию на возврат, если он возможен.</p>'
                    '<h3>Возврат денег</h3>'
                    '<p>Возврат средств осуществляется на тот же способ оплаты после получения и проверки товара. Обычно обработка занимает 5–10 рабочих дней.</p>'
                    '</div>'
                ),
            },
            {
                'slug': 'privacy',
                'title_en': 'Privacy Policy',
                'title_ru': 'Политика конфиденциальности',
                'content_en': (
                    '<div class="prose max-w-none">'
                    '<h2>Privacy Policy</h2>'
                    '<p>We value your privacy and handle your personal data in accordance with applicable laws. This page explains how we collect, use and protect your information.</p>'
                    '<h3>Information we collect</h3>'
                    '<p>We may collect contact information, order history and payment details necessary to process orders and provide customer service.</p>'
                    '<h3>How we use data</h3>'
                    '<p>Your data is used to process orders, send transactional emails, and improve our services. We do not sell personal data to third parties.</p>'
                    '<h3>Security</h3>'
                    '<p>We implement appropriate security measures to protect your data. For more details, contact support.</p>'
                    '</div>'
                ),
                'content_ru': (
                    '<div class="prose max-w-none">'
                    '<h2>Политика конфиденциальности</h2>'
                    '<p>Мы ценим вашу конфиденциальность и обрабатываем персональные данные в соответствии с действующим законодательством. На этой странице объясняется, какие данные мы собираем, как мы их используем и защищаем.</p>'
                    '<h3>Какие данные мы собираем</h3>'
                    '<p>Мы можем собирать контактную информацию, историю заказов и данные для оплаты, необходимые для обработки заказов и обслуживания клиентов.</p>'
                    '<h3>Как мы используем данные</h3>'
                    '<p>Ваши данные используются для обработки заказов, отправки служебных сообщений и улучшения сервиса. Мы не продаём персональные данные третьим лицам.</p>'
                    '<h3>Безопасность</h3>'
                    '<p>Мы внедряем соответствующие меры безопасности для защиты данных. Для деталей свяжитесь со службой поддержки.</p>'
                    '</div>'
                ),
            },
        ]

        for p in pages:
            obj, created = Page.objects.update_or_create(
                slug=p['slug'],
                defaults={
                    'title_en': p['title_en'],
                    'title_ru': p['title_ru'],
                    'content_en': p['content_en'],
                    'content_ru': p['content_ru'],
                    'is_active': True,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created page: {obj.slug}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated page: {obj.slug}"))

        self.stdout.write(self.style.SUCCESS('Initial pages loaded.'))
