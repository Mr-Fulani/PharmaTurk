"""
Модуль OAuth авторизации через социальные сети.

Реализованные провайдеры:
- Google (через Google Identity Services: только id_token)
- VK     (через VK API: access_token + user_id из VK SDK)

Паттерн реализации аналогичен telegram_auth.py.
"""

import logging
import time
import uuid
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.crypto import get_random_string
from PIL import Image

from .models import User

logger = logging.getLogger(__name__)


MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000

# Google profile pictures are served from this dedicated host. VK uses
# per-region subdomains below userapi.com. Broad domains such as google.com or
# vk.com are deliberately not accepted: the URL comes from an external API and
# must never become a generic server-side URL fetcher.
_AVATAR_EXACT_HOSTS: dict[str, frozenset[str]] = {
    "google": frozenset({"lh3.googleusercontent.com"}),
    "vk": frozenset(),
}
_AVATAR_HOST_SUFFIXES: dict[str, tuple[str, ...]] = {
    "google": (),
    "vk": (".userapi.com",),
}
_IMAGE_FORMAT_TO_MIME_AND_EXTENSION: dict[str, tuple[str, str]] = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "GIF": ("image/gif", "gif"),
    "WEBP": ("image/webp", "webp"),
}


def _normalise_email_verified(value: object) -> bool:
    """Normalise only provider representations that unambiguously mean true."""
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def get_verified_social_email(user_info: dict) -> str | None:
    """Return a normalised email only when the provider explicitly verified it."""
    raw_email = user_info.get("email")
    email = raw_email.strip() if isinstance(raw_email, str) and raw_email.strip() else None
    if user_info.get("email_verified") is not True:
        return None
    return email


def _is_allowed_avatar_url(provider_name: str, avatar_url: str) -> bool:
    """Return whether an avatar URL is HTTPS and belongs to the provider CDN."""
    try:
        parsed = urlsplit(avatar_url)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.port not in (None, 443):
            return False

        host = parsed.hostname.lower().rstrip(".")
        exact_hosts = _AVATAR_EXACT_HOSTS.get(provider_name, frozenset())
        suffixes = _AVATAR_HOST_SUFFIXES.get(provider_name, ())
        return host in exact_hosts or any(host.endswith(suffix) for suffix in suffixes)
    except (TypeError, ValueError):
        return False


def _validated_avatar_extension(content: bytes, content_type: str) -> str | None:
    """Validate the decoded image metadata and return a safe file extension."""
    mime = content_type.partition(";")[0].strip().lower()
    accepted_mimes = {entry[0] for entry in _IMAGE_FORMAT_TO_MIME_AND_EXTENSION.values()}
    if mime not in accepted_mimes:
        return None

    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_AVATAR_PIXELS:
                return None

            format_details = _IMAGE_FORMAT_TO_MIME_AND_EXTENSION.get(image.format or "")
            if format_details is None or format_details[0] != mime:
                return None

            # verify() walks the encoded file without rendering it and catches
            # truncated/corrupt payloads before they are persisted.
            image.verify()
            return format_details[1]
    except Exception as exc:
        logger.debug(
            "Social avatar image validation failed: %s",
            type(exc).__name__,
        )
        return None


