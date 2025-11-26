from django.urls import path, include, re_path
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
    UserSessionsView,
    AppConfigView,
    SMSSendCodeView,
    SMSVerifyCodeView,
    SocialAuthView
)

# Роутер для ViewSets
router = DefaultRouter(trailing_slash=False)
router.register(r'profile', UserProfileViewSet, basename='user-profile')
router.register(r'addresses', UserAddressViewSet, basename='user-addresses')

urlpatterns = [
    # JWT токены
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Аутентификация
    path('register/', UserRegistrationView.as_view(), name='user-register'),
    re_path(r'^register$', UserRegistrationView.as_view(), name='user-register-noslash'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    re_path(r'^login$', UserLoginView.as_view(), name='user-login-noslash'),
    path('logout/', UserLogoutView.as_view(), name='user-logout'),
    re_path(r'^logout$', UserLogoutView.as_view(), name='user-logout-noslash'),
    
    # SMS авторизация (в разработке)
    path('sms/send-code/', SMSSendCodeView.as_view(), name='sms-send-code'),
    path('sms/verify/', SMSVerifyCodeView.as_view(), name='sms-verify'),
    
    # Социальные сети (в разработке)
    path('social-auth/', SocialAuthView.as_view(), name='social-auth'),
    
    # Подтверждение email
    path('verify-email/', UserEmailVerificationView.as_view(), name='user-verify-email'),
    re_path(r'^verify-email$', UserEmailVerificationView.as_view(), name='user-verify-email-noslash'),
    
    # Смена пароля
    path('change-password/', UserPasswordChangeView.as_view(), name='user-change-password'),
    re_path(r'^change-password$', UserPasswordChangeView.as_view(), name='user-change-password-noslash'),
    
    # Статистика
    path('stats/', UserStatsView.as_view(), name='user-stats'),
    
    # Сессии
    path('sessions/', UserSessionsView.as_view(), name='user-sessions'),
    path('sessions/<int:session_id>/', UserSessionsView.as_view(), name='user-session-detail'),
    
    # Конфигурация приложения
    path('config/', AppConfigView.as_view(), name='app-config'),
    
    # ViewSets
    path('', include(router.urls)),

    # Дублируем list-эндпоинт профиля без завершающего слэша, т.к. APPEND_SLASH=False
    re_path(r'^profile$', UserProfileViewSet.as_view({'get': 'list'}), name='user-profile-list-noslash'),
]
