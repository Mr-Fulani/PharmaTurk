"""API представления для каталога товаров."""

from typing import List
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from .models import (
    Category, Brand, Product, ProductAttribute, PriceHistory,
    ClothingCategory, ClothingProduct, ShoeCategory, ShoeProduct,
    ElectronicsCategory, ElectronicsProduct
)
from .services import CatalogService
from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductSerializer,
    ProductDetailSerializer,
    ProductAttributeSerializer,
    PriceHistorySerializer,
    ClothingCategorySerializer,
    ClothingProductSerializer,
    ShoeCategorySerializer,
    ShoeProductSerializer,
    ElectronicsCategorySerializer,
    ElectronicsProductSerializer
)


class StandardPagination(PageNumberPagination):
    """Стандартная пагинация для API."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями."""
    
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    pagination_class = StandardPagination
    
    @extend_schema(
        summary="Получить список категорий",
        description="Возвращает список активных категорий товаров"
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
        children = Category.objects.filter(parent=category, is_active=True)
        serializer = self.get_serializer(children, many=True)
        return Response(serializer.data)


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с брендами."""
    
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    pagination_class = StandardPagination

    PRODUCT_TYPE_ALIASES = {
        'supplements': 'medicines',
        'tableware': 'tableware',
        'furniture': 'furniture',
        'medical-equipment': 'medical-equipment',
    }
    
    PRODUCT_MODEL_MAP = {
        'medicines': Product,
        'tableware': Product,
        'furniture': Product,
        'medical-equipment': Product,
        'clothing': ClothingProduct,
        'shoes': ShoeProduct,
        'electronics': ElectronicsProduct,
    }

    PRODUCT_TYPE_CATEGORY_SLUGS = {
        'medicines': ['medicines-general'],
        'tableware': ['tableware-serveware'],
        'furniture': ['furniture-living'],
        'medical-equipment': ['medical-equipment'],
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
        description="Возвращает список активных брендов (можно фильтровать по типу товара)"
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
        min_price = self.request.query_params.get('min_price')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price')
        if max_price:
            try:
                max_price = Decimal(max_price)
                queryset = queryset.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass
        
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
    
    queryset = ClothingCategory.objects.filter(is_active=True)
    serializer_class = ClothingCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий одежды."""
        queryset = ClothingCategory.objects.filter(is_active=True)
        
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
        children = ClothingCategory.objects.filter(parent=category, is_active=True)
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
        queryset = ClothingProduct.objects.filter(is_active=True)
        
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
            queryset = queryset.filter(size=size)
        
        # Фильтр по цвету
        color = self.request.query_params.get('color')
        if color:
            queryset = queryset.filter(color__icontains=color)
        
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
        min_price = self.request.query_params.get('min_price')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price')
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


class ShoeCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями обуви."""
    
    queryset = ShoeCategory.objects.filter(is_active=True)
    serializer_class = ShoeCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий обуви."""
        queryset = ShoeCategory.objects.filter(is_active=True)
        
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
        children = ShoeCategory.objects.filter(parent=category, is_active=True)
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
        queryset = ShoeProduct.objects.filter(is_active=True)
        
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
            queryset = queryset.filter(size=size)
        
        # Фильтр по цвету
        color = self.request.query_params.get('color')
        if color:
            queryset = queryset.filter(color__icontains=color)
        
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
        min_price = self.request.query_params.get('min_price')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price')
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


class ElectronicsCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API для работы с категориями электроники."""
    
    queryset = ElectronicsCategory.objects.filter(is_active=True)
    serializer_class = ElectronicsCategorySerializer
    pagination_class = StandardPagination
    
    def get_queryset(self):
        """Фильтрация категорий электроники."""
        queryset = ElectronicsCategory.objects.filter(is_active=True)
        
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
        children = ElectronicsCategory.objects.filter(parent=category, is_active=True)
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
        min_price = self.request.query_params.get('min_price')
        if min_price:
            try:
                min_price = Decimal(min_price)
                queryset = queryset.filter(price__gte=min_price)
            except (ValueError, TypeError):
                pass
        
        max_price = self.request.query_params.get('max_price')
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
