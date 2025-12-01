from rest_framework import serializers
from .models import Testimonial


class TestimonialSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели отзыва.
    """
    author_avatar_url = serializers.ImageField(source='author_avatar', read_only=True)
    image_url = serializers.ImageField(source='image', read_only=True)
    video_file_url = serializers.FileField(source='video_file', read_only=True)

    class Meta:
        model = Testimonial
        fields = (
            'id',
            'author_name',
            'author_avatar_url',
            'text',
            'rating',
            'media_type',
            'image_url',
            'video_url',
            'video_file_url',
            'created_at',
        )
