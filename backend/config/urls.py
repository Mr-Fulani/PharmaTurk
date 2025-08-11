"""Глобальные URL-маршруты проекта.

Включает OpenAPI-схему и Swagger UI, а также метрики Prometheus.
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    # Админка
    path("admin/", admin.site.urls),

    # OpenAPI / Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),

    # Метрики Prometheus (включаем корневые url, чтобы путь был /metrics)
    path("", include("django_prometheus.urls")),

    # Основной API
    path("api/", include("api.urls")),
]

