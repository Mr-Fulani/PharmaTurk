from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from .models import User, UserProfile, UserAddress, UserSession
from django.utils import timezone


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
        """Проверка совпадения паролей"""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(_("Пароли не совпадают"))
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
        
        # Создаем профиль пользователя
        UserProfile.objects.create(user=user)
        
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Сериализатор для входа пользователей
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        """Проверка учетных данных"""
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(request=self.context.get('request'),
                              username=email, password=password)
            if not user:
                raise serializers.ValidationError(_("Неверные учетные данные"))
            if not user.is_active:
                raise serializers.ValidationError(_("Аккаунт заблокирован"))
            attrs['user'] = user
        else:
            raise serializers.ValidationError(_("Необходимо указать email и пароль"))
        
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Сериализатор для профиля пользователя
    """
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'user_email', 'user_username',
            'first_name', 'last_name', 'middle_name',
            'country', 'city', 'postal_code', 'address',
            'avatar', 'bio',
            'is_public_profile', 'show_email', 'show_phone',
            'total_orders', 'total_spent',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['total_orders', 'total_spent', 'created_at', 'updated_at']


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


class UserSerializer(serializers.ModelSerializer):
    """
    Сериализатор для основной информации пользователя
    """
    profile = UserProfileSerializer(read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'birth_date', 'is_verified',
            'language', 'currency',
            'email_notifications', 'telegram_notifications', 'push_notifications',
            'telegram_username',
            'profile',
            'date_joined', 'last_login'
        ]
        read_only_fields = ['id', 'is_verified', 'date_joined', 'last_login']


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
