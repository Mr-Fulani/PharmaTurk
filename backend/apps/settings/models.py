"""Модели для настроек сайта."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def _default_footer_email() -> str:
    return (getattr(settings, "EMAIL_API_FROM", "") or getattr(settings, "COMPANY_SUPPORT_EMAIL", "") or getattr(settings, "DEFAULT_FROM_EMAIL", "")).strip()


class FooterSettings(models.Model):
    """Настройки футера сайта (singleton - только одна запись)."""
    
    # Контакты
    phone = models.CharField(_("Телефон"), max_length=50, blank=True, default="+90 552 582 14 97")
    email = models.EmailField(_("Email"), blank=True, default=_default_footer_email)
    location = models.CharField(_("Адрес"), max_length=200, blank=True, default="Стамбул, Турция")
    
    # Социальные сети
    telegram_url = models.URLField(_("Ссылка на Telegram"), blank=True)
    whatsapp_url = models.URLField(_("Ссылка на WhatsApp"), blank=True)
    vk_url = models.URLField(_("Ссылка на VK"), blank=True)
    instagram_url = models.URLField(_("Ссылка на Instagram"), blank=True)
    
    # Дополнительная информация
    crypto_payment_text = models.CharField(
        _("Текст про оплату криптовалютой"), 
        max_length=200, 
        blank=True,
        default="Возможна оплата криптовалютой"
    )
    
    # Метаданные
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)
    
    class Meta:
        verbose_name = _("📄 Настройки футера")
        verbose_name_plural = _("📄 Контент — Настройки футера")
    
    def __str__(self):
        return "Настройки футера"
    
    def save(self, *args, **kwargs):
        """Обеспечиваем, что существует только одна запись."""
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        """Загружает или создает единственную запись настроек."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class SiteAppearance(models.Model):
    """Оформление сайта (singleton): тема, которую видят все посетители."""

    class Theme(models.TextChoices):
        CREAM = "cream", _("Кремовая — прежний вид")
        IZNIK = "iznik", _("Изник — белый и синий")
        GREEN = "green", _("Зелёная аптека")

    theme = models.CharField(
        _("Тема оформления"),
        max_length=20,
        choices=Theme.choices,
        default=Theme.CREAM,
        help_text=_("Меняет цвета и шрифты всего сайта; блоки и их порядок остаются прежними."),
    )
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("🎨 Тема оформления")
        verbose_name_plural = _("🎨 Оформление — Тема сайта")

    def __str__(self):
        return "Тема оформления"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class HomeBlock(models.Model):
    """Блок главной страницы: показывать ли его и на каком месте.

    Набор блоков задан кодом (Key) и заводится миграцией данных; в админке
    меняются только «Показывать» и «Порядок». Содержимое блока (баннеры,
    карточки брендов, отзывы) настраивается там же, где и раньше.
    """

    class Key(models.TextChoices):
        MAIN_BANNER = "main_banner", _("Баннер 1 — главный, вверху страницы")
        BENEFITS = "benefits", _("Строка преимуществ — заявка, доставка, поиск по ссылке, возврат")
        BRANDS = "brands", _("Популярные бренды")
        BANNER_AFTER_BRANDS = "banner_after_brands", _("Баннер 2 — после брендов")
        CATEGORIES = "categories", _("Категории товаров")
        BANNER_BEFORE_FOOTER = "banner_before_footer", _("Баннер 3 — после категорий")
        BESTSELLERS = "bestsellers", _("Хиты продаж")
        SOURCING = "sourcing", _("«Найдём любой товар» — заявка по ссылке или фото")
        RECOMMENDATIONS = "recommendations", _("«Вам может понравиться» — по просмотрам покупателя")
        BANNER_AFTER_POPULAR = "banner_after_popular", _("Баннер 4 — после хитов")
        TESTIMONIALS = "testimonials", _("Отзывы покупателей")
        FACTS = "facts", _("«Как работает Mudaroba» — текст для поисковиков")

    key = models.CharField(_("Блок"), max_length=40, choices=Key.choices, unique=True)
    is_enabled = models.BooleanField(_("Показывать"), default=True)
    sort_order = models.PositiveSmallIntegerField(
        _("Порядок"), default=0, help_text=_("Блоки идут сверху вниз по возрастанию числа.")
    )

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = _("🏠 Блок главной")
        verbose_name_plural = _("🏠 Главная — Блоки (показ и порядок)")

    def __str__(self):
        return self.get_key_display()

    @classmethod
    def is_shown(cls, key: str) -> bool:
        """Включён ли блок. Блок без записи считается включённым."""
        enabled = cls.objects.filter(key=key).values_list("is_enabled", flat=True).first()
        return True if enabled is None else enabled
