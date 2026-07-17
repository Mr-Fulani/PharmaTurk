"""Парсер для сайта IKEA Turkey."""

import logging
from typing import Iterator, List, Optional
from urllib.parse import urlparse
from ..base.scraper import BaseScraper, ScrapedProduct
from apps.catalog.services import IkeaService


class IkeaParser(BaseScraper):
    """Парсер для IKEA Turkey (через внутренний API)."""

    SUPPORTS_PAGE_CHUNKING = True
    REPORTS_PAGES_PROCESSED = True
    MAX_PAGES_PER_CHUNK = 1
    API_PAGE_SIZE = 40

    def __init__(self, base_url: str, **kwargs):
        super().__init__(base_url, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.ikea_service = IkeaService()

    def get_name(self) -> str:
        return "ikea"

    def get_supported_domains(self) -> List[str]:
        return ["ikea.com.tr", "www.ikea.com.tr"]

    @classmethod
    def is_ikea_product_url(cls, url: str) -> bool:
        parts = [part for part in urlparse(url or "").path.strip("/").split("/") if part]
        return any(part in ("urun", "product", "p") for part in parts)

    @classmethod
    def supports_page_chunking_for_url(cls, url: str) -> bool:
        """Only IKEA category/API listings have a meaningful page cursor."""
        return not cls.is_ikea_product_url(url)

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
        start_page: int = 1,
    ) -> Iterator[ScrapedProduct]:
        """Парсит список товаров из категории."""
        self.has_more_pages = True
        self.logger.info(f"Начинаем парсинг каталога IKEA: {category_url}")
        
        # Получаем category_id из URL (если это возможно) или просто ищем товары
        # Для IKEA TR URL обычно имеет вид /kategori/kallax-serisi или /urun-gruplari/...
        # Мы используем поиск по ключевым словам или извлекаем слаг категории.
        
        category_slug, site_language = self.ikea_service.parse_category_list_url(category_url)
        if not category_slug:
            self.logger.warning(f"Не удалось извлечь категорию из URL: {category_url}")
            return []

        api_category_slug = self.ikea_service.resolve_category_api_slug(
            category_url,
            category_slug,
        )

        # Получаем краткие данные из поиска (язык из пути: /en/category/... vs /kategori/...)
        seen_spr: set[str] = set()
        yielded = 0
        final_limit = self.max_products or max_pages * self.API_PAGE_SIZE

        for page in range(max(1, start_page), max(1, start_page) + max(1, max_pages)):
            brief_results = self.ikea_service.get_category_products(
                api_category_slug,
                limit=self.API_PAGE_SIZE,
                language=site_language,
                page=page,
            )
            self.pages_processed += 1
            if not brief_results:
                self.has_more_pages = False
                break

            item_codes = []
            page_codes: set[str] = set()
            for item in brief_results:
                code = item.get("sprCode") or item.get("id")
                clean_code = self.ikea_service._clean_spr_code(code)
                if (
                    clean_code
                    and clean_code not in seen_spr
                    and clean_code not in page_codes
                ):
                    item_codes.append(clean_code)
                    page_codes.add(clean_code)

            self.logger.info(
                "IKEA API: страница %s, найдено %s артикулов для детальной обработки",
                page,
                len(item_codes),
            )
            full_results = self.ikea_service.fetch_items(item_codes)

            for item in full_results:
                row_code = self.ikea_service._clean_spr_code(
                    item.get("sprCode") or item.get("id")
                )
                if not row_code or row_code in seen_spr:
                    continue
                variant_details = self.ikea_service.collect_color_variant_details(item)
                for raw in variant_details:
                    clean_variant = self.ikea_service._clean_spr_code(
                        raw.get("sprCode") or raw.get("id")
                    )
                    if clean_variant:
                        seen_spr.add(clean_variant)
                scraped = self._scraped_product_from_variant_details(
                    variant_details,
                    canonical_spr=row_code,
                )
                scraped.attributes["ikea_source_category_slug"] = category_slug
                yield scraped
                yielded += 1
                if yielded >= final_limit:
                    return

            if len(brief_results) < self.API_PAGE_SIZE:
                self.has_more_pages = False
                break

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
                "ikea_category": raw.get("category"),
                "ikea_function": raw.get("function"),
            },
        )
