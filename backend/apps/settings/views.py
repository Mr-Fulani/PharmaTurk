"""Представления для настроек сайта."""

from rest_framework import serializers, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer

from .models import FooterSettings, HomeBlock, SiteAppearance
from .serializers import FooterSettingsSerializer, HomeBlockSerializer


class FooterSettingsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для получения настроек футера."""

    permission_classes = [AllowAny]
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


class SiteAppearanceView(APIView):
    """Оформление сайта для фронтенда: тема и блоки главной в порядке показа."""

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Тема оформления и блоки главной",
        responses={
            200: inline_serializer(
                name="SiteAppearance",
                fields={
                    "theme": serializers.ChoiceField(choices=SiteAppearance.Theme.choices),
                    "home_blocks": HomeBlockSerializer(many=True),
                },
            )
        },
    )
    def get(self, request, *args, **kwargs):
        return Response(
            {
                "theme": SiteAppearance.load().theme,
                "home_blocks": HomeBlockSerializer(HomeBlock.objects.all(), many=True).data,
            }
        )
