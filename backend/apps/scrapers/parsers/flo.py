"""Парсер FLO (flo.com.tr) — турецкая обувь и аксессуары.

Сайт отдаёт серверный HTML без анти-бота. Все данные карточки лежат в одном
JS-объекте ``window.productDetail`` (бренд, цена, размеры с barcode/остатком,
цвет, пол, обувные атрибуты, галерея). Парсер читает его, как Zara читает
``viewPayload`` — без исполнения JavaScript.
"""

import json
import re
from typing import Any, Dict, Iterator, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text


class FloParser(BaseScraper):
    """Парсер flo.com.tr на основе серверного JSON ``window.productDetail``."""

    SUPPORTS_PAGE_CHUNKING = True

    PRODUCT_PATH_RE = re.compile(r"/urun/[^/?#]*?-(\d{4,})(?:[/?#]|$)", re.IGNORECASE)
    PRODUCT_DETAIL_MARKER = "window.productDetail = "
    PRODUCT_LINK_RE = re.compile(r'href="(/urun/[^"#?]*-\d{4,})"', re.IGNORECASE)
    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000

    def __init__(self, base_url: str = "https://www.flo.com.tr", **kwargs):
        super().__init__(base_url=base_url, delay_range=(1, 3), **kwargs)
        self.client.headers.update(
            {
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                "Referer": "https://www.flo.com.tr/",
            }
        )

    def get_name(self) -> str:
        return "flo"

    def get_supported_domains(self) -> List[str]:
        return ["flo.com.tr", "www.flo.com.tr"]

    @classmethod
    def is_flo_product_url(cls, url: str) -> bool:
        return bool(cls.PRODUCT_PATH_RE.search(urlparse(url).path or url))

    @classmethod
    def is_flo_category_url(cls, url: str) -> bool:
        """Категория — любой не-товарный путь на домене flo."""
        host = urlparse(url).netloc.lower()
        is_flo = host.endswith("flo.com.tr") or not host
        return is_flo and not cls.is_flo_product_url(url)

    @staticmethod
    def _canonical_url(url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))

    @staticmethod
    def _page_url(category_url: str, page: int) -> str:
        parsed = urlparse(category_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if page <= 1:
            query.pop("page", None)
        else:
            query["page"] = str(page)
        return urlunparse(parsed._replace(query=urlencode(query), fragment=""))

    def _extract_product_detail(self, html: str) -> Optional[Dict[str, Any]]:
        """Достаёт JSON из ``window.productDetail = {...}`` без regex по телу."""
        if not html or self.PRODUCT_DETAIL_MARKER not in html:
            return None
        marker_index = html.find(self.PRODUCT_DETAIL_MARKER)
        json_text = html[marker_index + len(self.PRODUCT_DETAIL_MARKER):].lstrip()
        try:
            payload, _ = json.JSONDecoder().raw_decode(json_text)
        except (json.JSONDecodeError, TypeError) as exc:
            self.logger.warning("FLO: не удалось разобрать productDetail: %s", exc)
            return None
        return payload if isinstance(payload, dict) else None

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
        start_page: int = 1,
    ) -> Iterator[ScrapedProduct]:
        seen_products: Set[str] = set()
        yielded = 0
        page = max(1, start_page)
        pages_done = 0

        while pages_done < max(1, max_pages):
            page_url = self._page_url(category_url, page)
            html = self._make_request(page_url)
            if not html:
                break

            product_urls = self._extract_product_links(html)
            new_on_page = 0
            for product_url in product_urls:
                identity = self._canonical_url(product_url)
                if identity in seen_products:
                    continue
                seen_products.add(identity)
                new_on_page += 1

                product = self.parse_product_detail(product_url)
                if product and self.validate_product(product):
                    yield product
                    yielded += 1
                    if self.max_products and yielded >= self.max_products:
                        return

            pages_done += 1
            if new_on_page == 0 or 'rel="next"' not in html:
                break
            page += 1

    def _extract_product_links(self, html: str) -> List[str]:
        links: List[str] = []
        seen: Set[str] = set()
        for href in self.PRODUCT_LINK_RE.findall(html):
            url = self._canonical_url(urljoin(self.base_url, href))
            if url in seen:
                continue
            seen.add(url)
            links.append(url)
        return links

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        html = self._make_request(product_url)
        if not html:
            return None
        detail = self._extract_product_detail(html)
        if not detail or not detail.get("name"):
            return None

        sku = str(detail.get("sku") or "")
        external_id = f"flo-{sku}" if sku else ""
        sizes = self._build_sizes(detail.get("options"))
        images = self._extract_images(detail)
        price = self._normalize_price_value(detail.get("price"))
        color = clean_text(str(detail.get("renk") or detail.get("orj_renk") or ""))
        is_available = str(detail.get("is_in_stock")).lower() == "true" or any(
            row["is_available"] for row in sizes
        )

        variant = {
            "external_id": f"flo-variant-{sku}",
            "sort_order": 0,
            "color": color,
            "display_name": clean_text(
                f"{detail.get('name') or ''} - {color}".strip(" -")
            ),
            "price": price,
            "currency": "TRY",
            "external_url": self._canonical_url(product_url),
            "images": images,
            "stock_quantity": (
                self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0
            ),
            "is_available": is_available,
            "sizes": sizes,
            "sku": sku,
        }

        attributes: Dict[str, Any] = {
            "fashion_variants": [variant],
            "variant_group_id": f"flo-{detail.get('model_code') or sku}",
            "color": color,
            "gender": self._map_gender(detail.get("cinsiyet") or detail.get("gender")),
            "sizes": [row["size"] for row in sizes],
        }
        attributes.update(self._shoe_attributes(detail))

        return ScrapedProduct(
            name=clean_text(str(detail.get("name") or "")),
            description=self._clean_description(detail.get("description")),
            price=price,
            currency="TRY",
            url=self._canonical_url(product_url),
            images=images,
            category=self._extract_category(detail),
            brand=clean_text(str(detail.get("manufacturer") or "")),
            external_id=external_id,
            sku=sku,
            is_available=is_available,
            stock_quantity=(self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0),
            attributes=attributes,
            source=self.get_name(),
        )

    def _build_sizes(self, options: Any) -> List[Dict[str, Any]]:
        sizes: List[Dict[str, Any]] = []
        for index, option in enumerate(options or []):
            if not isinstance(option, dict) or not option.get("option_value"):
                continue
            available = bool(option.get("is_in_stock"))
            sizes.append(
                {
                    "size": clean_text(str(option.get("option_value"))),
                    "is_available": available,
                    "stock_quantity": (
                        self.DEFAULT_ASSUMED_STOCK_QUANTITY if available else 0
                    ),
                    "sort_order": index,
                    "sku": str(option.get("sku") or ""),
                    "barcode": str(option.get("barcode") or ""),
                }
            )
        return sizes

    def _extract_images(self, detail: Dict[str, Any]) -> List[str]:
        images: List[str] = []
        seen: Set[str] = set()
        for media in detail.get("media_gallery") or []:
            if not isinstance(media, dict):
                continue
            url = str(media.get("url_vertical") or media.get("url") or "").strip()
            if not url:
                continue
            identity = url.split("?", 1)[0]
            if identity in seen:
                continue
            seen.add(identity)
            images.append(url)
        return images

    def _shoe_attributes(self, detail: Dict[str, Any]) -> Dict[str, Any]:
        """Маппит turkish-поля FLO на ключи, распознаваемые attribute_specs."""
        mapping = {
            "material": detail.get("materyal"),
            "sole_material": detail.get("taban"),
            "lining": detail.get("ic_astar_1"),
        }
        return {
            key: clean_text(str(value))
            for key, value in mapping.items()
            if value
        }

    def _extract_category(self, detail: Dict[str, Any]) -> str:
        breadcrumb = detail.get("breadcrumb") or []
        for row in reversed(breadcrumb):
            if isinstance(row, dict) and row.get("name"):
                return clean_text(str(row["name"]))
        return ""

    @staticmethod
    def _clean_description(value: Any) -> str:
        text = re.sub(r"<[^>]+>", " ", str(value or ""))
        return clean_text(text)

    @staticmethod
    def _normalize_price_value(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return round(float(str(value).replace(",", ".")), 2)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _map_gender(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"erkek", "man", "men", "male"}:
            return "men"
        if normalized in {"kadın", "kadin", "woman", "women", "female"}:
            return "women"
        if normalized in {"çocuk", "cocuk", "kid", "kids", "children"}:
            return "kids"
        if normalized in {"unisex"}:
            return "unisex"
        return ""
