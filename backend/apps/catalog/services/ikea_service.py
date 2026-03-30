import httpx
import re
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
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


def extract_ikea_color_from_variant_info(variant_info: Any) -> str:
    """
    Значение цвета из variantInfo ответа IKEA TR.
    Часто приходит как dict: {"color": {"name": "Renk", "value": "bej-beyaz"}, ...},
    реже как список словарей {name, value}.
    """
    if not variant_info:
        return ""
    if isinstance(variant_info, dict):
        c = variant_info.get("color")
        if isinstance(c, dict):
            val = (c.get("value") or "").strip()
            return val[:50] if val else ""
        if isinstance(c, str) and c.strip():
            return c.strip()[:50]
        return ""
    if isinstance(variant_info, list):
        for v in variant_info:
            if not isinstance(v, dict):
                continue
            name = (v.get("name") or "").lower()
            if "renk" in name or "color" in name:
                val = (v.get("value") or "").strip()
                if val:
                    return val[:50]
    return ""


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

    @staticmethod
    def _extract_item_code(url: str) -> Optional[str]:
        """
        Артикул из URL карточки товара ikea.com.tr.

        Поддержка:
        - /urun/slug-80275887 (турецкая витрина)
        - /en/product/slug-39440475, /tr/product/... (англ./локаль перед product)
        """
        if not url or not isinstance(url, str):
            return None
        path = urlparse(url.strip()).path.strip("/")
        if not path:
            return None
        segments = [s for s in path.split("/") if s]
        if not segments:
            return None

        last: Optional[str] = None
        # /urun/slug — не путать с /urun-gruplari/
        if segments[0] == "urun" and len(segments) >= 2:
            last = segments[-1].split("?")[0]
        # /en/product/slug или /tr/product/slug
        elif "product" in segments:
            idx = segments.index("product")
            if idx + 1 < len(segments):
                last = segments[idx + 1].split("?")[0]
        if not last:
            return None

        m = re.search(r"(\d{8})$", last)
        if m:
            return m.group(1)
        digits_only = re.sub(r"\D", "", last)
        if len(digits_only) >= 8:
            return digits_only[-8:]
        found = re.findall(r"\d{8}", path.replace(".", ""))
        return found[-1] if found else None

    @staticmethod
    def parse_category_list_url(category_url: str) -> Tuple[str, str]:
        """
        Слаг категории и язык для API поиска.

        Примеры:
        - https://www.ikea.com.tr/en/category/four-seats → (four-seats, en)
        - https://www.ikea.com.tr/kategori/acik-kitapliklar → (acik-kitapliklar, tr)
        """
        if not category_url or not isinstance(category_url, str):
            return "", "tr"
        path = urlparse(category_url.strip()).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if not parts:
            return "", "tr"
        # /en/category/foo или /tr/category/foo
        if len(parts) >= 3 and parts[1] == "category" and parts[0] in ("en", "tr"):
            return parts[2], parts[0]
        # /kategori/foo-bar
        if parts[0] == "kategori" and len(parts) >= 2:
            return parts[1], "tr"
        return parts[-1], "tr"

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

    @staticmethod
    def _clean_spr_code(code: Optional[str]) -> str:
        return str(code or "").replace(".", "").strip()

    def collect_color_variant_details(self, main_detail: Dict) -> List[Dict]:
        """Полные деталки по каждому цветовому варианту (options.colorOptions)."""
        if not main_detail:
            return []
        opts = main_detail.get("options") or {}
        color_opts = opts.get("colorOptions") or []
        if not color_opts or not isinstance(color_opts, list):
            return [main_detail]

        codes_ordered: List[str] = []
        seen: set[str] = set()
        for entry in color_opts:
            if not isinstance(entry, dict):
                continue
            clean = self._clean_spr_code(entry.get("sprCode"))
            if not clean or clean in seen:
                continue
            seen.add(clean)
            codes_ordered.append(clean)

        if len(codes_ordered) <= 1:
            return [main_detail]

        main_code = self._clean_spr_code(main_detail.get("sprCode") or main_detail.get("id"))
        out: List[Dict] = []
        for clean in codes_ordered:
            if clean == main_code:
                out.append(main_detail)
                continue
            time.sleep(0.45)
            other = self.fetch_item_details(clean)
            if other:
                out.append(other)
        return out if out else [main_detail]

    @staticmethod
    def _resolve_public_url(item: Dict, item_no: str) -> str:
        """Канонический URL карточки (slug), если есть в options."""
        plain = str(item_no).replace(".", "").strip()
        opts = item.get("options") or {}
        for key in ("colorOptions", "functionOptions", "variant1Options"):
            for o in opts.get(key) or []:
                if not isinstance(o, dict):
                    continue
                if IkeaService._clean_spr_code(o.get("sprCode")) != plain:
                    continue
                full = o.get("fullUrl")
                if full and isinstance(full, str) and full.startswith("http"):
                    return full
                path = o.get("urlPath")
                if path and isinstance(path, str):
                    return f"https://www.ikea.com.tr/{path.lstrip('/')}"
                break
        return f"https://www.ikea.com.tr/urun/{plain}"

    @staticmethod
    def _resolve_stock_and_availability(item: Dict) -> Tuple[Optional[int], bool]:
        """Остаток с сайта (>0) или None под дефолт парсера (3 шт); доступность для витрины."""
        raw = item.get("stockCount")
        if raw is None:
            raw = item.get("stock")
        try:
            stock_int = int(raw) if raw is not None and raw != "" else 0
        except (TypeError, ValueError):
            stock_int = 0

        is_sellable = bool(item.get("isSellable", True))
        is_active = bool(item.get("isActive", True))
        # Нет в продаже / выведен
        if not is_sellable or not is_active:
            return 0, False
        # Явный положительный остаток
        if stock_int > 0:
            return stock_int, True
        # IKEA часто отдаёт stockCount=0 и onlineStockStatus=NoStock при онлайн-заказе;
        # количество тогда задаётся в scrapers (дефолт 3 шт).
        return None, True

    def search_items(
        self,
        query: str,
        category: str = None,
        limit: int = 24,
        *,
        language: str = "tr",
    ) -> List[Dict]:
        """Ищет товары по запросу или категории."""
        url = f"{self.BASE_URL}/search/products"
        params = {
            "storeCode": "331",
            "includeSuggestions": "true",
            "searchIn": "All",
            "language": language,
            "size": limit,
        }
        if query:
            params["keyword"] = query
        if category:
            params["Category"] = category

        headers = {**self.HEADERS, "x-bone-language": language}

        try:
            response = self.client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("products", [])
            else:
                logger.warning(
                    f"IKEA Search returned {response.status_code} for q='{query}', "
                    f"cat='{category}', lang='{language}'"
                )
                return []
        except Exception as e:
            logger.error(
                f"Error searching IKEA for q='{query}', cat='{category}', lang='{language}': {str(e)}"
            )
            return []

    def get_category_products(
        self,
        category_slug: str,
        limit: int = 24,
        *,
        language: str = "tr",
    ) -> List[Dict]:
        """Получает товары конкретной категории по её слагу."""
        # Исследование показало, что API IKEA ожидает весьма специфическую нормализацию:
        # Например, для URL https://www.ikea.com.tr/kategori/acik-kitapliklar
        # API ожидает Category=açik-kitapliklar (с турецкой ç, но ОБЫЧНОЙ i вместо ı)
        #
        # Английские URL (/en/category/four-seats) с language=tr часто дают 404 — пробуем en + tr.

        def try_langs(slug: str) -> List[Dict]:
            order: List[str] = []
            for lang in (language, "tr", "en"):
                if lang not in order:
                    order.append(lang)
            for lang in order:
                found = self.search_items(query=None, category=slug, limit=limit, language=lang)
                if found:
                    return found
            return []

        products = try_langs(category_slug)

        # Если пусто, пробуем «гибридную» нормализацию турецких слагов в URL
        if not products:
            hybrid_slug = category_slug.replace("acik", "açik").replace("kitapliklar", "kitapliklar")
            if hybrid_slug != category_slug:
                products = try_langs(hybrid_slug)

        # Расширенный запрос (как на витрине категории)
        if not products:
            url = f"{self.BASE_URL}/search/products"
            for lang in (language, "tr", "en"):
                if lang not in ("tr", "en"):
                    continue
                params = {
                    "language": lang,
                    "Category": category_slug.replace("acik", "açik"),
                    "IncludeFilters": "true",
                    "StoreCode": "331",
                    "sortby": "None",
                    "size": limit,
                    "SearchFrom": "Category",
                    "IncludeColorVariants": "true",
                }
                headers = {**self.HEADERS, "x-bone-language": lang}
                try:
                    response = self.client.get(url, params=params, headers=headers)
                    if response.status_code == 200:
                        products = response.json().get("products", [])
                        if products:
                            break
                except Exception as e:
                    logger.error(f"Error in fallback category search (lang={lang}): {e}")

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

        # Варианты / характеристики (цвет из variantInfo — list или nested dict)
        color = extract_ikea_color_from_variant_info(item.get("variantInfo"))

        dimensions = item.get("dimensionsDetail", "") or item.get("dimensions", "")
        material = item.get("materialDetail", "") or item.get("material", "")
        
        # Видео
        video_url = ""
        video_data = item.get("video")
        if isinstance(video_data, dict):
            video_url = video_data.get("url") or video_data.get("videoUrl") or ""
        elif isinstance(video_data, str):
            video_url = video_data

        stock, listing_available = self._resolve_stock_and_availability(item)

        # Тип мебели из функции
        furniture_type = ""
        func_data = item.get("function")
        if isinstance(func_data, dict):
            furniture_type = func_data.get("name", "")

        public_url = self._resolve_public_url(item, str(item_no))

        logger.info(
            f"Normalized IKEA item {item_no}: Name={name}, Price={price}, "
            f"DescLen={len(desc)}, Images={len(images)}, stock={stock!r}, available={listing_available}"
        )

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
            "listing_available": listing_available,
            "furniture_type": furniture_type,
            "category_name": category_name,
            "raw_item": item,
            "url": public_url,
        }

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
        listing_ok = normalized.get("listing_available", True)
        raw_stock = normalized.get("stock")
        if raw_stock is not None:
            eff_stock = int(raw_stock)
        elif listing_ok:
            eff_stock = 3
        else:
            eff_stock = 0

        # 1. FurnitureProduct
        product, created = FurnitureProduct.objects.get_or_create(
            external_id=item_no,
            defaults={
                "name": name,
                "slug": slug_base,
                "description": normalized.get("description", ""),
                "price": price,
                "currency": currency,
                "brand": self.brand, # Для новых товаров
                "category": self.default_category,
                "dimensions": normalized.get("dimensions", "")[:500],
                "material": normalized.get("material", "")[:500],
                "furniture_type": normalized.get("furniture_type", "")[:100],
                "main_image": normalized["images"][0] if normalized.get("images") else "",
                "video_url": normalized.get("video_url", ""),
                "external_url": normalized.get("url", ""),
                "external_data": {"source": "ikea_tr_direct", "raw": normalized.get("raw_item", {})},
                "stock_quantity": eff_stock,
                "is_available": listing_ok and eff_stock > 0,
                "is_active": True
            }
        )
        
        # Принудительная установка бренда и категории (если они пустые или изменились)
        if not product.brand and self.brand:
            product.brand = self.brand
            product.save(update_fields=["brand"])
            
        if not product.category and self.default_category:
            product.category = self.default_category
            product.save(update_fields=["category"])
        
        # Сохраняем видео, если оно есть (даже для существующего товара)
        if normalized.get("video_url") and product.video_url != normalized["video_url"]:
             product.video_url = normalized["video_url"]
             product.save(update_fields=["video_url"])
             
        # Галерея товара не дублируется: изображения только у FurnitureVariant (см. блок ниже).

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
            for attr in ["dimensions", "material", "furniture_type", "color", "main_image", "video_url", "brand", "category"]:
                new_val = normalized.get(attr, "")
                if not new_val and attr == "brand":
                     new_val = self.brand
                if not new_val and attr == "category":
                     new_val = self.default_category
                     
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
