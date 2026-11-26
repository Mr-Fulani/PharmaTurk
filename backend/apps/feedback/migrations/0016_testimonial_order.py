import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0015_testimonialsectionsettings_allow_guest_testimonials"),
        ("orders", "0027_order_review_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="testimonial",
            name="order",
            field=models.ForeignKey(
                blank=True,
                help_text="Заполняется, когда отзыв пришёл по личной ссылке из заявки; на сайте у такого отзыва отметка «Покупатель».",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="testimonials",
                to="orders.order",
                verbose_name="Заявка покупателя",
            ),
        ),
    ]
