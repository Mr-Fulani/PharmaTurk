"""Сервисы для работы с каталогом товаров."""

import logging
import re
import uuid
import httpx
from typing import Dict, List, Optional, Any
from decimal import Decimal
from django.utils.text import slugify
from transliterate import slugify as trans_slugify
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import Category, Brand, Product, ProductImage, ProductAttribute, PriceHistory
from apps.vapi.client import ProductData
from apps.catalog.utils.storage_paths import detect_media_type

logger = logging.getLogger(__name__)


class CatalogNormalizer:
    """Сервис для нормализации данных из API парсера в модели БД."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _resolve_media_type(self, media_url: str) -> str:
        media_type = detect_media_type(media_url)
        if media_type != "image":
            return media_type
        if "/products/parsed/" not in (media_url or ""):
            return media_type
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                response = client.head(media_url)
                if response.status_code >= 400:
                    return media_type
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if content_type.startswith("video/"):
                    return "video"
                if content_type == "image/gif" or content_type.endswith("+gif"):
                    return "gif"
                if content_type.startswith("image/"):
                    return "image"
        except Exception:
            return media_type
        return media_type

    def _sync_product_fields_from_metadata(self, product: Product, metadata: Dict[str, Any]) -> None:
        attrs = (metadata or {}).get("attributes") or {}
        if not isinstance(attrs, dict):
            return

        updated_fields: List[str] = []

        isbn = attrs.get("isbn")
        if isbn:
            new_isbn = str(isbn).strip()
            digits = re.sub(r"\D", "", new_isbn)
            is_valid_length = len(digits) in (10, 13)
            is_placeholder = "00000" in new_isbn or "..." in new_isbn
            if is_valid_length and not is_placeholder and new_isbn != (product.isbn or ""):
                product.isbn = new_isbn
                updated_fields.append("isbn")

        pages = attrs.get("pages")
        if pages is not None:
            try:
                pages_val = int(str(pages).strip())
            except (ValueError, TypeError):
                pages_val = None
            if pages_val is not None and 0 < pages_val < 10000 and pages_val != product.pages:
                product.pages = pages_val
                updated_fields.append("pages")

        publisher = attrs.get("publisher")
        if publisher:
            publisher_val = str(publisher).strip()
            if publisher_val and publisher_val != (product.publisher or ""):
                product.publisher = publisher_val
                updated_fields.append("publisher")

        cover_type = attrs.get("cover_type")
        if cover_type:
            cover_type_val = str(cover_type).strip()
            if cover_type_val and cover_type_val != (product.cover_type or ""):
                product.cover_type = cover_type_val
                updated_fields.append("cover_type")

        language = attrs.get("language")
        if language:
            language_val = str(language).strip()
            if language_val and language_val != (product.language or ""):
                product.language = language_val
                updated_fields.append("language")

        if updated_fields:
            product.save(update_fields=updated_fields)
    
    def normalize_category(self, category_data: Dict[str, Any]) -> Category:
        """Нормализует данные категории из API."""
        external_id = category_data.get("id", "")
        name = category_data.get("name", "Неизвестная категория")
        
        # Генерируем slug
        base_slug = trans_slugify(name, language_code='ru') or slugify(name)
        if not base_slug:
            base_slug = "category"
        slug = f"{base_slug}-{external_id}" if external_id else base_slug
        
        # Ищем существующую категорию по external_id
        category, created = Category.objects.get_or_create(
            external_id=external_id,
            defaults={
                "name": name,
                "slug": slug,
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
        name = brand_data.get("name", "Неизвестный бренд")
        
        # Генерируем slug
        base_slug = trans_slugify(name, language_code='ru') or slugify(name)
        if not base_slug:
            base_slug = "brand"
        slug = f"{base_slug}-{external_id}" if external_id else base_slug
        
        # Ищем существующий бренд по external_id
        brand, created = Brand.objects.get_or_create(
            external_id=external_id,
            defaults={
                "name": name,
                "slug": slug,
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
        external_id = str(product_data.id).strip() if product_data.id is not None else ""
        
        # Ищем существующий товар по external_id
        # Используем filter().first() вместо get_or_create, так как external_id не уникален
        if external_id:
            existing_products = Product.objects.filter(external_id=external_id)
        else:
            existing_products = Product.objects.none()
        
        # Генерируем slug
        base_slug = trans_slugify(product_data.name, language_code='ru') or slugify(product_data.name)
        if not base_slug:
            base_slug = "product"
        
        # Добавляем external_id к slug для уникальности
        if external_id:
            slug = f"{base_slug}-{external_id}"
        else:
            slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
        
        main_image_url = ""
        for media_url in product_data.images or []:
            if self._resolve_media_type(media_url) == "image":
                main_image_url = media_url
                break

        defaults = {
            "name": product_data.name,
            "slug": slug,
            "description": product_data.description or "",
            "price": product_data.price,
            "currency": product_data.currency,
            "is_available": product_data.availability,
            "main_image": main_image_url,
            "external_url": product_data.url or "",
            "external_data": product_data.metadata,
        }
        
        if existing_products.exists():
            product = existing_products.first()
            created = False
            if existing_products.count() > 1:
                self.logger.warning(f"Найдено {existing_products.count()} товаров с external_id {external_id}. Используется первый.")
        else:
            product = Product.objects.create(external_id=external_id, **defaults)
            created = True
        
        # Обновляем stock_quantity если он есть в данных парсера
        if hasattr(product_data, 'metadata') and product_data.metadata:
            stock = product_data.metadata.get('stock_quantity')
            if stock is not None:
                product.stock_quantity = stock
                product.save(update_fields=['stock_quantity'])

        # Обновляем video_url если есть в метаданных (от парсеров)
        if hasattr(product_data, 'metadata') and product_data.metadata:
            attributes = product_data.metadata.get('attributes', {})
            if attributes.get('video_url'):
                product.video_url = attributes['video_url']
                product.save(update_fields=['video_url'])

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

        if hasattr(product_data, "metadata") and product_data.metadata:
            self._sync_product_fields_from_metadata(product, product_data.metadata)
        
        # Обрабатываем категорию
        # Если категория пришла как строка (название), ищем или создаем по названию
        if product_data.category:
            if isinstance(product_data.category, str) and not product_data.category.isdigit():
                # Это название категории (например "Книги")
                # Ищем категорию по имени или slug
                cat_name = product_data.category
                cat_slug = trans_slugify(cat_name, language_code='ru') or slugify(cat_name)
                normalized_name = (cat_name or "").strip().lower()
                if cat_slug == "knigi" or normalized_name in {"книги", "книга", "books"}:
                    books_category = Category.objects.filter(slug="books").first()
                    if books_category:
                        category = books_category
                        cat_slug = "books"
                    else:
                        category = None
                else:
                    category = Category.objects.filter(
                        Q(name__iexact=cat_name) | Q(slug=cat_slug)
                    ).first()
                
                if not category:
                    # Если не нашли, создаем
                    self.logger.info(f"Создание новой категории из парсера: {cat_name}")
                    category = Category.objects.create(
                        name=cat_name,
                        slug=cat_slug,
                        is_active=True
                    )
                
                product.category = category
                
                # Обновляем product_type если категория "Книги"
                if cat_name.lower() == 'книги' or cat_slug == 'knigi' or cat_slug == 'books':
                    product.product_type = 'books'
                
                product.save()
            else:
                # Это ID категории
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

        metadata = product.external_data if isinstance(product.external_data, dict) else {}
        attrs = metadata.get("attributes") if isinstance(metadata.get("attributes"), dict) else {}
        gallery_video_url = next(
            (url for url in image_urls if self._resolve_media_type(url) == "video"),
            None,
        )
        preferred_main_video_url = attrs.get("main_video_url") or attrs.get("main_media_url")
        if not isinstance(preferred_main_video_url, str) or not preferred_main_video_url:
            preferred_main_video_url = None
        elif self._resolve_media_type(preferred_main_video_url) != "video":
            preferred_main_video_url = None

        if preferred_main_video_url and preferred_main_video_url not in image_urls:
            image_urls = [preferred_main_video_url] + list(image_urls)

        deduped_urls = []
        seen_urls = set()
        for url in image_urls:
            if not url:
                continue
            if url in seen_urls:
                continue
            deduped_urls.append(url)
            seen_urls.add(url)
        image_urls = deduped_urls
        
        # Удаляем старые изображения, которых нет в новом списке
        existing_image_urls = set(product.images.values_list("image_url", flat=True))
        existing_video_urls = set(product.images.values_list("video_url", flat=True))
        existing_urls = existing_image_urls | existing_video_urls
        new_urls = set(image_urls)
        
        # Удаляем изображения, которых больше нет
        product.images.exclude(Q(image_url__in=new_urls) | Q(video_url__in=new_urls)).delete()
        
        # Добавляем новые изображения
        main_image_url = None
        for i, image_url in enumerate(image_urls):
            media_type = self._resolve_media_type(image_url)
            existing_item = product.images.filter(Q(image_url=image_url) | Q(video_url=image_url)).first()
            desired_is_main = False
            if preferred_main_video_url:
                if media_type == "video" and image_url == preferred_main_video_url:
                    desired_is_main = True
            elif media_type == "image" and main_image_url is None:
                desired_is_main = True
                main_image_url = image_url
            if existing_item:
                updates = {}
                if media_type == "video" and existing_item.video_url != image_url:
                    updates = {"video_url": image_url, "image_url": "", "is_main": False}
                elif media_type == "image" and existing_item.image_url != image_url:
                    updates = {"image_url": image_url, "video_url": ""}
                if existing_item.sort_order != i:
                    updates["sort_order"] = i
                if existing_item.is_main != desired_is_main:
                    updates["is_main"] = desired_is_main
                if updates:
                    existing_item.__class__.objects.filter(pk=existing_item.pk).update(**updates)
                continue
            ProductImage.objects.create(
                product=product,
                image_url=image_url if media_type == "image" else "",
                video_url=image_url if media_type == "video" else "",
                sort_order=i,
                is_main=desired_is_main
            )
        
        if preferred_main_video_url:
            product.images.filter(is_main=True).exclude(video_url=preferred_main_video_url).update(is_main=False)
            product.images.filter(video_url=preferred_main_video_url).update(is_main=True)
            update_fields = []
            if product.main_image:
                product.main_image = ""
                update_fields.append("main_image")
            if product.video_url != preferred_main_video_url:
                product.video_url = preferred_main_video_url
                update_fields.append("video_url")
            if update_fields:
                product.save(update_fields=update_fields)
            return

        if gallery_video_url:
            update_fields = []
            if product.video_url != gallery_video_url:
                product.video_url = gallery_video_url
                update_fields.append("video_url")
            if product.main_video_file:
                product.main_video_file.delete(save=False)
                product.main_video_file = None
                update_fields.append("main_video_file")
            if update_fields:
                product.save(update_fields=update_fields)

        main_image_url = None
        for media_url in image_urls:
            if self._resolve_media_type(media_url) == "image":
                main_image_url = media_url
                break

        if main_image_url:
            product.images.filter(is_main=True).exclude(image_url=main_image_url).update(is_main=False)
            product.images.filter(image_url=main_image_url).update(is_main=True)
            product.main_image = main_image_url
            product.save()
        else:
            product.images.filter(is_main=True).update(is_main=False)
            if product.main_image:
                product.main_image = ""
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
        queryset = Product.objects.filter(is_active=True).exclude(
            Q(product_type__in=['clothing', 'shoes']) &
            (Q(external_data__has_key='source_variant_id') | Q(external_data__has_key='source_variant_slug'))
        )
        
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
