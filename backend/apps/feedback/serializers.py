from urllib.parse import quote, urlparse
from django.conf import settings
from rest_framework import serializers
from .models import Testimonial, TestimonialMedia


def _build_proxy_media_url(file_field, request):
    if not file_field:
        return None
    path = getattr(file_field, "name", None)
    if not path:
        url = getattr(file_field, "url", None)
        if not url:
            return None
        parsed = urlparse(url)
        path = parsed.path.lstrip('/')
        media_prefix = (settings.MEDIA_URL or '').lstrip('/')
        if media_prefix and path.startswith(media_prefix):
            path = path[len(media_prefix):]
    if path.startswith('media/'):
        path = path[len('media/'):]
    # Относительный URL — браузер подставит свой origin (localhost/ngrok/production)
    return f"/api/catalog/proxy-media/?path={quote(path)}"


def _resolve_file_url(file_field, request):
    return _build_proxy_media_url(file_field, request)


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
        request = self.context.get('request')
        return _resolve_file_url(getattr(obj, 'image', None), request)

    def get_video_file_url(self, obj):
        """Возвращает URL видео файла."""
        request = self.context.get('request')
        return _resolve_file_url(getattr(obj, 'video_file', None), request)


class TestimonialSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели отзыва.
    """
    author_avatar_url = serializers.SerializerMethodField()
    media = TestimonialMediaSerializer(many=True, read_only=True)
    user_id = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = (
            'id',
            'author_name',
            'author_avatar_url',
            'text',
            'rating',
            'media',
            'created_at',
            'user_id',
            'user_username',
        )
    
    def get_user_id(self, obj):
        """Возвращает ID пользователя, если он привязан к отзыву."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            # Проверяем, что user загружен (select_related должен это обеспечить)
            if hasattr(obj, 'user') and obj.user is not None:
                user_id = obj.user.id
                logger.info(f'Testimonial {obj.id} (author_name={obj.author_name}): user_id={user_id}, user_username={obj.user.username}')
                return user_id
        except AttributeError as e:
            logger.warning(f'Testimonial {obj.id}: AttributeError in get_user_id: {e}')
        except Exception as e:
            logger.error(f'Testimonial {obj.id}: Error in get_user_id: {e}')
        logger.info(f'Testimonial {obj.id} (author_name={obj.author_name}): user_id=None (no user)')
        return None
    
    def get_user_username(self, obj):
        """Возвращает username пользователя, если он привязан к отзыву."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            # Проверяем, что user загружен (select_related должен это обеспечить)
            if hasattr(obj, 'user') and obj.user is not None:
                username = obj.user.username
                logger.info(f'Testimonial {obj.id} (author_name={obj.author_name}): user_username={username}')
                return username
        except AttributeError as e:
            logger.warning(f'Testimonial {obj.id}: AttributeError in get_user_username: {e}')
        except Exception as e:
            logger.error(f'Testimonial {obj.id}: Error in get_user_username: {e}')
        logger.info(f'Testimonial {obj.id} (author_name={obj.author_name}): user_username=None (no user)')
        return None

    def get_author_avatar_url(self, obj):
        """Возвращает URL аватара автора."""
        request = self.context.get('request')
        user = getattr(obj, 'user', None)
        if user and getattr(user, 'avatar', None):
            return _resolve_file_url(getattr(user, 'avatar', None), request)
        return _resolve_file_url(getattr(obj, 'author_avatar', None), request)


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
    author_name = serializers.CharField(required=False, read_only=True)
    author_avatar = serializers.ImageField(required=False, read_only=True)

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
        
        # Получаем пользователя из запроса
        user = self.context['request'].user
        
        author_name = validated_data.pop('author_name', None)
        if not author_name:
            # Формируем имя из профиля или username
            if user.first_name or user.last_name:
                name_parts = [user.first_name, user.last_name]
                author_name = ' '.join(filter(None, name_parts))
            else:
                author_name = user.username or user.email
        
        author_avatar = validated_data.pop('author_avatar', None)
        if not author_avatar and user.avatar:
            # Копируем аватар из профиля
            # Открываем файл и создаем копию для отзыва
            user.avatar.open('rb')
            file_content = user.avatar.read()
            user.avatar.close()
            
            # Создаем новый файл для отзыва
            from django.core.files.base import ContentFile
            import os
            file_name = os.path.basename(user.avatar.name)
            author_avatar = ContentFile(file_content, name=file_name)
        
        testimonial = Testimonial.objects.create(
            user=user,
            is_active=False,
            author_name=author_name,
            author_avatar=author_avatar,
            **validated_data
        )
        
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
