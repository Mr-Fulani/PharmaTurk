"""Публичные эндпоинты для управления синхронизацией с API парсера."""
from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from .tasks import (
    pull_products,
    pull_product_details,
    search_products_task,
    sync_categories_and_brands,
    full_catalog_sync
)
from .serializers import (
    VapiFullSyncQuerySerializer,
    VapiProductDetailsQuerySerializer,
    VapiPullQuerySerializer,
    VapiPullResponseSerializer,
    VapiSearchQuerySerializer,
    VapiSearchResponseSerializer,
    VapiProductDetailsResponseSerializer,
    VapiTaskResponseSerializer,
    VapiFullSyncResponseSerializer,
)


class VapiAdminAPIView(APIView):
    """Base class for catalog synchronization endpoints restricted to staff."""

    permission_classes = [IsAdminUser]


class VapiPullView(VapiAdminAPIView):
    """Запускает задачу Celery по загрузке товаров из API парсера."""

    @extend_schema(
        summary="Старт фоновой загрузки товаров из API парсера",
        description="Запускает асинхронную задачу для загрузки товаров с указанными параметрами",
        request=None,
        parameters=[
            OpenApiParameter(
                name="page", 
                type=int, 
                required=False, 
                description="Номер страницы (по умолчанию 1)",
                default=1
            ),
            OpenApiParameter(
                name="page_size", 
                type=int, 
                required=False, 
                description="Размер страницы (по умолчанию 100)",
                default=100
            ),
            OpenApiParameter(
                name="category", 
                type=str, 
                required=False, 
                description="Фильтр по категории"
            ),
            OpenApiParameter(
                name="brand", 
                type=str, 
                required=False, 
                description="Фильтр по бренду"
            ),
            OpenApiParameter(
                name="search", 
                type=str, 
                required=False, 
                description="Поисковый запрос"
            ),
        ],
        responses={
            200: VapiPullResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки query-параметров",
            ),
        },
        examples=[
            OpenApiExample(
                "Успешный запуск",
                value={
                    "task_id": "abc123-def456",
                    "message": "Задача загрузки товаров запущена",
                    "parameters": {
                        "page": 1,
                        "page_size": 100,
                        "category": None,
                        "brand": None,
                        "search": None
                    }
                }
            )
        ]
    )
    def post(self, request: Request) -> Response:
        serializer = VapiPullQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        parameters = serializer.validated_data

        page = parameters["page"]
        page_size = parameters["page_size"]
        category = parameters.get("category")
        brand = parameters.get("brand")
        search = parameters.get("search")
        
        # Запускаем задачу
        task = pull_products.delay(
            page=page,
            page_size=page_size,
            category=category,
            brand=brand,
            search=search
        )
        
        return Response({
            "task_id": task.id,
            "message": "Задача загрузки товаров запущена",
            "parameters": {
                "page": page,
                "page_size": page_size,
                "category": category,
                "brand": brand,
                "search": search
            }
        }, status=status.HTTP_200_OK)


class VapiProductDetailsView(VapiAdminAPIView):
    """Запускает задачу по загрузке деталей товара."""

    @extend_schema(
        summary="Загрузка деталей товара",
        description="Запускает асинхронную задачу для загрузки детальной информации о товаре",
        request=None,
        parameters=[
            OpenApiParameter(
                name="product_id", 
                type=str, 
                required=True, 
                description="Идентификатор товара"
            ),
        ],
        responses={
            200: VapiProductDetailsResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки query-параметров",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = VapiProductDetailsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]
        
        task = pull_product_details.delay(product_id)
        
        return Response({
            "task_id": task.id,
            "message": "Задача загрузки деталей товара запущена",
            "product_id": product_id
        }, status=status.HTTP_200_OK)


class VapiSearchView(VapiAdminAPIView):
    """Запускает задачу поиска товаров."""

    @extend_schema(
        summary="Поиск товаров",
        description="Запускает асинхронную задачу для поиска товаров по запросу",
        request=None,
        parameters=[
            OpenApiParameter(
                name="query", 
                type=str, 
                required=True, 
                description="Поисковый запрос"
            ),
            OpenApiParameter(
                name="limit", 
                type=int, 
                required=False, 
                description="Максимальное количество результатов (по умолчанию 50)",
                default=50
            ),
        ],
        responses={
            200: VapiSearchResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки query-параметров",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = VapiSearchQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data["query"]
        limit = serializer.validated_data["limit"]
        
        task = search_products_task.delay(query, limit)
        
        return Response({
            "task_id": task.id,
            "message": "Задача поиска товаров запущена",
            "query": query,
            "limit": limit
        }, status=status.HTTP_200_OK)


class VapiSyncCategoriesView(VapiAdminAPIView):
    """Запускает задачу синхронизации категорий и брендов."""

    @extend_schema(
        summary="Синхронизация категорий и брендов",
        description="Запускает асинхронную задачу для синхронизации справочников категорий и брендов",
        request=None,
        responses={200: VapiTaskResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        task = sync_categories_and_brands.delay()
        
        return Response({
            "task_id": task.id,
            "message": "Задача синхронизации категорий и брендов запущена"
        }, status=status.HTTP_200_OK)


class VapiFullSyncView(VapiAdminAPIView):
    """Запускает задачу полной синхронизации каталога."""

    @extend_schema(
        summary="Полная синхронизация каталога",
        description="Запускает асинхронную задачу для полной синхронизации всего каталога товаров",
        request=None,
        parameters=[
            OpenApiParameter(
                name="max_pages", 
                type=int, 
                required=False, 
                description="Максимальное количество страниц для загрузки (по умолчанию 100)",
                default=100
            ),
        ],
        responses={
            200: VapiFullSyncResponseSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Ошибки query-параметров",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = VapiFullSyncQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        max_pages = serializer.validated_data["max_pages"]
        
        task = full_catalog_sync.delay(max_pages)
        
        return Response({
            "task_id": task.id,
            "message": "Задача полной синхронизации каталога запущена",
            "max_pages": max_pages
        }, status=status.HTTP_200_OK)
