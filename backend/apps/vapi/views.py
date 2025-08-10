"""Публичные эндпоинты для управления синхронизацией с API парсера."""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .tasks import (
    pull_products,
    pull_product_details,
    search_products_task,
    sync_categories_and_brands,
    full_catalog_sync
)


class VapiPullView(APIView):
    """Запускает задачу Celery по загрузке товаров из API парсера."""

    @extend_schema(
        summary="Старт фоновой загрузки товаров из API парсера",
        description="Запускает асинхронную задачу для загрузки товаров с указанными параметрами",
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
            200: {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID задачи Celery"},
                    "message": {"type": "string", "description": "Сообщение о запуске"},
                    "parameters": {"type": "object", "description": "Параметры задачи"}
                }
            }
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
        # Получаем параметры из запроса
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 100))
        category = request.query_params.get("category")
        brand = request.query_params.get("brand")
        search = request.query_params.get("search")
        
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


class VapiProductDetailsView(APIView):
    """Запускает задачу по загрузке деталей товара."""

    @extend_schema(
        summary="Загрузка деталей товара",
        description="Запускает асинхронную задачу для загрузки детальной информации о товаре",
        parameters=[
            OpenApiParameter(
                name="product_id", 
                type=str, 
                required=True, 
                description="Идентификатор товара"
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID задачи Celery"},
                    "message": {"type": "string", "description": "Сообщение о запуске"},
                    "product_id": {"type": "string", "description": "ID товара"}
                }
            }
        }
    )
    def post(self, request: Request) -> Response:
        product_id = request.query_params.get("product_id")
        
        if not product_id:
            return Response(
                {"error": "product_id обязателен"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task = pull_product_details.delay(product_id)
        
        return Response({
            "task_id": task.id,
            "message": "Задача загрузки деталей товара запущена",
            "product_id": product_id
        }, status=status.HTTP_200_OK)


class VapiSearchView(APIView):
    """Запускает задачу поиска товаров."""

    @extend_schema(
        summary="Поиск товаров",
        description="Запускает асинхронную задачу для поиска товаров по запросу",
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
            200: {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID задачи Celery"},
                    "message": {"type": "string", "description": "Сообщение о запуске"},
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "limit": {"type": "integer", "description": "Лимит результатов"}
                }
            }
        }
    )
    def post(self, request: Request) -> Response:
        query = request.query_params.get("query")
        limit = int(request.query_params.get("limit", 50))
        
        if not query:
            return Response(
                {"error": "query обязателен"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task = search_products_task.delay(query, limit)
        
        return Response({
            "task_id": task.id,
            "message": "Задача поиска товаров запущена",
            "query": query,
            "limit": limit
        }, status=status.HTTP_200_OK)


class VapiSyncCategoriesView(APIView):
    """Запускает задачу синхронизации категорий и брендов."""

    @extend_schema(
        summary="Синхронизация категорий и брендов",
        description="Запускает асинхронную задачу для синхронизации справочников категорий и брендов",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID задачи Celery"},
                    "message": {"type": "string", "description": "Сообщение о запуске"}
                }
            }
        }
    )
    def post(self, request: Request) -> Response:
        task = sync_categories_and_brands.delay()
        
        return Response({
            "task_id": task.id,
            "message": "Задача синхронизации категорий и брендов запущена"
        }, status=status.HTTP_200_OK)


class VapiFullSyncView(APIView):
    """Запускает задачу полной синхронизации каталога."""

    @extend_schema(
        summary="Полная синхронизация каталога",
        description="Запускает асинхронную задачу для полной синхронизации всего каталога товаров",
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
            200: {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID задачи Celery"},
                    "message": {"type": "string", "description": "Сообщение о запуске"},
                    "max_pages": {"type": "integer", "description": "Максимальное количество страниц"}
                }
            }
        }
    )
    def post(self, request: Request) -> Response:
        max_pages = int(request.query_params.get("max_pages", 100))
        
        task = full_catalog_sync.delay(max_pages)
        
        return Response({
            "task_id": task.id,
            "message": "Задача полной синхронизации каталога запущена",
            "max_pages": max_pages
        }, status=status.HTTP_200_OK)


