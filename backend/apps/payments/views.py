"""Публичные представления-плейсхолдеры для платежей."""
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .providers import DummyProvider


class PaymentInitView(APIView):
    """Инициализация платежа через провайдера-заглушку."""

    @extend_schema(summary="Инициализация платежа (заглушка)", responses={200: dict})
    def post(self, request: Request) -> Response:  # type: ignore[override]
        provider = DummyProvider()
        result = provider.create_payment(
            amount_minor=100,
            currency="RUB",
            description="Тестовый платёж",
            metadata={},
        )
        return Response({
            "payment_id": result.payment_id,
            "redirect_url": result.redirect_url,
            "extra": result.extra,
        })

