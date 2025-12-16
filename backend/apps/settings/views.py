"""Представления для настроек сайта."""

from rest_framework import viewsets
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import FooterSettings
from .serializers import FooterSettingsSerializer


class FooterSettingsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для получения настроек футера."""
    
    queryset = FooterSettings.objects.all()
    serializer_class = FooterSettingsSerializer
    pagination_class = None
    
    @extend_schema(
        summary="Получить настройки футера",
        description="Возвращает настройки футера (контакты, соцсети, текст про криптовалюту)",
        responses={200: FooterSettingsSerializer}
    )
    def list(self, request):
        """Получить настройки футера (singleton - всегда возвращает одну запись)."""
        settings = FooterSettings.load()
        serializer = self.get_serializer(settings)
        return Response(serializer.data)

