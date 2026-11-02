"""Что последний раз отправлено в IndexNow (Bing, Яндекс). Устройство — docs/INDEXNOW.md."""
from django.db import models
from django.utils.translation import gettext_lazy as _


class IndexNowUrlState(models.Model):
    """Страница товара, как её видела последняя отправка: отпечаток значимых полей."""

    path = models.CharField(_("Путь"), max_length=700, unique=True)
    fingerprint = models.CharField(
        _("Отпечаток"),
        max_length=32,
        blank=True,
        help_text=_("MD5 названия, описания, наличия и переводов RU/EN; цена не входит."),
    )
    is_public = models.BooleanField(_("На витрине"), default=True)
    submitted_at = models.DateTimeField(
        _("Отправлено в IndexNow"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Пусто — страница записана при первом запуске и ещё не отправлялась."),
    )

    class Meta:
        verbose_name = _("Страница в IndexNow")
        verbose_name_plural = _("Страницы в IndexNow")

    def __str__(self) -> str:
        return self.path
