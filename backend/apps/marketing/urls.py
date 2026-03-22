from django.urls import path
from .views import CookieConsentView

urlpatterns = [
    path("cookie-consent/", CookieConsentView.as_view(), name="cookie-consent"),
]
