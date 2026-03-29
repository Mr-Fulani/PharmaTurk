"""Парсер для сайта IKEA Turkey."""

import logging
from typing import List, Optional
from urllib.parse import urlparse

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
        
        path = urlparse(category_url).path.strip('/')
        parts = path.split('/')
        category_slug = parts[-1] if parts else ""
        
        if not category_slug:
            self.logger.warning(f"Не удалось извлечь категорию из URL: {category_url}")
            return []

        # Получаем краткие данные из поиска
        brief_results = self.ikea_service.get_category_products(category_slug, limit=max_products)
        
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
        
        scraped_products = []
        for item in full_results:
            scraped_products.append(self._to_scraped_product(item))
            
        return scraped_products

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит детальную страницу товара."""
        # Для IKEA TR URL содержит артикул (item_code) или слаг.
        # Пример: https://www.ikea.com.tr/urun/kallax-beyaz-77x147-cm-calisma-masali-unite-80275887
        
        item_code = self.ikea_service._extract_item_code(product_url)
        if not item_code:
            self.logger.warning(f"Не удалось извлечь артикул из URL: {product_url}")
            return None
            
        item_data = self.ikea_service.fetch_item_details(item_code)
        if not item_data:
            return None
            
        return self._to_scraped_product(item_data)

    def _to_scraped_product(self, item_data: dict) -> ScrapedProduct:
        """Нормализует данные из API IKEA в формат ScrapedProduct."""
        # Используем маппинг из IkeaService
        normalized = self.ikea_service._normalize_item_data(item_data)
        
        # Преобразуем в ScrapedProduct
        images = normalized.get("images", [])
        if not images and normalized.get("main_image"):
            images = [normalized["main_image"]]
            
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
            is_available=normalized.get("stock", 0) > 0,
            stock_quantity=normalized.get("stock"),
            source="ikea",
            attributes={
                "dimensions": normalized.get("dimensions"),
                "material": normalized.get("material"),
                "furniture_type": normalized.get("furniture_type"),
                "video_url": normalized.get("video_url"),
                "variant_info": normalized.get("variants"), # Если есть в raw
                "color": normalized.get("color"),
            }
        )
