"""
Кастомные бэкенды аутентификации для поддержки входа по username, email и телефону.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _


User = get_user_model()


class MultiFieldAuthBackend(ModelBackend):
    """
    Бэкенд аутентификации, поддерживающий вход по:
    - email
    - username
    - phone_number (в будущем)
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Аутентификация пользователя по email, username или телефону.
        
        Args:
            request: HTTP запрос
            username: может быть email, username или phone_number
            password: пароль пользователя
            
        Returns:
            User объект или None
        """
        if username is None or password is None:
            return None
        
        user = None
        
        # Определяем тип входа по формату
        # 1. Проверяем, является ли это email
        try:
            validate_email(username)
            # Это email - ищем по email
            try:
                user = User.objects.get(email__iexact=username)
            except User.DoesNotExist:
                return None
        except ValidationError:
            # Не email - проверяем username или телефон
            # 2. Проверяем, является ли это телефоном
            # Нормализуем номер телефона (убираем пробелы, дефисы, скобки и т.д.)
            cleaned_username = username.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('.', '')
            
            # Проверяем, похоже ли на телефон (начинается с + или только цифры)
            is_phone = cleaned_username.startswith('+') or cleaned_username.isdigit()
            
            if is_phone:
                # Это похоже на телефон - ищем по телефону
                # Пробуем разные варианты формата
                phone_variants = [
                    cleaned_username,  # Как введено
                    f'+{cleaned_username}' if not cleaned_username.startswith('+') else cleaned_username,  # С +
                    cleaned_username.lstrip('+'),  # Без +
                ]
                
                for phone_variant in phone_variants:
                    try:
                        user = User.objects.get(phone_number=phone_variant)
                        break
                    except User.DoesNotExist:
                        continue
                else:
                    # Не нашли по телефону - пробуем поиск по частичному совпадению
                    # (на случай, если номер хранится в другом формате)
                    try:
                        user = User.objects.filter(phone_number__icontains=cleaned_username.lstrip('+')).first()
                    except Exception:
                        user = None
            else:
                # Это username
                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    return None
        
        # Проверяем пароль
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        
        return None
    
    def get_user(self, user_id):
        """
        Получение пользователя по ID.
        """
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None

