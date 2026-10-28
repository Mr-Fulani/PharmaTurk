"""Ночная сверка наличия у продавцов и товары, пропавшие у продавца.

Хранится отдельно от основного models.py, как models_vk. Устройство —
docs/NIGHTLY_STOCK_CHECK.md.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

SOURCE_TITLES = {"lcw": "LC Waikiki", "ikea": "IKEA", "ummaland": "UmmaLand"}


class StockCheckSourceState(models.Model):
    """Состояние ночной сверки одного источника: где остановились и итог ночи."""

    parser_key = models.CharField(_("Источник"), max_length=50, unique=True)
    cursor_pk = models.BigIntegerField(
        _("Последний проверенный товар"),
        default=0,
        help_text=_("Следующая ночь продолжит с товара после этого ID."),
    )
    night = models.DateField(_("Ночь"), null=True, blank=True)
    stats = models.JSONField(_("Итог ночи"), default=dict, blank=True)
    catalog_size = models.PositiveIntegerField(_("Товаров к сверке"), default=0)
    last_full_cycle_at = models.DateTimeField(_("Весь каталог проверен"), null=True, blank=True)
    paused_reason = models.TextField(
        _("Пауза"),
        blank=True,
        help_text=_("Сверка источника остановлена предохранителем. Очистите поле, чтобы продолжить."),
    )
    paused_at = models.DateTimeField(_("Пауза с"), null=True, blank=True)
    reported_night = models.DateField(_("Отчёт отправлен за ночь"), null=True, blank=True)
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Ночная сверка наличия")
        verbose_name_plural = _("Ночная сверка наличия")
        ordering = ["parser_key"]

    def __str__(self):
        return self.parser_key


class StaleProductCandidate(models.Model):
    """Товар, которого больше нет у продавца (страница пропала).

    Отмечает ночная сверка; снова найденный у продавца товар перестаёт быть
    кандидатом. Удаляется только по решению владельца в админке.
    """

    class Status(models.TextChoices):
        CANDIDATE = "candidate", _("Нет у продавца")
        HIDDEN = "hidden", _("Скрыт с сайта")
        RETURNED = "returned", _("Снова есть у продавца")
        DISMISSED = "dismissed", _("Оставить, не удалять")

    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="stale_candidate",
        verbose_name=_("Товар"),
    )
    parser_key = models.CharField(_("Источник"), max_length=50, db_index=True)
    source_url = models.URLField(_("Ссылка у продавца"), max_length=2000)
    reason = models.CharField(_("Причина"), max_length=50, default="not_found")
    status = models.CharField(
        _("Статус"), max_length=20, choices=Status.choices, default=Status.CANDIDATE, db_index=True
    )
    first_seen_at = models.DateTimeField(_("Нет у продавца с"))
    last_gone_at = models.DateTimeField(_("Последняя проверка: нет"))
    gone_checks = models.PositiveIntegerField(_("Проверок подряд: нет"), default=1)
    hidden_at = models.DateTimeField(_("Скрыт с сайта"), null=True, blank=True)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Кто изменил статус"),
    )
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Неактуальный товар")
        verbose_name_plural = _("Неактуальные товары")
        ordering = ["first_seen_at"]

    def __str__(self):
        return f"{self.parser_key}: {self.product_id}"
