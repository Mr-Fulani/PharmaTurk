"""Глобальные URL-маршруты проекта.

Включает OpenAPI-схему и Swagger UI, а также метрики Prometheus.
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
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
    path('api/users/', include('apps.users.urls')),
    path('api/orders/', include('apps.orders.urls')),
    path('api/favorites/', include('apps.favorites.urls')),
    path('api/feedback/', include('apps.feedback.urls')),
]

# Раздача медиа файлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

