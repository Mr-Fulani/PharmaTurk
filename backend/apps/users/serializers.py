from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from .models import User, UserAddress, UserSession
from django.utils import timezone
from urllib.parse import urlparse, quote


def _build_proxy_media_url(file_field, request):
    if not file_field:
        return None
    path = getattr(file_field, 'name', None)
    if not path:
        url = getattr(file_field, 'url', None)
        if not url:
            return None
        parsed = urlparse(url)
        path = parsed.path.lstrip('/')
        media_prefix = (settings.MEDIA_URL or '').lstrip('/')
        if media_prefix and path.startswith(media_prefix):
            path = path[len(media_prefix):]
    if path.startswith('media/'):
        path = path[len('media/'):]
    if request:
        base = request.build_absolute_uri('/').rstrip('/')
        return f"{base}/api/catalog/proxy-media/?path={quote(path)}"
    return f"/api/catalog/proxy-media/?path={quote(path)}"


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Сериализатор для регистрации пользователей
    """
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone_number'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': True},
        }
    
    def validate(self, attrs):
        """Проверка пароля и совпадения"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(_("Пароли не совпадают"))

        password = attrs['password']
        # Базовые требования к сложности пароля: минимум 8 символов, буквы и цифры
        has_letter = any(ch.isalpha() for ch in password)
        has_digit = any(ch.isdigit() for ch in password)
        if not (has_letter and has_digit):
            raise serializers.ValidationError(_("Пароль должен содержать минимум 8 символов, включать буквы и цифры"))
        return attrs
    
    def validate_email(self, value):
        """Проверка уникальности email"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(_("Пользователь с таким email уже существует"))
        return value
    
    def validate_username(self, value):
        """Проверка уникальности username"""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(_("Пользователь с таким именем уже существует"))
        return value
    
    def create(self, validated_data):
        """Создание пользователя"""
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Сериализатор для входа пользователей.
    Поддерживает вход по email, username или телефону.
    """
    # Разрешаем вводить email, username или телефон в одно поле
    email = serializers.CharField(help_text="Email, имя пользователя или номер телефона")
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        """Проверка учетных данных"""
        login_value = attrs.get('email')
        password = attrs.get('password')
        
        if login_value and password:
            request = self.context.get('request')
            # Используем кастомный бэкенд аутентификации, который поддерживает
            # email, username и телефон
            user = authenticate(request=request, username=login_value, password=password)
            
            if not user:
                raise serializers.ValidationError(_("Неверные учетные данные"))
            if not user.is_active:
                raise serializers.ValidationError(_("Аккаунт заблокирован"))
            attrs['user'] = user
        else:
            raise serializers.ValidationError(_("Необходимо указать email/имя пользователя/телефон и пароль"))
        
        return attrs


class SMSSendCodeSerializer(serializers.Serializer):
    """
    Сериализатор для отправки SMS кода.
    TODO: Реализовать после интеграции SMS провайдера.
    """
    phone_number = serializers.CharField(
        max_length=17,
        help_text="Номер телефона в формате +79991234567"
    )
    
    def validate_phone_number(self, value):
        """Валидация номера телефона"""
        from django.core.validators import RegexValidator
        from django.core.exceptions import ValidationError
        
        phone_regex = RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Номер телефона должен быть в формате: '+999999999'. До 15 цифр."
        )
        try:
            phone_regex(value)
        except ValidationError:
            raise serializers.ValidationError("Неверный формат номера телефона")
        return value


class SMSVerifyCodeSerializer(serializers.Serializer):
    """
    Сериализатор для проверки SMS кода и входа.
    TODO: Реализовать после интеграции SMS провайдера.
    """
    phone_number = serializers.CharField(max_length=17)
    code = serializers.CharField(max_length=6, min_length=6)
    
    def validate_code(self, value):
        """Валидация кода (только цифры)"""
        if not value.isdigit():
            raise serializers.ValidationError("Код должен содержать только цифры")
        return value


