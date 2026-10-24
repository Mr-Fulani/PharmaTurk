import json
import logging
import uuid

from django.core.cache import cache
from django.db import connection
from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import BaseParser, MultiPartParser
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from drf_spectacular.utils import extend_schema

from apps.recommendations.services.safe_image_fetcher import (
    FORMAT_EXTENSIONS,
    MAX_IMAGE_BYTES,
    ImageFetchError,
    ImageTooLargeError,
    InvalidImageError,
    validate_image_bytes,
)
from apps.users.auth_cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    refresh_from_request,
    set_refresh_cookie,
)
from .authentication import JWTSafeAuthentication
from .throttles import CSP_REPORT_THROTTLES, LOGIN_THROTTLES, TOKEN_THROTTLES


logger = logging.getLogger(__name__)
csp_logger = logging.getLogger("csp")
CSP_REPORT_MAX_BYTES = 16 * 1024


class HealthCheckResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    db = serializers.BooleanField()
    cache = serializers.BooleanField()


class LivenessCheckResponseSerializer(serializers.Serializer):
    status = serializers.CharField()


class JWTObtainPairSerializer(TokenObtainPairSerializer):
    """Принимает username или email в поле username + password."""
    username_field = "username"

    def validate(self, attrs):
        login = (attrs.get("username") or "").strip()
        password = attrs.get("password")
        if not login or not password:
            from rest_framework import serializers
            raise serializers.ValidationError("Нужны username (или email) и password")
        user = authenticate(self.context.get("request"), username=login, password=password)
        if not user:
            from rest_framework import serializers
            raise serializers.ValidationError("Неверный логин или пароль")
        if not user.is_active:
            from rest_framework import serializers
            raise serializers.ValidationError("Аккаунт заблокирован")
        refresh = self.get_token(user)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class JWTObtainPairView(TokenObtainPairView):
    serializer_class = JWTObtainPairSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = LOGIN_THROTTLES


class JWTRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        required=False,
        help_text="Только для API-клиентов: браузер шлёт refresh в HttpOnly cookie.",
    )


class JWTRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(
        required=False,
        help_text="Только если refresh пришёл в теле запроса.",
    )


