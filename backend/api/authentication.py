"""Кастомная аутентификация для публичного API.

JWTSafeAuthentication: при невалидном/просроченном токене возвращает None (анонимный доступ)
вместо 401. Это позволяет AllowAny-эндпоинтам (каталог, баннеры, корзина) работать
при доступе через ngrok/production, когда у пользователя в cookies остался старый токен.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken


class JWTSafeAuthentication(JWTAuthentication):
    """JWT-аутентификация, которая при невалидном токене возвращает None вместо 401.

    Используется как DEFAULT_AUTHENTICATION_CLASSES, чтобы AllowAny-эндпоинты
    (каталог, баннеры, корзина) не возвращали 401 при просроченном токене в cookies.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except (InvalidToken, AuthenticationFailed):
            return None
