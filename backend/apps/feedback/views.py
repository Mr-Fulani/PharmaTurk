from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Testimonial
from .serializers import TestimonialSerializer, TestimonialCreateSerializer


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
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Получение одного отзыва по ID."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)
    
    def get_queryset(self):
        """Возвращает queryset с prefetch для медиа."""
        return super().get_queryset().prefetch_related('media')

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
                media_item['image'] = request.FILES[image_key]
            elif media_type == 'video' and video_url_key in request.data:
                media_item['video_url'] = request.data[video_url_key]
            elif media_type == 'video_file' and video_file_key in request.FILES:
                media_item['video_file'] = request.FILES[video_file_key]
            
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
