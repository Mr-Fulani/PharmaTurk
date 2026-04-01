"""URL-маршруты для каталога товаров."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet, BrandViewSet, ProductViewSet, FavoriteViewSet,
    ClothingCategoryViewSet, ClothingProductViewSet,
    ShoeCategoryViewSet, ShoeProductViewSet,
    ElectronicsCategoryViewSet, ElectronicsProductViewSet,
    FurnitureProductViewSet,
    JewelryProductViewSet,
    BookProductViewSet,
    PerfumeryProductViewSet,
    MedicineProductViewSet,
    SupplementProductViewSet,
    MedicalEquipmentProductViewSet,
    TablewareProductViewSet,
    AccessoryProductViewSet,
    IncenseProductViewSet,
    ServiceViewSet,
    BannerViewSet,
    SportsProductViewSet,
    AutoPartProductViewSet,
    HeadwearProductViewSet, UnderwearProductViewSet, IslamicClothingProductViewSet,
    proxy_image,
    proxy_media,
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

# Роутер для украшений
jewelry_router = DefaultRouter(trailing_slash=False)
jewelry_router.register(r'products', JewelryProductViewSet, basename='jewelry-product')

# Роутер для книг
books_router = DefaultRouter(trailing_slash=False)
books_router.register(r'products', BookProductViewSet, basename='book-product')

# Роутер для парфюмерии
perfumery_router = DefaultRouter(trailing_slash=False)
perfumery_router.register(r'products', PerfumeryProductViewSet, basename='perfumery-product')

# Роутер для медикаментов (домен)
medicines_router = DefaultRouter(trailing_slash=False)
medicines_router.register(r'products', MedicineProductViewSet, basename='medicine-product')

# Роутер для БАДов
supplements_router = DefaultRouter(trailing_slash=False)
supplements_router.register(r'products', SupplementProductViewSet, basename='supplement-product')

# Роутер для медтехники
medical_equipment_router = DefaultRouter(trailing_slash=False)
medical_equipment_router.register(r'products', MedicalEquipmentProductViewSet, basename='medical-equipment-product')

# Роутер для посуды
tableware_router = DefaultRouter(trailing_slash=False)
tableware_router.register(r'products', TablewareProductViewSet, basename='tableware-product')

# Роутер для аксессуаров
accessories_router = DefaultRouter(trailing_slash=False)
accessories_router.register(r'products', AccessoryProductViewSet, basename='accessory-product')

# Роутер для благовоний
incense_router = DefaultRouter(trailing_slash=False)
incense_router.register(r'products', IncenseProductViewSet, basename='incense-product')

# Роутер для спорттоваров
sports_router = DefaultRouter(trailing_slash=False)
sports_router.register(r'products', SportsProductViewSet, basename='sports-product')

# Роутер для автозапчастей
auto_parts_router = DefaultRouter(trailing_slash=False)
auto_parts_router.register(r'products', AutoPartProductViewSet, basename='auto-part-product')

# Роутер для услуг
services_router = DefaultRouter(trailing_slash=False)
services_router.register(r'services', ServiceViewSet, basename='service')

# Роутер для головных уборов
headwear_router = DefaultRouter(trailing_slash=False)
headwear_router.register(r'products', HeadwearProductViewSet, basename='headwear-product')

# Роутер для нижнего белья
underwear_router = DefaultRouter(trailing_slash=False)
underwear_router.register(r'products', UnderwearProductViewSet, basename='underwear-product')

# Роутер для исламской одежды
islamic_clothing_router = DefaultRouter(trailing_slash=False)
islamic_clothing_router.register(r'products', IslamicClothingProductViewSet, basename='islamic-clothing-product')

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
    
    # Маршруты для украшений
    path('jewelry/', include(jewelry_router.urls)),
    
    # Маршруты для книг
    path('books/', include(books_router.urls)),
    
    # Маршруты для парфюмерии
    path('perfumery/', include(perfumery_router.urls)),
    
    # Маршруты для медикаментов (домен)
    path('medicines/', include(medicines_router.urls)),
    
    # Маршруты для БАДов
    path('supplements/', include(supplements_router.urls)),
    
    # Маршруты для медтехники
    path('medical-equipment/', include(medical_equipment_router.urls)),
    
    # Маршруты для посуды
    path('tableware/', include(tableware_router.urls)),
    
    # Маршруты для аксессуаров
    path('accessories/', include(accessories_router.urls)),
    
    # Маршруты для благовоний
    path('incense/', include(incense_router.urls)),
    
    # Маршруты для спорттоваров
    path('sports/', include(sports_router.urls)),

    # Маршруты для автозапчастей
    path('auto-parts/', include(auto_parts_router.urls)),

    # Маршруты для услуг
    path('', include(services_router.urls)),

    # Маршруты для новых доменов
    path('headwear/', include(headwear_router.urls)),
    path('underwear/', include(underwear_router.urls)),
    path('islamic-clothing/', include(islamic_clothing_router.urls)),
    
    # Прокси для Instagram/CDN изображений (с/без slash — APPEND_SLASH=False)
    path('proxy-image/', proxy_image, name='proxy_image'),
    path('proxy-image', proxy_image, name='proxy_image_no_slash'),
    # Прокси для R2-медиа (видео/картинки) — устраняет ERR_SSL_PROTOCOL_ERROR
    path('proxy-media/', proxy_media, name='proxy_media'),
    path('proxy-media', proxy_media, name='proxy_media_no_slash'),
]
