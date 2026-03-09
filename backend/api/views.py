import os
import uuid
from PIL import Image

from django.db import connection
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
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


class TempImageUploadThrottle(AnonRateThrottle):
    rate = "10/min"


class TempImageUploadView(APIView):
    """
    Эндпоинт для временной загрузки картинок (для поиска по фото).
    Файлы сохраняются локально (или в R2) с уникальным именем и через время удаляются Celery.
    """
    parser_classes = [MultiPartParser]
    throttle_classes = [TempImageUploadThrottle, UserRateThrottle]
    permission_classes = []  # Доступно всем (AllowAny), но с Rate Limit

    @extend_schema(summary="Загрузка временного фото для поиска", responses={201: dict, 400: dict})
    def post(self, request: Request) -> Response:  # type: ignore[override]
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "Файл не передан"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Проверка размера файла (5 МБ)
        max_size = 5 * 1024 * 1024
        if file_obj.size > max_size:
            return Response({"error": "Размер файла превышает 5 МБ"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Проверка, что это действительно картинка
        try:
            img = Image.open(file_obj)
            img.verify()  # Проверяет целостность формата (без полной распаковки)
            
            # Pillow.verify() оставляет курсор файла в конце, нужно вернуть на начало для сохранения
            file_obj.seek(0)
            
            # Можно дополнительно проверить формат
            if img.format not in ["JPEG", "PNG", "WEBP"]:
                return Response(
                    {"error": f"Формат {img.format} не поддерживается. Разрешены: JPEG, PNG, WEBP"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception:
            return Response({"error": "Файл не является допустимым изображением"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Сохранение с безопасным уникальным именем
        ext = os.path.splitext(file_obj.name)[1].lower()
        if not ext or ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"  # Фолбэк
            
        filename = f"temp/{uuid.uuid4().hex}{ext}"
        
        try:
            # default_storage может быть как локальным FileSystemStorage, так и S3Boto3Storage
            saved_path = default_storage.save(filename, file_obj)
            file_url = default_storage.url(saved_path)
            
            # Для генерации абсолютного URL можно использовать request.build_absolute_uri() 
            # но если file_url уже начинается с http (как в S3Boto3), то оставляем как есть
            if not file_url.startswith("http"):
                file_url = request.build_absolute_uri(file_url)
                
            return Response({
                "url": file_url,
                "message": "Изображение загружено"
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response({"error": f"Ошибка сохранения: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