class JWTRefreshView(TokenRefreshView):
    """Обновление access по refresh из HttpOnly cookie (TD-018) или из тела.

    Новый refresh (ротация) всегда уходит в cookie. В теле ответа он есть, только
    если запрос прислал refresh в теле: API-клиенты и браузеры со старой сессией,
    где refresh ещё лежал в обычной cookie, — такой браузер переезжает на HttpOnly
    при первом же обновлении.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = TOKEN_THROTTLES

    @extend_schema(
        request=JWTRefreshRequestSerializer,
        responses={200: JWTRefreshResponseSerializer},
    )
    def post(self, request, *args, **kwargs):
        from_cookie = bool(request.COOKIES.get(REFRESH_COOKIE_NAME))
        refresh = refresh_from_request(request)
        if not refresh:
            response = Response(
                {"detail": "Refresh-токен не передан", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response

        serializer = self.get_serializer(data={"refresh": refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, AuthenticationFailed):
            response = Response(
                {"detail": "Refresh-токен недействителен или истёк", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_refresh_cookie(response)
            return response

        data = dict(serializer.validated_data)
        new_refresh = data.get("refresh") or refresh
        if from_cookie:
            data.pop("refresh", None)
        response = Response(data, status=status.HTTP_200_OK)
        set_refresh_cookie(response, new_refresh)
        return response


class CspReportParser(BaseParser):
    """Браузеры шлют отчёты CSP как application/csp-report или reports+json."""

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(CSP_REPORT_MAX_BYTES + 1) if stream else b""
        if len(raw) > CSP_REPORT_MAX_BYTES:
            return {}
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}


def _csp_violations(payload) -> list:
    """report-uri: {"csp-report": {...}}; Reporting API: [{"type": "csp-violation", "body": {...}}]."""
    if isinstance(payload, dict) and isinstance(payload.get("csp-report"), dict):
        return [payload["csp-report"]]
    if isinstance(payload, list):
        return [
            item["body"]
            for item in payload[:20]
            if isinstance(item, dict) and isinstance(item.get("body"), dict)
        ]
    return []


def _strip_query(value) -> str:
    return str(value or "").split("?", 1)[0].split("#", 1)[0][:300]


class CspReportView(APIView):
    """Приёмник отчётов Content-Security-Policy-Report-Only (TD-018).

    Пишет в лог ``csp`` директиву и заблокированный источник без query-строк
    (там могут быть персональные данные). По логу решаем, когда включать enforce.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = CSP_REPORT_THROTTLES
    parser_classes = [CspReportParser]

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        for violation in _csp_violations(request.data)[:20]:
            csp_logger.warning(
                "CSP violation: %s blocked %s on %s",
                str(
                    violation.get("effective-directive")
                    or violation.get("effectiveDirective")
                    or violation.get("violated-directive")
                    or ""
                )[:80],
                _strip_query(violation.get("blocked-uri") or violation.get("blockedURL")),
                _strip_query(violation.get("document-uri") or violation.get("documentURL")),
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class JWTVerifyView(TokenVerifyView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = TOKEN_THROTTLES


class HealthCheckView(APIView):
    """Readiness check: require database and the Redis-backed cache."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Проверка работоспособности",
        responses={
            200: HealthCheckResponseSerializer,
            503: HealthCheckResponseSerializer,
        },
    )
    def get(self, request: Request) -> Response:  # type: ignore[override]
        """Возвращает readiness по PostgreSQL и Redis-backed cache."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                _ = cursor.fetchone()
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        cache_key = f"health:readiness:{uuid.uuid4().hex}"
        try:
            cache.set(cache_key, "ok", timeout=5)
            cache_ok = cache.get(cache_key) == "ok"
            cache.delete(cache_key)
        except Exception:  # noqa: BLE001
            cache_ok = False
        ready = db_ok and cache_ok
        response_status = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(
            {
                "status": "ok" if ready else "unavailable",
                "db": db_ok,
                "cache": cache_ok,
            },
            status=response_status,
        )


class LivenessCheckView(APIView):
    """Process-only liveness check; does not contact external dependencies."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Проверка процесса",
        responses={200: LivenessCheckResponseSerializer},
    )
    def get(self, request: Request) -> Response:  # type: ignore[override]
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class TempImageUploadThrottle(AnonRateThrottle):
    rate = "10/min"


class TempImageUploadUserThrottle(UserRateThrottle):
    rate = "30/min"


class TempImageUploadRequestSerializer(serializers.Serializer):
    file = serializers.ImageField()


class TempImageUploadResponseSerializer(serializers.Serializer):
    url = serializers.URLField()
    message = serializers.CharField()


class TempImageUploadErrorSerializer(serializers.Serializer):
    error = serializers.CharField()


def _read_validated_temp_image(file_obj) -> tuple[bytes, str]:
    """Read a bounded upload and return bytes plus its detected extension."""

    try:
        data = file_obj.read(MAX_IMAGE_BYTES + 1)
    except Exception:
        raise InvalidImageError() from None
    if not isinstance(data, bytes):
        raise InvalidImageError()
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageTooLargeError()
    validated = validate_image_bytes(data)
    return data, FORMAT_EXTENSIONS[validated.format]


class TempImageUploadView(APIView):
    """
    Эндпоинт для временной загрузки картинок (для поиска по фото).
    Файлы сохраняются локально (или в R2) с уникальным именем и через время удаляются Celery.
    """
    # This is a public SPA endpoint. An unrelated Django admin/session cookie
    # must not opt the request into SessionAuthentication's CSRF enforcement.
    authentication_classes = [JWTSafeAuthentication]
    parser_classes = [MultiPartParser]
    throttle_classes = [TempImageUploadThrottle, TempImageUploadUserThrottle]
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Загрузка временного фото для поиска",
        request=TempImageUploadRequestSerializer,
        responses={
            201: TempImageUploadResponseSerializer,
            400: TempImageUploadErrorSerializer,
            500: TempImageUploadErrorSerializer,
        },
    )
    def post(self, request: Request) -> Response:  # type: ignore[override]
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "Файл не передан"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data, extension = _read_validated_temp_image(file_obj)
        except ImageTooLargeError:
            return Response({"error": "Размер файла превышает 5 МБ"}, status=status.HTTP_400_BAD_REQUEST)
        except ImageFetchError:
            return Response({"error": "Файл не является допустимым изображением"}, status=status.HTTP_400_BAD_REQUEST)

        filename = f"temp/{uuid.uuid4().hex}{extension}"
        validated_file = ContentFile(data, name=filename.rsplit("/", 1)[-1])
        validated_file.seek(0)

        try:
            saved_path = default_storage.save(filename, validated_file)
            file_url = default_storage.url(saved_path)

            # Для генерации абсолютного URL можно использовать request.build_absolute_uri()
            # но если file_url уже начинается с http (как в S3Boto3), то оставляем как есть
            if not file_url.startswith("http"):
                file_url = request.build_absolute_uri(file_url)

            return Response({
                "url": file_url,
                "message": "Изображение загружено"
            }, status=status.HTTP_201_CREATED)

        except Exception:
            logger.exception("Failed to save temporary visual-search image")
            return Response(
                {"error": "Ошибка сохранения изображения"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
