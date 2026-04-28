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


def _json_safe_for_external_data(value: Any) -> Any:
    """Рекурсивно приводит значения к типам, допустимым для JSONField (в т.ч. без Decimal)."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe_for_external_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_for_external_data(v) for v in value]
    return value


# Реестр: product_type → имя метода CatalogNormalizer для синхронизации атрибутов в доменную модель
SYNC_METADATA_HANDLER_NAMES = {
    "books": "_sync_books_metadata",
    "jewelry": "_sync_jewelry_metadata",
    "medicines": "_sync_medicines_metadata",
    "furniture": "_sync_furniture_metadata",
}


def _payload_variant_galleries_present(attrs: Optional[Dict[str, Any]]) -> bool:
    """Проверяет, есть ли в сыром payload варианты с собственными изображениями."""
    if not isinstance(attrs, dict):
        return False
    for key in ("furniture_variants", "fashion_variants", "variants"):
        rows = attrs.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        for spec in rows:
            if not isinstance(spec, dict):
                continue
            raw = spec.get("images") or []
            if any(isinstance(u, str) and u.strip() for u in raw):
                return True
    return False


def _domain_variants_have_gallery(product: Product) -> bool:
    """Есть ли у доменной модели активные варианты с собственной галереей."""
    domain_item = getattr(product, "domain_item", None)
    if not domain_item:
        return False
    variants_manager = getattr(domain_item, "variants", None)
    if variants_manager is None:
        return False
    try:
        active = list(variants_manager.filter(is_active=True))
    except Exception:
        try:
            active = list(variants_manager.all())
        except Exception:
            return False
    if len(active) > 1:
        return True
    for variant in active:
        images_manager = getattr(variant, "images", None)
        if images_manager is not None and images_manager.exists():
            return True
    return False


def _skip_shared_product_gallery(product: Product, attrs: Optional[Dict[str, Any]]) -> bool:
    """
    Не мержить корневой список изображений в parent/domain gallery: галерея только у вариантов.

    Учитывает как сырой payload вариаций, так и уже сохранённые варианты в БД.
    """
    ad = attrs if isinstance(attrs, dict) else {}
    if _payload_variant_galleries_present(ad):
        return True
    if _domain_variants_have_gallery(product):
        return True
    return False


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

    def _first_video_url_from_images(self, images: List[str]) -> Optional[str]:
        """Первый URL видео из списка медиа (после скрапера — обычно уже R2), приоритетнее сырого attributes."""
        for u in images or []:
            if isinstance(u, str) and self._resolve_media_type(u) == "video":
                return u
        return None

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
            if v and not book_product.publisher:
                book_product.publisher = v
                book_updated = True
        cover_type = attrs.get("cover_type")
        if cover_type:
            v = str(cover_type).strip()
            if v and not book_product.cover_type:
                book_product.cover_type = v
                book_updated = True
        language = attrs.get("language")
        if language:
            v = str(language).strip()
            if v and not book_product.language:
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
            if v in valid_jewelry_types and not jewelry_product.jewelry_type:
                jewelry_product.jewelry_type = v
                jewelry_updated = True
        if "material" in attrs and attrs["material"]:
            v = str(attrs["material"]).strip()[:100]
            if v and not jewelry_product.material:
                jewelry_product.material = v
                jewelry_updated = True
        if "metal_purity" in attrs and attrs["metal_purity"]:
            v = str(attrs["metal_purity"]).strip()[:50]
            if v and not jewelry_product.metal_purity:
                jewelry_product.metal_purity = v
                jewelry_updated = True
        if "stone_type" in attrs and attrs["stone_type"]:
            v = str(attrs["stone_type"]).strip()[:100]
            if v and not jewelry_product.stone_type:
                jewelry_product.stone_type = v
                jewelry_updated = True
        if "carat_weight" in attrs and attrs["carat_weight"] is not None:
            try:
                v = Decimal(str(attrs["carat_weight"]).strip().replace(",", "."))
                if v >= 0 and jewelry_product.carat_weight is None:
                    jewelry_product.carat_weight = v
                    jewelry_updated = True
            except (ValueError, TypeError):
                pass
        if "gender" in attrs and attrs["gender"]:
            v = str(attrs["gender"]).strip()[:10]
            if v and not jewelry_product.gender:
                jewelry_product.gender = v
                jewelry_updated = True
        if jewelry_updated:
            jewelry_product.save()

    def _sync_medicines_metadata(self, product: Product, attrs: Dict[str, Any]) -> None:
        """Синхронизирует атрибуты медикаментов в MedicineProduct."""
        medicine_keys = (
            "dosage_form", "active_ingredient", "prescription_required", "prescription_type", "volume", 
            "origin_country", "sgk_status", "administration_route", "barcode", "atc_code",
            "nfc_code", "sgk_equivalent_code", "sgk_active_ingredient_code", "sgk_public_no",
            "shelf_life", "storage_conditions"
        )
        if not any(k in attrs for k in medicine_keys):
            return
            
        medicine_product = getattr(product, "medicine_item", None)
        if not medicine_product:
            return  # домен создаётся сигналом ensure_domain_product_for_base при save Product
            
        medicine_updated = False
        
        # Маппинг ключей из attrs в поля модели и их лимиты (чтобы не было DataError)
        # (attr_key, model_field, max_len)
        field_mapping = [
            ("dosage_form", "dosage_form", 100),
            ("active_ingredient", "active_ingredient", 300),
            ("prescription_type", "prescription_type", 500),
            ("volume", "volume", 100),
            ("origin_country", "origin_country", 500),
            ("sgk_status", "sgk_status", 500),
            ("administration_route", "administration_route", 500),
            ("barcode", "barcode", 100),
            ("atc_code", "atc_code", 100),
            ("nfc_code", "nfc_code", 100),
            ("sgk_equivalent_code", "sgk_equivalent_code", 100),
            ("sgk_active_ingredient_code", "sgk_active_ingredient_code", 100),
            ("sgk_public_no", "sgk_public_no", 100),
            ("shelf_life", "shelf_life", 200),
            ("storage_conditions", "storage_conditions", 500),
        ]

        for attr_key, model_field, max_len in field_mapping:
            if attr_key in attrs and attrs[attr_key]:
                v = str(attrs[attr_key]).strip()[:max_len]
                current_val = getattr(medicine_product, model_field)
                # Обновляем только если поле сейчас пустое (защищаем данные ИИ-агента)
                if not current_val:
                    setattr(medicine_product, model_field, v)
                    medicine_updated = True
                
        if "prescription_required" in attrs:
            val = bool(attrs["prescription_required"])
            if val != medicine_product.prescription_required:
                medicine_product.prescription_required = val
                medicine_updated = True
                
        if medicine_updated:
            medicine_product.save()
            
    def _sync_furniture_metadata(self, product: Product, attrs: Dict[str, Any]) -> None:
        """Синхронизирует атрибуты мебели в FurnitureProduct."""
        furniture_product = getattr(product, "furniture_item", None)
        if not furniture_product:
            return
            
        updated = False

        # Только поля, реально существующие на FurnitureProduct / AbstractDomainProduct.
        # Цвет хранится на FurnitureVariant; item_no/designer в модели мебели отсутствуют.
        fields_map = {
            "material": ("material", 1000),
            "dimensions": ("dimensions", 500),
            "furniture_type": ("furniture_type", 255),
            "video_url": ("video_url", 2000),
        }

        for attr_key, (model_field, max_len) in fields_map.items():
            if attr_key in attrs and attrs[attr_key]:
                val = str(attrs[attr_key]).strip()[:max_len]
                current_val = getattr(furniture_product, model_field)
                if not current_val:
                    setattr(furniture_product, model_field, val)
                    updated = True

        if "item_no" in attrs and attrs["item_no"]:
            val = str(attrs["item_no"]).strip()[:500]
            if val != (furniture_product.external_id or ""):
                furniture_product.external_id = val
                updated = True

        ed_patch: Dict[str, Any] = {}
        if "designer" in attrs and attrs["designer"]:
            ed_patch["designer"] = str(attrs["designer"]).strip()
        if "color" in attrs and attrs["color"]:
            ed_patch["primary_color"] = str(attrs["color"]).strip()[:200]
        if ed_patch:
            ed = (
                furniture_product.external_data
                if isinstance(furniture_product.external_data, dict)
                else {}
            )
            need = any(ed.get(k) != v for k, v in ed_patch.items())
            if need:
                furniture_product.external_data = {**ed, **ed_patch}
                updated = True
        
        # Габариты (ширина, высота, глубина)
        for dim in ["width", "height", "depth"]:
            if dim in attrs and attrs[dim] is not None:
                try:
                    val = Decimal(str(attrs[dim]).replace(",", "."))
                    if val != getattr(furniture_product, dim):
                        setattr(furniture_product, dim, val)
                        updated = True
                except:
                    pass
        
        if updated:
            furniture_product.save()
            
        # Галерея изображений (FurnitureProductImage) — не заполняем из корня, если галереи на вариантах
        images = attrs.get("images")
        if isinstance(images, list) and images and not _skip_shared_product_gallery(product, attrs):
            from apps.catalog.models import FurnitureProductImage

            existing_urls = set(furniture_product.images.values_list("image_url", flat=True))
            for idx, url in enumerate(images):
                if url and url not in existing_urls:
                    FurnitureProductImage.objects.create(
                        product=furniture_product,
                        image_url=url,
                        sort_order=idx,
                    )

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
        base_slug = trans_slugify(name, language_code='ru') or slugify(name, allow_unicode=False)
        if not base_slug:
            # Если латиница/кириллица не сработали, пробуем unicode-slugify
            base_slug = slugify(name, allow_unicode=True)
            
        if not base_slug or len(base_slug) < 2:
            base_slug = "brand"
            
        slug = f"{base_slug}-{external_id}" if external_id else base_slug
        
        # Ищем существующий бренд
        if external_id:
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
        else:
            # Если нет внешнего ID, ищем по имени
            brand, created = Brand.objects.get_or_create(
                name=name,
                defaults={
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
        raw_meta: Dict[str, Any] = (
            product_data.metadata if isinstance(product_data.metadata, dict) else {}
        )
        safe_external_meta = _json_safe_for_external_data(raw_meta)

        # Разрешаем категорию и product_type до создания Product (единый маппинг)
        resolved_category = None
        resolved_product_type = None
        if product_data.category and isinstance(product_data.category, str) and not product_data.category.isdigit():
            resolved_category, resolved_product_type = resolve_category_and_product_type(product_data.category)

        # Разрешаем бренд до создания (чтобы pre_save сигнал не подставил "Другое" если бренд известен)
        resolved_brand = None
        if product_data.brand:
            raw_brand = str(product_data.brand).strip()
            if raw_brand:
                resolved_brand = Brand.objects.filter(external_id=raw_brand).first()
                if not resolved_brand:
                    resolved_brand = Brand.objects.filter(name__iexact=raw_brand).first()

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
            "external_data": safe_external_meta,
        }
        if resolved_category is not None:
            defaults["category_id"] = resolved_category.pk
        if resolved_product_type is not None:
            defaults["product_type"] = resolved_product_type
        if resolved_brand is not None:
            defaults["brand_id"] = resolved_brand.pk

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

        # Видео: сначала URL из списка images (R2 после парсера), иначе attributes — чтобы не скачивать дубликат в main/.
        if hasattr(product_data, "metadata") and product_data.metadata:
            attributes = product_data.metadata.get("attributes", {}) or {}
            if not product.video_url:
                from_images = self._first_video_url_from_images(
                    getattr(product_data, "images", None) or []
                )
                if from_images:
                    product.video_url = from_images
                    product.save()
                elif attributes.get("video_url"):
                    product.video_url = attributes["video_url"]
                    # Нельзя save(update_fields=['video_url']): pre_save скачивает видео в main_video_file,
                    # а при ограниченном update_fields Django не пишет FileField — файл не попадает в R2/БД
                    # (для только что созданного товара полного save() ниже по коду нет).
                    product.save()

        if not created:
            # Обновляем существующий товар
            old_price = product.price
            if not product.name and product_data.name:
                product.name = product_data.name
            if not product.description and product_data.description:
                product.description = product_data.description
            
            product.is_available = product_data.availability
            
            # Мержим external_data вместо полной перезаписи, чтобы сохранить данные ИИ-агента
            if isinstance(product.external_data, dict):
                product.external_data.update(safe_external_meta)
            else:
                product.external_data = safe_external_meta
                
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
        if _skip_shared_product_gallery(product, attrs):
            # Не дублируем корневую галерею на parent/domain-товаре — картинки только у вариантов.
            return

        # Используем максимально специфичный объект (BookProduct и т.д.) для сохранения изображений
        target = product.domain_item
        image_manager_name = "images"
        if not hasattr(target, 'images'):
            if hasattr(target, 'gallery_images'):
                image_manager_name = "gallery_images"
            else:
                target = product
                image_manager_name = "images"
                
        is_domain = target != product
        image_manager = getattr(target, image_manager_name)

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
            exclude_query = Q(image_url__in=image_urls)
            
            if hasattr(image_manager.model, 'video_url'):
                parser_images_query |= Q(video_url__contains='/products/parsed/')
                exclude_query |= Q(video_url__in=image_urls)
                
            # Мы удаляем все парсерные картинки, КРОМЕ тех, что есть в новом списке image_urls.
            # Иначе `post_delete` сигнал удалит физический файл из R2.
            image_manager.filter(parser_images_query).exclude(exclude_query).delete()
        except Exception as e:
            self.logger.warning(f"Error while cleaning up old parser images for {product.pk}: {e}")


        # 2. Битые ссылки проверяем только для ручных (не парсерных) изображений,
        # и только если их немного (не более 5), чтобы не тормозить парсинг.
        existing_images = list(image_manager.all())
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
            image_manager.filter(pk__in=broken_ids).delete()

        # Узнаем, установлено ли уже главное изображение вручную или с прошлого парсинга
        existing_any_main = image_manager.filter(is_main=True).exists()
        has_manual_main = False
        if bool(getattr(product, 'main_image_file', None)):
            has_manual_main = True
        elif bool(getattr(product, 'main_image', None)):
            # Если это загруженная парсером картинка, мы не считаем её "ручной"
            if '/products/parsed/' not in product.main_image:
                has_manual_main = True
                
        has_video = bool(getattr(product, 'video_url', None) or getattr(product, 'main_video_file', None))
        
        # Добавляем новые изображения
        main_image_url = None
        for i, image_url in enumerate(image_urls):
            media_type = self._resolve_media_type(image_url)
            
            filter_query = Q(image_url=image_url)
            if hasattr(image_manager.model, 'video_url'):
                filter_query |= Q(video_url=image_url)
                
            existing_item = image_manager.filter(filter_query).first()
            
            desired_is_main = False
            if not existing_any_main and not has_manual_main:
                if preferred_main_video_url:
                    if media_type == "video" and image_url == preferred_main_video_url:
                        desired_is_main = True
                elif media_type == "image" and main_image_url is None:
                    main_image_url = image_url
                    # По просьбе пользователя: при парсинге никогда не отмечаем картинку
                    # чекбоксом "Главное изображение" (is_main=True).
                    # Приоритеты выстроены на фронтенде: видео > гифки > картинки,
                    # а чекбокс (если проставлен вручную в админке) имеет наивысший приоритет.
            
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
                "sort_order": image_manager.count() + i,
                "is_main": desired_is_main
            }
            if hasattr(image_manager.model, 'video_url'):
                create_kwargs["video_url"] = image_url if media_type == "video" else ""
            elif media_type == "video":
                # Модели галереи без video_url: пропускаем, иначе получится пустая «картинка».
                continue
            
            create_kwargs["product"] = target
            image_manager.model.objects.create(**create_kwargs)
        
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
