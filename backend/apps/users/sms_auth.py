"""
Модуль для авторизации через SMS.

Структура для будущей реализации:
- Отправка SMS кодов
- Верификация кодов
- Автоматическая регистрация при первом входе
"""
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
import secrets
import string


def generate_sms_code(length=6):
    """Генерация случайного SMS кода"""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


class SMSVerificationCode(models.Model):
    """
    Модель для хранения SMS кодов верификации.
    
    TODO: Создать миграцию после реализации функционала.
    """
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message=_("Номер телефона должен быть в формате: '+999999999'. До 15 цифр.")
    )
    
    phone_number = models.CharField(
        _('номер телефона'),
        max_length=17,
        validators=[phone_regex],
        db_index=True
    )
    code = models.CharField(_('код'), max_length=6)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    expires_at = models.DateTimeField(_('истекает'))
    verified = models.BooleanField(_('подтвержден'), default=False)
    verified_at = models.DateTimeField(_('подтвержден в'), null=True, blank=True)
    attempts = models.PositiveIntegerField(_('попытки'), default=0)
    max_attempts = models.PositiveIntegerField(_('максимум попыток'), default=3)
    
    class Meta:
        verbose_name = _('SMS код верификации')
        verbose_name_plural = _('SMS коды верификации')
        db_table = 'sms_verification_codes'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone_number', 'verified']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.phone_number} - {self.code} ({'✓' if self.verified else '✗'})"
    
    def is_valid(self):
        """Проверка валидности кода"""
        if self.verified:
            return False
        if self.attempts >= self.max_attempts:
            return False
        if timezone.now() > self.expires_at:
            return False
        return True
    
    def verify(self, code: str) -> bool:
        """
        Проверка кода.
        
        Args:
            code: Введенный код
            
        Returns:
            True если код верный, False иначе
        """
        if not self.is_valid():
            return False
        
        self.attempts += 1
        
        if self.code == code:
            self.verified = True
            self.verified_at = timezone.now()
            self.save()
            return True
        
        self.save()
        return False


# TODO: Реализовать функции для работы с SMS
# 
# def send_sms_code(phone_number: str) -> SMSVerificationCode:
#     """
#     Отправка SMS кода на номер телефона.
#     
#     Args:
#         phone_number: Номер телефона
#         
#     Returns:
#         SMSVerificationCode объект
#     """
#     from datetime import timedelta
#     
#     # Генерируем код
#     code = generate_sms_code()
#     
#     # Создаем запись
#     verification = SMSVerificationCode.objects.create(
#         phone_number=phone_number,
#         code=code,
#         expires_at=timezone.now() + timedelta(minutes=5)  # Код действителен 5 минут
#     )
#     
#     # TODO: Интеграция с SMS провайдером (SMS.ru, Twilio, и т.д.)
#     # send_sms_via_provider(phone_number, f"Ваш код: {code}")
#     
#     return verification
#
#
# def verify_sms_code(phone_number: str, code: str) -> tuple[bool, SMSVerificationCode | None]:
#     """
#     Проверка SMS кода.
#     
#     Args:
#         phone_number: Номер телефона
#         code: Код из SMS
#         
#     Returns:
#         Tuple (успех, объект кода)
#     """
#     verification = SMSVerificationCode.objects.filter(
#         phone_number=phone_number,
#         verified=False
#     ).order_by('-created_at').first()
#     
#     if not verification:
#         return False, None
#     
#     if verification.verify(code):
#         return True, verification
#     
#     return False, verification

