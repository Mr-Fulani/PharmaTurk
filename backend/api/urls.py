"""URL-маршруты для публичного API (v1)."""
from django.urls import path, include, re_path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import HealthCheckView, JWTObtainPairView, TempImageUploadView

TokenRefresh = TokenRefreshView.as_view()

urlpatterns = [
    # Проверка здоровья сервиса
    path("health/", HealthCheckView.as_view(), name="health-check"),
    
    # Временная загрузка файлов
    re_path(r"^upload/temp/?$", TempImageUploadView.as_view(), name="temp-upload"),

    # Аутентификация (JWT): в теле username или email + password
    path("auth/jwt/create/", JWTObtainPairView.as_view(), name="jwt-create"),
    path("auth/jwt/refresh/", TokenRefresh, name="jwt-refresh"),
    re_path(r"^auth/jwt/refresh/?$", TokenRefresh),  # для совместимости с/без trailing slash

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

    # Маркетинг: cookie consent, аналитика
    path("marketing/", include("apps.marketing.urls")),
]

