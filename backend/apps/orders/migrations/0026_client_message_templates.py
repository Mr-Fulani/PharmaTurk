from django.db import migrations, models

# Русские тексты утверждены владельцем 26.11.2026; английские — перевод для заявок с английской версии сайта.
DELIVERY_RU = """Здравствуйте, {имя}! Это Mudaroba, по вашей заявке №{номер}.

{товары}

Товары: {сумма товаров}
Доставка из Стамбула (%(kind)s): {сумма доставки}
Итого: {итого}

Как всё проходит:
1. Мы выкупаем товар в Турции и отправляем из Стамбула в Москву или Махачкалу — туда, куда едет ближайший курьер.
2. Оттуда отправляем на ваш адрес: СДЭК, Ozon или другим удобным вам способом.
3. Доставку по России вы оплачиваете отдельно при получении — в сумму выше она не входит.

Сроки: %(terms)s

Если есть дополнительные вопросы — задавайте, с радостью отвечу. Если всё подходит — напишите, и я пришлю детали по оплате."""

DELIVERY_EN = """Hello, {имя}! This is Mudaroba, regarding your request No. {номер}.

{товары}

Items: {сумма товаров}
Delivery from Istanbul (%(kind)s): {сумма доставки}
Total: {итого}

How it works:
1. We buy the items in Turkey and send them from Istanbul to Moscow or Makhachkala — wherever the next courier is going.
2. From there we send the parcel to your address by CDEK, Ozon or another service convenient for you.
3. Delivery within Russia is paid separately on receipt — it is not included in the amount above.

Delivery time: %(terms)s

If you have any questions, just ask — I will be glad to help. If everything suits you, let me know and I will send the payment details."""

TEMPLATES = [
    (
        "air",
        DELIVERY_RU % {"kind": "авиа", "terms": "авиадоставка — от 3 до 14 дней."},
        DELIVERY_EN % {"kind": "air", "terms": "air delivery takes 3 to 14 days."},
    ),
    (
        "ground",
        DELIVERY_RU % {"kind": "наземная", "terms": "наземная доставка — от 14 до 21 дня."},
        DELIVERY_EN % {"kind": "ground", "terms": "ground delivery takes 14 to 21 days."},
    ),
    (
        "shipped",
        "Здравствуйте, {имя}! Ваш заказ №{номер} отправлен из Стамбула. Как только он прибудет в Россию и уйдёт "
        "на ваш адрес, пришлю трек-номер. Доставка по России оплачивается при получении. Если есть вопросы — пишите.",
        "Hello, {имя}! Your order No. {номер} has been sent from Istanbul. As soon as it arrives in Russia and is "
        "forwarded to your address, I will send you the tracking number. Delivery within Russia is paid on receipt. "
        "If you have any questions, just write.",
    ),
    (
        "review",
        "Здравствуйте, {имя}! Надеюсь, заказ №{номер} дошёл и всё в порядке. Будем очень благодарны за отзыв на "
        "сайте — это займёт минуту и помогает другим покупателям: {ссылка на отзывы}\n\nСпасибо, что выбрали Mudaroba!",
        "Hello, {имя}! I hope order No. {номер} has arrived and everything is fine. We would be very grateful for a "
        "review on our website — it takes a minute and helps other customers: {ссылка на отзывы}\n\n"
        "Thank you for choosing Mudaroba!",
    ),
]


def create_templates(apps, schema_editor):
    Template = apps.get_model("orders", "ClientMessageTemplate")
    for key, text_ru, text_en in TEMPLATES:
        Template.objects.get_or_create(key=key, defaults={"text_ru": text_ru, "text_en": text_en})


class Migration(migrations.Migration):
    """Готовые сообщения клиенту и их начальные тексты. Только база, без сети."""

    dependencies = [
        ('orders', '0025_orderprocessingevent_actor_label'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientMessageTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('air', 'Как проходит доставка — авиа'), ('ground', 'Как проходит доставка — наземная'), ('shipped', 'Заказ отправлен'), ('review', 'Просьба об отзыве')], max_length=16, unique=True, verbose_name='Сообщение')),
                ('text_ru', models.TextField(verbose_name='Текст по-русски')),
                ('text_en', models.TextField(blank=True, help_text='Для заявок, оформленных на английской версии сайта. Пусто — уйдёт русский текст.', verbose_name='Текст по-английски')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Дата обновления')),
            ],
            options={
                'verbose_name': '✉️ Готовое сообщение клиенту',
                'verbose_name_plural': '🛒 Заказы — Готовые сообщения клиенту',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(create_templates, migrations.RunPython.noop),
    ]
