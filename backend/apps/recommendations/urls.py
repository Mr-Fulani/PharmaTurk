"""URL routes for recommendations API."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# trailing_slash=True, чтобы /api/recommendations/personalized/ работал
router = DefaultRouter(trailing_slash=True)
router.register(r"", views.RecommendationViewSet, basename="recommendation")

# Дублируем personalized для пути без trailing slash (fetch/axios не всегда следует редиректу)
personalized_view = views.RecommendationViewSet.as_view({'get': 'personalized'})
search_by_image_view = views.RecommendationViewSet.as_view({'post': 'search_by_image'})

urlpatterns = [
    path("personalized", personalized_view),
    path("search_by_image", search_by_image_view),
    path("", include(router.urls)),
]
