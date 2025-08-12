"""Фоновые задачи Celery для интеграции с Vapi API (vapi.co)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from celery import shared_task
from django.utils import timezone

from .client import VapiClient, ProductData
from apps.catalog.services import CatalogNormalizer

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def pull_products(
    self,
    page: int = 1, 
    page_size: int = 100,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    search: Optional[str] = None,
    product_type: Optional[str] = None,  # "drug" или "supplement"
    lang: Optional[str] = None,
    sort: Optional[str] = None,
) -> Dict:
    """Задача: загрузить список товаров из Vapi API.
    
    Args:
        page: Номер страницы
        page_size: Размер страницы
        category: Фильтр по категории
        brand: Фильтр по бренду
        search: Поисковый запрос
        product_type: Тип продукта ("drug", "supplement")
        
    Returns:
        Словарь с результатами загрузки
    """
    try:
        client = VapiClient.from_env()
        data = client.list_products(
            page=page, 
            page_size=page_size,
            category=category,
            brand=brand,
            search=search,
            product_type=product_type,
            lang=lang,
            sort=sort,
        )
        
        # Нормализуем данные в БД
        normalizer = CatalogNormalizer()
        products_data = []
        
        for item in data.get("data", []):
            try:
                # Преобразуем данные API в ProductData
                product_data = ProductData(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    description=item.get("description"),
                    price=item.get("price"),
                    currency=item.get("currency", "RUB"),
                    category=item.get("category"),
                    brand=item.get("brand"),
                    images=item.get("images", []),
                    url=item.get("url"),
                    availability=item.get("availability", True),
                    metadata=item.get("metadata", {}),
                    active_ingredients=item.get("active_ingredients", []),
                    manufacturer=item.get("manufacturer"),
                    dosage_form=item.get("dosage_form"),
                    strength=item.get("strength"),
                    barcode=item.get("barcode"),
                    atc_code=item.get("atc_code"),
                    rx_required=item.get("rx_required", False),
                    contraindications=item.get("contraindications", []),
                    side_effects=item.get("side_effects", []),
                    interactions=item.get("interactions", [])
                )
                products_data.append(product_data)
            except Exception as e:
                logger.error(f"Ошибка при обработке товара {item.get('id')}: {e}")
        
        # Синхронизируем товары в БД
        synced_count = normalizer.sync_products(products_data)
        
        result = {
            "page": page,
            "page_size": page_size,
            "total_products": len(data.get("data", [])),
            "synced_count": synced_count,
            "product_type": product_type,
            "status": "success",
            "timestamp": timezone.now().isoformat()
        }
        
        logger.info(f"Задача pull_products завершена: {synced_count} товаров синхронизировано")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка в задаче pull_products: {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {
            "page": page,
            "page_size": page_size,
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def pull_product_details(self, product_id: str, lang: Optional[str] = None) -> Dict:
    """Задача: загрузить детальную информацию о товаре.
    
    Args:
        product_id: Идентификатор товара
        
    Returns:
        Словарь с результатами загрузки
    """
    try:
        client = VapiClient.from_env()
        product_data = client.get_product(product_id, lang=lang)
        
        if not product_data:
            return {
                "product_id": product_id,
                "status": "not_found",
                "timestamp": timezone.now().isoformat()
            }
        
        # Нормализуем данные в БД
        normalizer = CatalogNormalizer()
        product = normalizer.normalize_product(product_data)
        
        # Загружаем дополнительные данные
        interactions = client.get_drug_interactions(product_id, lang=lang)
        contraindications = client.get_contraindications(product_id, lang=lang)
        
        result = {
            "product_id": product_id,
            "product_name": product.name,
            "interactions_count": len(interactions),
            "contraindications_count": len(contraindications),
            "status": "success",
            "timestamp": timezone.now().isoformat()
        }
        
        logger.info(f"Детали товара {product_id} загружены")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка в задаче pull_product_details для {product_id}: {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {
            "product_id": product_id,
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def search_products_task(self, query: str, limit: int = 50, product_type: Optional[str] = None, lang: Optional[str] = None) -> Dict:
    """Задача: поиск товаров по запросу.
    
    Args:
        query: Поисковый запрос
        limit: Максимальное количество результатов
        product_type: Тип продукта ("drug", "supplement")
        
    Returns:
        Словарь с результатами поиска
    """
    try:
        client = VapiClient.from_env()
        products_data = client.search_products(query, limit, product_type, lang=lang)
        
        # Нормализуем данные в БД
        normalizer = CatalogNormalizer()
        synced_count = normalizer.sync_products(products_data)
        
        result = {
            "query": query,
            "limit": limit,
            "product_type": product_type,
            "found_products": len(products_data),
            "synced_count": synced_count,
            "status": "success",
            "timestamp": timezone.now().isoformat()
        }
        
        logger.info(f"Поиск товаров '{query}' завершен: {synced_count} товаров синхронизировано")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка в задаче search_products_task для '{query}': {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {
            "query": query,
            "limit": limit,
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_categories_and_brands(self) -> Dict:
    """Задача: синхронизация категорий и брендов из Vapi API.
    
    Returns:
        Словарь с результатами синхронизации
    """
    try:
        client = VapiClient.from_env()
        
        # Загружаем категории
        categories_data = client.get_categories()
        
        # Загружаем бренды
        brands_data = client.get_brands()
        
        # Нормализуем данные в БД
        normalizer = CatalogNormalizer()
        normalizer.sync_categories_and_brands(categories_data, brands_data)
        
        result = {
            "categories_count": len(categories_data),
            "brands_count": len(brands_data),
            "status": "success",
            "timestamp": timezone.now().isoformat()
        }
        
        logger.info(f"Синхронизация справочников завершена: {len(categories_data)} категорий, {len(brands_data)} брендов")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка в задаче sync_categories_and_brands: {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def full_catalog_sync(self, max_pages: int = 100) -> Dict:
    """Задача: полная синхронизация каталога.
    
    Args:
        max_pages: Максимальное количество страниц для загрузки
        
    Returns:
        Словарь с результатами синхронизации
    """
    try:
        client = VapiClient.from_env()
        normalizer = CatalogNormalizer()
        
        total_products = 0
        total_synced = 0
        page = 1
        
        # Сначала синхронизируем справочники
        sync_categories_and_brands.delay()
        
        while page <= max_pages:
            try:
                # Загружаем страницу товаров
                data = client.list_products(page=page, page_size=100)
                products = data.get("data", [])
                
                if not products:
                    break
                
                # Преобразуем в ProductData
                products_data = []
                for item in products:
                    try:
                        product_data = ProductData(
                            id=item.get("id", ""),
                            name=item.get("name", ""),
                            description=item.get("description"),
                            price=item.get("price"),
                            currency=item.get("currency", "RUB"),
                            category=item.get("category"),
                            brand=item.get("brand"),
                            images=item.get("images", []),
                            url=item.get("url"),
                            availability=item.get("availability", True),
                            metadata=item.get("metadata", {}),
                            active_ingredients=item.get("active_ingredients", []),
                            manufacturer=item.get("manufacturer"),
                            dosage_form=item.get("dosage_form"),
                            strength=item.get("strength"),
                            barcode=item.get("barcode"),
                            atc_code=item.get("atc_code"),
                            rx_required=item.get("rx_required", False),
                            contraindications=item.get("contraindications", []),
                            side_effects=item.get("side_effects", []),
                            interactions=item.get("interactions", [])
                        )
                        products_data.append(product_data)
                    except Exception as e:
                        logger.error(f"Ошибка при обработке товара {item.get('id')}: {e}")
                
                # Синхронизируем товары
                synced_count = normalizer.sync_products(products_data)
                total_products += len(products)
                total_synced += synced_count
                
                logger.info(f"Страница {page}: {synced_count}/{len(products)} товаров синхронизировано")
                
                page += 1
                
            except Exception as e:
                logger.error(f"Ошибка при загрузке страницы {page}: {e}")
                break
        
        result = {
            "total_pages": page - 1,
            "total_products": total_products,
            "total_synced": total_synced,
            "status": "success",
            "timestamp": timezone.now().isoformat()
        }
        
        logger.info(f"Полная синхронизация завершена: {total_synced}/{total_products} товаров")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка в задаче full_catalog_sync: {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": timezone.now().isoformat()
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_drugs_only(self, max_pages: int = 50) -> Dict:
    """Задача: синхронизация только лекарственных препаратов.
    
    Args:
        max_pages: Максимальное количество страниц для загрузки
        
    Returns:
        Словарь с результатами синхронизации
    """
    return pull_products.delay(
        page=1,
        page_size=100,
        product_type="drug",
        max_pages=max_pages
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_supplements_only(self, max_pages: int = 50) -> Dict:
    """Задача: синхронизация только БАДов.
    
    Args:
        max_pages: Максимальное количество страниц для загрузки
        
    Returns:
        Словарь с результатами синхронизации
    """
    return pull_products.delay(
        page=1,
        page_size=100,
        product_type="supplement",
        max_pages=max_pages
    )

