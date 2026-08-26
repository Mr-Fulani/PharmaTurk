from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductQuestionViewSet,
    ProductReviewViewSet,
    ReviewFeedView,
    TestimonialSectionSettingsView,
    TestimonialViewSet,
)

router = DefaultRouter()
router.register(r'testimonials', TestimonialViewSet, basename='testimonial')
router.register(r'product-reviews', ProductReviewViewSet, basename='product-review')
router.register(r'product-questions', ProductQuestionViewSet, basename='product-question')

# Дублируем list и create для пути без trailing slash (fetch/axios не всегда следует редиректу)
testimonials_list = TestimonialViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

urlpatterns = [
    path('testimonials', testimonials_list),
    path('reviews-feed/', ReviewFeedView.as_view(), name='reviews-feed'),
    path('reviews-feed', ReviewFeedView.as_view()),
    path('testimonials-section-settings', TestimonialSectionSettingsView.as_view()),
    path('', include(router.urls)),
]
