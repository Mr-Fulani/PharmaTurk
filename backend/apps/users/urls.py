from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)

from .views import (
    UserRegistrationView,
    UserLoginView,
    UserLogoutView,
    UserProfileViewSet,
    UserAddressViewSet,
    UserPasswordChangeView,
    UserEmailVerificationView,
    UserStatsView,
    UserSessionsView
)

# Роутер для ViewSets
router = DefaultRouter()
router.register(r'profile', UserProfileViewSet, basename='user-profile')
router.register(r'addresses', UserAddressViewSet, basename='user-addresses')

urlpatterns = [
    # JWT токены
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Аутентификация
    path('register/', UserRegistrationView.as_view(), name='user-register'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    path('logout/', UserLogoutView.as_view(), name='user-logout'),
    
    # Подтверждение email
    path('verify-email/', UserEmailVerificationView.as_view(), name='user-verify-email'),
    
    # Смена пароля
    path('change-password/', UserPasswordChangeView.as_view(), name='user-change-password'),
    
    # Статистика
    path('stats/', UserStatsView.as_view(), name='user-stats'),
    
    # Сессии
    path('sessions/', UserSessionsView.as_view(), name='user-sessions'),
    path('sessions/<int:session_id>/', UserSessionsView.as_view(), name='user-session-detail'),
    
    # ViewSets
    path('', include(router.urls)),
]
