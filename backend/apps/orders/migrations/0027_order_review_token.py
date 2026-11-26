from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0026_client_message_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="review_token",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="Создаётся, когда менеджер берёт сообщение «Просьба об отзыве».",
                max_length=43,
                null=True,
                unique=True,
                verbose_name="Ключ личной ссылки на отзыв",
            ),
        ),
    ]
