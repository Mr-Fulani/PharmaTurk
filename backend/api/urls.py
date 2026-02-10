"""URL-маршруты для публичного API (v1)."""
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

from .views import HealthCheckView, JWTObtainPairView


urlpatterns = [
    # Проверка здоровья сервиса
    path("health/", HealthCheckView.as_view(), name="health-check"),

    # Аутентификация (JWT): в теле username или email + password
    path("auth/jwt/create/", JWTObtainPairView.as_view(), name="jwt-create"),
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

    # AI: логи, генерация контента, модерация
    path("ai/", include("apps.ai.urls")),

    # Рекомендации (векторная RecSys на Qdrant)
    path("recommendations/", include("apps.recommendations.urls")),
]

