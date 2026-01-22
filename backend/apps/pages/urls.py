"""URL-конфигурация для приложения pages.

Маршрут: /api/pages/<slug>/
"""

from django.urls import path
from .views import PageDetailView


urlpatterns = [
    # Возвращает JSON-детали страницы по slug. Пример: /api/pages/delivery/?lang=ru
    path('<slug:slug>/', PageDetailView.as_view(), name='page-detail'),
]
