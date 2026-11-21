import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0246_markup_scale_choice"),
        ("marketing", "0002_cookieconsent"),
    ]

    operations = [
        migrations.CreateModel(
            name="TelegramChannelSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Пока выключено, по расписанию ничего не уходит. Кнопка «Опубликовать сейчас» работает всегда.",
                        verbose_name="Публикация по расписанию включена",
                    ),
                ),
                (
                    "channel_id",
                    models.CharField(
                        blank=True,
                        help_text="Имя канала с собачкой (@mudaroba) или числовой id (-1001234567890). Бот сайта должен быть администратором канала с правом публиковать сообщения.",
                        max_length=100,
                        verbose_name="Канал",
                    ),
                ),
                (
                    "publish_times",
                    models.CharField(
                        default="10:00, 14:00, 19:00",
                        help_text="Через запятую. Сколько времён — столько постов в день: в каждое время уходит один пост из очереди.",
                        max_length=200,
                        verbose_name="Время публикаций (по Москве)",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Telegram-канал: настройки",
                "verbose_name_plural": "Telegram-канал: настройки",
            },
        ),
        migrations.CreateModel(
            name="TelegramChannelPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "В очереди"),
                            ("sending", "Отправляется"),
                            ("published", "Опубликован"),
                            ("error", "Ошибка"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "position",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Меньше число — раньше уйдёт. При равных числах — кто раньше встал в очередь.",
                        verbose_name="Порядок",
                    ),
                ),
                (
                    "queued_at",
                    models.DateTimeField(default=django.utils.timezone.now, verbose_name="Поставлен в очередь"),
                ),
                ("published_at", models.DateTimeField(blank=True, null=True, verbose_name="Опубликован")),
                ("by_schedule", models.BooleanField(default=False, verbose_name="По расписанию")),
                ("message_id", models.BigIntegerField(blank=True, null=True, verbose_name="Номер сообщения")),
                ("post_url", models.URLField(blank=True, max_length=300, verbose_name="Ссылка на пост")),
                ("error", models.TextField(blank=True, verbose_name="Ошибка")),
                (
                    "product",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="telegram_channel_post",
                        to="catalog.product",
                        verbose_name="Товар",
                    ),
                ),
            ],
            options={
                "verbose_name": "Telegram-канал: пост",
                "verbose_name_plural": "Telegram-канал: очередь постов",
                "ordering": ("position", "queued_at", "id"),
            },
        ),
    ]
