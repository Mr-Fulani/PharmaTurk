from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import CookieConsent


def get_client_ip(request) -> str | None:
    """Извлекает реальный IP из заголовков (учитывает nginx proxy)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class CookieConsentView(APIView):
    """
    POST /api/marketing/cookie-consent/

    Сохраняет факт согласия/отказа пользователя от аналитических cookie.
    Используется для GDPR/KVKK аудита.

    Тело запроса: { "consent": true/false }
    Не требует аутентификации.
    """

    permission_classes = [AllowAny]
    # Лёгкий rate limit через throttle
    throttle_scope = "cookie_consent"

    def post(self, request, *args, **kwargs):
        consent_value = request.data.get("consent")

        if consent_value is None:
            return Response(
                {"detail": "Поле 'consent' обязательно."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(consent_value, bool):
            return Response(
                {"detail": "Поле 'consent' должно быть булевым значением."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        CookieConsent.objects.create(
            consent_given=consent_value,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
            session_id=request.session.session_key or "",
        )

        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
