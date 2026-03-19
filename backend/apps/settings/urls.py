"""URL-маршруты для настроек сайта."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import FooterSettingsViewSet

# Роутер для настроек футера
router = DefaultRouter(trailing_slash=True)
router.register(r'footer-settings', FooterSettingsViewSet, basename='footer-settings')

urlpatterns = [
    path('', include(router.urls)),
]

