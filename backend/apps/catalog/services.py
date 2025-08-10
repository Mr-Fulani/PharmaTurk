"""Сервисы для работы с каталогом товаров."""

import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal
from django.utils.text import slugify
from django.utils import timezone
from django.db import transaction

from .models import Category, Brand, Product, ProductImage, ProductAttribute, PriceHistory
from apps.vapi.client import ProductData

logger = logging.getLogger(__name__)


class CatalogNormalizer:
    """Сервис для нормализации данных из API парсера в модели БД."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def normalize_category(self, category_data: Dict[str, Any]) -> Category:
        """Нормализует данные категории из API."""
        external_id = category_data.get("id", "")
        
        # Ищем существующую категорию по external_id
        category, created = Category.objects.get_or_create(
            external_id=external_id,
            defaults={
                "name": category_data.get("name", "Неизвестная категория"),
                "slug": slugify(category_data.get("name", "unknown")),
                "description": category_data.get("description", ""),
                "external_data": category_data,
            }
        )
        
        if not created:
            # Обновляем существующую категорию
            category.name = category_data.get("name", category.name)
            category.description = category_data.get("description", category.description)
            category.external_data = category_data
            category.save()
        
        # Обрабатываем родительскую категорию
        parent_data = category_data.get("parent")
        if parent_data:
            parent_category = self.normalize_category(parent_data)
            category.parent = parent_category
            category.save()
        
        action = "создана" if created else "обновлена"
        self.logger.info(f"Категория {category.name} {action} (external_id: {external_id})")
        
        return category
    
    def normalize_brand(self, brand_data: Dict[str, Any]) -> Brand:
        """Нормализует данные бренда из API."""
        external_id = brand_data.get("id", "")
        
        # Ищем существующий бренд по external_id
        brand, created = Brand.objects.get_or_create(
            external_id=external_id,
            defaults={
                "name": brand_data.get("name", "Неизвестный бренд"),
                "slug": slugify(brand_data.get("name", "unknown")),
                "description": brand_data.get("description", ""),
                "logo": brand_data.get("logo", ""),
                "website": brand_data.get("website", ""),
                "external_data": brand_data,
            }
        )
        
        if not created:
            # Обновляем существующий бренд
            brand.name = brand_data.get("name", brand.name)
            brand.description = brand_data.get("description", brand.description)
            brand.logo = brand_data.get("logo", brand.logo)
            brand.website = brand_data.get("website", brand.website)
            brand.external_data = brand_data
            brand.save()
        
        action = "создан" if created else "обновлен"
        self.logger.info(f"Бренд {brand.name} {action} (external_id: {external_id})")
        
        return brand
    
    def normalize_product(self, product_data: ProductData) -> Product:
        """Нормализует данные товара из API."""
        external_id = product_data.id
        
        # Ищем существующий товар по external_id
        product, created = Product.objects.get_or_create(
            external_id=external_id,
            defaults={
                "name": product_data.name,
                "slug": slugify(product_data.name),
                "description": product_data.description or "",
                "price": product_data.price,
                "currency": product_data.currency,
                "is_available": product_data.availability,
                "main_image": product_data.images[0] if product_data.images else "",
                "external_url": product_data.url or "",
                "external_data": product_data.metadata,
            }
        )
        
        if not created:
            # Обновляем существующий товар
            old_price = product.price
            product.name = product_data.name
            product.description = product_data.description or product.description
            product.is_available = product_data.availability
            product.external_data = product_data.metadata
            product.last_synced_at = timezone.now()
            
            # Обновляем цену и сохраняем историю
            if product_data.price is not None and product_data.price != old_price:
                product.old_price = old_price
                product.price = product_data.price
                product.currency = product_data.currency
                
                # Создаем запись в истории цен
                PriceHistory.objects.create(
                    product=product,
                    price=product_data.price,
                    currency=product_data.currency,
                    source="api"
                )
            
            product.save()
        
        # Обрабатываем категорию
        if product_data.category:
            category = Category.objects.filter(
                external_id=product_data.category
            ).first()
            if category:
                product.category = category
                product.save()
        
        # Обрабатываем бренд
        if product_data.brand:
            brand = Brand.objects.filter(
                external_id=product_data.brand
            ).first()
            if brand:
                product.brand = brand
                product.save()
        
        # Обрабатываем изображения
        self._normalize_product_images(product, product_data.images)
        
        action = "создан" if created else "обновлен"
        self.logger.info(f"Товар {product.name} {action} (external_id: {external_id})")
        
        return product
    
    def _normalize_product_images(self, product: Product, image_urls: List[str]):
        """Нормализует изображения товара."""
        if not image_urls:
            return
        
        # Удаляем старые изображения, которых нет в новом списке
        existing_urls = set(product.images.values_list("image_url", flat=True))
        new_urls = set(image_urls)
        
        # Удаляем изображения, которых больше нет
        product.images.filter(image_url__in=existing_urls - new_urls).delete()
        
        # Добавляем новые изображения
        for i, image_url in enumerate(image_urls):
            if image_url not in existing_urls:
                is_main = i == 0  # Первое изображение - главное
                ProductImage.objects.create(
                    product=product,
                    image_url=image_url,
                    sort_order=i,
                    is_main=is_main
                )
        
        # Обновляем главное изображение товара
        main_image = product.images.filter(is_main=True).first()
        if main_image:
            product.main_image = main_image.image_url
            product.save()
    
    def normalize_product_attributes(self, product: Product, attributes_data: Dict[str, Any]):
        """Нормализует атрибуты товара из API."""
        if not attributes_data:
            return
        
        # Маппинг типов атрибутов
        attribute_mapping = {
            "composition": "composition",
            "indications": "indications", 
            "contraindications": "contraindications",
            "side_effects": "side_effects",
            "dosage": "dosage",
            "storage": "storage",
            "expiry": "expiry",
            "manufacturer": "manufacturer",
            "country": "country",
            "form": "form",
            "weight": "weight",
        }
        
        # Удаляем старые атрибуты
        product.attributes.all().delete()
        
        # Создаем новые атрибуты
        for attr_type, value in attributes_data.items():
            if attr_type in attribute_mapping and value:
                ProductAttribute.objects.create(
                    product=product,
                    attribute_type=attribute_mapping[attr_type],
                    name=attr_type.title(),
                    value=str(value),
                    sort_order=len(product.attributes.all())
                )
    
    @transaction.atomic
    def sync_categories_and_brands(self, categories_data: List[Dict], brands_data: List[Dict]):
        """Синхронизирует категории и бренды из API."""
        self.logger.info(f"Начинаем синхронизацию: {len(categories_data)} категорий, {len(brands_data)} брендов")
        
        # Синхронизируем категории
        for category_data in categories_data:
            self.normalize_category(category_data)
        
        # Синхронизируем бренды
        for brand_data in brands_data:
            self.normalize_brand(brand_data)
        
        self.logger.info("Синхронизация категорий и брендов завершена")
    
    @transaction.atomic
    def sync_products(self, products_data: List[ProductData]):
        """Синхронизирует товары из API."""
        self.logger.info(f"Начинаем синхронизацию {len(products_data)} товаров")
        
        synced_count = 0
        for product_data in products_data:
            try:
                product = self.normalize_product(product_data)
                synced_count += 1
                
                # Если есть дополнительные атрибуты, нормализуем их
                if hasattr(product_data, 'attributes') and product_data.attributes:
                    self.normalize_product_attributes(product, product_data.attributes)
                    
            except Exception as e:
                self.logger.error(f"Ошибка при синхронизации товара {product_data.id}: {e}")
        
        self.logger.info(f"Синхронизация завершена: {synced_count}/{len(products_data)} товаров")
        return synced_count


class CatalogService:
    """Основной сервис для работы с каталогом."""
    
    def __init__(self):
        self.normalizer = CatalogNormalizer()
        self.logger = logging.getLogger(__name__)
    
    def get_products(self, 
                    category_id: Optional[int] = None,
                    brand_id: Optional[int] = None,
                    search: Optional[str] = None,
                    min_price: Optional[Decimal] = None,
                    max_price: Optional[Decimal] = None,
                    is_available: Optional[bool] = None,
                    limit: int = 50,
                    offset: int = 0) -> List[Product]:
        """Получает товары с фильтрацией."""
        queryset = Product.objects.filter(is_active=True)
        
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)
        
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)
        
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)
        
        if is_available is not None:
            queryset = queryset.filter(is_available=is_available)
        
        return list(queryset[offset:offset + limit])
    
    def get_product_by_slug(self, slug: str) -> Optional[Product]:
        """Получает товар по slug."""
        try:
            return Product.objects.get(slug=slug, is_active=True)
        except Product.DoesNotExist:
            return None
    
    def get_categories(self, parent_id: Optional[int] = None) -> List[Category]:
        """Получает категории."""
        queryset = Category.objects.filter(is_active=True)
        
        if parent_id is None:
            queryset = queryset.filter(parent__isnull=True)
        else:
            queryset = queryset.filter(parent_id=parent_id)
        
        return list(queryset)
    
    def get_brands(self) -> List[Brand]:
        """Получает бренды."""
        return list(Brand.objects.filter(is_active=True))
    
    def get_price_history(self, product_id: int, days: int = 30) -> List[PriceHistory]:
        """Получает историю цен товара."""
        from datetime import timedelta
        
        start_date = timezone.now() - timedelta(days=days)
        return list(
            PriceHistory.objects.filter(
                product_id=product_id,
                recorded_at__gte=start_date
            )
        )