class SocialAuthSerializer(serializers.Serializer):
    """
    Сериализатор для авторизации через социальные сети.
    TODO: Реализовать после интеграции OAuth провайдеров.
    """
    provider = serializers.ChoiceField(
        choices=['google', 'facebook', 'vk', 'yandex', 'apple'],
        help_text="Провайдер социальной сети"
    )
    access_token = serializers.CharField(
        help_text="Access token от провайдера"
    )
    id_token = serializers.CharField(
        required=False,
        help_text="ID token (для некоторых провайдеров)"
    )


class UserSerializer(serializers.ModelSerializer):
    """
    Сериализатор для основной информации пользователя
    """
    user_email = serializers.EmailField(source='email', read_only=True)
    user_username = serializers.CharField(source='username', read_only=True)
    avatar_url = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'user_email', 'username', 'user_username',
            'first_name', 'last_name', 'middle_name',
            'phone_number', 'birth_date', 'is_verified',
            'language', 'currency',
            'email_notifications', 'telegram_notifications', 'push_notifications',
            'telegram_username', 'whatsapp_phone',
            'country', 'city', 'postal_code', 'address',
            'avatar', 'avatar_url', 'bio',
            'is_public_profile', 'show_email', 'show_phone',
            'date_joined', 'last_login', 'created_at', 'updated_at',
            'total_orders', 'total_spent',
        ]
        read_only_fields = [
            'id', 'is_verified', 'date_joined', 'last_login',
            'created_at', 'updated_at', 'total_orders', 'total_spent',
            'user_email', 'user_username'
        ]
    
    def get_avatar_url(self, obj):
        """Получение URL аватара"""
        if obj.avatar:
            request = self.context.get('request')
            return _build_proxy_media_url(obj.avatar, request)
        return None
    
    def get_total_orders(self, obj):
        """Расчет общего количества заказов пользователя"""
        import logging
        logger = logging.getLogger(__name__)
        from apps.orders.models import Order
        
        # Считаем все заказы пользователя (исключая отмененные)
        count = Order.objects.filter(
            user=obj
        ).exclude(
            status='cancelled'
        ).count()
        
        # Логирование для отладки
        all_orders_count = Order.objects.filter(user=obj).count()
        
        user_email = obj.email
        user_username = obj.username
        
        orders_by_email = Order.objects.filter(contact_email=user_email).exclude(status='cancelled').count() if user_email else 0
        orders_without_user = Order.objects.filter(user__isnull=True, contact_email=user_email).exclude(status='cancelled').count() if user_email else 0
        
        if user_email:
            all_orders_with_email = Order.objects.filter(contact_email=user_email).exclude(status='cancelled')
            orders_info = []
            for order in all_orders_with_email:
                orders_info.append(f"order_id={order.id}, number={order.number}, user_id={order.user.id if order.user else None}, user_username={order.user.username if order.user else None}, contact_name={order.contact_name}")
            if orders_info:
                logger.info(f'All orders with email {user_email}: {"; ".join(orders_info)}')
        
        if user_username:
            orders_by_name = Order.objects.filter(
                contact_name__icontains=user_username
            ).exclude(status='cancelled').exclude(user=obj)
            if orders_by_name.exists():
                orders_by_name_info = []
                for order in orders_by_name:
                    orders_by_name_info.append(f"order_id={order.id}, number={order.number}, user_id={order.user.id if order.user else None}, user_username={order.user.username if order.user else None}, contact_email={order.contact_email}, contact_name={order.contact_name}")
                logger.info(f'Orders with username "{user_username}" in contact_name (not linked to this user): {"; ".join(orders_by_name_info)}')
        
        logger.info(
            f'UserSerializer.get_total_orders: user={user_username} (id={obj.id}), '
            f'email={user_email}, all_orders={all_orders_count}, non_cancelled={count}, '
            f'orders_by_email={orders_by_email}, orders_without_user={orders_without_user}'
        )
        
        return count
    
    def get_total_spent(self, obj):
        """Расчет общей суммы потраченных денег"""
        from django.db.models import Sum
        from apps.orders.models import Order
        
        result = Order.objects.filter(
            user=obj
        ).exclude(
            status='cancelled'
        ).aggregate(
            total=Sum('total_amount')
        )
        total = result['total'] or 0
        return str(total)


