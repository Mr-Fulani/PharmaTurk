from rest_framework import serializers
from .models import Testimonial, TestimonialMedia


class TestimonialMediaSerializer(serializers.ModelSerializer):
    """
    Сериализатор для медиа отзывов.
    """
    image_url = serializers.SerializerMethodField()
    video_file_url = serializers.SerializerMethodField()

    class Meta:
        model = TestimonialMedia
        fields = (
            'id',
            'media_type',
            'image_url',
            'video_url',
            'video_file_url',
            'order',
        )

    def get_image_url(self, obj):
        """Возвращает URL изображения."""
        if obj.image and hasattr(obj.image, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_video_file_url(self, obj):
        """Возвращает URL видео файла."""
        if obj.video_file and hasattr(obj.video_file, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.video_file.url)
            return obj.video_file.url
        return None


class TestimonialSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели отзыва.
    """
    author_avatar_url = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    video_file_url = serializers.SerializerMethodField()
    media = TestimonialMediaSerializer(many=True, read_only=True)

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
            'media',
            'created_at',
        )

    def get_author_avatar_url(self, obj):
        """Возвращает URL аватара автора."""
        if obj.author_avatar and hasattr(obj.author_avatar, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.author_avatar.url)
            return obj.author_avatar.url
        return None

    def get_image_url(self, obj):
        """Возвращает URL изображения (для обратной совместимости)."""
        if obj.image and hasattr(obj.image, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_video_file_url(self, obj):
        """Возвращает URL видео файла (для обратной совместимости)."""
        if obj.video_file and hasattr(obj.video_file, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.video_file.url)
            return obj.video_file.url
        return None


class TestimonialCreateSerializer(serializers.ModelSerializer):
    """
    Сериализатор для создания отзывов с медиа.
    """
    media_items = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        write_only=True
    )

    class Meta:
        model = Testimonial
        fields = (
            'author_name',
            'author_avatar',
            'text',
            'rating',
            'media_items',
        )

    def create(self, validated_data):
        """Создает отзыв с медиа файлами."""
        media_items = validated_data.pop('media_items', [])
        testimonial = Testimonial.objects.create(is_active=False, **validated_data)
        
        for idx, media_item in enumerate(media_items):
            media_type = media_item.get('media_type')
            if media_type == 'image' and 'image' in media_item:
                TestimonialMedia.objects.create(
                    testimonial=testimonial,
                    media_type='image',
                    image=media_item['image'],
                    order=idx
                )
            elif media_type == 'video' and 'video_url' in media_item:
                TestimonialMedia.objects.create(
                    testimonial=testimonial,
                    media_type='video',
                    video_url=media_item['video_url'],
                    order=idx
                )
            elif media_type == 'video_file' and 'video_file' in media_item:
                TestimonialMedia.objects.create(
                    testimonial=testimonial,
                    media_type='video_file',
                    video_file=media_item['video_file'],
                    order=idx
                )
        
        return testimonial
