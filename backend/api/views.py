"""Представления публичного API.

Docstring и комментарии написаны на русском языке.
"""
from django.db import connection
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema


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


