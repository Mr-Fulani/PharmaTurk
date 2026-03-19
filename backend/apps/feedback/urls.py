from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TestimonialViewSet

router = DefaultRouter()
router.register(r'testimonials', TestimonialViewSet, basename='testimonial')

# Дублируем list для пути без trailing slash (fetch/axios не всегда следует редиректу)
testimonials_list = TestimonialViewSet.as_view({'get': 'list'})

urlpatterns = [
    path('testimonials', testimonials_list),
    path('', include(router.urls)),
]
