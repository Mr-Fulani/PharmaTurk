"""URL-маршруты для каталога товаров."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet, BrandViewSet, ProductViewSet, FavoriteViewSet,
    ClothingCategoryViewSet, ClothingProductViewSet,
    ShoeCategoryViewSet, ShoeProductViewSet,
    ElectronicsCategoryViewSet, ElectronicsProductViewSet,
    FurnitureProductViewSet,
    ServiceViewSet,
    BannerViewSet,
)

# Основной роутер для медикаментов (существующий)
router = DefaultRouter(trailing_slash=False)
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'favorites', FavoriteViewSet, basename='favorite')
router.register(r'banners', BannerViewSet, basename='banner')

# Роутер для одежды
clothing_router = DefaultRouter(trailing_slash=False)
clothing_router.register(r'categories', ClothingCategoryViewSet, basename='clothing-category')
clothing_router.register(r'products', ClothingProductViewSet, basename='clothing-product')

# Роутер для обуви
shoes_router = DefaultRouter(trailing_slash=False)
shoes_router.register(r'categories', ShoeCategoryViewSet, basename='shoe-category')
shoes_router.register(r'products', ShoeProductViewSet, basename='shoe-product')

# Роутер для электроники
electronics_router = DefaultRouter(trailing_slash=False)
electronics_router.register(r'categories', ElectronicsCategoryViewSet, basename='electronics-category')
electronics_router.register(r'products', ElectronicsProductViewSet, basename='electronics-product')

# Роутер для мебели
furniture_router = DefaultRouter(trailing_slash=False)
furniture_router.register(r'products', FurnitureProductViewSet, basename='furniture-product')

# Роутер для услуг
services_router = DefaultRouter(trailing_slash=False)
services_router.register(r'services', ServiceViewSet, basename='service')

urlpatterns = [
    # Основные маршруты для медикаментов
    path('', include(router.urls)),
    
    # Маршруты для одежды
    path('clothing/', include(clothing_router.urls)),
    
    # Маршруты для обуви
    path('shoes/', include(shoes_router.urls)),
    
    # Маршруты для электроники
    path('electronics/', include(electronics_router.urls)),
    
    # Маршруты для мебели
    path('furniture/', include(furniture_router.urls)),
    
    # Маршруты для услуг
    path('', include(services_router.urls)),
]
