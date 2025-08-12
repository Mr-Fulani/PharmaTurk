from django.utils import translation
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings


class LanguageMiddleware(MiddlewareMixin):
    """
    Middleware для определения языка из заголовков запроса
    Поддерживает заголовки Accept-Language и X-Language для мобильных приложений
    """
    
    def process_request(self, request):
        """Определение языка из заголовков"""
        # Приоритет определения языка:
        # 1. Заголовок X-Language (для мобильных приложений)
        # 2. Accept-Language (стандартный браузерный заголовок)
        # 3. Язык пользователя (если аутентифицирован)
        # 4. Язык по умолчанию из настроек
        
        language = None
        
        # Проверяем заголовок X-Language (для мобильных приложений)
        x_language = request.META.get('HTTP_X_LANGUAGE')
        if x_language and x_language in dict(settings.LANGUAGES):
            language = x_language
        
        # Проверяем Accept-Language
        if not language:
            accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
            if accept_language:
                # Парсим Accept-Language заголовок
                for lang_code in accept_language.split(','):
                    lang_code = lang_code.split(';')[0].strip()
                    # Проверяем полный код языка
                    if lang_code in dict(settings.LANGUAGES):
                        language = lang_code
                        break
                    # Проверяем код языка без региона
                    lang_code_short = lang_code.split('-')[0]
                    if lang_code_short in dict(settings.LANGUAGES):
                        language = lang_code_short
                        break
        
        # Проверяем язык пользователя (если аутентифицирован)
        if not language and hasattr(request, 'user') and request.user.is_authenticated:
            if request.user.language in dict(settings.LANGUAGES):
                language = request.user.language
        
        # Используем язык по умолчанию
        if not language:
            language = settings.LANGUAGE_CODE
        
        # Устанавливаем язык для текущего запроса
        translation.activate(language)
        request.LANGUAGE_CODE = language
        # Сохраняем язык в сессии для использования LocaleMiddleware (ключ по умолчанию)
        if hasattr(request, 'session'):
            request.session['django_language'] = language

        return None


class MobileDetectionMiddleware(MiddlewareMixin):
    """
    Middleware для определения мобильных устройств
    Добавляет флаг is_mobile в request
    """
    
    def process_request(self, request):
        """Определение мобильного устройства"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        
        # Простая проверка мобильных устройств
        mobile_keywords = [
            'mobile', 'android', 'iphone', 'ipad', 'ipod', 
            'blackberry', 'windows phone', 'opera mini'
        ]
        
        request.is_mobile = any(keyword in user_agent for keyword in mobile_keywords)
        
        # Определяем тип платформы
        if 'android' in user_agent:
            request.platform = 'android'
        elif 'iphone' in user_agent or 'ipad' in user_agent or 'ipod' in user_agent:
            request.platform = 'ios'
        elif 'windows phone' in user_agent:
            request.platform = 'windows_phone'
        else:
            request.platform = 'web'
        
        return None
