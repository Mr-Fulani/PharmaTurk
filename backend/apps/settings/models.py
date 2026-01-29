"""Модели для настроек сайта."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class FooterSettings(models.Model):
    """Настройки футера сайта (singleton - только одна запись)."""
    
    # Контакты
    phone = models.CharField(_("Телефон"), max_length=50, blank=True, default="+90 552 582 14 97")
    email = models.EmailField(_("Email"), blank=True, default="fulani.dev@gmail.com")
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

