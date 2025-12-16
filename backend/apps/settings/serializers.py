"""Сериализаторы для настроек сайта."""

from rest_framework import serializers
from .models import FooterSettings


class FooterSettingsSerializer(serializers.ModelSerializer):
    """Сериализатор для настроек футера."""
    
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
        ]

