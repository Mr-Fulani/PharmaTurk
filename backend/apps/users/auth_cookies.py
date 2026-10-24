"""Refresh-токен JWT в HttpOnly cookie (TD-018).

Браузер получает refresh только в cookie, недоступной JavaScript: XSS больше не
может унести долгоживущую сессию. Access-токен (60 мин) по-прежнему в теле ответа —
фронт кладёт его в обычную cookie для заголовка Authorization и SSR.

Cookie без Max-Age, как и прежние cookie фронта: закрытие браузера = выход.
SameSite=Lax не отдаёт её межсайтовым POST — подделать обновление/выход с чужого
сайта нельзя.
"""

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

REFRESH_COOKIE_NAME = "refresh_token"
# Нужна только эндпоинтам /api/auth/jwt/refresh/ и /api/users/logout/.
REFRESH_COOKIE_PATH = "/api/"


def set_refresh_cookie(response, refresh) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        str(refresh),
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, samesite="Lax")


def refresh_from_request(request) -> str:
    """Refresh из HttpOnly cookie; из тела — для API-клиентов и старых сессий браузера."""
    cookie_value = request.COOKIES.get(REFRESH_COOKIE_NAME)
    if cookie_value:
        return cookie_value
    data = getattr(request, "data", None)
    body_value = data.get("refresh") if hasattr(data, "get") else None
    return body_value if isinstance(body_value, str) else ""


def auth_tokens_payload(user) -> tuple[dict, RefreshToken]:
    """Тело ``tokens`` для ответов входа: только access, refresh уходит в cookie."""
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token)}, refresh
