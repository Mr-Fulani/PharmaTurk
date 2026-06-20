from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from django.utils.text import slugify
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
import logging
import os
import os
import uuid
from api.authentication import JWTSafeAuthentication
from .models import ProductReview, ProductReviewMedia, Testimonial, TestimonialSectionSettings
from .review_policy import can_user_review
from .serializers import (
    ProductReviewSerializer,
    ProductReviewWriteSerializer,
    TestimonialSerializer,
    TestimonialCreateSerializer,
    TestimonialSectionSettingsSerializer,
)
from .tasks import notify_admin_product_review

logger = logging.getLogger(__name__)


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
    # SessionAuthentication применяет CSRF к POST даже при AllowAny — используем только JWT
    authentication_classes = [JWTSafeAuthentication]

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


class ProductReviewViewSet(viewsets.ModelViewSet):
    authentication_classes = [JWTSafeAuthentication]
    queryset = ProductReview.objects.select_related("user").prefetch_related("media")

    def get_serializer_class(self):
        return ProductReviewWriteSerializer if self.action in {"create", "partial_update", "update"} else ProductReviewSerializer

    def get_permissions(self):
        if self.action in {"create", "partial_update", "update", "destroy"}:
            return [IsAuthenticated()]
        return [AllowAny()]

    @staticmethod
    def _target(request):
        product_type = str(request.query_params.get("product_type") or "").strip().lower().replace("_", "-")
        product_slug = str(request.query_params.get("product_slug") or "").strip()
        return product_type, product_slug

    def list(self, request, *args, **kwargs):
        product_type, product_slug = self._target(request)
        if not product_type or not product_slug:
            return Response({"detail": "Укажите product_type и product_slug"}, status=status.HTTP_400_BAD_REQUEST)

        target_qs = self.get_queryset().filter(product_type=product_type, product_slug=product_slug)
        approved = target_qs.filter(status=ProductReview.Status.APPROVED)
        aggregate = approved.aggregate(average_rating=Avg("rating"), reviews_count=Count("id"))
        own_review = None
        if request.user.is_authenticated:
            own_review = target_qs.filter(user=request.user).first()

        return Response({
            "average_rating": round(float(aggregate["average_rating"] or 0), 1),
            "reviews_count": aggregate["reviews_count"],
            "reviews": ProductReviewSerializer(approved, many=True, context={"request": request}).data,
            "own_review": ProductReviewSerializer(own_review, context={"request": request}).data if own_review else None,
            "can_review": can_user_review(request.user, product_type, product_slug),
        })

    def retrieve(self, request, *args, **kwargs):
        review = self.get_object()
        if review.status != ProductReview.Status.APPROVED and (
            not request.user.is_authenticated or review.user_id != request.user.id
        ):
            return Response({"detail": "Отзыв не найден"}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProductReviewSerializer(review, context={"request": request}).data)

    @staticmethod
    def _notify_admin(review_id, event):
        try:
            notify_admin_product_review.delay(review_id, event)
        except Exception:
            logger.exception("Failed to enqueue product review Telegram notification")

    @staticmethod
    def _validate_media(files, existing_count=0):
        if existing_count + len(files) > 3:
            raise ValueError("К отзыву можно прикрепить не более трёх файлов")
        validated = []
        for uploaded in files:
            content_type = str(getattr(uploaded, "content_type", "") or "").lower()
            extension = os.path.splitext(str(uploaded.name))[1].lower()
            if content_type.startswith("image/"):
                if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                    raise ValueError("Неподдерживаемый формат изображения")
                try:
                    from PIL import Image
                    image = Image.open(uploaded)
                    image.verify()
                    uploaded.seek(0)
                except Exception as error:
                    raise ValueError("Повреждённый или неподдерживаемый файл изображения") from error
                media_type, max_size = ProductReviewMedia.MediaType.IMAGE, 10 * 1024 * 1024
            elif content_type.startswith("video/"):
                if extension not in {".mp4", ".webm", ".mov", ".m4v"}:
                    raise ValueError("Поддерживаются видео MP4, WebM и MOV")
                media_type, max_size = ProductReviewMedia.MediaType.VIDEO, 50 * 1024 * 1024
            else:
                raise ValueError("Разрешены только изображения и видео")
            if uploaded.size > max_size:
                limit_mb = max_size // (1024 * 1024)
                raise ValueError(f"Файл {uploaded.name} превышает лимит {limit_mb} МБ")
            validated.append((media_type, uploaded))
        return validated

    @staticmethod
    def _author_name(user):
        return " ".join(filter(None, [user.first_name, user.last_name])).strip() or user.username or user.email

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data
        if not can_user_review(request.user, target["product_type"], target["product_slug"]):
            return Response({"detail": "Оставлять отзыв могут только покупатели товара"}, status=status.HTTP_403_FORBIDDEN)
        try:
            media = self._validate_media(request.FILES.getlist("media"))
        except ValueError as error:
            return Response({"media": [str(error)]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                review = serializer.save(
                    user=request.user,
                    author_name=self._author_name(request.user),
                    status=ProductReview.Status.PENDING,
                )
                for order, (media_type, uploaded) in enumerate(media):
                    ProductReviewMedia.objects.create(review=review, media_type=media_type, file=uploaded, order=order)
        except IntegrityError:
            return Response({"detail": "Вы уже оставили отзыв на этот товар"}, status=status.HTTP_409_CONFLICT)

        self._notify_admin(review.pk, "created")
        return Response(ProductReviewSerializer(review, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        review = self.get_object()
        if review.user_id != request.user.id:
            return Response({"detail": "Недостаточно прав"}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(review, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            media = self._validate_media(request.FILES.getlist("media"), review.media.count())
        except ValueError as error:
            return Response({"media": [str(error)]}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            review = serializer.save(
                author_name=self._author_name(request.user),
                status=ProductReview.Status.PENDING,
                published_at=None,
            )
            start = review.media.count()
            for offset, (media_type, uploaded) in enumerate(media):
                ProductReviewMedia.objects.create(review=review, media_type=media_type, file=uploaded, order=start + offset)
        self._notify_admin(review.pk, "updated")
        return Response(ProductReviewSerializer(review, context={"request": request}).data)

    update = partial_update

    def destroy(self, request, *args, **kwargs):
        review = self.get_object()
        if review.user_id != request.user.id:
            return Response({"detail": "Недостаточно прав"}, status=status.HTTP_403_FORBIDDEN)
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TestimonialSectionSettingsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        settings_obj = TestimonialSectionSettings.load()
        serializer = TestimonialSectionSettingsSerializer(settings_obj)
        return Response(serializer.data)
