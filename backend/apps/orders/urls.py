from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CartViewSet, OrderViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='orders')

urlpatterns = [
    path('', include(router.urls)),
]
