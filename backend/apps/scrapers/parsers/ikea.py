"""Парсер для сайта IKEA Turkey."""

import logging
from typing import List, Optional
from ..base.scraper import BaseScraper, ScrapedProduct
from apps.catalog.services import IkeaService


class IkeaParser(BaseScraper):
    """Парсер для IKEA Turkey (через внутренний API)."""

    def __init__(self, base_url: str, **kwargs):
        super().__init__(base_url, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.ikea_service = IkeaService()

    def get_name(self) -> str:
        return "ikea"

    def get_supported_domains(self) -> List[str]:
        return ["ikea.com.tr", "www.ikea.com.tr"]

    def parse_product_list(self, category_url: str, max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из категории."""
        max_products = max_pages * 24 # Примерное количество на странице
        self.logger.info(f"Начинаем парсинг каталога IKEA: {category_url}")
        
        # Получаем category_id из URL (если это возможно) или просто ищем товары
        # Для IKEA TR URL обычно имеет вид /kategori/kallax-serisi или /urun-gruplari/...
        # Мы используем поиск по ключевым словам или извлекаем слаг категории.
        
        category_slug, site_language = self.ikea_service.parse_category_list_url(category_url)
        if not category_slug:
            self.logger.warning(f"Не удалось извлечь категорию из URL: {category_url}")
            return []

        # Получаем краткие данные из поиска (язык из пути: /en/category/... vs /kategori/...)
        brief_results = self.ikea_service.get_category_products(
            category_slug, limit=max_products, language=site_language
        )
        
        # Извлекаем артикулы (sprCode) для получения полных данных
        item_codes = []
        for item in brief_results:
            code = item.get("sprCode") or item.get("id")
            if code:
                item_codes.append(str(code))
        
        # Ограничиваем список кодов согласно лимиту (если задан в self.max_products или max_products)
        final_limit = self.max_products or max_products
        item_codes = item_codes[:final_limit]
        
        self.logger.info(f"Найдено {len(item_codes)} артикулов для детальной обработки (лимит: {final_limit})")
        
        # Получаем ПОЛНЫЕ данные о товарах (с видео, всеми фото и т.д.)
        full_results = self.ikea_service.fetch_items(item_codes)

        # В листинге с цветовыми вариантами один и тот же диван может быть несколькими sprCode —
        # собираем цвета в одну карточку и пропускаем уже учтённые артикулы.
        scraped_products: List[ScrapedProduct] = []
        seen_spr: set[str] = set()
        for item in full_results:
            row_code = self.ikea_service._clean_spr_code(item.get("sprCode") or item.get("id"))
            if not row_code or row_code in seen_spr:
                continue
            variant_details = self.ikea_service.collect_color_variant_details(item)
            for raw in variant_details:
                c = self.ikea_service._clean_spr_code(raw.get("sprCode") or raw.get("id"))
                if c:
                    seen_spr.add(c)
            scraped_products.append(
                self._scraped_product_from_variant_details(variant_details, canonical_spr=row_code)
            )

        return scraped_products

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит карточку товара; несколько цветов — одна позиция каталога, варианты в attributes."""
        item_code = self.ikea_service._extract_item_code(product_url)
        if not item_code:
            self.logger.warning(f"Не удалось извлечь артикул из URL: {product_url}")
            return None

        main = self.ikea_service.fetch_item_details(item_code)
        if not main:
            return None

        variant_details = self.ikea_service.collect_color_variant_details(main)
        return self._scraped_product_from_variant_details(variant_details, canonical_spr=item_code)

    def _scraped_product_from_variant_details(
        self,
        variant_details: List[dict],
        *,
        canonical_spr: str,
    ) -> ScrapedProduct:
        """Одна ScrapedProduct: при нескольких цветах — furniture_variants (как при парсинге по URL)."""
        if not variant_details:
            raise ValueError("variant_details не должен быть пустым")

        url_clean = self.ikea_service._clean_spr_code(canonical_spr)
        primary_raw = None
        for raw in variant_details:
            if self.ikea_service._clean_spr_code(raw.get("sprCode")) == url_clean:
                primary_raw = raw
                break
        if primary_raw is None:
            primary_raw = variant_details[0]

        scraped = self._to_scraped_product(primary_raw)
        scraped.external_id = url_clean
        scraped.sku = url_clean

        if len(variant_details) <= 1:
            return scraped

        payloads: List[dict] = []
        for idx, raw in enumerate(variant_details):
            n = self.ikea_service._normalize_item_data(raw)
            ext = str(n["item_no"]).replace(".", "").strip()
            payloads.append(
                {
                    "external_id": ext,
                    "sort_order": idx,
                    "color": (n.get("color") or "")[:50],
                    "display_name": (n.get("name") or "")[:500],
                    "price": n.get("price"),
                    "currency": n.get("currency") or "TRY",
                    "external_url": (n.get("url") or "")[:2000],
                    "images": list(n.get("images") or []),
                    "stock_quantity": n.get("stock"),
                    "is_available": n.get("listing_available", True),
                    "variant_info": raw.get("variantInfo"),
                }
            )

        payloads.sort(key=lambda p: (0 if p["external_id"] == url_clean else 1, p["sort_order"]))
        for i, p in enumerate(payloads):
            p["sort_order"] = i

        scraped.attributes = dict(scraped.attributes or {})
        scraped.attributes["furniture_variants"] = payloads
        self.logger.info(
            "IKEA: у артикула %s объединяем %d цветовых вариантов в одну карточку мебели",
            url_clean,
            len(payloads),
        )
        return scraped

    def _to_scraped_product(self, item_data: dict) -> ScrapedProduct:
        """Нормализует данные из API IKEA в формат ScrapedProduct."""
        # Используем маппинг из IkeaService
        normalized = self.ikea_service._normalize_item_data(item_data)
        
        # Преобразуем в ScrapedProduct
        images = normalized.get("images", [])
        if not images and normalized.get("main_image"):
            images = [normalized["main_image"]]
            
        raw = normalized.get("raw_item") or {}
        return ScrapedProduct(
            external_id=normalized["item_no"],
            sku=normalized["item_no"],
            name=normalized["name"],
            description=normalized["description"],
            price=normalized["price"],
            currency=normalized["currency"],
            category=normalized.get("category_name", "Мебель"),
            brand="IKEA",
            images=images,
            url=normalized["url"],
            is_available=normalized.get("listing_available", True),
            stock_quantity=normalized.get("stock"),
            source="ikea",
            attributes={
                "dimensions": normalized.get("dimensions"),
                "material": normalized.get("material"),
                "furniture_type": normalized.get("furniture_type"),
                "video_url": normalized.get("video_url"),
                "variant_info": raw.get("variantInfo"),
                "color": normalized.get("color"),
            },
        )
