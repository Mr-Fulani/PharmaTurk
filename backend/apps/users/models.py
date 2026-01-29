from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator


class User(AbstractUser):
    """
    Расширенная модель пользователя с дополнительными полями
    """
    # Основная информация
    email = models.EmailField(_('email address'), unique=True)
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message=_("Номер телефона должен быть в формате: '+999999999'. До 15 цифр.")
    )
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    
    # Дополнительные поля
    birth_date = models.DateField(_('дата рождения'), null=True, blank=True)
    is_verified = models.BooleanField(_('подтвержден'), default=False)
    verification_code = models.CharField(_('код подтверждения'), max_length=6, blank=True)
    verification_code_expires = models.DateTimeField(_('срок действия кода'), null=True, blank=True)
    middle_name = models.CharField(_('отчество'), max_length=150, blank=True)
    country = models.CharField(_('страна'), max_length=100, blank=True)
    city = models.CharField(_('город'), max_length=100, blank=True)
    postal_code = models.CharField(_('почтовый индекс'), max_length=20, blank=True)
    address = models.TextField(_('адрес'), blank=True)
    avatar = models.ImageField(_('аватар'), upload_to='avatars/', null=True, blank=True)
    bio = models.TextField(_('о себе'), blank=True)
    whatsapp_phone = models.CharField(_('WhatsApp'), max_length=17, blank=True)
    
    # Настройки уведомлений
    email_notifications = models.BooleanField(_('email уведомления'), default=True)
    telegram_notifications = models.BooleanField(_('telegram уведомления'), default=False)
    push_notifications = models.BooleanField(_('push уведомления'), default=True)
    
    # Telegram
    telegram_id = models.CharField(_('telegram ID'), max_length=50, blank=True)
    telegram_username = models.CharField(_('Telegram'), max_length=50, blank=True)
    
    # Социальные сети (для будущей интеграции)
    # Поля для хранения ID пользователей в соцсетях
    google_id = models.CharField(_('Google ID'), max_length=100, blank=True, null=True, unique=True)
    facebook_id = models.CharField(_('Facebook ID'), max_length=100, blank=True, null=True, unique=True)
    vk_id = models.CharField(_('VK ID'), max_length=100, blank=True, null=True, unique=True)
    yandex_id = models.CharField(_('Yandex ID'), max_length=100, blank=True, null=True, unique=True)
    apple_id = models.CharField(_('Apple ID'), max_length=100, blank=True, null=True, unique=True)
    
    # Метаданные
    created_at = models.DateTimeField(_('дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('дата обновления'), auto_now=True)
    last_login_ip = models.GenericIPAddressField(_('последний IP входа'), null=True, blank=True)
    is_public_profile = models.BooleanField(_('публичный профиль'), default=False)
    show_email = models.BooleanField(_('показывать email'), default=False)
    show_phone = models.BooleanField(_('показывать телефон'), default=False)
    
    # Язык и валюта
    language = models.CharField(_('язык'), max_length=10, choices=[
        ('en', 'English'),
        ('ru', 'Русский'),
        ('tr', 'Türkçe'),
    ], default='en')
    currency = models.CharField(_('валюта'), max_length=3, choices=[
        ('USD', 'Доллар США'),
        ('RUB', 'Рубль'),
        ('EUR', 'Евро'),
        ('TRY', 'Турецкая лира'),
        ('KZT', 'Казахстанский тенге'),
    ], default='USD')
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        verbose_name = _('👥 пользователь')
        verbose_name_plural = _('👥 Пользователи — Пользователи')
        db_table = 'users'
        
    def __str__(self):
        return self.email or self.username


class UserAddress(models.Model):
    """
    Адреса пользователя для доставки
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    
    # Тип адреса
    ADDRESS_TYPES = [
        ('home', 'Дом'),
        ('work', 'Работа'),
        ('other', 'Другое'),
    ]
    address_type = models.CharField(_('тип адреса'), max_length=10, choices=ADDRESS_TYPES, default='home')
    
    # Контактная информация
    contact_name = models.CharField(_('имя получателя'), max_length=150)
    contact_phone = models.CharField(_('телефон получателя'), max_length=17)
    
    # Адрес
    country = models.CharField(_('страна'), max_length=100)
    region = models.CharField(_('область/регион'), max_length=100, blank=True)
    city = models.CharField(_('город'), max_length=100)
    postal_code = models.CharField(_('почтовый индекс'), max_length=20, blank=True)
    street = models.CharField(_('улица'), max_length=200)
    house = models.CharField(_('дом'), max_length=20)
    apartment = models.CharField(_('квартира'), max_length=20, blank=True)
    
    # Дополнительная информация
    entrance = models.CharField(_('подъезд'), max_length=10, blank=True)
    floor = models.CharField(_('этаж'), max_length=10, blank=True)
    intercom = models.CharField(_('домофон'), max_length=20, blank=True)
    comment = models.TextField(_('комментарий'), blank=True)
    
    # Настройки
    is_default = models.BooleanField(_('адрес по умолчанию'), default=False)
    is_active = models.BooleanField(_('активен'), default=True)
    
    # Метаданные
    created_at = models.DateTimeField(_('дата создания'), auto_now_add=True)
    updated_at = models.DateTimeField(_('дата обновления'), auto_now=True)
    
    class Meta:
        verbose_name = _('👥 адрес пользователя')
        verbose_name_plural = _('👥 Пользователи — Адреса пользователей')
        db_table = 'user_addresses'
        ordering = ['-is_default', '-created_at']
        
    def __str__(self):
        return f"{self.contact_name} - {self.city}, {self.street}, {self.house}"


class UserSession(models.Model):
    """
    Сессии пользователей для отслеживания активности
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    
    # Информация о сессии
    session_key = models.CharField(_('ключ сессии'), max_length=40, unique=True)
    ip_address = models.GenericIPAddressField(_('IP адрес'))
    user_agent = models.TextField(_('user agent'), blank=True)
    
    # Геолокация
    country = models.CharField(_('страна'), max_length=100, blank=True)
    city = models.CharField(_('город'), max_length=100, blank=True)
    
    # Статус
    is_active = models.BooleanField(_('активна'), default=True)
    
    # Временные метки
    created_at = models.DateTimeField(_('дата создания'), auto_now_add=True)
    last_activity = models.DateTimeField(_('последняя активность'), auto_now=True)
    expires_at = models.DateTimeField(_('истекает'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('👥 сессия пользователя')
        verbose_name_plural = _('👥 Пользователи — Сессии пользователей')
        db_table = 'user_sessions'
        ordering = ['-last_activity']
        
    def __str__(self):
        return f"Сессия {self.user.email} - {self.ip_address}"
