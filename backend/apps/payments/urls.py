from django.urls import path, re_path

from .views import CryptoWebhookView, PaymentInitView


urlpatterns = [
    path("init/", PaymentInitView.as_view(), name="payment-init"),
    # CoinRemitter проверяет notify_url POST-запросом; иногда без trailing slash
    re_path(r"^crypto/webhook/?$", CryptoWebhookView.as_view(), name="crypto-webhook"),
]

