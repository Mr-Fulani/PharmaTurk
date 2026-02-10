"""URL routes for recommendations API."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# trailing_slash=True, чтобы /api/recommendations/personalized/ работал
router = DefaultRouter(trailing_slash=True)
router.register(r"", views.RecommendationViewSet, basename="recommendation")

urlpatterns = [
    path("", include(router.urls)),
]
