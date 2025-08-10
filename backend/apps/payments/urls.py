from django.urls import path

from .views import PaymentInitView


urlpatterns = [
    path("init/", PaymentInitView.as_view(), name="payment-init"),
]

