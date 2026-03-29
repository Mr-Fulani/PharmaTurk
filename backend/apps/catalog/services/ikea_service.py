import httpx
import time
import logging
from typing import Dict, List, Optional
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone

from apps.catalog.models import (
    FurnitureProduct,
    FurnitureVariant,
    FurnitureVariantImage,
    Brand,
    Category
)

logger = logging.getLogger(__name__)


class IkeaService:
    """Сервис для интеграции с IKEA Turkey через прямые API эндпоинты."""

    BASE_URL = "https://frontendapi.ikea.com.tr/api"
    HEADERS = {
        "x-channel": "WebSite",
        "x-version": "V2",
        "x-bone-language": "tr",
        "referer": "https://www.ikea.com.tr/",
        "origin": "https://www.ikea.com.tr",
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def __init__(self):
        self.brand = self._get_or_create_brand()
        self.default_category = Category.objects.filter(slug='furniture').first()
        self.client = httpx.Client(headers=self.HEADERS, timeout=10.0)

    def _get_or_create_brand(self) -> Brand:
        brand, created = Brand.objects.get_or_create(
            name="IKEA",
            defaults={
                "slug": "ikea",
                "description": "IKEA Products",
                "is_active": True,
                "primary_category_slug": "furniture",
                "category_slugs": ["furniture", "tableware"]
            }
        )
        return brand

    def fetch_item_details(self, item_code: str) -> Optional[Dict]:
        """Получает детальную информацию об одном товаре."""
        clean_code = str(item_code).replace(".", "").strip()
        url = f"{self.BASE_URL}/product/{clean_code}/detail?language=tr"
        try:
            response = self.client.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"IKEA API returned {response.status_code} for item {clean_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching IKEA item {clean_code}: {str(e)}")
            return None

    def fetch_items(self, item_codes: List[str]) -> List[Dict]:
        """Получает детали товаров по списку артикулов."""
        results = []
        for code in item_codes:
            data = self.fetch_item_details(code)
            if data:
                results.append(data)
            # Небольшая пауза, чтобы не заблокировали
            time.sleep(0.5)
        return results

    def search_items(self, query: str, category: str = None, limit: int = 24) -> List[Dict]:
        """Ищет товары по запросу или категории."""
        url = f"{self.BASE_URL}/search/products"
        params = {
            "storeCode": "331",
            "includeSuggestions": "true",
            "searchIn": "All",
            "language": "tr",
            "size": limit
        }
        if query:
            params["keyword"] = query
        if category:
            params["Category"] = category
            
        try:
            response = self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return data.get("products", [])
            else:
                logger.warning(f"IKEA Search returned {response.status_code} for q='{query}', cat='{category}'")
                return []
        except Exception as e:
            logger.error(f"Error searching IKEA for q='{query}', cat='{category}': {str(e)}")
            return []

    def get_category_products(self, category_slug: str, limit: int = 24) -> List[Dict]:
        """Получает товары конкретной категории по её слагу."""
        # Исследование показало, что API IKEA ожидает весьма специфическую нормализацию:
        # Например, для URL https://www.ikea.com.tr/kategori/acik-kitapliklar
        # API ожидает Category=açik-kitapliklar (с турецкой ç, но ОБЫЧНОЙ i вместо ı)
        
        # Попробуем сначала оригинальный слаг
        products = self.search_items(query=None, category=category_slug, limit=limit)
        
        # Если пусто, пробуем "гибридную" нормализацию (ç -> c, но i остается i)
        if not products:
            # Заменяем только c на ç и s на ş, g на ğ (наиболее частые случаи в навигации ИКЕА)
            hybrid_slug = category_slug.replace("acik", "açik").replace("kitapliklar", "kitapliklar")
            # На самом деле, просто попробуем наиболее вероятные замены для IKEA TR
            if hybrid_slug != category_slug:
                products = self.search_items(query=None, category=hybrid_slug, limit=limit)
        
        # Если все еще пусто, пробуем еще варианты (добавление параметров, которые видел subagent)
        if not products:
            url = f"{self.BASE_URL}/search/products"
            params = {
                "language": "tr",
                "Category": category_slug.replace("acik", "açik"), # Самый частый случай
                "IncludeFilters": "true",
                "StoreCode": "331",
                "sortby": "None",
                "size": limit,
                "SearchFrom": "Category",
                "IncludeColorVariants": "true"
            }
            try:
                response = self.client.get(url, params=params)
                if response.status_code == 200:
                    products = response.json().get("products", [])
            except Exception as e:
                logger.error(f"Error in fallback category search: {e}")
                
        return products

    def _normalize_item_data(self, item: Dict) -> Dict:
        """Нормализует данные из IKEA TR API в формат проекта."""
        # sprCode — это артикул (напр. 80275887)
        item_no = item.get("sprCode") or str(item.get("id", ""))
        name = item.get("title") or ""
        sub_title = item.get("subTitle") or ""
        
        # Собираем богатое описание
        detail = item.get('detail', '')
        long_benefits = item.get('longBenefits', '')
        material_detail = item.get('materialDetail', '')
        good_to_know = item.get('goodToKnowDetail', '')
        
        # Объединяем все части описания
        desc_parts = []
        if sub_title:
             desc_parts.append(f"<h3>{sub_title}</h3>")
        if detail:
             desc_parts.append(detail)
        if long_benefits:
             desc_parts.append(f"<div>{long_benefits}</div>")
        if material_detail:
             desc_parts.append(f"<h4>Материалы и компоненты:</h4>{material_detail}")
        if good_to_know:
             desc_parts.append(f"<h4>Полезно знать:</h4>{good_to_know}")
             
        desc = "".join(desc_parts)
        
        # Категория
        category_name = "Мебель"
        cat_data = item.get("category")
        if isinstance(cat_data, dict):
            category_name = cat_data.get("name", category_name)
        
        # Цена (в разных форматах API)
        price = 0
        price_data = item.get("price")
        if isinstance(price_data, dict):
             # В детальной карточке
             price = price_data.get("sellPrice") or price_data.get("total") or price_data.get("price") or 0
        elif isinstance(price_data, (int, float, str)):
             # В поиске или если цена пришла числом/строкой
             try:
                 price_str = str(price_data).replace(".", "").replace(",", ".")
                 price = float(price_str)
             except:
                 price = 0
        
        # Если в price пусто, попробуем formattedPrice (иногда там "3.999")
        if not price and item.get("formattedPrice"):
             try:
                 price_str = item["formattedPrice"].replace(".", "").replace(",", ".")
                 price = float(price_str)
             except:
                 pass
                 
        if not price and item.get("sellPrice"):
             price = float(item["sellPrice"])

        # Изображения
        images = []
        raw_images = item.get("images", [])
        if isinstance(raw_images, list):
            for img in raw_images:
                # 1. Приоритет zoomableImage (обычно 2000x2000)
                img_url = img.get("zoomableImage") or img.get("image") or img.get("url") or img.get("imageUrl")
                if img_url:
                    # Улучшаем качество до 2000_2000 если это IKEA CDN и еще не заменено
                    if "500_500" in img_url:
                        img_url = img_url.replace("500_500", "2000_2000")
                    if img_url not in images:
                        images.append(img_url)
                    continue
                
                # 2. Если есть только код (code)
                img_code = img.get("code", "")
                if img_code:
                    if not img_code.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        img_code = f"{img_code}.jpg"
                    img_url = f"https://cdn.ikea.com.tr/urunler/2000_2000/{img_code}"
                    if img_url not in images:
                        images.append(img_url)
        
        # Резервные поля
        for field in ["mainImageUrl", "imageUrl", "productImage", "mobileImage", "zoomableImage"]:
             val = item.get(field)
             if val and isinstance(val, str) and val not in images:
                 images.append(val)

        # Варианты / характеристики
        color = ""
        variant_info = item.get("variantInfo", [])
        if variant_info and isinstance(variant_info, list):
            # Ищем цвет
            for v in variant_info:
                if "renk" in v.get("name", "").lower() or "color" in v.get("name", "").lower():
                    color = v.get("value", "")
                    break

        dimensions = item.get("dimensionsDetail", "") or item.get("dimensions", "")
        material = item.get("materialDetail", "") or item.get("material", "")
        
        # Видео
        video_url = ""
        video_data = item.get("video")
        if isinstance(video_data, dict):
            video_url = video_data.get("url") or video_data.get("videoUrl") or ""
        elif isinstance(video_data, str):
            video_url = video_data
            
        stock = item.get("stockCount", 0) or item.get("stock", 0)
        
        # Тип мебели из функции
        furniture_type = ""
        func_data = item.get("function")
        if isinstance(func_data, dict):
            furniture_type = func_data.get("name", "")

        logger.info(f"Normalized IKEA item {item_no}: Name={name}, Price={price}, DescLen={len(desc)}, Images={len(images)}")
        
        return {
            "item_no": str(item_no),
            "name": name,
            "description": desc,
            "price": price,
            "currency": "TRY",
            "images": images,
            "color": color,
            "dimensions": dimensions,
            "material": material,
            "video_url": video_url,
            "stock": stock,
            "furniture_type": furniture_type,
            "category_name": category_name,
            "raw_item": item,
            "url": f"https://www.ikea.com.tr/urun/{item_no}"
        }

    def _sync_gallery(self, product: FurnitureProduct, images: List[str]):
        """Синхронизирует галерею изображений товара."""
        if not images:
            return
            
        from apps.catalog.models import FurnitureProductImage
        
        # Для простоты: удаляем старые и создаем новые (или ищем по URL)
        # В реальном проекте лучше не удалять, а сравнивать.
        
        existing_images = list(product.images.all())
        existing_filenames = []
        for img in existing_images:
            if img.image_url:
                # Берем имя файла из URL (последняя часть после /)
                fname = img.image_url.split('/')[-1].split('?')[0]
                existing_filenames.append(fname)

        for idx, img_url in enumerate(images):
            # Извлекаем имя файла из входящего URL (например, PE928093.jpg)
            incoming_fname = img_url.split('/')[-1].split('?')[0]
            
            if incoming_fname not in existing_filenames:
                FurnitureProductImage.objects.create(
                    product=product,
                    image_url=img_url,
                    sort_order=idx
                )
                
        # Обновляем основное изображение, если его нет
        if not product.main_image and images:
            product.main_image = images[0]
            product.save(update_fields=["main_image"])

    def upsert_furniture_product(self, item_data: Dict) -> Optional[FurnitureProduct]:
        """Создает или обновляет товар в БД."""
        if not item_data:
            return None
            
        # Нормализуем если это сырой ответ
        if "raw_item" not in item_data:
            normalized = self._normalize_item_data(item_data)
        else:
            normalized = item_data
            
        item_no = normalized.get("item_no")
        if not item_no:
            return None
            
        name = normalized.get("name", f"IKEA {item_no}")
        slug_base = f"ikea-{slugify(name)[:100]}-{item_no}"
        
        price = normalized.get("price", 0)
        currency = normalized.get("currency", "TRY")
        
        # 1. FurnitureProduct
        product, created = FurnitureProduct.objects.get_or_create(
            external_id=item_no,
            defaults={
                "name": name,
                "slug": slug_base,
                "description": normalized.get("description", ""),
                "price": price,
                "currency": currency,
                "brand": self.brand,
                "category": self.default_category,
                "dimensions": normalized.get("dimensions", "")[:500],
                "material": normalized.get("material", "")[:500],
                "furniture_type": normalized.get("furniture_type", "")[:100],
                "main_image": normalized["images"][0] if normalized.get("images") else "",
                "video_url": normalized.get("video_url", ""),
                "external_url": normalized.get("url", ""),
                "external_data": {"source": "ikea_tr_direct", "raw": normalized.get("raw_item", {})},
                "stock_quantity": normalized.get("stock", 0),
                "is_available": normalized.get("stock", 0) > 0,
                "is_active": True
            }
        )
        
        # Сохраняем видео, если оно есть (даже для существующего товара)
        if normalized.get("video_url") and product.video_url != normalized["video_url"]:
             product.video_url = normalized["video_url"]
             product.save(update_fields=["video_url"])
             
        # Сохраняем галерею
        self._sync_gallery(product, normalized.get("images", []))
        
        if not created:
            updated = False
            # Обновляем поля, если они изменились или были пусты
            if product.price != price:
                product.old_price = product.price
                product.price = price
                updated = True
                
            if not product.description or (normalized.get("description") and len(normalized["description"]) > len(product.description)):
                product.description = normalized["description"]
                updated = True
                
            # Обновляем характеристики
            for attr in ["dimensions", "material", "furniture_type", "color", "main_image", "video_url"]:
                new_val = normalized.get(attr, "")
                if new_val and getattr(product, attr, "") != new_val:
                    setattr(product, attr, new_val)
                    updated = True
            
            if updated:
                product.save()
            
            # Обновляем внешние данные
            product.external_data = {
                "source": "ikea_tr_direct",
                "raw": normalized.get("raw_item", {}),
                "attributes": {
                    "color": normalized.get("color", ""),
                    "material": normalized.get("material", ""),
                    "video_url": normalized.get("video_url", ""),
                    "dimensions": normalized.get("dimensions", ""),
                    "furniture_type": normalized.get("furniture_type", ""),
                },
                "scraped_at": timezone.now().isoformat()
            }
            
            if updated or True: # Всегда сохраняем внешние данные
                product.save()

            if result_url := normalized.get("url"):
                if product.external_url != result_url:
                    product.external_url = result_url
                    updated = True
            
            if updated:
                 product.save(update_fields=["price", "old_price", "external_url", "stock_quantity", "is_available", "updated_at"])

        # 2. FurnitureVariant
        variant_name = f"{name} ({normalized.get('color', 'Standard')})"
        variant_slug = f"v-{slug_base}"
        
        variant, v_created = FurnitureVariant.objects.get_or_create(
            product=product,
            external_id=item_no,
            defaults={
                "name": variant_name,
                "slug": variant_slug,
                "color": normalized.get("color", "")[:50],
                "sku": item_no,
                "price": price,
                "currency": currency,
                "main_image": normalized["images"][0] if normalized.get("images") else "",
                "external_url": normalized.get("url", ""),
                "is_available": True,
                "is_active": True
            }
        )
        
        if not v_created and variant.price != price:
            variant.old_price = variant.price
            variant.price = price
            variant.save(update_fields=["price", "old_price", "updated_at"])

        # 3. FurnitureVariantImage
        if normalized.get("images"):
            variant.images.all().delete()
            image_objs = []
            for i, img_url in enumerate(normalized["images"]):
                image_objs.append(
                    FurnitureVariantImage(
                        variant=variant,
                        image_url=img_url,
                        sort_order=i,
                        is_main=(i == 0)
                    )
                )
            if image_objs:
                FurnitureVariantImage.objects.bulk_create(image_objs)

        return product
