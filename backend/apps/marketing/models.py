from django.db import models
from django.utils import timezone


class CookieConsent(models.Model):
    """
    Фиксирует согласие/отказ пользователя от аналитических cookie.
    Используется для GDPR/KVKK аудита.
    """

    session_id = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="Идентификатор сессии",
    )
    consent_given = models.BooleanField(
        verbose_name="Согласие дано",
        help_text="True — пользователь принял все cookie, False — только необходимые.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес",
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name="User-Agent",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата и время",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Согласие на cookie"
        verbose_name_plural = "Согласия на cookie"
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        status = "принято" if self.consent_given else "отклонено"
        return f"Cookie {status} | {self.ip_address} | {self.created_at:%Y-%m-%d %H:%M}"


def parse_publish_times(value: str) -> list:
    """«10:00, 14:00» → [time(10, 0), time(14, 0)]; ошибка формата — ValueError."""
    from datetime import time

    result = []
    for part in (value or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        hours, _sep, minutes = part.partition(":")
        result.append(time(int(hours), int(minutes or 0)))
    return sorted(set(result))


class TelegramChannelSettings(models.Model):
    """Telegram-канал с карточками товаров — одна запись, правится в админке (docs/TELEGRAM_CHANNEL.md)."""

    enabled = models.BooleanField(
        "Публикация по расписанию включена",
        default=False,
        help_text="Пока выключено, по расписанию ничего не уходит. Кнопка «Опубликовать сейчас» работает всегда.",
    )
    channel_id = models.CharField(
        "Канал",
        max_length=100,
        blank=True,
        help_text="Имя канала с собачкой (@mudaroba) или числовой id (-1001234567890). "
        "Бот сайта должен быть администратором канала с правом публиковать сообщения.",
    )
    publish_times = models.CharField(
        "Время публикаций (по Москве)",
        max_length=200,
        default="10:00, 14:00, 19:00",
        help_text="Через запятую. Сколько времён — столько постов в день: в каждое время уходит один пост из очереди.",
    )
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Telegram-канал: настройки"
        verbose_name_plural = "Telegram-канал: настройки"

    def __str__(self):
        return "Настройки Telegram-канала"

    def clean(self):
        from django.core.exceptions import ValidationError

        try:
            parse_publish_times(self.publish_times)
        except ValueError:
            raise ValidationError({"publish_times": "Время пишется так: 10:00, 14:00, 19:00"}) from None

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class TelegramChannelPost(models.Model):
    """Товар в очереди Telegram-канала. Одна строка на товар: опубликованный уходит повторно,
    только когда его вернули в очередь вручную."""

    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        SENDING = "sending", "Отправляется"
        PUBLISHED = "published", "Опубликован"
        ERROR = "error", "Ошибка"

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="telegram_channel_post",
        verbose_name="Товар",
    )
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    position = models.PositiveIntegerField(
        "Порядок", default=0, help_text="Меньше число — раньше уйдёт. При равных числах — кто раньше встал в очередь."
    )
    queued_at = models.DateTimeField("Поставлен в очередь", default=timezone.now)
    published_at = models.DateTimeField("Опубликован", null=True, blank=True)
    by_schedule = models.BooleanField("По расписанию", default=False)
    message_id = models.BigIntegerField("Номер сообщения", null=True, blank=True)
    post_url = models.URLField("Ссылка на пост", max_length=300, blank=True)
    error = models.TextField("Ошибка", blank=True)

    class Meta:
        ordering = ("position", "queued_at", "id")
        verbose_name = "Telegram-канал: пост"
        verbose_name_plural = "Telegram-канал: очередь постов"

    def __str__(self):
        return f"{self.product} — {self.get_status_display()}"
