"""URL-маршруты для публичного API (v1)."""
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import HealthCheckView


urlpatterns = [
    # Проверка здоровья сервиса
    path("health/", HealthCheckView.as_view(), name="health-check"),

    # Аутентификация (JWT)
    path("auth/jwt/create/", TokenObtainPairView.as_view(), name="jwt-create"),
    path("auth/jwt/refresh/", TokenRefreshView.as_view(), name="jwt-refresh"),

    # Пользователи
    path("users/", include("apps.users.urls")),

    # Платежи (заглушки)
    path("payments/", include("apps.payments.urls")),

    # Vapi
    path("vapi/", include("apps.vapi.urls")),

    # Каталог товаров
    path("catalog/", include("apps.catalog.urls")),

    # Настройки сайта
    path("settings/", include("apps.settings.urls")),

    # Корзина и заказы
    path("orders/", include("apps.orders.urls")),
]

