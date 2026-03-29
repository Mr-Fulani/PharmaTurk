from django.db import models


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
