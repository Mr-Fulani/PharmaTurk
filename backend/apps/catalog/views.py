"""API представления для каталога товаров."""

from typing import List
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.db import models
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
import requests
import hashlib

from .models import (
    Category, Brand, Product, ProductAttribute, PriceHistory, Favorite,
    ClothingProduct, ClothingVariant,
    ShoeProduct, ShoeVariant,
    ElectronicsProduct,
    FurnitureProduct, FurnitureVariant,
    Service,
    Banner, BannerMedia,
)
from .services import CatalogService
from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductSerializer,
    ProductDetailSerializer,
    ProductAttributeSerializer,
    PriceHistorySerializer,
    FavoriteSerializer,
    AddToFavoriteSerializer,
    ClothingCategorySerializer,
    ClothingProductSerializer,
    ShoeCategorySerializer,
    ShoeProductSerializer,
    ElectronicsCategorySerializer,
    ElectronicsProductSerializer,
    FurnitureProductSerializer,
    ServiceSerializer,
    BannerSerializer
)


class StandardPagination(PageNumberPagination):
    """Стандартная пагинация для API."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями."""
    
    queryset = Category.objects.filter(is_active=True).select_related('category_type').prefetch_related('translations')
    serializer_class = CategorySerializer
    pagination_class = StandardPagination

    def _parse_bool(self, value: str | None) -> bool | None:
        """Безопасно парсит булево из query-параметра."""
        if value is None:
            return None
        return value.lower() in ('true', '1', 'yes')

    def _parse_slug_list(self, param: str) -> list[str]:
        """Парсит список slug из query-параметров."""
        raw = self.request.query_params.get(param)
        if not raw:
            return []
        return [s.strip() for s in raw.split(',') if s.strip()]

    def _parse_int_list(self, param: str) -> list[int]:
        """Парсит список ID из query-параметров."""
        values = self.request.query_params.getlist(param) or self.request.query_params.getlist(f'{param}[]')
        result: list[int] = []
        for value in values:
            try:
                result.append(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def get_queryset(self):
        """
        Фильтрует категории.

        Поддерживаемые параметры:
        - all=true               — вернуть все активные категории без ограничений.
        - top_level=true         — только корневые категории (parent is null).
        - slug / category_slug   — одна или несколько через запятую; вернёт указанную категорию и (по умолчанию) её дочерние.
        - include_children=false — если передан slug, можно отключить добавление детей.
        - parent_slug            — вернуть только детей указанного родителя (slug).
        - parent_id              — вернуть только детей указанного родителя (id).
        """
        base_qs = Category.objects.filter(is_active=True).select_related('category_type').prefetch_related('translations').order_by('sort_order', 'name')

        # Явный запрос "все категории"
        if self._parse_bool(self.request.query_params.get('all')) is True:
            return base_qs

        # Фильтр по parent_id / parent_slug
        parent_ids = self._parse_int_list('parent_id')
        parent_slugs = self._parse_slug_list('parent_slug')

        # Фильтр по slug (или category_slug)
        slug_list = self._parse_slug_list('slug') or self._parse_slug_list('category_slug')
        include_children = self._parse_bool(self.request.query_params.get('include_children'))
        if include_children is None:
            include_children = True  # по умолчанию берём детей, если указан slug

        # Если задан slug — возвращаем саму категорию и (опционально) её детей
        if slug_list:
            main_qs = base_qs.filter(slug__in=slug_list)
            if not include_children:
                return main_qs
            parent_ids_set = list(main_qs.values_list('id', flat=True))
            children_qs = base_qs.filter(parent_id__in=parent_ids_set)
            return main_qs.union(children_qs).order_by('sort_order', 'name')

        # Если задан parent — возвращаем только детей
        if parent_ids or parent_slugs:
            qs = base_qs
            if parent_ids:
                qs = qs.filter(parent_id__in=parent_ids)
            if parent_slugs:
                qs = qs.filter(parent__slug__in=parent_slugs)
            return qs

        # Если top_level=true — только корневые
        if self._parse_bool(self.request.query_params.get('top_level')) is True:
            return base_qs.filter(parent__isnull=True)

        # По умолчанию безопасно отдаём только корневые, чтобы не засорять фронт
        return base_qs.filter(parent__isnull=True)
    
    @extend_schema(
        summary="Получить список категорий",
        description="Возвращает активные категории с серверной фильтрацией",
        parameters=[
            OpenApiParameter(name="all", type=bool, required=False, description="Вернуть все активные категории без ограничений"),
            OpenApiParameter(name="top_level", type=bool, required=False, description="Только корневые категории"),
            OpenApiParameter(name="slug", type=str, required=False, description="Slug категории (или несколько через запятую)"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Алиас slug категории"),
            OpenApiParameter(name="include_children", type=bool, required=False, description="Добавлять ли дочерние при фильтре по slug (по умолчанию true)"),
            OpenApiParameter(name="parent_slug", type=str, required=False, description="Вернуть только детей категории с указанным slug"),
            OpenApiParameter(name="parent_id", type=int, required=False, description="Вернуть только детей категории с указанным ID"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Получить категорию по ID",
        description="Возвращает детальную информацию о категории"
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории",
        description="Возвращает список подкатегорий для указанной категории"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, is_active=True).select_related('category_type').prefetch_related('translations')
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с брендами."""
    
    queryset = Brand.objects.filter(is_active=True).prefetch_related('translations')
    serializer_class = BrandSerializer
    pagination_class = StandardPagination

    PRODUCT_TYPE_ALIASES = {
        'supplements': 'supplements',
        'medical-equipment': 'medical_equipment',
        'medical_equipment': 'medical_equipment',
        'accessories': 'accessories',
        'medical-accessories': 'accessories',
        'medical_accessories': 'accessories',
        'furniture': 'furniture',
        'tableware': 'tableware',
        'jewelry': 'jewelry',
        'underwear': 'underwear',
        'headwear': 'headwear',
    }
    
    PRODUCT_MODEL_MAP = {
        'medicines': Product,
        'supplements': Product,
        'medical_equipment': Product,
        'tableware': Product,
        'accessories': Product,
        'jewelry': Product,
        'underwear': Product,
        'headwear': Product,
        'clothing': ClothingProduct,
        'shoes': ShoeProduct,
        'electronics': ElectronicsProduct,
        'furniture': FurnitureProduct,
    }

    PRODUCT_TYPE_CATEGORY_SLUGS = {
        # Для базовых типов (медицина/БАДы/медтехника/аксессуары) список slug задаётся при необходимости.
    }

    def _normalize_product_type(self, raw_type: str | None) -> str | None:
        """Нормализует тип товара (учитываем алиасы)."""
        if not raw_type:
            return None
        raw_type = raw_type.lower()
        return self.PRODUCT_TYPE_ALIASES.get(raw_type, raw_type)

    def _parse_id_list(self, param: str) -> list[int]:
        """Парсит список ID из query-параметров."""
        values = self.request.query_params.getlist(param) or self.request.query_params.getlist(f'{param}[]')
        result: list[int] = []
        for value in values:
            try:
                result.append(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def _parse_slug_list(self, param: str) -> list[str]:
        """Парсит список slug из query-параметров."""
        value = self.request.query_params.get(param)
        if not value:
            return []
        return [slug.strip() for slug in value.split(',') if slug.strip()]

    def get_queryset(self):
        """Фильтрует бренды по типу товара/категории."""
        queryset = Brand.objects.filter(is_active=True).order_by('name')

        # Прямой фильтр по primary_category_slug
        primary_slugs = self._parse_slug_list('primary_category_slug')
        if primary_slugs:
            normalized_slugs = [slug.replace('-', '_') for slug in primary_slugs]
            return queryset.filter(primary_category_slug__in=normalized_slugs).distinct()

        product_type = self._normalize_product_type(self.request.query_params.get('product_type'))
        if not product_type:
            return queryset

        product_model = self.PRODUCT_MODEL_MAP.get(product_type)
        if not product_model:
            return queryset
        
        product_qs = product_model.objects.filter(is_active=True, brand__isnull=False)

        category_slugs_filter = self.PRODUCT_TYPE_CATEGORY_SLUGS.get(product_type)
        if category_slugs_filter and product_model is Product:
            product_qs = product_qs.filter(category__slug__in=category_slugs_filter)

        category_ids = self._parse_id_list('category_id')
        if category_ids:
            product_qs = product_qs.filter(category_id__in=category_ids)

        category_slugs = self._parse_slug_list('category_slug')
        if category_slugs:
            product_qs = product_qs.filter(category__slug__in=category_slugs)

        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() in ('true', '1', 'yes'):
            product_qs = product_qs.filter(is_available=True)

        brand_ids = product_qs.values_list('brand_id', flat=True).distinct()
        return queryset.filter(id__in=brand_ids).distinct()
    
    @extend_schema(
        summary="Получить список брендов",
        description="Возвращает список активных брендов (можно фильтровать по типу товара или основной категории)",
        parameters=[
            OpenApiParameter(name="primary_category_slug", type=str, required=False, description="Основная категория бренда (slug или несколько через запятую, например furniture)"),
            OpenApiParameter(name="product_type", type=str, required=False, description="Тип товара для фильтра (medicines, supplements, shoes, clothing, electronics, furniture и т.д.)"),
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории для фильтрации по товарам"),
            OpenApiParameter(name="category_slug", type=str, required=False, description="Slug категории для фильтрации по товарам"),
            OpenApiParameter(name="in_stock", type=bool, required=False, description="Только бренды с товарами в наличии"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Получить бренд по ID",
        description="Возвращает детальную информацию о бренде"
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами."""
    
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django.
        
        Преобразует:
        - name_asc -> name
        - name_desc -> -name
        - price_asc -> price
        - price_desc -> -price
        - newest -> -created_at
        - popular -> -is_featured, -created_at
        """
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',  # Популярные = рекомендуемые товары
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров по параметрам."""
        queryset = Product.objects.filter(is_active=True)
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по slug категории (поддержка нескольких через запятую)
        category_slug = self.request.query_params.get('category_slug')
        if category_slug:
            slugs = [s.strip() for s in category_slug.split(',') if s.strip()]
            if slugs:
                queryset = queryset.filter(category__slug__in=slugs)
        
        # Фильтр по бренду (поддержка массивов)
        brand_ids = self.request.query_params.getlist('brand_id') or self.request.query_params.getlist('brand_id[]')
        if brand_ids:
            try:
                brand_ids = [int(bid) for bid in brand_ids if bid]
                if brand_ids:
                    queryset = queryset.filter(brand_id__in=brand_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        min_price = self.request.query_params.get('min_price') or self.request.query_params.get('price_min')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price') or self.request.query_params.get('price_max')
        if max_price:
            try:
                max_price = Decimal(max_price)
                queryset = queryset.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по типу товара
        product_type = self.request.query_params.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type=product_type)

        # Фильтр по статусу доступности
        availability_status = self.request.query_params.get('availability_status')
        if availability_status:
            queryset = queryset.filter(availability_status=availability_status)

        # Фильтр по стране происхождения
        country_of_origin = self.request.query_params.get('country_of_origin')
        if country_of_origin:
            countries = [c.strip() for c in country_of_origin.split(',') if c.strip()]
            if countries:
                queryset = queryset.filter(country_of_origin__in=countries)
        
        # Фильтр по наличию
        is_available = self.request.query_params.get('is_available')
        if is_available is not None:
            is_available = is_available.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_available=is_available)
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return queryset
    
    def get_serializer_class(self):
        """Выбираем сериализатор в зависимости от действия."""
        if self.action == 'retrieve':
            return ProductDetailSerializer
        return ProductSerializer
    
    @extend_schema(
        summary="Получить список товаров",
        description="Возвращает список товаров с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="is_available", type=bool, required=False, description="В наличии"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
                OpenApiParameter(name="product_type", type=str, required=False, description="Тип товара (например, medicines, clothing)"),
                OpenApiParameter(name="availability_status", type=str, required=False, description="Статус доступности (in_stock, backorder, preorder, out_of_stock, discontinued)"),
                OpenApiParameter(name="country_of_origin", type=str, required=False, description="Страна происхождения (можно через запятую)"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @extend_schema(
        summary="Получить товар по slug",
        description="Возвращает детальную информацию о товаре"
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить атрибуты товара",
        description="Возвращает список атрибутов товара (состав, показания и т.д.)"
    )
    def attributes(self, request, slug=None):
        """Получить атрибуты товара."""
        product = self.get_object()
        attributes = ProductAttribute.objects.filter(product=product)
        serializer = ProductAttributeSerializer(attributes, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить историю цен",
        description="Возвращает историю изменения цен товара",
        parameters=[
            OpenApiParameter(name="days", type=int, required=False, description="Количество дней", default=30),
        ]
    )
    def price_history(self, request, slug=None):
        """Получить историю цен товара."""
        product = self.get_object()
        days = int(request.query_params.get('days', 30))
        
        service = CatalogService()
        history = service.get_price_history(product.id, days)
        serializer = PriceHistorySerializer(history, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Поиск товаров",
        description="Поиск товаров по названию и описанию",
        parameters=[
            OpenApiParameter(name="q", type=str, required=True, description="Поисковый запрос"),
            OpenApiParameter(name="limit", type=int, required=False, description="Лимит результатов", default=20),
        ]
    )
    def search(self, request):
        """Поиск товаров."""
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response(
                {"error": "Поисковый запрос обязателен"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        limit = int(request.query_params.get('limit', 20))
        service = CatalogService()
        products = service.get_products(search=query, limit=limit)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Рекомендуемые товары",
        description="Возвращает список рекомендуемых товаров"
    )
    def featured(self, request):
        """Получить рекомендуемые товары."""
        featured_products = Product.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)


# ============================================================================
# API ДЛЯ ОДЕЖДЫ, ОБУВИ И ЭЛЕКТРОНИКИ
# ============================================================================

class ClothingCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями одежды."""
    
    queryset = Category.objects.filter(clothing_type__isnull=False).exclude(clothing_type='').filter(is_active=True)
    serializer_class = ClothingCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий одежды."""
        queryset = Category.objects.filter(clothing_type__isnull=False).exclude(clothing_type='').filter(is_active=True)
        
        # Фильтр по полу
        gender = self.request.query_params.get('gender')
        if gender:
            queryset = queryset.filter(gender=gender)
        
        # Фильтр по типу одежды
        clothing_type = self.request.query_params.get('clothing_type')
        if clothing_type:
            queryset = queryset.filter(clothing_type=clothing_type)
        
        return queryset.order_by('sort_order', 'name')
    
    @extend_schema(
        summary="Получить список категорий одежды",
        description="Возвращает список активных категорий одежды",
        parameters=[
            OpenApiParameter(name="gender", type=str, required=False, description="Пол (men, women, unisex, kids)"),
            OpenApiParameter(name="clothing_type", type=str, required=False, description="Тип одежды"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории одежды",
        description="Возвращает список подкатегорий для указанной категории одежды"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, clothing_type__isnull=False).exclude(clothing_type='').filter(is_active=True)
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class ClothingProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами одежды."""
    
    queryset = ClothingProduct.objects.filter(is_active=True)
    serializer_class = ClothingProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров одежды по параметрам."""
        queryset = ClothingProduct.objects.filter(is_active=True).prefetch_related(
            'images',
            'variants',
            'variants__images',
        )
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по бренду (поддержка массивов)
        brand_ids = self.request.query_params.getlist('brand_id') or self.request.query_params.getlist('brand_id[]')
        if brand_ids:
            try:
                brand_ids = [int(bid) for bid in brand_ids if bid]
                if brand_ids:
                    queryset = queryset.filter(brand_id__in=brand_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по полу
        gender = self.request.query_params.get('gender')
        if gender:
            queryset = queryset.filter(category__gender=gender)
        
        # Фильтр по размеру
        size = self.request.query_params.get('size')
        if size:
            queryset = queryset.filter(
                models.Q(size=size) | models.Q(variants__sizes__size=size)
            )
        
        # Фильтр по цвету
        color = self.request.query_params.get('color')
        if color:
            queryset = queryset.filter(models.Q(color__icontains=color) | models.Q(variants__color__icontains=color))
        
        # Фильтр по материалу
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        
        # Фильтр по сезону
        season = self.request.query_params.get('season')
        if season:
            queryset = queryset.filter(season=season)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        min_price = self.request.query_params.get('min_price') or self.request.query_params.get('price_min')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price') or self.request.query_params.get('price_max')
        if max_price:
            try:
                max_price = Decimal(max_price)
                queryset = queryset.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return queryset
    
    @extend_schema(
        summary="Получить список товаров одежды",
        description="Возвращает список товаров одежды с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="gender", type=str, required=False, description="Пол"),
            OpenApiParameter(name="size", type=str, required=False, description="Размер"),
            OpenApiParameter(name="color", type=str, required=False, description="Цвет"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="season", type=str, required=False, description="Сезон"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Рекомендуемые товары одежды",
        description="Возвращает список рекомендуемых товаров одежды"
    )
    def featured(self, request):
        """Получить рекомендуемые товары одежды."""
        featured_products = ClothingProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Деталь по товару или по варианту (если slug варианта)."""
        slug = kwargs.get("slug")
        active_variant_slug = None
        obj = None
        if slug:
            variant = ClothingVariant.objects.filter(slug=slug, is_active=True).select_related('product').first()
            if variant:
                obj = variant.product
                active_variant_slug = variant.slug
        if obj is None:
            obj = self.get_object()
        serializer = self.get_serializer(
            obj,
            context={**self.get_serializer_context(), "active_variant_slug": active_variant_slug}
        )
        return Response(serializer.data)


class ShoeCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями обуви."""
    
    queryset = Category.objects.filter(shoe_type__isnull=False).exclude(shoe_type='').filter(is_active=True)
    serializer_class = ShoeCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий обуви."""
        queryset = Category.objects.filter(shoe_type__isnull=False).exclude(shoe_type='').filter(is_active=True)
        
        # Фильтр по полу
        gender = self.request.query_params.get('gender')
        if gender:
            queryset = queryset.filter(gender=gender)
        
        # Фильтр по типу обуви
        shoe_type = self.request.query_params.get('shoe_type')
        if shoe_type:
            queryset = queryset.filter(shoe_type=shoe_type)
        
        return queryset.order_by('sort_order', 'name')
    
    @extend_schema(
        summary="Получить список категорий обуви",
        description="Возвращает список активных категорий обуви",
        parameters=[
            OpenApiParameter(name="gender", type=str, required=False, description="Пол (men, women, unisex, kids)"),
            OpenApiParameter(name="shoe_type", type=str, required=False, description="Тип обуви"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории обуви",
        description="Возвращает список подкатегорий для указанной категории обуви"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, shoe_type__isnull=False).exclude(shoe_type='').filter(is_active=True)
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class ShoeProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами обуви."""
    
    queryset = ShoeProduct.objects.filter(is_active=True)
    serializer_class = ShoeProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров обуви по параметрам."""
        queryset = ShoeProduct.objects.filter(is_active=True).prefetch_related(
            'images',
            'variants',
            'variants__images',
        )
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по бренду (поддержка массивов)
        brand_ids = self.request.query_params.getlist('brand_id') or self.request.query_params.getlist('brand_id[]')
        if brand_ids:
            try:
                brand_ids = [int(bid) for bid in brand_ids if bid]
                if brand_ids:
                    queryset = queryset.filter(brand_id__in=brand_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по полу
        gender = self.request.query_params.get('gender')
        if gender:
            queryset = queryset.filter(category__gender=gender)
        
        # Фильтр по размеру
        size = self.request.query_params.get('size')
        if size:
            queryset = queryset.filter(
                models.Q(size=size) | models.Q(variants__sizes__size=size)
            )
        
        # Фильтр по цвету
        color = self.request.query_params.get('color')
        if color:
            queryset = queryset.filter(models.Q(color__icontains=color) | models.Q(variants__color__icontains=color))
        
        # Фильтр по материалу
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        
        # Фильтр по высоте каблука
        heel_height = self.request.query_params.get('heel_height')
        if heel_height:
            queryset = queryset.filter(heel_height=heel_height)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        min_price = self.request.query_params.get('min_price') or self.request.query_params.get('price_min')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price') or self.request.query_params.get('price_max')
        if max_price:
            try:
                max_price = Decimal(max_price)
                queryset = queryset.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return queryset
    
    @extend_schema(
        summary="Получить список товаров обуви",
        description="Возвращает список товаров обуви с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="gender", type=str, required=False, description="Пол"),
            OpenApiParameter(name="size", type=str, required=False, description="Размер"),
            OpenApiParameter(name="color", type=str, required=False, description="Цвет"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="heel_height", type=str, required=False, description="Высота каблука"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Рекомендуемые товары обуви",
        description="Возвращает список рекомендуемых товаров обуви"
    )
    def featured(self, request):
        """Получить рекомендуемые товары обуви."""
        featured_products = ShoeProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """Деталь по товару или по варианту (если slug варианта)."""
        slug = kwargs.get("slug")
        active_variant_slug = None
        obj = None
        if slug:
            variant = ShoeVariant.objects.filter(slug=slug, is_active=True).select_related('product').first()
            if variant:
                obj = variant.product
                active_variant_slug = variant.slug
        if obj is None:
            obj = self.get_object()
        serializer = self.get_serializer(
            obj,
            context={**self.get_serializer_context(), "active_variant_slug": active_variant_slug}
        )
        return Response(serializer.data)


class ElectronicsCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями электроники."""
    
    queryset = Category.objects.filter(device_type__isnull=False).exclude(device_type='').filter(is_active=True)
    serializer_class = ElectronicsCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий электроники."""
        queryset = Category.objects.filter(device_type__isnull=False).exclude(device_type='').filter(is_active=True)
        
        # Фильтр по типу устройства
        device_type = self.request.query_params.get('device_type')
        if device_type:
            queryset = queryset.filter(device_type=device_type)
        
        return queryset.order_by('sort_order', 'name')
    
    @extend_schema(
        summary="Получить список категорий электроники",
        description="Возвращает список активных категорий электроники",
        parameters=[
            OpenApiParameter(name="device_type", type=str, required=False, description="Тип устройства"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=True, methods=['get'])
    @extend_schema(
        summary="Получить подкатегории электроники",
        description="Возвращает список подкатегорий для указанной категории электроники"
    )
    def children(self, request, pk=None):
        """Получить подкатегории."""
        category = self.get_object()
        children = Category.objects.filter(parent=category, device_type__isnull=False).exclude(device_type='').filter(is_active=True)
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class ElectronicsProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами электроники."""
    
    queryset = ElectronicsProduct.objects.filter(is_active=True)
    serializer_class = ElectronicsProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров электроники по параметрам."""
        queryset = ElectronicsProduct.objects.filter(is_active=True)
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по бренду (поддержка массивов)
        brand_ids = self.request.query_params.getlist('brand_id') or self.request.query_params.getlist('brand_id[]')
        if brand_ids:
            try:
                brand_ids = [int(bid) for bid in brand_ids if bid]
                if brand_ids:
                    queryset = queryset.filter(brand_id__in=brand_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по модели
        model = self.request.query_params.get('model')
        if model:
            queryset = queryset.filter(model__icontains=model)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        min_price = self.request.query_params.get('min_price') or self.request.query_params.get('price_min')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price') or self.request.query_params.get('price_max')
        if max_price:
            try:
                max_price = Decimal(max_price)
                queryset = queryset.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return queryset
    
    @extend_schema(
        summary="Получить список товаров электроники",
        description="Возвращает список товаров электроники с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="model", type=str, required=False, description="Модель"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Рекомендуемые товары электроники",
        description="Возвращает список рекомендуемых товаров электроники"
    )
    def featured(self, request):
        """Получить рекомендуемые товары электроники."""
        featured_products = ElectronicsProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)


class FurnitureProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с товарами мебели."""
    
    queryset = FurnitureProduct.objects.filter(is_active=True)
    serializer_class = FurnitureProductSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def _normalize_ordering(self, ordering: str) -> str:
        """Преобразует формат сортировки из фронтенда в формат Django."""
        ordering_map = {
            'name_asc': 'name',
            'name_desc': '-name',
            'price_asc': 'price',
            'price_desc': '-price',
            'newest': '-created_at',
            'popular': '-is_featured',
        }
        return ordering_map.get(ordering, ordering)
    
    def get_queryset(self):
        """Фильтрация товаров мебели по параметрам."""
        queryset = FurnitureProduct.objects.filter(is_active=True)
        
        # Фильтр по категории (поддержка массивов)
        category_ids = self.request.query_params.getlist('category_id') or self.request.query_params.getlist('category_id[]')
        if category_ids:
            try:
                category_ids = [int(cid) for cid in category_ids if cid]
                if category_ids:
                    queryset = queryset.filter(category_id__in=category_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по бренду (поддержка массивов)
        brand_ids = self.request.query_params.getlist('brand_id') or self.request.query_params.getlist('brand_id[]')
        if brand_ids:
            try:
                brand_ids = [int(bid) for bid in brand_ids if bid]
                if brand_ids:
                    queryset = queryset.filter(brand_id__in=brand_ids)
            except (ValueError, TypeError):
                pass
        
        # Фильтр по типу мебели
        furniture_type = self.request.query_params.get('furniture_type')
        if furniture_type:
            queryset = queryset.filter(furniture_type__icontains=furniture_type)
        
        # Фильтр по материалу
        material = self.request.query_params.get('material')
        if material:
            queryset = queryset.filter(material__icontains=material)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Фильтр по цене
        min_price = self.request.query_params.get('min_price') or self.request.query_params.get('price_min')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price') or self.request.query_params.get('price_max')
        if max_price:
            try:
                max_price = Decimal(max_price)
                queryset = queryset.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
        # Сортировка
        ordering = self.request.query_params.get('ordering', '-created_at')
        ordering = self._normalize_ordering(ordering)
        queryset = queryset.order_by(ordering)
        
        return queryset
    
    @extend_schema(
        summary="Получить список товаров мебели",
        description="Возвращает список товаров мебели с возможностью фильтрации",
        parameters=[
            OpenApiParameter(name="category_id", type=int, required=False, description="ID категории"),
            OpenApiParameter(name="brand_id", type=int, required=False, description="ID бренда"),
            OpenApiParameter(name="furniture_type", type=str, required=False, description="Тип мебели"),
            OpenApiParameter(name="material", type=str, required=False, description="Материал"),
            OpenApiParameter(name="search", type=str, required=False, description="Поисковый запрос"),
            OpenApiParameter(name="min_price", type=float, required=False, description="Минимальная цена"),
            OpenApiParameter(name="max_price", type=float, required=False, description="Максимальная цена"),
            OpenApiParameter(name="ordering", type=str, required=False, description="Сортировка"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    @extend_schema(
        summary="Рекомендуемые товары мебели",
        description="Возвращает список рекомендуемых товаров мебели"
    )
    def featured(self, request):
        """Получить рекомендуемые товары мебели."""
        featured_products = FurnitureProduct.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:10]
        serializer = self.get_serializer(featured_products, many=True)
        return Response(serializer.data)


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с услугами."""
    
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    pagination_class = StandardPagination
    lookup_field = 'slug'
    
    def get_queryset(self):
        """Фильтрация услуг по параметрам."""
        queryset = Service.objects.filter(is_active=True)
        
        # Фильтр по категории
        category_id = self.request.query_params.get('category_id')
        if category_id:
            try:
                queryset = queryset.filter(category_id=int(category_id))
            except (ValueError, TypeError):
                pass
        
        # Фильтр по типу услуги
        service_type = self.request.query_params.get('service_type')
        if service_type:
            queryset = queryset.filter(service_type__icontains=service_type)
        
        # Фильтр по поиску
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Сортировка
        queryset = queryset.order_by('-created_at')
        
        return queryset


class FavoriteViewSet(viewsets.ViewSet):
    """API для работы с избранным."""
    
    from rest_framework.permissions import AllowAny
    permission_classes = [AllowAny]
    
    def _get_session_key(self, request):
        """Получить ключ сессии для анонимных пользователей."""
        header_session = request.META.get('HTTP_X_CART_SESSION') or getattr(request, 'headers', {}).get('X-Cart-Session')
        cookie_session = getattr(request, 'COOKIES', {}).get('cart_session')
        django_session = None
        if hasattr(request, 'session'):
            django_session = request.session.session_key
            if not django_session:
                request.session.save()
                django_session = request.session.session_key
        return header_session or cookie_session or django_session
    
    @extend_schema(
        summary="Получить список избранных товаров",
        description="Возвращает список товаров в избранном для текущего пользователя или сессии",
        responses=FavoriteSerializer(many=True),
        examples=[
            OpenApiExample(
                'Пример ответа',
                value=[
                    {
                        "id": 1,
                        "product": {
                            "id": 1,
                            "name": "Test Product",
                            "slug": "test-product",
                            "price": "10.00",
                            "currency": "USD",
                            "main_image_url": "https://example.com/image.jpg"
                        },
                        "created_at": "2024-01-01T12:00:00Z"
                    }
                ],
                response_only=True
            )
        ]
    )
    def list(self, request):
        """Получить список избранных товаров."""
        from django.contrib.contenttypes.models import ContentType
        
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if user:
            favorites = Favorite.objects.filter(user=user).select_related('content_type')
        elif session_key:
            favorites = Favorite.objects.filter(session_key=session_key).select_related('content_type')
        else:
            favorites = Favorite.objects.none()
        
        serializer = FavoriteSerializer(favorites, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Добавить товар в избранное",
        description="Добавляет товар в избранное для текущего пользователя или сессии",
        request=AddToFavoriteSerializer,
        responses={201: FavoriteSerializer, 400: None},
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1},
                request_only=True
            ),
            OpenApiExample(
                'Ответ',
                value={
                    "id": 1,
                    "product": {
                        "id": 1,
                        "name": "Test Product",
                        "slug": "test-product",
                        "price": "10.00",
                        "currency": "USD"
                    },
                    "created_at": "2024-01-01T12:00:00Z"
                },
                response_only=True
            )
        ]
    )
    @action(detail=False, methods=['post'], url_path='add')
    def add(self, request):
        """Добавить товар в избранное."""
        from django.contrib.contenttypes.models import ContentType
        
        serializer = AddToFavoriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product = serializer.validated_data['_product']
        content_type = ContentType.objects.get_for_model(product)
        
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if not user and not session_key:
            return Response(
                {"detail": "Требуется авторизация или сессия"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Проверяем, не добавлен ли уже товар
        if user:
            favorite, created = Favorite.objects.get_or_create(
                user=user,
                content_type=content_type,
                object_id=product.id
            )
        else:
            favorite, created = Favorite.objects.get_or_create(
                session_key=session_key,
                content_type=content_type,
                object_id=product.id
            )
        
        if not created:
            return Response(
                {"detail": "Товар уже в избранном"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Загружаем связанные данные в зависимости от типа товара
        favorite = Favorite.objects.filter(pk=favorite.pk).select_related('content_type').first()
        return Response(FavoriteSerializer(favorite).data, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="Удалить товар из избранного",
        description="Удаляет товар из избранного по ID товара",
        request=AddToFavoriteSerializer,
        responses={200: {"detail": "Товар удален из избранного"}, 404: None},
        examples=[
            OpenApiExample(
                'Запрос',
                value={"product_id": 1},
                request_only=True
            )
        ]
    )
    @action(detail=False, methods=['delete'], url_path='remove')
    def remove(self, request):
        """Удалить товар из избранного."""
        from django.contrib.contenttypes.models import ContentType
        
        serializer = AddToFavoriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        product = serializer.validated_data['_product']
        content_type = ContentType.objects.get_for_model(product)
        
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if not user and not session_key:
            return Response(
                {"detail": "Требуется авторизация или сессия"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Удаляем товар из избранного
        if user:
            deleted = Favorite.objects.filter(
                user=user,
                content_type=content_type,
                object_id=product.id
            ).delete()[0]
        else:
            deleted = Favorite.objects.filter(
                session_key=session_key,
                content_type=content_type,
                object_id=product.id
            ).delete()[0]
        
        if not deleted:
            return Response(
                {"detail": "Товар не найден в избранном"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response({"detail": "Товар удален из избранного"}, status=status.HTTP_200_OK)
    
    @extend_schema(
        summary="Проверить, находится ли товар в избранном",
        description="Проверяет, находится ли товар в избранном для текущего пользователя или сессии",
        parameters=[
            OpenApiParameter(name="product_id", type=int, required=True, description="ID товара")
        ],
        responses={200: {"is_favorite": True}, 404: None}
    )
    @action(detail=False, methods=['get'], url_path='check')
    def check(self, request):
        """Проверить, находится ли товар в избранном."""
        from django.contrib.contenttypes.models import ContentType
        
        product_id = request.query_params.get('product_id')
        product_type = request.query_params.get('product_type', 'medicines')
        
        if not product_id:
            return Response(
                {"detail": "Не указан product_id"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Определяем модель товара по типу
        PRODUCT_MODEL_MAP = {
            'medicines': Product,
            'supplements': Product,
            'medical_equipment': Product,
            'tableware': Product,
            'accessories': Product,
            'jewelry': Product,
            'clothing': ClothingProduct,
            'shoes': ShoeProduct,
            'electronics': ElectronicsProduct,
            'furniture': FurnitureProduct,
        }
        
        model_class = PRODUCT_MODEL_MAP.get(product_type, Product)
        
        try:
            product = model_class.objects.get(id=product_id)
        except model_class.DoesNotExist:
            return Response({"is_favorite": False})
        
        content_type = ContentType.objects.get_for_model(product)
        
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if not user and not session_key:
            return Response({"is_favorite": False})
        
        if user:
            is_favorite = Favorite.objects.filter(
                user=user,
                content_type=content_type,
                object_id=product.id
            ).exists()
        else:
            is_favorite = Favorite.objects.filter(
                session_key=session_key,
                content_type=content_type,
                object_id=product.id
            ).exists()
        
        return Response({"is_favorite": is_favorite})
    
    @extend_schema(
        summary="Получить количество товаров в избранном",
        description="Возвращает количество товаров в избранном для текущего пользователя или сессии",
        responses={200: {"count": 5}}
    )
    @action(detail=False, methods=['get'], url_path='count')
    def count(self, request):
        """Получить количество товаров в избранном."""
        user = request.user if request.user.is_authenticated else None
        session_key = None if user else self._get_session_key(request)
        
        if user:
            count = Favorite.objects.filter(user=user).count()
        elif session_key:
            count = Favorite.objects.filter(session_key=session_key).count()
        else:
            count = 0
        
        return Response({"count": count})


class BannerViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с баннерами."""
    
    queryset = Banner.objects.filter(is_active=True).prefetch_related(
        models.Prefetch('media_files', queryset=BannerMedia.objects.all().order_by('sort_order'))
    )
    serializer_class = BannerSerializer
    permission_classes = []  # Публичный доступ
    
    @extend_schema(
        summary="Получить список баннеров",
        description="Возвращает список активных баннеров с медиа-файлами, отсортированных по позиции и порядку сортировки",
        parameters=[
            OpenApiParameter(
                name="position",
                type=str,
                required=False,
                description="Фильтр по позиции баннера: main, after_brands, before_footer",
                enum=['main', 'after_brands', 'before_footer']
            ),
        ],
        responses={200: BannerSerializer(many=True)},
    )
    def list(self, request):
        """Получить список баннеров с фильтрацией по позиции."""
        position = request.query_params.get('position')
        queryset = self.get_queryset()
        
        if position:
            queryset = queryset.filter(position=position)
        
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


from django.views.decorators.http import require_GET, require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

@require_GET
def proxy_image(request):
    """
    Прокси для Instagram изображений с кешированием.
    Принимает URL изображения напрямую через параметр url.
    """
    # Получаем URL напрямую
    image_url = request.GET.get('url')
    
    if not image_url:
        return JsonResponse({'error': 'url parameter required'}, status=400)
    
    # Логирование для отладки
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Raw URL: {image_url}")
    logger.info(f"URL length: {len(image_url)}")
    logger.info(f"Contains instagram.f: {'instagram.f' in image_url}")
    logger.info(f"Contains cdninstagram: {'cdninstagram.com' in image_url}")
    
    # Проверяем, что это Instagram домен
    if not ('instagram.f' in image_url or 'cdninstagram.com' in image_url):
        logger.error(f"Invalid domain check failed for URL: {image_url}")
        return JsonResponse({'error': f'Invalid domain: {image_url[:100]}...'}, status=400)
    
    # Создаем ключ кеша
    cache_key = f"insta_img_{hashlib.md5(image_url.encode()).hexdigest()}"
    
    # Проверяем кеш
    cached_response = cache.get(cache_key)
    if cached_response:
        return HttpResponse(cached_response, content_type='image/jpeg')
    
    try:
        # Загружаем изображение с правильными headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.instagram.com/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        }
        
        response = requests.get(image_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Кешируем на 24 часа
            cache.set(cache_key, response.content, 86400)
            
            # Возвращаем изображение с правильными headers
            django_response = HttpResponse(response.content, content_type='image/jpeg')
            django_response['Cache-Control'] = 'public, max-age=86400'
            django_response['Access-Control-Allow-Origin'] = '*'
            return django_response
        else:
            return JsonResponse({'error': f'Failed to fetch image: {response.status_code}'}, status=400)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
