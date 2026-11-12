"""URL-маршруты для настроек сайта."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import FooterSettingsViewSet, SiteAppearanceView

# Роутер для настроек футера
router = DefaultRouter(trailing_slash=False)
router.register(r'footer-settings', FooterSettingsViewSet, basename='footer-settings')

urlpatterns = [
    path('appearance', SiteAppearanceView.as_view(), name='site-appearance'),
    path('', include(router.urls)),
]

