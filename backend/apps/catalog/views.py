"""API представления для каталога товаров."""

from typing import List
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from .models import Category, Brand, Product, ProductAttribute, PriceHistory
from .services import CatalogService
from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductSerializer,
    ProductDetailSerializer,
    ProductAttributeSerializer,
    PriceHistorySerializer
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
    
    @extend_schema(
        summary="Получить список брендов",
        description="Возвращает список активных брендов"
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
    
    def get_queryset(self):
        """Фильтрация товаров по параметрам."""
        queryset = Product.objects.filter(is_active=True)
        
        # Фильтр по категории
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Фильтр по бренду
        brand_id = self.request.query_params.get('brand_id')
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        
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
