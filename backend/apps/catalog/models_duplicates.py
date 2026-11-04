"""Одинаковые товары разных продавцов (FLO ↔ SuperStep). Устройство — docs/CROSS_SOURCE_DUPLICATES.md.

Хранится отдельно от основного models.py, как models_stock.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class CrossSourceDuplicate(models.Model):
    """Цвет товара, скрытый с сайта как дубль того же цвета у другого продавца.

    Строка есть — цвет скрыт этим механизмом (``is_active=False`` у варианта), а
    не снят по другой причине. Удаляется, когда цвет снова показывается.
    """

    class Match(models.TextChoices):
        EAN = "ean", _("Штрихкод производителя")
        ARTICLE = "article", _("Бренд + артикул")

    class Reason(models.TextChoices):
        PRICE = "price", _("Показан более дорогой")
        STOCK = "stock", _("У более дорогого нет размеров в наличии")

    product_type = models.CharField(_("Тип товара"), max_length=30)
    hidden_variant_id = models.PositiveBigIntegerField(_("Скрытый цвет (ID варианта)"))
    shown_variant_id = models.PositiveBigIntegerField(_("Показанный цвет (ID варианта)"), null=True, blank=True)
    hidden_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="hidden_duplicate_rows",
        verbose_name=_("Скрытый товар"),
    )
    # SET_NULL, а не CASCADE: удалили показанный товар — строка остаётся, и
    # следующий пересчёт снова покажет скрытый цвет.
    shown_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shown_duplicate_rows",
        verbose_name=_("Показан вместо него"),
    )
    match = models.CharField(_("Как узнали"), max_length=20, choices=Match.choices)
    reason = models.CharField(_("Почему показан другой"), max_length=20, choices=Reason.choices)
    hidden_price = models.DecimalField(_("Цена скрытого на сайте, лиры"), max_digits=10, decimal_places=2, null=True, blank=True)
    shown_price = models.DecimalField(_("Цена показанного на сайте, лиры"), max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(_("Валюта"), max_length=5, blank=True)
    product_hidden = models.BooleanField(
        _("Скрыта вся карточка"),
        default=False,
        help_text=_("Все цвета товара оказались дублями — товар снят с сайта, его адрес ведёт на показанный."),
    )
    created_at = models.DateTimeField(_("Скрыт"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Проверено"), auto_now=True)

    class Meta:
        verbose_name = _("Дубль у другого продавца")
        verbose_name_plural = _("Дубли у других продавцов")
        constraints = [
            models.UniqueConstraint(
                fields=["product_type", "hidden_variant_id"],
                name="uniq_cross_source_duplicate_variant",
            ),
        ]
        indexes = [models.Index(fields=["product_type", "shown_variant_id"], name="cross_dup_shown_variant_idx")]

    def __str__(self) -> str:
        return f"{self.product_type} #{self.hidden_variant_id} → #{self.shown_variant_id}"
