from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0014_feedback_translations"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="testimonialsectionsettings",
            options={
                "verbose_name": "💬 Настройки отзывов",
                "verbose_name_plural": "💬 Отзывы — Настройки",
            },
        ),
        migrations.AddField(
            model_name="testimonialsectionsettings",
            name="allow_guest_testimonials",
            field=models.BooleanField(
                default=True,
                help_text="Если выключить, оставить отзыв смогут только вошедшие в аккаунт. Гостевой отзыв в любом случае появляется на сайте только после галочки «Активен».",
                verbose_name="Принимать отзывы без входа в аккаунт",
            ),
        ),
    ]
