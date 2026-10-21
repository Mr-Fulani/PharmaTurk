from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .cart_reminder_views import cart_reminder_click, cart_reminder_unsubscribe
from .views import CartViewSet, OrderViewSet, SourcingRequestCreateView

router = DefaultRouter(trailing_slash=False)
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='orders')

urlpatterns = [
    path('sourcing-requests/', SourcingRequestCreateView.as_view(), name='sourcing-request-create'),
    path('sourcing-requests', SourcingRequestCreateView.as_view(), name='sourcing-request-create-no-slash'),
    path('cart-reminders/unsubscribe/', cart_reminder_unsubscribe, name='cart-reminder-unsubscribe'),
    path('cart-reminders/go/', cart_reminder_click, name='cart-reminder-click'),
    path('', include(router.urls)),
]
