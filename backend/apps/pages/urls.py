"""URL-конфигурация для приложения pages.

Маршрут: /api/pages/<slug>/
"""

from django.urls import path
from .views import PageDetailView, PageListView


urlpatterns = [
    # Возвращает список страниц. Пример: /api/pages/?show_in_footer=1&lang=ru
    path('', PageListView.as_view(), name='page-list'),
    # Возвращает JSON-детали страницы по slug. Пример: /api/pages/delivery/?lang=ru
    path('<slug:slug>/', PageDetailView.as_view(), name='page-detail'),
]
