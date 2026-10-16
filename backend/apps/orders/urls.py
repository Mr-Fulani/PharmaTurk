from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CartViewSet, OrderViewSet, SourcingRequestCreateView

router = DefaultRouter(trailing_slash=False)
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='orders')

urlpatterns = [
    path('sourcing-requests/', SourcingRequestCreateView.as_view(), name='sourcing-request-create'),
    path('sourcing-requests', SourcingRequestCreateView.as_view(), name='sourcing-request-create-no-slash'),
    path('', include(router.urls)),
]
