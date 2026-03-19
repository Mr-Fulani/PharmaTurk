from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils.text import slugify
import os
import uuid
from .models import Testimonial
from .serializers import TestimonialSerializer, TestimonialCreateSerializer


def _build_testimonial_media_filename(user, media_type, original_name):
    ext = os.path.splitext(str(original_name).split("?")[0])[1].lower() or ".jpg"
    parts = []
    if getattr(user, 'username', None):
        parts.append(user.username)
    full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    if full_name:
        parts.append(full_name)
    parts.append(media_type)
    base = "-".join(slugify(p).strip("-") for p in parts if p).strip("-")
    if not base:
        base = f"user-{getattr(user, 'id', '') or uuid.uuid4().hex[:6]}"
    suffix = uuid.uuid4().hex[:10]
    return f"{base}-{suffix}{ext}"


class TestimonialViewSet(viewsets.ModelViewSet):
    """
    ViewSet для работы с отзывами.
    """
    queryset = Testimonial.objects.filter(is_active=True)
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        """Возвращает соответствующий сериализатор в зависимости от действия."""
        if self.action == 'create':
            return TestimonialCreateSerializer
        return TestimonialSerializer

    def get_permissions(self):
        """Разрешения для разных действий."""
        if self.action == 'create':
            return [IsAuthenticated()]  # Только зарегистрированные пользователи могут создавать отзывы
        return [AllowAny()]

    def list(self, request, *args, **kwargs):
        """Получение списка активных отзывов."""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Фильтрация по username пользователя
        username = request.query_params.get('username')
        if username:
            queryset = queryset.filter(user__username=username)
        
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Получение одного отзыва по ID."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)
    
    def get_queryset(self):
        """Возвращает queryset с prefetch для медиа и select_related для пользователя."""
        return super().get_queryset().select_related('user').prefetch_related('media')

    def create(self, request, *args, **kwargs):
        """Создание нового отзыва с медиа."""
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        # Обработка медиа файлов из FormData
        media_items = []
        if 'media_items' in request.data:
            # Если медиа переданы как JSON
            try:
                import json
                if isinstance(request.data['media_items'], str):
                    media_items = json.loads(request.data['media_items'])
                else:
                    media_items = request.data['media_items']
            except:
                media_items = []
        
        # Обработка медиа файлов из multipart/form-data
        file_index = 0
        while True:
            image_key = f'media_image_{file_index}'
            video_file_key = f'media_video_file_{file_index}'
            video_url_key = f'media_video_url_{file_index}'
            media_type_key = f'media_type_{file_index}'
            
            if media_type_key not in request.data:
                break
            
            media_type = request.data[media_type_key]
            media_item = {'media_type': media_type}
            
            if media_type == 'image' and image_key in request.FILES:
                image_file = request.FILES[image_key]
                try:
                    from apps.catalog.utils.image_optimizer import ImageOptimizer
                    optimizer = ImageOptimizer()
                    image_file = optimizer.optimize_image(image_file, quality=85, max_size=(1200, 1200))
                except Exception:
                    pass
                image_file.name = _build_testimonial_media_filename(request.user, 'image', image_file.name)
                media_item['image'] = image_file
            elif media_type == 'video' and video_url_key in request.data:
                media_item['video_url'] = request.data[video_url_key]
            elif media_type == 'video_file' and video_file_key in request.FILES:
                video_file = request.FILES[video_file_key]
                video_file.name = _build_testimonial_media_filename(request.user, 'video', video_file.name)
                media_item['video_file'] = video_file
            
            if 'media_type' in media_item:
                media_items.append(media_item)
            
            file_index += 1
        
        # Создаем копию validated_data и добавляем media_items
        validated_data = serializer.validated_data.copy()
        validated_data['media_items'] = media_items
        
        # Создаем отзыв
        testimonial = serializer.create(validated_data)
        
        # Возвращаем созданный отзыв
        response_serializer = TestimonialSerializer(testimonial, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
