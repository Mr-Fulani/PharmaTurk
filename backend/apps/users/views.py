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
import uuid

from .models import User, UserProfile, UserAddress, UserSession
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    UserAddressSerializer, UserSerializer, UserPasswordChangeSerializer,
    UserEmailVerificationSerializer, UserSessionSerializer, UserStatsSerializer,
    SMSSendCodeSerializer, SMSVerifyCodeSerializer, SocialAuthSerializer,
    PublicUserProfileSerializer
)


def create_user_session(user, request):
    """Создание сессии пользователя"""
    # Генерируем уникальный session_key если его нет
    session_key = request.session.session_key
    if not session_key:
        session_key = str(uuid.uuid4())
    
    # Проверяем, не существует ли уже сессия с таким ключом
    if not UserSession.objects.filter(session_key=session_key).exists():
        UserSession.objects.create(
            user=user,
            session_key=session_key,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            expires_at=timezone.now() + timedelta(days=30)
        )


def get_client_ip(request):
    """Получение IP адреса клиента"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


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
            create_user_session(user, request)
            
            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': _('Пользователь успешно зарегистрирован')
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            user.last_login_ip = get_client_ip(request)
            user.save()
            
            # Генерируем JWT токены
            refresh = RefreshToken.for_user(user)
            
            # Создаем сессию
            create_user_session(user, request)
            
            return Response({
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                },
                'message': _('Успешный вход')
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        summary="Получить полную информацию о текущем пользователе",
        description="Получение полной информации о текущем пользователе, включая профиль и статистику",
        responses={200: UserSerializer}
    )
    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Получение полной информации о текущем пользователе"""
        serializer = UserSerializer(request.user, context={'request': request})
        return Response(serializer.data)
    
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
        
        serializer = self.get_serializer(profile, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        summary="Список профилей текущего пользователя",
        description="Возвращает массив с одним профилем пользователя; если профиль отсутствует — создаёт его",
        responses={200: UserProfileSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """Список профилей (создаёт при отсутствии)"""
        profile = self.get_queryset().first()
        if not profile:
            profile = UserProfile.objects.create(user=request.user)
        serializer = self.get_serializer(profile, context={'request': request})
        return Response([serializer.data])
    
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
        
        serializer = self.get_serializer(profile, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @extend_schema(
        summary="Загрузить аватар",
        description="Загрузка аватара пользователя",
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'avatar': {'type': 'string', 'format': 'binary'}
                }
            }
        },
        responses={200: UserProfileSerializer}
    )
    @action(detail=False, methods=['post'], url_path='upload-avatar')
    def upload_avatar(self, request):
        """Загрузка аватара"""
        profile = self.get_queryset().first()
        if not profile:
            profile = UserProfile.objects.create(user=request.user)
        
        if 'avatar' not in request.FILES:
            return Response({'error': 'Файл аватара не предоставлен'}, status=status.HTTP_400_BAD_REQUEST)
        
        avatar_file = request.FILES['avatar']
        
        # Валидация размера файла (максимум 5MB)
        if avatar_file.size > 5 * 1024 * 1024:
            return Response({'error': 'Размер файла не должен превышать 5MB'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Валидация типа файла
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if avatar_file.content_type not in allowed_types:
            return Response({'error': 'Недопустимый тип файла. Разрешены: JPEG, PNG, GIF, WebP'}, status=status.HTTP_400_BAD_REQUEST)
        
        profile.avatar = avatar_file
        profile.save()
        
        serializer = self.get_serializer(profile, context={'request': request})
        return Response(serializer.data)


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


class AppConfigView(APIView):
    """
    Конфигурация приложения для мобильных клиентов
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Получить конфигурацию приложения",
        description="Получение поддерживаемых языков, валют и настроек приложения",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "languages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"},
                                "native_name": {"type": "string"}
                            }
                        }
                    },
                    "currencies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"},
                                "symbol": {"type": "string"}
                            }
                        }
                    },
                    "current_language": {"type": "string"},
                    "current_currency": {"type": "string"},
                    "is_mobile": {"type": "boolean"},
                    "platform": {"type": "string"},
                    "version": {"type": "string"}
                }
            }
        }
    )
    def get(self, request):
        """Получение конфигурации приложения"""
        from django.conf import settings
        
        # Поддерживаемые языки
        languages = [
            {
                'code': 'en',
                'name': 'English',
                'native_name': 'English'
            },
            {
                'code': 'ru',
                'name': 'Russian',
                'native_name': 'Русский'
            },
            {
                'code': 'tr',
                'name': 'Turkish',
                'native_name': 'Türkçe'
            }
        ]
        
        # Поддерживаемые валюты
        currencies = [
            {
                'code': 'USD',
                'name': 'US Dollar',
                'symbol': '$'
            },
            {
                'code': 'RUB',
                'name': 'Russian Ruble',
                'symbol': '₽'
            },
            {
                'code': 'EUR',
                'name': 'Euro',
                'symbol': '€'
            },
            {
                'code': 'TRY',
                'name': 'Turkish Lira',
                'symbol': '₺'
            }
        ]
        
        # Текущий язык и валюта
        current_language = getattr(request, 'LANGUAGE_CODE', settings.LANGUAGE_CODE)
        current_currency = 'USD'  # По умолчанию
        
        # Если пользователь аутентифицирован, используем его настройки
        if hasattr(request, 'user') and request.user.is_authenticated:
            current_currency = request.user.currency
        
        config = {
            'languages': languages,
            'current_language': current_language,
            'currencies': currencies,
            'current_currency': current_currency,
            'is_mobile': getattr(request, 'is_mobile', False),
            'platform': getattr(request, 'platform', 'web'),
            'version': '1.0.0'
        }
        
        return Response(config)


class SMSSendCodeView(APIView):
    """
    Отправка SMS кода на номер телефона.
    TODO: Реализовать после интеграции SMS провайдера.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Отправить SMS код",
        description="Отправка SMS кода на номер телефона для входа",
        request=SMSSendCodeSerializer,
        responses={
            200: {"description": "Код отправлен"},
            400: "Ошибка валидации"
        }
    )
    def post(self, request):
        """Отправка SMS кода"""
        serializer = SMSSendCodeSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            
            # TODO: Реализовать отправку SMS
            # from .sms_auth import send_sms_code
            # verification = send_sms_code(phone_number)
            
            return Response({
                'message': _('SMS код будет отправлен в ближайшее время'),
                'phone_number': phone_number,
                'note': 'Функционал находится в разработке'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SMSVerifyCodeView(APIView):
    """
    Проверка SMS кода и вход/регистрация пользователя.
    TODO: Реализовать после интеграции SMS провайдера.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Войти по SMS коду",
        description="Проверка SMS кода и аутентификация пользователя",
        request=SMSVerifyCodeSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "user": {"type": "object"},
                    "tokens": {"type": "object"},
                    "message": {"type": "string"}
                }
            },
            400: "Ошибка валидации"
        }
    )
    def post(self, request):
        """Проверка SMS кода и вход"""
        serializer = SMSVerifyCodeSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            code = serializer.validated_data['code']
            
            # TODO: Реализовать проверку кода и вход
            # from .sms_auth import verify_sms_code
            # success, verification = verify_sms_code(phone_number, code)
            # if success:
            #     # Найти или создать пользователя
            #     user, created = User.objects.get_or_create(
            #         phone_number=phone_number,
            #         defaults={'email': f'{phone_number}@sms.user', 'username': phone_number}
            #     )
            #     # Генерируем токены и возвращаем
            #     ...
            
            return Response({
                'message': _('Вход по SMS будет доступен в ближайшее время'),
                'note': 'Функционал находится в разработке'
            }, status=status.HTTP_501_NOT_IMPLEMENTED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SocialAuthView(APIView):
    """
    Авторизация через социальные сети.
    TODO: Реализовать после интеграции OAuth провайдеров.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Войти через соцсеть",
        description="Авторизация через Google, Facebook, VK, Yandex или Apple",
        request=SocialAuthSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "user": {"type": "object"},
                    "tokens": {"type": "object"},
                    "message": {"type": "string"}
                }
            },
            400: "Ошибка валидации"
        }
    )
    def post(self, request):
        """Авторизация через соцсеть"""
        serializer = SocialAuthSerializer(data=request.data)
        if serializer.is_valid():
            provider = serializer.validated_data['provider']
            access_token = serializer.validated_data['access_token']
            
            # TODO: Реализовать OAuth авторизацию
            # from .social_auth import authenticate_social_user
            # user = authenticate_social_user(provider, access_token)
            # if user:
            #     # Генерируем токены и возвращаем
            #     ...
            
            return Response({
                'message': _('Авторизация через соцсети будет доступна в ближайшее время'),
                'provider': provider,
                'note': 'Функционал находится в разработке'
            }, status=status.HTTP_501_NOT_IMPLEMENTED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PublicUserProfileView(APIView):
    """
    Публичный профиль пользователя
    """
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="Получить публичный профиль пользователя",
        description="Получение публичного профиля пользователя по username или по ID отзыва",
        parameters=[
            OpenApiParameter(
                name='username',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Username пользователя',
                required=False
            ),
            OpenApiParameter(
                name='testimonial_id',
                type=int,
                location=OpenApiParameter.QUERY,
                description='ID отзыва для поиска пользователя',
                required=False
            ),
        ],
        responses={
            200: PublicUserProfileSerializer,
            404: "Пользователь не найден или профиль не публичный"
        }
    )
    def get(self, request):
        """Получение публичного профиля пользователя"""
        username = request.query_params.get('username')
        testimonial_id = request.query_params.get('testimonial_id')
        
        user = None
        
        # Поиск по testimonial_id
        if testimonial_id:
            try:
                from apps.feedback.models import Testimonial
                testimonial = Testimonial.objects.get(id=testimonial_id, is_active=True)
                if testimonial.user:
                    user = testimonial.user
            except Testimonial.DoesNotExist:
                pass
        
        # Поиск по username
        if not user and username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                pass
        
        if not user:
            return Response(
                {'error': 'Пользователь не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Получаем профиль
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'Профиль не найден'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Проверяем, является ли профиль публичным
        # Если это текущий пользователь (и он аутентифицирован), показываем профиль в любом случае
        is_own_profile = request.user.is_authenticated and request.user == user
        
        # Отладочная информация
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f'Public profile check: user={user.username}, is_public_profile={profile.is_public_profile}, is_own_profile={is_own_profile}, request_user={request.user}')
        
        if not profile.is_public_profile and not is_own_profile:
            return Response(
                {'error': 'Профиль не является публичным'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Передаем testimonial_id в контекст сериализатора для получения аватара из отзыва
        serializer = PublicUserProfileSerializer(
            profile,
            context={
                'request': request,
                'testimonial_id': testimonial_id
            }
        )
        return Response(serializer.data)
