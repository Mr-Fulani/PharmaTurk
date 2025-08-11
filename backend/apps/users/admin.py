from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, UserProfile, UserAddress, UserSession


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Админка для модели пользователя."""
    list_display = ('email', 'username', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'is_verified', 'language', 'currency', 'date_joined')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('username', 'first_name', 'last_name', 'phone_number', 'birth_date')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'groups', 'user_permissions'),
        }),
        (_('Settings'), {'fields': ('language', 'currency', 'email_notifications', 'telegram_notifications', 'push_notifications')}),
        (_('Telegram'), {'fields': ('telegram_id', 'telegram_username')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Админка для профиля пользователя."""
    list_display = ('user', 'first_name', 'last_name', 'country', 'city', 'total_orders', 'total_spent')
    list_filter = ('is_public_profile', 'show_email', 'show_phone', 'created_at')
    search_fields = ('user__email', 'user__username', 'first_name', 'last_name', 'country', 'city')
    ordering = ('-created_at',)
    
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'middle_name')}),
        (_('Address'), {'fields': ('country', 'city', 'postal_code', 'address')}),
        (_('Additional'), {'fields': ('avatar', 'bio')}),
        (_('Privacy'), {'fields': ('is_public_profile', 'show_email', 'show_phone')}),
        (_('Statistics'), {'fields': ('total_orders', 'total_spent')}),
    )


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    """Админка для адресов пользователя."""
    list_display = ('user', 'contact_name', 'address_type', 'country', 'city', 'street', 'house', 'is_default', 'is_active')
    list_filter = ('address_type', 'is_default', 'is_active', 'country', 'created_at')
    search_fields = ('user__email', 'contact_name', 'country', 'city', 'street')
    ordering = ('-created_at',)
    
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Contact'), {'fields': ('contact_name', 'contact_phone')}),
        (_('Address'), {'fields': ('address_type', 'country', 'region', 'city', 'postal_code', 'street', 'house', 'apartment')}),
        (_('Additional'), {'fields': ('entrance', 'floor', 'intercom', 'comment')}),
        (_('Settings'), {'fields': ('is_default', 'is_active')}),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """Админка для сессий пользователя."""
    list_display = ('user', 'session_key', 'ip_address', 'country', 'city', 'is_active', 'last_activity')
    list_filter = ('is_active', 'country', 'created_at', 'last_activity')
    search_fields = ('user__email', 'session_key', 'ip_address', 'country', 'city')
    ordering = ('-last_activity',)
    readonly_fields = ('session_key', 'ip_address', 'user_agent', 'created_at', 'last_activity')
    
    fieldsets = (
        (_('User'), {'fields': ('user',)}),
        (_('Session'), {'fields': ('session_key', 'ip_address', 'user_agent')}),
        (_('Location'), {'fields': ('country', 'city')}),
        (_('Status'), {'fields': ('is_active', 'expires_at')}),
        (_('Timestamps'), {'fields': ('created_at', 'last_activity')}),
    )
