"""
Модуль OAuth авторизации через социальные сети.

Реализованные провайдеры:
- Google (через Google Identity Services: id_token / OAuth2 access_token)
- VK     (через VK API: access_token + user_id из VK SDK)

Паттерн реализации аналогичен telegram_auth.py.
"""

import logging
import uuid

import httpx
from django.conf import settings
from django.utils.crypto import get_random_string

from .models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Базовый класс провайдера
# ---------------------------------------------------------------------------

class SocialAuthProvider:
    """Базовый класс для OAuth-провайдеров."""

    name: str = ""  # 'google' | 'vk'
    id_field: str = ""  # поле в модели User: 'google_id' | 'vk_id'

    def get_user_info(self, token: str, **kwargs) -> dict | None:
        """
        Обращается к API провайдера и возвращает нормализованный словарь:
        {
            'provider_id': str,   # уникальный ID пользователя у провайдера
            'email': str | None,
            'first_name': str,
            'last_name': str,
            'avatar_url': str | None,
        }
        Возвращает None при ошибке.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Google OAuth провайдер
# ---------------------------------------------------------------------------

class GoogleOAuthProvider(SocialAuthProvider):
    """
    Поддерживает два сценария:
    1. Google One Tap / Sign In With Google → фронт отдаёт `credential` (id_token/JWT).
       Верифицируем через https://oauth2.googleapis.com/tokeninfo?id_token=...
    2. Обычный OAuth2 popup → фронт отдаёт `access_token`.
       Получаем данные через https://www.googleapis.com/oauth2/v3/userinfo
    """

    name = "google"
    id_field = "google_id"

    # Google One Tap endpoint (верификация id_token)
    TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
    # OAuth2 userinfo endpoint (для access_token)
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def get_user_info(self, token: str, **kwargs) -> dict | None:
        """
        token может быть:
        - id_token (JWT из Google One Tap — поле 'credential' от GSI)
        - access_token (из обычного OAuth2 flow)
        """
        # Пробуем сначала как id_token (Google One Tap)
        user_data = self._verify_id_token(token)
        if user_data is None:
            # Если не сработало — пробуем как access_token
            user_data = self._get_userinfo(token)

        if user_data is None:
            logger.warning("Google: не удалось верифицировать токен")
            return None

        google_id = user_data.get("sub")
        if not google_id:
            logger.warning("Google: в ответе нет поля 'sub' (google_id)")
            return None

        return {
            "provider_id": str(google_id),
            "email": user_data.get("email"),
            "first_name": user_data.get("given_name", ""),
            "last_name": user_data.get("family_name", ""),
            "avatar_url": user_data.get("picture"),
        }

    def _verify_id_token(self, id_token: str) -> dict | None:
        """Верификация Google id_token через tokeninfo endpoint."""
        try:
            client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    self.TOKENINFO_URL,
                    params={"id_token": id_token},
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
            # Проверяем aud (audience) — должен совпадать с нашим CLIENT_ID
            if client_id and data.get("aud") != client_id:
                logger.warning("Google id_token: aud не совпадает с GOOGLE_CLIENT_ID")
                return None
            return data
        except Exception as exc:
            logger.debug(f"Google _verify_id_token error: {exc}")
            return None

    def _get_userinfo(self, access_token: str) -> dict | None:
        """Получение данных пользователя через userinfo endpoint (access_token)."""
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    self.USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception as exc:
            logger.debug(f"Google _get_userinfo error: {exc}")
            return None


# ---------------------------------------------------------------------------
# VK OAuth провайдер
# ---------------------------------------------------------------------------

class VKOAuthProvider(SocialAuthProvider):
    """
    VK отдаёт access_token через VK ID SDK.
    Дополнительно принимает vk_user_id (из SDK) для надёжности,
    но подтверждаем через API.
    """

    name = "vk"
    id_field = "vk_id"

    USERS_GET_URL = "https://api.vk.com/method/users.get"
    VK_API_VERSION = "5.199"

    def get_user_info(self, token: str, **kwargs) -> dict | None:
        """
        token — access_token из VK SDK.
        kwargs может содержать vk_user_id — ID пользователя (для передачи в API).
        """
        try:
            params = {
                "access_token": token,
                "fields": "photo_100,first_name,last_name",
                "v": self.VK_API_VERSION,
            }
            vk_user_id = kwargs.get("vk_user_id")
            if vk_user_id:
                params["user_ids"] = str(vk_user_id)

            with httpx.Client(timeout=10) as client:
                resp = client.get(self.USERS_GET_URL, params=params)

            if resp.status_code != 200:
                logger.warning(f"VK API вернул статус {resp.status_code}")
                return None

            data = resp.json()
            error = data.get("error")
            if error:
                logger.warning(f"VK API ошибка: {error}")
                return None

            response_list = data.get("response", [])
            if not response_list:
                return None

            vk_user = response_list[0]
            vk_id = vk_user.get("id")
            if not vk_id:
                return None

            return {
                "provider_id": str(vk_id),
                "email": None,  # VK не отдаёт email через base scope
                "first_name": vk_user.get("first_name", ""),
                "last_name": vk_user.get("last_name", ""),
                "avatar_url": vk_user.get("photo_100"),
            }
        except Exception as exc:
            logger.warning(f"VK get_user_info error: {exc}")
            return None


# ---------------------------------------------------------------------------
# Реестр провайдеров
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, type[SocialAuthProvider]] = {
    "google": GoogleOAuthProvider,
    "vk": VKOAuthProvider,
}


# ---------------------------------------------------------------------------
# Общая фабричная функция (DRY, по образцу Telegram)
# ---------------------------------------------------------------------------

def get_or_create_social_user(
    provider: SocialAuthProvider,
    user_info: dict,
) -> User:
    """
    Ищет или создаёт пользователя для данного OAuth провайдера.

    Стратегия поиска:
    1. По provider_id в соответствующем поле (google_id / vk_id)
    2. По email (если провайдер отдал email) — привязывает google_id/vk_id к существующему
    3. Создаёт нового пользователя

    Возвращает объект User.
    """
    provider_id: str = user_info["provider_id"]
    email: str | None = user_info.get("email")
    first_name: str = user_info.get("first_name", "")
    last_name: str = user_info.get("last_name", "")

    id_field = provider.id_field  # 'google_id' | 'vk_id'

    # 1. Ищем по provider_id
    user = User.objects.filter(**{id_field: provider_id}).first()

    if user:
        # Обновляем имя/фамилию если они пустые
        update_fields = []
        if first_name and not user.first_name:
            user.first_name = first_name
            update_fields.append("first_name")
        if last_name and not user.last_name:
            user.last_name = last_name
            update_fields.append("last_name")
        if update_fields:
            user.save(update_fields=update_fields)
        logger.info(f"Social login [{provider.name}]: существующий пользователь id={user.id}")
        return user

    # 2. Ищем по email (привязываем аккаунт)
    if email:
        user = User.objects.filter(email=email).first()
        if user:
            setattr(user, id_field, provider_id)
            update_fields = [id_field]
            if first_name and not user.first_name:
                user.first_name = first_name
                update_fields.append("first_name")
            if last_name and not user.last_name:
                user.last_name = last_name
                update_fields.append("last_name")
            user.save(update_fields=update_fields)
            logger.info(
                f"Social login [{provider.name}]: привязан к существующему email={email}, user_id={user.id}"
            )
            return user

    # 3. Создаём нового пользователя
    dummy_email = (
        email
        if email
        else f"{provider.name}_{provider_id}@mudaroba.local"
    )
    # Уникальность email (крайне маловероятно, но защищаемся)
    if User.objects.filter(email=dummy_email).exists():
        dummy_email = f"{provider.name}_{provider_id}_{uuid.uuid4().hex[:6]}@mudaroba.local"

    # Генерируем username
    base_username = (
        email.split("@")[0] if email else f"{provider.name}_{provider_id}"
    )
    # Обрезаем до 30 символов (лимит Django)
    base_username = base_username[:30]
    final_username = base_username
    counter = 1
    while User.objects.filter(username=final_username).exists():
        final_username = f"{base_username[:27]}{counter}"
        counter += 1

    user = User.objects.create_user(
        email=dummy_email,
        username=final_username,
        password=get_random_string(20),
        first_name=first_name,
        last_name=last_name,
        is_verified=True,  # OAuth аккаунты считаем верифицированными
        **{id_field: provider_id},
    )
    logger.info(
        f"Social login [{provider.name}]: создан новый пользователь id={user.id}, email={dummy_email}"
    )
    return user
