from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from api.throttles import COOKIE_CONSENT_THROTTLES, get_trusted_client_ip

from .models import CookieConsent


def get_client_ip(request) -> str | None:
    """Backward-compatible alias for the project's trusted proxy resolver."""
    return get_trusted_client_ip(request)


class CookieConsentView(APIView):
    """
    POST /api/marketing/cookie-consent/

    Сохраняет факт согласия/отказа пользователя от аналитических cookie.
    Используется для GDPR/KVKK аудита.

    Тело запроса: { "consent": true/false }
    Не требует аутентификации.
    Rate limit на trusted client IP: 10 запросов/минуту и 100 запросов/сутки.
    """

    permission_classes = [AllowAny]
    throttle_classes = COOKIE_CONSENT_THROTTLES

    @extend_schema(
        request=inline_serializer(
            name="CookieConsentRequest",
            fields={"consent": serializers.BooleanField()},
        ),
        responses={
            201: inline_serializer(
                name="CookieConsentResponse",
                fields={"status": serializers.CharField()},
            ),
            400: OpenApiResponse(description="Invalid or missing consent value."),
            429: OpenApiResponse(description="Trusted client IP rate limit exceeded."),
        },
    )
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

        session = getattr(request, "session", None)
        CookieConsent.objects.create(
            consent_given=consent_value,
            ip_address=get_trusted_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
            session_id=getattr(session, "session_key", "") or "",
        )

        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
