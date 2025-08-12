"""URL-маршруты для каталога товаров."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, BrandViewSet, ProductViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'products', ProductViewSet, basename='product')

urlpatterns = [
    path('', include(router.urls)),
]
