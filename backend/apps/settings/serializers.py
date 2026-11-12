"""Сериализаторы для настроек сайта."""

from django.conf import settings
from rest_framework import serializers
from .models import FooterSettings, HomeBlock


class FooterSettingsSerializer(serializers.ModelSerializer):
    """Сериализатор для настроек футера."""
    
    site_url = serializers.SerializerMethodField()
    
    class Meta:
        model = FooterSettings
        fields = [
            'phone',
            'email',
            'location',
            'telegram_url',
            'whatsapp_url',
            'vk_url',
            'instagram_url',
            'crypto_payment_text',
            'site_url',
        ]
    
    def get_site_url(self, obj):
        """Базовый URL сайта для ссылок на страницы (политика, доставка и т.д.)."""
        return getattr(settings, 'COMPANY_SITE_URL', 'https://mudaroba.com').rstrip('/')


class HomeBlockSerializer(serializers.ModelSerializer):
    """Блок главной: ключ и признак показа; порядок задаёт место в списке."""

    class Meta:
        model = HomeBlock
        fields = ["key", "is_enabled"]
