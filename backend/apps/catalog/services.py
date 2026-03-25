"""Сервисы для работы с каталогом товаров."""

import datetime
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

from .models import Category, Brand, Product, ProductImage, PriceHistory
from .scraper_category_mapping import resolve_category_and_product_type
from apps.vapi.client import ProductData
from apps.catalog.utils.storage_paths import detect_media_type

logger = logging.getLogger(__name__)

# Реестр: product_type → имя метода CatalogNormalizer для синхронизации атрибутов в доменную модель
SYNC_METADATA_HANDLER_NAMES = {
    "books": "_sync_books_metadata",
    "jewelry": "_sync_jewelry_metadata",
    "medicines": "_sync_medicines_metadata",
}


class CatalogNormalizer:
    """Сервис для нормализации данных из API парсера в модели БД."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Кеш результатов HEAD-запросов для определения типа медиа.
        # Хранится на уровне экземпляра, чтобы не делать повторные запросы
        # к одному и тому же URL в рамках одного запуска парсера.
        self._media_type_cache: dict = {}

    def _resolve_media_type(self, media_url: str) -> str:
        if media_url in self._media_type_cache:
            return self._media_type_cache[media_url]
        media_type = detect_media_type(media_url)
        if media_type != "image" or "/products/parsed/" not in (media_url or ""):
            self._media_type_cache[media_url] = media_type
            return media_type
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                response = client.head(media_url)
                if response.status_code >= 400:
                    self._media_type_cache[media_url] = media_type
                    return media_type
                content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if content_type.startswith("video/"):
                    media_type = "video"
                elif content_type == "image/gif" or content_type.endswith("+gif"):
                    media_type = "gif"
                elif content_type.startswith("image/"):
                    media_type = "image"
        except Exception:
            pass
        self._media_type_cache[media_url] = media_type
        return media_type

    def _is_books_category(self, category: Category | None) -> bool:
        if not category:
            return False
        if (category.slug or "").lower() == "books":
            return True
        parent = getattr(category, "parent", None)
        if parent and (parent.slug or "").lower() == "books":
            return True
        return False

    def _is_books_payload(self, category_value: str | None, attrs: Dict[str, Any]) -> bool:
        raw = (category_value or "").strip().lower()
        if raw in {"книги", "книга", "books", "book"}:
            return True
        if not isinstance(attrs, dict):
            return False
        return any(
            bool(attrs.get(key))
            for key in (
                "isbn",
                "author",
                "publisher",
                "pages",
                "language",
                "cover_type",
                "format_type",
            )
        )

    def _normalize_publisher(self, p: str) -> str:
        if not p:
            return ""
        
        # 1. Убираем кавычки
        p = re.sub(r'[\"\'«»]', '', p)
        
        # 2. Убираем слова издательство, издательский дом (игнорируя регистр)
        p = re.sub(r'(?i)\b(издательский\s+дом|издательство)\b', '', p)
        
        # 3. Убираем лишние пробелы по краям и внутри
        p = re.sub(r'\s+', ' ', p).strip()
        
        if not p:
            return ""

        # 4. Спец-кейсы написания:
        if p.upper() == 'UMMA LAND':
            p = 'UMMALAND'
        
        # 5. Красивый регистр: если все большими буквами, делаем Title (кроме некоторых)
        if p.isupper() and p.upper() != 'UMMALAND':
            p = p.title()
            
        return p

    def _sync_books_metadata(self, product: Product, attrs: Dict[str, Any]) -> None:
        """Синхронизирует книжные атрибуты в BookProduct."""
        book_keys = ("isbn", "publisher", "pages", "cover_type", "language", "publication_year")
        from apps.catalog.models import BookProduct

        book_product = getattr(product, "book_item", None)
        if not book_product:
            base_slug = product.slug or slugify(product.name)
            slug = f"book-{base_slug}"
            i = 2
            while BookProduct.objects.filter(slug=slug).exists():
                slug = f"book-{base_slug}-{i}"
                i += 1
            book_product = BookProduct.objects.create(
                base_product=product,
                name=product.name,
                slug=slug,
                description=product.description or "",
                category=product.category,
                brand=product.brand,
                price=product.price,
                currency=product.currency or "RUB",
                old_price=product.old_price,
                external_id=product.external_id or "",
                external_url=product.external_url or "",
                external_data=product.external_data or {},
                is_active=product.is_active,
                is_available=product.is_available,
                main_image=product.main_image or "",
            )
            product.book_item = book_product

        book_updated = False
        isbn = attrs.get("isbn")
        if isbn:
            new_isbn = str(isbn).strip()
            digits = re.sub(r"\D", "", new_isbn)
            if len(digits) in (10, 13) and "00000" not in new_isbn and "..." not in new_isbn and new_isbn != (book_product.isbn or ""):
                book_product.isbn = new_isbn
                book_updated = True
        pages = attrs.get("pages")
        if pages is not None:
            try:
                pages_val = int(str(pages).strip())
                if 0 < pages_val < 10000 and pages_val != book_product.pages:
                    book_product.pages = pages_val
                    book_updated = True
            except (ValueError, TypeError):
                pass
        publisher = attrs.get("publisher")
        if publisher:
            v = self._normalize_publisher(str(publisher))
            if v and v != (book_product.publisher or ""):
                book_product.publisher = v
                book_updated = True
        cover_type = attrs.get("cover_type")
        if cover_type:
            v = str(cover_type).strip()
            if v and v != (book_product.cover_type or ""):
                book_product.cover_type = v
                book_updated = True
        language = attrs.get("language")
        if language:
            v = str(language).strip()
            if v and v != (book_product.language or ""):
                book_product.language = v
                book_updated = True
        publication_year = attrs.get("publication_year")
        if publication_year is not None and str(publication_year).strip():
            try:
                year = int(str(publication_year).strip())
                if 1900 <= year <= 2100:
                    new_date = datetime.date(year, 1, 1)
                    if book_product.publication_date != new_date:
                        book_product.publication_date = new_date
                        book_updated = True
            except (ValueError, TypeError):
                pass
        if book_updated:
            book_product.save()

    def _sync_jewelry_metadata(self, product: Product, attrs: Dict[str, Any]) -> None:
        """Синхронизирует атрибуты украшений в JewelryProduct."""
        jewelry_keys = ("jewelry_type", "material", "metal_purity", "stone_type", "carat_weight", "gender")
        if not any(k in attrs for k in jewelry_keys):
            return
        jewelry_product = getattr(product, "jewelry_item", None)
        if not jewelry_product:
            return  # домен создаётся сигналом ensure_domain_product_for_base при save Product
        jewelry_updated = False
        valid_jewelry_types = {"ring", "bracelet", "necklace", "earrings", "pendant"}
        if "jewelry_type" in attrs and attrs["jewelry_type"]:
            v = str(attrs["jewelry_type"]).strip().lower()
            if v in valid_jewelry_types and v != (jewelry_product.jewelry_type or ""):
                jewelry_product.jewelry_type = v
                jewelry_updated = True
        if "material" in attrs and attrs["material"]:
            v = str(attrs["material"]).strip()[:100]
            if v != (jewelry_product.material or ""):
                jewelry_product.material = v
                jewelry_updated = True
        if "metal_purity" in attrs and attrs["metal_purity"]:
            v = str(attrs["metal_purity"]).strip()[:50]
            if v != (jewelry_product.metal_purity or ""):
                jewelry_product.metal_purity = v
                jewelry_updated = True
        if "stone_type" in attrs and attrs["stone_type"]:
            v = str(attrs["stone_type"]).strip()[:100]
            if v != (jewelry_product.stone_type or ""):
                jewelry_product.stone_type = v
                jewelry_updated = True
        if "carat_weight" in attrs and attrs["carat_weight"] is not None:
            try:
                v = Decimal(str(attrs["carat_weight"]).strip().replace(",", "."))
                if v >= 0 and (jewelry_product.carat_weight is None or jewelry_product.carat_weight != v):
                    jewelry_product.carat_weight = v
                    jewelry_updated = True
            except (ValueError, TypeError):
                pass
        if "gender" in attrs and attrs["gender"]:
            v = str(attrs["gender"]).strip()[:10]
            if v != (jewelry_product.gender or ""):
                jewelry_product.gender = v
                jewelry_updated = True
        if jewelry_updated:
            jewelry_product.save()

    def _sync_medicines_metadata(self, product: Product, attrs: Dict[str, Any]) -> None:
        """Синхронизирует атрибуты медикаментов в MedicineProduct."""
        medicine_keys = (
            "dosage_form", "active_ingredient", "prescription_required", "prescription_type", "volume", 
            "origin_country", "sgk_status", "administration_route"
        )
        if not any(k in attrs for k in medicine_keys):
            return
            
        medicine_product = getattr(product, "medicine_item", None)
        if not medicine_product:
            return  # домен создаётся сигналом ensure_domain_product_for_base при save Product
            
        medicine_updated = False
        
        if "dosage_form" in attrs and attrs["dosage_form"]:
            v = str(attrs["dosage_form"]).strip()[:100]
            if v != (medicine_product.dosage_form or ""):
                medicine_product.dosage_form = v
                medicine_updated = True
                
        if "active_ingredient" in attrs and attrs["active_ingredient"]:
            v = str(attrs["active_ingredient"]).strip()[:300]
            if v != (medicine_product.active_ingredient or ""):
                medicine_product.active_ingredient = v
                medicine_updated = True
                
                
        if "prescription_required" in attrs:
            val = bool(attrs["prescription_required"])
            if val != medicine_product.prescription_required:
                medicine_product.prescription_required = val
                medicine_updated = True
                
        if medicine_updated:
            medicine_product.save()

    def _sync_product_fields_from_metadata(self, product: Product, metadata: Dict[str, Any]) -> None:
        attrs = (metadata or {}).get("attributes") or {}
        if not isinstance(attrs, dict):
            return

        handler_name = SYNC_METADATA_HANDLER_NAMES.get(product.product_type)
        if handler_name:
            handler = getattr(self, handler_name, None)
            if handler:
                handler(product, attrs)

        updated_fields: List[str] = []
        weight = attrs.get("weight")
        if weight is not None and str(weight).strip():
            try:
                weight_str = str(weight).strip().replace(",", ".")
                weight_val = float(weight_str)
                if weight_val >= 0 and (product.weight_value is None or float(product.weight_value) != weight_val):
                    product.weight_value = weight_val
                    product.weight_unit = getattr(product, "weight_unit", None) or "kg"
                    updated_fields.extend(["weight_value", "weight_unit"])
            except (ValueError, TypeError):
                pass

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

        # Разрешаем категорию и product_type до создания Product (единый маппинг)
        resolved_category = None
        resolved_product_type = None
        if product_data.category and isinstance(product_data.category, str) and not product_data.category.isdigit():
            resolved_category, resolved_product_type = resolve_category_and_product_type(product_data.category)

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
        if resolved_category is not None:
            defaults["category_id"] = resolved_category.pk
        if resolved_product_type is not None:
            defaults["product_type"] = resolved_product_type

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

        # Обновляем video_url если есть в метаданных (от парсеров) и у нас его нет
        if hasattr(product_data, 'metadata') and product_data.metadata:
            attributes = product_data.metadata.get('attributes', {})
            if attributes.get('video_url') and not product.video_url:
                product.video_url = attributes['video_url']
                product.save(update_fields=['video_url'])

        if not created:
            # Обновляем существующий товар
            old_price = product.price
            if not product.name and product_data.name:
                product.name = product_data.name
            if not product.description and product_data.description:
                product.description = product_data.description
            
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

        # Обрабатываем категорию: для существующего товара обновляем category и product_type из маппинга
        if product_data.category and not product.category:
            if isinstance(product_data.category, str) and not product_data.category.isdigit():
                category, product_type = resolve_category_and_product_type(product_data.category)
                if category is not None:
                    product.category = category
                    if product_type is not None and not product.product_type:
                        product.product_type = product_type
                    product.save()
            else:
                # Это ID категории
                category = Category.objects.filter(
                    external_id=product_data.category
                ).first()
                if category:
                    product.category = category
                    product.save()

        # Синхронизируем книжные поля ПОСЛЕ того, как product_type установлен сигналом
        if hasattr(product_data, "metadata") and product_data.metadata:
            self._sync_product_fields_from_metadata(product, product_data.metadata)

        # Обрабатываем бренд
        if product_data.brand and not product.brand:
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

        # Используем максимально специфичный объект (BookProduct и т.д.) для сохранения изображений
        target = product.domain_item
        if not hasattr(target, 'images'):
            target = product
        is_domain = target != product
        
        metadata = product.external_data if isinstance(product.external_data, dict) else {}
        attrs = metadata.get("attributes") if isinstance(metadata.get("attributes"), dict) else {}
        source = metadata.get("source") or attrs.get("source")
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
        
        # 1. Удаляем ВСЕ парсерные картинки (в которых есть /products/parsed/), чтобы при этом парсинге скачать и заново сохранить только свежие хэши от инстаграма.
        # Ручные загрузки (image_file и image_url без /products/parsed/) не трогаем!
        try:
            parser_images_query = Q(image_url__contains='/products/parsed/')
            
            if hasattr(target.images.model, 'video_url'):
                parser_images_query |= Q(video_url__contains='/products/parsed/')
                
            # Мы удаляем все парсерные картинки. Если они есть в новом списке - они добавятся заново ниже.
            # Если их нет в новом списке - они просто удалятся.
            # Это решает проблему дублирования и "бесконечного накопления" парсерных картинок.
            target.images.filter(parser_images_query).delete()
        except Exception as e:
            self.logger.warning(f"Error while cleaning up old parser images for {product.pk}: {e}")

        # 2. Битые ссылки проверяем только для ручных (не парсерных) изображений,
        # и только если их немного (не более 5), чтобы не тормозить парсинг.
        existing_images = list(target.images.all())
        broken_ids = []
        manual_images = [
            img for img in existing_images
            if not ('/products/parsed/' in (img.image_url or '') or '/products/parsed/' in (getattr(img, 'video_url', '') or ''))
        ]
        if manual_images and len(manual_images) <= 5:
            import httpx
            with httpx.Client(timeout=3, follow_redirects=True) as client:
                for img in manual_images:
                    url_to_check = img.video_url if hasattr(img, 'video_url') and img.video_url else img.image_url
                    if not url_to_check or not url_to_check.startswith('http'):
                        continue
                    try:
                        res = client.head(url_to_check)
                        if res.status_code >= 400:
                            self.logger.info(f"Найдена битая ссылка {url_to_check} у товара {product.name}, удаляем из базы.")
                            broken_ids.append(img.pk)
                    except Exception as e:
                        self.logger.warning(f"Ошибка проверки ссылки {url_to_check}: {e}")

        if broken_ids:
            target.images.filter(pk__in=broken_ids).delete()

        # Узнаем, установлено ли уже главное изображение вручную или с прошлого парсинга
        existing_any_main = target.images.filter(is_main=True).exists()
        has_manual_main = False
        if bool(getattr(product, 'main_image_file', None)):
            has_manual_main = True
        elif bool(getattr(product, 'main_image', None)):
            # Если это загруженная парсером картинка, мы не считаем её "ручной"
            if '/products/parsed/' not in product.main_image:
                has_manual_main = True
        
        # Добавляем новые изображения
        main_image_url = None
        for i, image_url in enumerate(image_urls):
            media_type = self._resolve_media_type(image_url)
            
            filter_query = Q(image_url=image_url)
            if hasattr(target.images.model, 'video_url'):
                filter_query |= Q(video_url=image_url)
                
            existing_item = target.images.filter(filter_query).first()
            
            desired_is_main = False
            if not existing_any_main and not has_manual_main:
                if preferred_main_video_url:
                    if media_type == "video" and image_url == preferred_main_video_url:
                        desired_is_main = True
                elif media_type == "image" and main_image_url is None:
                    desired_is_main = True
                    main_image_url = image_url
            
            if existing_item:
                updates: Dict[str, Any] = {}
                if hasattr(existing_item, 'video_url'):
                    if media_type == "video" and existing_item.video_url != image_url:
                        updates = {"video_url": image_url, "image_url": ""}
                    elif media_type == "image" and existing_item.image_url != image_url:
                        updates = {"image_url": image_url, "video_url": ""}
                else:
                    if media_type == "image" and existing_item.image_url != image_url:
                        updates = {"image_url": image_url}
                
                # Обновляем is_main только если мы решили его сделать главным, 
                # и он сейчас таковым не является
                if desired_is_main and not existing_item.is_main:
                    updates["is_main"] = desired_is_main
                
                if updates:
                    existing_item.__class__.objects.filter(pk=existing_item.pk).update(**updates)
                continue
            
            # Создаем новое изображение в правильной модели
            create_kwargs = {
                "image_url": image_url if media_type == "image" else "",
                "sort_order": target.images.count() + i,
                "is_main": desired_is_main
            }
            if hasattr(target.images.model, 'video_url'):
                create_kwargs["video_url"] = image_url if media_type == "video" else ""
            
            create_kwargs["product"] = target
            target.images.model.objects.create(**create_kwargs)
        
        # Обновляем главное медиа в самих объектах ТОЛЬКО если оно пустое
        if preferred_main_video_url:
            for obj in [product, target] if is_domain else [product]:
                update_fields = []
                if hasattr(obj, 'video_url') and not obj.video_url:
                    obj.video_url = preferred_main_video_url
                    update_fields.append("video_url")
                if update_fields:
                    obj.save(update_fields=update_fields)
            return

        if main_image_url and not existing_any_main and not has_manual_main:
            for obj in [product, target] if is_domain else [product]:
                if hasattr(obj, 'main_image'):
                    if not obj.main_image or '/products/parsed/' in obj.main_image:
                        obj.main_image = main_image_url
                        obj.save(update_fields=['main_image'])
    
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
