from rest_framework import status, generics, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from datetime import timedelta
import random
import string

from .models import User, UserProfile, UserAddress, UserSession
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    UserAddressSerializer, UserSerializer, UserPasswordChangeSerializer,
    UserEmailVerificationSerializer, UserSessionSerializer, UserStatsSerializer
)


class UserRegistrationView(APIView):
    """
    Регистрация нового пользователя
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Регистрация пользователя",
        description="Создание нового аккаунта пользователя",
        request=UserRegistrationSerializer,
        responses={
            201: UserSerializer,
            400: "Ошибка валидации"
        },
        examples=[
            OpenApiExample(
                "Успешная регистрация",
                value={
                    "email": "user@example.com",
                    "username": "user123",
                    "password": "securepass123",
                    "password_confirm": "securepass123",
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "phone_number": "+79001234567"
                }
            )
        ]
    )
    def post(self, request):
        """Регистрация пользователя"""
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Генерируем JWT токены
            refresh = RefreshToken.for_user(user)
            
            # Создаем сессию
            self._create_user_session(user, request)
            
            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': _('Пользователь успешно зарегистрирован')
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def _create_user_session(self, user, request):
        """Создание сессии пользователя"""
        UserSession.objects.create(
            user=user,
            session_key=request.session.session_key or '',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            expires_at=timezone.now() + timedelta(days=30)
        )
    
    def _get_client_ip(self, request):
        """Получение IP адреса клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class UserLoginView(APIView):
    """
    Вход пользователя
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Вход пользователя",
        description="Аутентификация пользователя и получение JWT токенов",
        request=UserLoginSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "user": {"type": "object"},
                    "tokens": {
                        "type": "object",
                        "properties": {
                            "access": {"type": "string"},
                            "refresh": {"type": "string"}
                        }
                    },
                    "message": {"type": "string"}
                }
            },
            400: "Ошибка аутентификации"
        }
    )
    def post(self, request):
        """Вход пользователя"""
        serializer = UserLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Обновляем последний вход
            user.last_login = timezone.now()
            user.last_login_ip = self._get_client_ip(request)
            user.save()
            
            # Генерируем JWT токены
            refresh = RefreshToken.for_user(user)
            
            # Создаем сессию
            self._create_user_session(user, request)
            
            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': _('Успешный вход')
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def _create_user_session(self, user, request):
        """Создание сессии пользователя"""
        UserSession.objects.create(
            user=user,
            session_key=request.session.session_key or '',
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            expires_at=timezone.now() + timedelta(days=30)
        )
    
    def _get_client_ip(self, request):
        """Получение IP адреса клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class UserLogoutView(APIView):
    """
    Выход пользователя
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="Выход пользователя",
        description="Выход из системы и инвалидация токенов",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                }
            }
        }
    )
    def post(self, request):
        """Выход пользователя"""
        try:
            # Инвалидируем refresh токен
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            # Деактивируем сессии пользователя
            UserSession.objects.filter(
                user=request.user,
                is_active=True
            ).update(is_active=False)
            
            return Response({
                'message': _('Успешный выход из системы')
            })
        except Exception as e:
            return Response({
                'message': _('Ошибка при выходе из системы')
            }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileViewSet(viewsets.ModelViewSet):
    """
    Управление профилем пользователя
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    
    def get_queryset(self):
        """Получение профиля текущего пользователя"""
        return UserProfile.objects.filter(user=self.request.user)
    
    @extend_schema(
        summary="Получить профиль пользователя",
        description="Получение профиля текущего пользователя",
        responses={200: UserProfileSerializer}
    )
    def retrieve(self, request, *args, **kwargs):
        """Получение профиля"""
        profile = self.get_queryset().first()
        if not profile:
            profile = UserProfile.objects.create(user=request.user)
        
        serializer = self.get_serializer(profile)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Обновить профиль пользователя",
        description="Обновление профиля текущего пользователя",
        request=UserProfileSerializer,
        responses={200: UserProfileSerializer}
    )
    def update(self, request, *args, **kwargs):
        """Обновление профиля"""
        profile = self.get_queryset().first()
        if not profile:
            profile = UserProfile.objects.create(user=request.user)
        
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserAddressViewSet(viewsets.ModelViewSet):
    """
    Управление адресами пользователя
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserAddressSerializer
    
    def get_queryset(self):
        """Получение адресов текущего пользователя"""
        return UserAddress.objects.filter(user=self.request.user, is_active=True)
    
    def perform_create(self, serializer):
        """Создание адреса с привязкой к пользователю"""
        serializer.save(user=self.request.user)
    
    @extend_schema(
        summary="Получить адреса пользователя",
        description="Получение списка адресов текущего пользователя",
        responses={200: UserAddressSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Создать адрес",
        description="Создание нового адреса для пользователя",
        request=UserAddressSerializer,
        responses={201: UserAddressSerializer}
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @extend_schema(
        summary="Обновить адрес",
        description="Обновление существующего адреса",
        request=UserAddressSerializer,
        responses={200: UserAddressSerializer}
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @extend_schema(
        summary="Удалить адрес",
        description="Мягкое удаление адреса (деактивация)",
        responses={204: "Адрес успешно удален"}
    )
    def destroy(self, request, *args, **kwargs):
        """Мягкое удаление адреса"""
        address = self.get_object()
        address.is_active = False
        address.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserPasswordChangeView(APIView):
    """
    Смена пароля пользователя
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="Сменить пароль",
        description="Смена пароля текущего пользователя",
        request=UserPasswordChangeSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                }
            },
            400: "Ошибка валидации"
        }
    )
    def post(self, request):
        """Смена пароля"""
        serializer = UserPasswordChangeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            
            return Response({
                'message': _('Пароль успешно изменен')
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserEmailVerificationView(APIView):
    """
    Подтверждение email пользователя
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Подтвердить email",
        description="Подтверждение email с помощью кода верификации",
        request=UserEmailVerificationSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                }
            },
            400: "Ошибка валидации"
        }
    )
    def post(self, request):
        """Подтверждение email"""
        serializer = UserEmailVerificationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            user.is_verified = True
            user.verification_code = ''
            user.verification_code_expires = None
            user.save()
            
            return Response({
                'message': _('Email успешно подтвержден')
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserStatsView(APIView):
    """
    Статистика пользователя
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="Получить статистику пользователя",
        description="Получение статистики текущего пользователя",
        responses={200: UserStatsSerializer}
    )
    def get(self, request):
        """Получение статистики пользователя"""
        user = request.user
        profile = user.profile
        
        # Рассчитываем дни с регистрации
        days_since_registration = (timezone.now() - user.date_joined).days
        
        # TODO: Добавить подсчет избранных товаров и последнего заказа
        # когда будут созданы соответствующие модели
        
        stats = {
            'total_orders': profile.total_orders,
            'total_spent': profile.total_spent,
            'favorite_products_count': 0,  # TODO: реализовать
            'active_addresses_count': user.addresses.filter(is_active=True).count(),
            'last_order_date': None,  # TODO: реализовать
            'registration_date': user.date_joined,
            'days_since_registration': days_since_registration
        }
        
        serializer = UserStatsSerializer(stats)
        return Response(serializer.data)


class UserSessionsView(APIView):
    """
    Управление сессиями пользователя
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="Получить активные сессии",
        description="Получение списка активных сессий пользователя",
        responses={200: UserSessionSerializer(many=True)}
    )
    def get(self, request):
        """Получение активных сессий"""
        sessions = UserSession.objects.filter(
            user=request.user,
            is_active=True
        ).order_by('-last_activity')
        
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Завершить сессию",
        description="Завершение конкретной сессии пользователя",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                }
            }
        }
    )
    def delete(self, request, session_id):
        """Завершение сессии"""
        try:
            session = UserSession.objects.get(
                id=session_id,
                user=request.user,
                is_active=True
            )
            session.is_active = False
            session.save()
            
            return Response({
                'message': _('Сессия успешно завершена')
            })
        except UserSession.DoesNotExist:
            return Response({
                'message': _('Сессия не найдена')
            }, status=status.HTTP_404_NOT_FOUND)
