"""Представления публичного API.

Docstring и комментарии написаны на русском языке.
"""
from django.db import connection
from django.contrib.auth import authenticate
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from drf_spectacular.utils import extend_schema


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


class HealthCheckView(APIView):
    """Простой health-check: проверяет доступность БД и возвращает OK."""

    @extend_schema(summary="Проверка работоспособности", responses={200: dict})
    def get(self, request: Request) -> Response:  # type: ignore[override]
        """Возвращает статус сервиса и пинг к базе данных."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                _ = cursor.fetchone()
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        return Response({"status": "ok", "db": db_ok})