class UserAddressSerializer(serializers.ModelSerializer):
    """
    Сериализатор для адресов пользователя
    """
    class Meta:
        model = UserAddress
        fields = [
            'id', 'address_type', 'contact_name', 'contact_phone',
            'country', 'region', 'city', 'postal_code',
            'street', 'house', 'apartment',
            'entrance', 'floor', 'intercom', 'comment',
            'is_default', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def validate(self, attrs):
        """Проверка адреса"""
        user = self.context['request'].user
        
        # Если это адрес по умолчанию, сбрасываем другие
        if attrs.get('is_default', False):
            UserAddress.objects.filter(user=user, is_default=True).update(is_default=False)
        
        return attrs


class UserPasswordChangeSerializer(serializers.Serializer):
    """
    Сериализатор для смены пароля
    """
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        """Проверка паролей"""
        user = self.context['request'].user
        
        # Проверяем текущий пароль
        if not user.check_password(attrs['current_password']):
            raise serializers.ValidationError(_("Неверный текущий пароль"))
        
        # Проверяем совпадение новых паролей
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(_("Новые пароли не совпадают"))
        
        return attrs


class UserEmailVerificationSerializer(serializers.Serializer):
    """
    Сериализатор для подтверждения email
    """
    email = serializers.EmailField()
    verification_code = serializers.CharField(max_length=6)
    
    def validate(self, attrs):
        """Проверка кода подтверждения"""
        try:
            user = User.objects.get(email=attrs['email'])
            if user.verification_code != attrs['verification_code']:
                raise serializers.ValidationError(_("Неверный код подтверждения"))
            if user.verification_code_expires and user.verification_code_expires < timezone.now():
                raise serializers.ValidationError(_("Код подтверждения истек"))
            attrs['user'] = user
        except User.DoesNotExist:
            raise serializers.ValidationError(_("Пользователь не найден"))
        
        return attrs


class UserSessionSerializer(serializers.ModelSerializer):
    """
    Сериализатор для сессий пользователя
    """
    class Meta:
        model = UserSession
        fields = [
            'id', 'session_key', 'ip_address', 'user_agent',
            'country', 'city', 'is_active',
            'created_at', 'last_activity', 'expires_at'
        ]
        read_only_fields = ['session_key', 'ip_address', 'user_agent', 'country', 'city']


class UserStatsSerializer(serializers.Serializer):
    """
    Сериализатор для статистики пользователя
    """
    total_orders = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=10, decimal_places=2)
    favorite_products_count = serializers.IntegerField()
    active_addresses_count = serializers.IntegerField()
    last_order_date = serializers.DateTimeField(allow_null=True)
    registration_date = serializers.DateTimeField()
    days_since_registration = serializers.IntegerField()


