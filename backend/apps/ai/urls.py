from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AIProcessingLogViewSet, GenerateContentView

router = DefaultRouter()
router.register(r'logs', AIProcessingLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('generate/', GenerateContentView.as_view(), name='ai-generate'),
]
