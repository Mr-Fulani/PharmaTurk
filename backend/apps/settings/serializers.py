"""Сериализаторы для настроек сайта."""

from django.conf import settings
from rest_framework import serializers
from .models import FooterSettings


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
        return getattr(settings, 'COMPANY_SITE_URL', 'https://pharmaturk.ru').rstrip('/')