class PublicUserProfileSerializer(serializers.ModelSerializer):
    """
    Сериализатор для публичного профиля пользователя
    """
    user_username = serializers.CharField(source='username', read_only=True)
    avatar_url = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()
    testimonial_id = serializers.SerializerMethodField()
    social_links = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'user_username',
            'first_name',
            'last_name',
            'middle_name',
            'avatar_url',
            'bio',
            'whatsapp_phone',
            'telegram_username',
            'country',
            'city',
            'testimonial_id',
            'total_orders',
            'social_links',
        ]
    
    def get_avatar_url(self, obj):
        """Получение URL аватара из профиля или из отзыва"""
        request = self.context.get('request')
        
        if obj.avatar:
            return _build_proxy_media_url(obj.avatar, request)
        
        from apps.feedback.models import Testimonial
        testimonial_id = self.context.get('testimonial_id')
        
        if testimonial_id:
            try:
                testimonial_id_int = int(testimonial_id) if isinstance(testimonial_id, str) else testimonial_id
                testimonial = Testimonial.objects.filter(
                    id=testimonial_id_int,
                    user=obj,
                    is_active=True,
                    author_avatar__isnull=False
                ).first()
                if testimonial and testimonial.author_avatar:
                    return _build_proxy_media_url(testimonial.author_avatar, request)
            except (ValueError, TypeError):
                pass
        
        try:
            testimonial = Testimonial.objects.filter(
                user=obj,
                is_active=True,
                author_avatar__isnull=False
            ).first()
            if testimonial and testimonial.author_avatar:
                return _build_proxy_media_url(testimonial.author_avatar, request)
        except Exception:
            pass
        return None
    
    def get_total_orders(self, obj):
        """Расчет общего количества заказов пользователя"""
        import logging
        logger = logging.getLogger(__name__)
        from apps.orders.models import Order
        
        count = Order.objects.filter(
            user=obj
        ).exclude(
            status='cancelled'
        ).count()
        
        all_orders_count = Order.objects.filter(user=obj).count()
        
        user_email = obj.email
        user_username = obj.username
        
        orders_by_email = Order.objects.filter(contact_email=user_email).exclude(status='cancelled').count() if user_email else 0
        orders_without_user = Order.objects.filter(user__isnull=True, contact_email=user_email).exclude(status='cancelled').count() if user_email else 0
        
        if user_email:
            all_orders_with_email = Order.objects.filter(contact_email=user_email).exclude(status='cancelled')
            orders_info = []
            for order in all_orders_with_email:
                orders_info.append(f"order_id={order.id}, number={order.number}, user_id={order.user.id if order.user else None}, user_username={order.user.username if order.user else None}, contact_name={order.contact_name}")
            if orders_info:
                logger.info(f'All orders with email {user_email}: {"; ".join(orders_info)}')
        
        if user_username:
            orders_by_name = Order.objects.filter(
                contact_name__icontains=user_username
            ).exclude(status='cancelled').exclude(user=obj)
            if orders_by_name.exists():
                orders_by_name_info = []
                for order in orders_by_name:
                    orders_by_name_info.append(f"order_id={order.id}, number={order.number}, user_id={order.user.id if order.user else None}, user_username={order.user.username if order.user else None}, contact_email={order.contact_email}, contact_name={order.contact_name}")
                logger.info(f'Orders with username "{user_username}" in contact_name (not linked to this user): {"; ".join(orders_by_name_info)}')
        
        logger.info(
            f'PublicUserProfileSerializer.get_total_orders: user={user_username} (id={obj.id}), '
            f'email={user_email}, all_orders={all_orders_count}, non_cancelled={count}, '
            f'orders_by_email={orders_by_email}, orders_without_user={orders_without_user}'
        )
        
        return count
    
    def get_testimonial_id(self, obj):
        """Получение ID отзыва пользователя, если есть"""
        from apps.feedback.models import Testimonial
        testimonial = Testimonial.objects.filter(user=obj, is_active=True).first()
        return testimonial.id if testimonial else None
    
    def get_social_links(self, obj):
        """Получение ссылок на социальные сети"""
        links = {}
        
        if obj.telegram_username:
            links['telegram'] = f"https://t.me/{obj.telegram_username.lstrip('@')}"
        
        if obj.whatsapp_phone:
            links['whatsapp'] = f"https://wa.me/{obj.whatsapp_phone.lstrip('+')}"
        
        if obj.google_id:
            links['google'] = f"https://plus.google.com/{obj.google_id}"
        if obj.facebook_id:
            links['facebook'] = f"https://facebook.com/{obj.facebook_id}"
        if obj.vk_id:
            links['vk'] = f"https://vk.com/id{obj.vk_id}"
        if obj.yandex_id:
            links['yandex'] = f"https://yandex.ru/profile/{obj.yandex_id}"
        
        return links
