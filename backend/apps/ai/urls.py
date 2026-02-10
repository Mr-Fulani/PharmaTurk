from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AIProcessingLogViewSet,
    AIModerationQueueViewSet,
    AITemplateViewSet,
    GenerateContentView,
    ProcessProductView,
    AIStatsView,
)

router = DefaultRouter()
router.register(r"logs", AIProcessingLogViewSet, basename="ai-logs")
router.register(r"moderation", AIModerationQueueViewSet, basename="ai-moderation")
router.register(r"templates", AITemplateViewSet, basename="ai-templates")

urlpatterns = [
    path("", include(router.urls)),
    path("generate/", GenerateContentView.as_view(), name="ai-generate"),
    path("process/<int:product_id>/", ProcessProductView.as_view(), name="ai-process"),
    path("stats/", AIStatsView.as_view(), name="ai-stats"),
]
