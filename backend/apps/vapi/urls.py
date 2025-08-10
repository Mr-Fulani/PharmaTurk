from django.urls import path

from .views import (
    VapiPullView,
    VapiProductDetailsView,
    VapiSearchView,
    VapiSyncCategoriesView,
    VapiFullSyncView
)


urlpatterns = [
    # Основная загрузка товаров
    path("pull/", VapiPullView.as_view(), name="vapi-pull"),
    
    # Загрузка деталей товара
    path("product-details/", VapiProductDetailsView.as_view(), name="vapi-product-details"),
    
    # Поиск товаров
    path("search/", VapiSearchView.as_view(), name="vapi-search"),
    
    # Синхронизация справочников
    path("sync-categories/", VapiSyncCategoriesView.as_view(), name="vapi-sync-categories"),
    
    # Полная синхронизация каталога
    path("full-sync/", VapiFullSyncView.as_view(), name="vapi-full-sync"),
]

