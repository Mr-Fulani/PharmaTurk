from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import AllowAny
from .models import Testimonial
from .serializers import TestimonialSerializer


class TestimonialViewSet(ReadOnlyModelViewSet):
    """
    ViewSet для получения списка активных отзывов.
    """
    queryset = Testimonial.objects.filter(is_active=True)
    serializer_class = TestimonialSerializer
    permission_classes = [AllowAny]