def _download_social_avatar(provider_name: str, avatar_url: str) -> tuple[str, bytes] | None:
    """Download and validate a provider avatar with a strict resource budget."""
    if not _is_allowed_avatar_url(provider_name, avatar_url):
        logger.debug("Social avatar URL is outside the %s allowlist", provider_name)
        return None

    try:
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            with client.stream("GET", avatar_url) as response:
                if response.status_code != 200:
                    return None

                raw_length = response.headers.get("content-length")
                if raw_length:
                    try:
                        if int(raw_length) > MAX_AVATAR_BYTES:
                            return None
                    except ValueError:
                        return None

                chunks: list[bytes] = []
                downloaded = 0
                for chunk in response.iter_bytes():
                    downloaded += len(chunk)
                    if downloaded > MAX_AVATAR_BYTES:
                        return None
                    chunks.append(chunk)

                content = b"".join(chunks)
                extension = _validated_avatar_extension(
                    content,
                    response.headers.get("content-type", ""),
                )
                if extension is None:
                    return None
                return extension, content
    except Exception as exc:
        # Provider avatar URLs may contain signed query parameters.
        logger.debug("Failed to fetch social avatar: %s", type(exc).__name__)
        return None


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
            'email_verified': bool,
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
    Google One Tap / Sign In With Google передаёт `credential` (id_token/JWT).
    Токен проверяется через tokeninfo; обычные OAuth access token здесь не
    принимаются, потому что userinfo сам по себе не доказывает audience этого
    приложения.
    """

    name = "google"
    id_field = "google_id"

    # Google One Tap endpoint (верификация id_token)
    TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    def get_user_info(self, token: str, **kwargs) -> dict | None:
        """Validate a Google ID token and return normalised trusted claims."""
        user_data = self._verify_id_token(token)
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
            "email_verified": user_data["email_verified"],
            "first_name": user_data.get("given_name", ""),
            "last_name": user_data.get("family_name", ""),
            "avatar_url": user_data.get("picture"),
        }

    def _verify_id_token(self, id_token: str) -> dict | None:
        """Верификация Google id_token через tokeninfo endpoint."""
        client_id = str(getattr(settings, "GOOGLE_CLIENT_ID", "") or "").strip()
        if not client_id:
            logger.error("Google social auth disabled: GOOGLE_CLIENT_ID is empty")
            return None

        id_token = str(id_token or "").strip()
        if id_token.count(".") != 2:
            # Google ID tokens are JWTs; fail before making a remote request for
            # opaque OAuth access tokens.
            return None

        try:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                resp = client.get(
                    self.TOKENINFO_URL,
                    params={"id_token": id_token},
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None

            # Exact audience matching prevents accepting a token issued for a
            # different application in the same Google account/project.
            if data.get("aud") != client_id:
                logger.warning("Google id_token: aud не совпадает с GOOGLE_CLIENT_ID")
                return None

            if data.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
                logger.warning("Google id_token: недопустимый issuer")
                return None

            email = data.get("email")
            email_verified = _normalise_email_verified(data.get("email_verified"))
            if email and not email_verified:
                logger.warning("Google id_token: email не подтверждён провайдером")
                return None

            data["email"] = email.strip() if isinstance(email, str) and email.strip() else None
            data["email_verified"] = bool(data["email"] and email_verified)
            return data
        except Exception as exc:
            # httpx exceptions may include the tokeninfo URL with id_token.
            logger.debug("Google ID token verification failed: %s", type(exc).__name__)
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
    USER_INFO_URL = "https://id.vk.com/oauth2/user_info"
    VK_API_VERSION = "5.199"

    def get_user_info(self, token: str, **kwargs) -> dict | None:
        client_id = str(getattr(settings, "VK_APP_ID", "") or "").strip()

        # Шаг 1: серверный VK ID endpoint. Email считается подтверждённым
        # только когда он получен именно из успешного ответа этого endpoint,
        # связанного с настроенным приложением.
        if client_id:
            try:
                with httpx.Client(timeout=10, follow_redirects=False) as client:
                    res = client.post(
                        self.USER_INFO_URL,
                        data={
                            "client_id": client_id,
                            "access_token": token,
                        },
                    )
                    if res.status_code == 200:
                        payload = res.json()
                        user_data = payload.get("user", {}) if isinstance(payload, dict) else {}
                        vk_id = user_data.get("user_id")

                        expected_vk_id = kwargs.get("vk_user_id")
                        if expected_vk_id and str(expected_vk_id) != str(vk_id):
                            logger.warning("VK ID: user_id ответа не совпадает с SDK")
                            return None

                        if vk_id:
                            # Обогащение выполняется до выхода из контекстного
                            # менеджера: ранее здесь использовался уже закрытый client.
                            supp_token = (
                                getattr(settings, "VK_USER_TOKEN", "")
                                or getattr(settings, "VK_API_TOKEN", "")
                            )
                            if supp_token:
                                try:
                                    supp_res = client.get(
                                        self.USERS_GET_URL,
                                        params={
                                            "user_ids": vk_id,
                                            "fields": "photo_100,first_name,last_name",
                                            "v": self.VK_API_VERSION,
                                            "access_token": supp_token,
                                        },
                                    )
                                    if supp_res.status_code == 200:
                                        supp_payload = supp_res.json()
                                        response_items = (
                                            supp_payload.get("response", [])
                                            if isinstance(supp_payload, dict)
                                            else []
                                        )
                                        if response_items:
                                            supp_data = response_items[0]
                                            user_data["first_name"] = supp_data.get(
                                                "first_name", user_data.get("first_name")
                                            )
                                            user_data["last_name"] = supp_data.get(
                                                "last_name", user_data.get("last_name")
                                            )
                                            user_data["avatar"] = supp_data.get(
                                                "photo_100", user_data.get("avatar")
                                            )
                                except Exception as exc:
                                    # The enrichment URL carries a supplementary token.
                                    logger.debug(
                                        "VK profile enrichment failed: %s",
                                        type(exc).__name__,
                                    )

                            email = user_data.get("email")
                            if not isinstance(email, str) or not email.strip():
                                email = None
                            else:
                                email = email.strip()

                            return {
                                "provider_id": str(vk_id),
                                "email": email,
                                "email_verified": email is not None,
                                "first_name": user_data.get("first_name", ""),
                                "last_name": user_data.get("last_name", ""),
                                "avatar_url": user_data.get("avatar"),
                            }
            except Exception as exc:
                logger.debug("VK user_info request failed: %s", type(exc).__name__)

        # Шаг 2: фолбэк на классический VK API. Для некоторых клиентских
        # токенов он может вернуть ошибку из-за IP-адреса.
        try:
            params = {
                "access_token": token,
                "fields": "photo_100,first_name,last_name",
                "v": self.VK_API_VERSION,
            }

            # Не передаём user_ids: с клиентским значением VK вернул бы
            # публичный профиль произвольного пользователя, а не владельца
            # access token. SDK ID используется только для последующей сверки.
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                resp = client.get(self.USERS_GET_URL, params=params)

            if resp.status_code != 200:
                logger.warning(f"VK API вернул статус {resp.status_code}")
                return None

            data = resp.json()
            error = data.get("error")
            if error:
                error_code = error.get("error_code") if isinstance(error, dict) else None
                logger.warning("VK API returned an error, code=%s", error_code)
                return None

            response_list = data.get("response", [])
            if not response_list:
                return None

            vk_user = response_list[0]
            vk_id = vk_user.get("id")
            if not vk_id:
                return None

            expected_vk_id = kwargs.get("vk_user_id")
            if expected_vk_id and str(expected_vk_id) != str(vk_id):
                logger.warning("VK API: user_id владельца токена не совпадает с SDK")
                return None

            return {
                "provider_id": str(vk_id),
                "email": None,  # VK не отдаёт email через base scope
                "email_verified": False,
                "first_name": vk_user.get("first_name", ""),
                "last_name": vk_user.get("last_name", ""),
                "avatar_url": vk_user.get("photo_100"),
            }
        except Exception as exc:
            # Classic VK API places access_token in the query string.
            logger.warning("VK profile request failed: %s", type(exc).__name__)
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
    2. По подтверждённому провайдером email — привязывает google_id/vk_id к существующему
    3. Создаёт нового пользователя

    Возвращает объект User.
    """
    provider_id: str = user_info["provider_id"]
    trusted_email = get_verified_social_email(user_info)
    email_verified = trusted_email is not None
    first_name: str = user_info.get("first_name", "")
    last_name: str = user_info.get("last_name", "")
    avatar_url: str | None = user_info.get("avatar_url")

    def _assign_avatar_if_needed(u: User) -> bool:
        if avatar_url and not u.avatar:
            original_avatar = u.avatar
            try:
                downloaded = _download_social_avatar(provider.name, avatar_url)
                if downloaded is not None:
                    extension, content = downloaded
                    filename = f"social_{provider.name}_{u.id}_{int(time.time())}.{extension}"
                    u.avatar.save(filename, ContentFile(content), save=False)
                    return True
            except Exception as exc:
                u.avatar = original_avatar
                logger.debug(
                    "Failed to persist social avatar: %s",
                    type(exc).__name__,
                )
        return False

    id_field = provider.id_field  # 'google_id' | 'vk_id'

    # 1. Ищем по provider_id
    user = User.objects.filter(**{id_field: provider_id}).first()

    if user:
        # Обновляем имя/фамилию если они пустые
        update_fields = []
        current_email = str(getattr(user, "email", "") or "").strip()
        if trusted_email and current_email.casefold() == trusted_email.casefold():
            if not user.is_verified:
                user.is_verified = True
                update_fields.append("is_verified")
        elif trusted_email and current_email.lower().endswith("@mudaroba.local"):
            email_conflict = (
                User.objects.filter(email__iexact=trusted_email)
                .exclude(pk=user.pk)
                .exists()
            )
            if not email_conflict:
                user.email = trusted_email
                user.is_verified = True
                update_fields.extend(["email", "is_verified"])
            else:
                logger.warning(
                    "Social login [%s]: verified email belongs to another user; "
                    "provider login continues without replacing placeholder email",
                    provider.name,
                )
        if first_name and not user.first_name:
            user.first_name = first_name
            update_fields.append("first_name")
        if last_name and not user.last_name:
            user.last_name = last_name
            update_fields.append("last_name")
        if avatar_url and not user.avatar and _assign_avatar_if_needed(user):
            update_fields.append("avatar")
        if update_fields:
            user.save(update_fields=update_fields)
        logger.info(
            "Social login [%s]: существующий пользователь id=%s",
            provider.name,
            user.id,
        )
        return user

    # 2. Ищем только по подтверждённому провайдером email. Иначе владелец
    # неподтверждённого адреса смог бы захватить уже существующий аккаунт.
    if trusted_email:
        user = User.objects.filter(email__iexact=trusted_email).first()
        if user:
            setattr(user, id_field, provider_id)
            update_fields = [id_field]
            if not user.is_verified:
                user.is_verified = True
                update_fields.append("is_verified")
            if first_name and not user.first_name:
                user.first_name = first_name
                update_fields.append("first_name")
            if last_name and not user.last_name:
                user.last_name = last_name
                update_fields.append("last_name")
            if avatar_url and not user.avatar and _assign_avatar_if_needed(user):
                update_fields.append("avatar")
            user.save(update_fields=update_fields)
            logger.info(
                "Social login [%s]: linked to existing verified account user_id=%s",
                provider.name,
                user.id,
            )
            return user

    # 3. Создаём нового пользователя
    dummy_email = (
        trusted_email if trusted_email else f"{provider.name}_{provider_id}@mudaroba.local"
    )
    # Уникальность email (крайне маловероятно, но защищаемся)
    if User.objects.filter(email=dummy_email).exists():
        dummy_email = f"{provider.name}_{provider_id}_{uuid.uuid4().hex[:6]}@mudaroba.local"

    # Генерируем username
    base_username = (
        trusted_email.split("@")[0] if trusted_email else f"{provider.name}_{provider_id}"
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
        is_verified=email_verified,
        **{id_field: provider_id},
    )

    # Загружаем аватар для нового аккаунта
    if avatar_url and _assign_avatar_if_needed(user):
        user.save(update_fields=["avatar"])

    logger.info(
        "Social login [%s]: created user_id=%s",
        provider.name,
        user.id,
    )
    return user
