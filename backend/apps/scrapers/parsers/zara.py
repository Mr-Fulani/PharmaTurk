"""Парсер Zara для категорий и отдельных карточек товара."""

import json
import random
import re
import time
from typing import Any, Dict, Iterator, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from celery.exceptions import SoftTimeLimitExceeded

from apps.http_errors import raise_for_blocked_status

from ..base.scraper import BaseScraper, ScrapedProduct, ScraperAccessBlockedError
from ..base.utils import clean_text


class ZaraParser(BaseScraper):
    """Парсер турецкой версии Zara на основе серверного JSON payload."""

    SUPPORTS_PAGE_CHUNKING = True

    PRODUCT_PATH_RE = re.compile(r"-p(\d+)\.html(?:$|[?#])", re.IGNORECASE)
    CATEGORY_PATH_RE = re.compile(r"-l(\d+)\.html(?:$|[?#])", re.IGNORECASE)
    MARKETING_PATH_RE = re.compile(r"-mkt(\d+)\.html(?:$|[?#])", re.IGNORECASE)
    VIEW_PAYLOAD_MARKER = "window.zara.viewPayload = "
    AVAILABLE_STATUSES = {"in_stock", "low_on_stock"}
    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000
    IMAGE_WIDTH = 2048
    MIN_REQUEST_DELAY_SECONDS = 2.5
    BATCH_REQUEST_SIZE = 20
    BATCH_PAUSE_RANGE = (15.0, 30.0)
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, base_url: str = "https://www.zara.com", **kwargs):
        super().__init__(base_url=base_url, delay_range=(2, 4), **kwargs)
        self.client.headers.update(
            {
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                "Referer": "https://www.zara.com/tr/tr/",
            }
        )
        self.ajax_session = requests.Session()
        self.ajax_session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            }
        )
        self._last_ajax_response_at: Optional[float] = None
        self._ajax_request_count = 0

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ajax_session.close()
        return super().__exit__(exc_type, exc_val, exc_tb)

    def get_name(self) -> str:
        return "zara"

    def get_supported_domains(self) -> List[str]:
        return ["zara.com", "www.zara.com", "tr.zara.com"]

    @classmethod
    def is_zara_product_url(cls, url: str) -> bool:
        return bool(cls.PRODUCT_PATH_RE.search(urlparse(url).path or url))

    @classmethod
    def is_zara_category_url(cls, url: str) -> bool:
        path = urlparse(url).path or url
        return bool(cls.CATEGORY_PATH_RE.search(path) or cls.MARKETING_PATH_RE.search(path))

    @classmethod
    def is_zara_marketing_url(cls, url: str) -> bool:
        return bool(cls.MARKETING_PATH_RE.search(urlparse(url).path or url))

    @classmethod
    def supports_page_chunking_for_url(cls, url: str) -> bool:
        """У ``mkt`` нет общей нумерации страниц для всех вложенных категорий."""
        return bool(cls.CATEGORY_PATH_RE.search(urlparse(url).path or url))

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

    @staticmethod
    def _ajax_url(url: str) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["ajax"] = "true"
        return urlunparse(parsed._replace(query=urlencode(query), fragment=""))

    def _extract_view_payload(self, html: str) -> Optional[Dict[str, Any]]:
        """Извлекает JSON без regex по всему документу.

        Это не даёт символам ``;`` внутри строк преждевременно обрезать payload.
        """
        if not html or self.VIEW_PAYLOAD_MARKER not in html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text() or ""
            marker_index = script_text.find(self.VIEW_PAYLOAD_MARKER)
            if marker_index < 0:
                continue
            json_text = script_text[marker_index + len(self.VIEW_PAYLOAD_MARKER):].lstrip()
            try:
                payload, _ = json.JSONDecoder().raw_decode(json_text)
            except (json.JSONDecodeError, TypeError) as exc:
                self.logger.warning(
                    "Zara: не удалось разобрать viewPayload: %s",
                    exc,
                )
                return None
            return payload if isinstance(payload, dict) else None
        return None

    def _make_ajax_request(self, url: str) -> Optional[str]:
        """Запрашивает чистый JSON Zara через отдельный HTTP/1.1 transport."""
        ajax_url = self._ajax_url(url)
        for attempt in range(self.max_retries + 1):
            try:
                self._wait_before_ajax_request()
                self.logger.info(
                    "Zara AJAX-запрос к %s (попытка %s)",
                    ajax_url,
                    attempt + 1,
                )
                response = self.ajax_session.get(
                    ajax_url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                self._ajax_request_count += 1
                self._last_ajax_response_at = time.monotonic()
                response.raise_for_status()
                return response.text
            except SoftTimeLimitExceeded:
                raise
            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                self.logger.warning(
                    "Ошибка Zara AJAX-запроса к %s (HTTP %s): %s",
                    ajax_url,
                    status_code or "network",
                    exc,
                )
                if status_code in (401, 403):
                    raise_for_blocked_status(
                        status_code=status_code,
                        url=str(getattr(exc.response, "url", None) or ajax_url),
                        source="Zara",
                    )
                if attempt >= self.max_retries:
                    break
                if status_code and status_code not in self.RETRYABLE_STATUS_CODES:
                    break
                retry_after = self._retry_after_seconds(getattr(exc, "response", None))
                backoff = retry_after or min(120.0, (2 ** attempt) * random.uniform(2.0, 4.0))
                self.logger.info("Zara: повторный запрос через %.1f сек.", backoff)
                time.sleep(backoff)
        return None

    def _wait_before_ajax_request(self) -> None:
        """Ограничивает частоту запросов и делает длинные обходы менее равномерными."""
        wait_seconds = 0.0
        if self._last_ajax_response_at is not None:
            delay_min = max(self.MIN_REQUEST_DELAY_SECONDS, float(self.delay_range[0]))
            delay_max = max(delay_min, float(self.delay_range[1]))
            target_delay = random.uniform(delay_min, delay_max)
            elapsed = max(0.0, time.monotonic() - self._last_ajax_response_at)
            wait_seconds = max(0.0, target_delay - elapsed)

        if (
            self._ajax_request_count > 0
            and self._ajax_request_count % self.BATCH_REQUEST_SIZE == 0
        ):
            wait_seconds = max(wait_seconds, random.uniform(*self.BATCH_PAUSE_RANGE))

        if wait_seconds > 0:
            self.logger.info("Zara: защитная пауза %.1f сек.", wait_seconds)
            time.sleep(wait_seconds)

    @staticmethod
    def _retry_after_seconds(response) -> Optional[float]:
        if response is None:
            return None
        raw_value = str(response.headers.get("Retry-After") or "").strip()
        try:
            return min(300.0, max(0.0, float(raw_value))) if raw_value else None
        except (TypeError, ValueError):
            return None

    def _request_payload(self, url: str) -> Optional[Dict[str, Any]]:
        # AJAX-режим Zara возвращает чистый JSON и не требует выполнения
        # JavaScript-проверки Akamai, которая встречается в обычном HTML.
        access_error = None
        try:
            response_text = self._make_ajax_request(url)
        except ScraperAccessBlockedError as exc:
            # Иногда блокируется только AJAX endpoint, а обычный HTML остаётся
            # доступным. Поэтому сначала пробуем резервный путь и только потом
            # считаем блокировку окончательной.
            access_error = exc
            response_text = None
        if response_text:
            try:
                payload = json.loads(response_text)
            except (json.JSONDecodeError, TypeError):
                payload = self._extract_view_payload(response_text)
            if isinstance(payload, dict):
                return payload

        # HTML оставляем резервным контрактом для тестовых снимков и на случай,
        # если Zara отключит JSON-режим для конкретного типа страницы.
        response_text = self._make_request(url)
        if not response_text:
            if access_error is not None:
                raise access_error
            return None
        payload = self._extract_view_payload(response_text)
        if payload is None:
            self.logger.warning("Zara: payload отсутствует на странице %s", url)
        return payload

    def parse_categories(self) -> List[Dict[str, Any]]:
        html = self._make_request(self.base_url)
        if not html:
            return []
        return self._extract_category_links(html, self.base_url)

    def _extract_category_links(self, html: str, page_url: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        categories: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not self.CATEGORY_PATH_RE.search(urlparse(href).path or href):
                continue
            url = self._canonical_url(urljoin(page_url, href))
            if url in seen:
                continue
            seen.add(url)
            match = self.CATEGORY_PATH_RE.search(urlparse(url).path)
            categories.append(
                {
                    "name": clean_text(anchor.get_text(" ", strip=True)) or "Zara",
                    "url": url,
                    "external_id": match.group(1) if match else "",
                    "source": self.get_name(),
                }
            )
        return categories

    def _extract_category_links_from_payload(
        self,
        payload: Dict[str, Any],
        page_url: str,
    ) -> List[Dict[str, Any]]:
        """Собирает товарные категории из вложенных блоков маркетингового payload."""
        categories: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        def walk(value: Any, depth: int = 0) -> None:
            if depth > 12 or len(categories) >= 500:
                return
            if isinstance(value, list):
                for row in value:
                    walk(row, depth + 1)
                return
            if not isinstance(value, dict):
                return

            seo = value.get("seo") if isinstance(value.get("seo"), dict) else {}
            keyword = str(seo.get("keyword") or "").strip(" /")
            seo_category_id = str(seo.get("seoCategoryId") or "").strip()
            layout = str(value.get("layout") or "")
            if keyword and seo_category_id and layout == "products-category-view":
                parsed = urlparse(page_url)
                path_parts = [part for part in parsed.path.split("/") if part]
                locale_prefix = (
                    "/" + "/".join(path_parts[:2]) if len(path_parts) >= 2 else "/tr/tr"
                )
                url = urlunparse(
                    parsed._replace(
                        path=f"{locale_prefix}/{keyword}-l{seo_category_id}.html",
                        query="",
                        fragment="",
                    )
                )
                if url not in seen:
                    seen.add(url)
                    categories.append(
                        {
                            "name": clean_text(str(value.get("name") or keyword)),
                            "url": url,
                            "external_id": seo_category_id,
                            "source": self.get_name(),
                        }
                    )

            for child in value.values():
                walk(child, depth + 1)

        walk(payload)
        return categories

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
        start_page: int = 1,
    ) -> Iterator[ScrapedProduct]:
        if self.is_zara_marketing_url(category_url):
            yield from self._parse_marketing_category(category_url, max_categories=max_pages)
            return

        seen_products: Set[str] = set()
        yielded = 0
        page = max(1, start_page)
        pages_done = 0

        while pages_done < max(1, max_pages):
            page_url = self._page_url(category_url, page)
            payload = self._request_payload(page_url)
            if not payload:
                break

            components = self._extract_category_components(payload, page)
            new_on_page = 0
            for component in components:
                product_url = self._build_product_url(component, category_url)
                identity = self._component_identity(component, product_url)
                if not product_url or not identity or identity in seen_products:
                    continue
                seen_products.add(identity)
                new_on_page += 1

                product = self.parse_product_detail(product_url)
                if product is None:
                    product = self._build_list_fallback(component, product_url, payload)
                if product and self.validate_product(product):
                    yield product
                    yielded += 1
                    if self.max_products and yielded >= self.max_products:
                        return

            pages_done += 1
            pagination = payload.get("paginationInfo") or {}
            if pagination.get("isLastPage") is True or new_on_page == 0:
                break
            page += 1

    def _parse_marketing_category(
        self,
        marketing_url: str,
        *,
        max_categories: int,
    ) -> Iterator[ScrapedProduct]:
        """Обходит товарные категории лендинга без авточепочки чанков."""
        payload = self._request_payload(marketing_url)
        if not payload:
            return
        categories = self._extract_category_links_from_payload(payload, marketing_url)
        seen_products: Set[str] = set()
        yielded = 0
        for category in categories[: max(1, max_categories)]:
            for product in self.parse_product_list(category["url"], max_pages=1, start_page=1):
                identity = product.external_id or product.url
                if identity in seen_products:
                    continue
                seen_products.add(identity)
                yield product
                yielded += 1
                if self.max_products and yielded >= self.max_products:
                    return

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        payload = self._request_payload(product_url)
        if not payload:
            return None
        product = payload.get("product")
        if not isinstance(product, dict) or not product.get("name"):
            return None

        detail = product.get("detail") if isinstance(product.get("detail"), dict) else {}
        colors = detail.get("colors") if isinstance(detail.get("colors"), list) else []
        variants = [
            self._build_variant(product, color, product_url, index)
            for index, color in enumerate(colors)
            if isinstance(color, dict)
        ]
        variants = [variant for variant in variants if variant.get("external_id")]

        seo = product.get("seo") if isinstance(product.get("seo"), dict) else {}
        seo_product_id = str(seo.get("seoProductId") or product.get("id") or "").strip()
        external_id = f"zara-{seo_product_id}" if seo_product_id else ""
        category = self._extract_product_category(product, payload)
        description = self._extract_description(product, colors)
        first_variant = variants[0] if variants else {}
        price = first_variant.get("price")
        if price is None:
            price = self._normalize_price_value(payload.get("analyticsData", {}).get("mainPrice"))

        attrs: Dict[str, Any] = {
            "fashion_variants": variants,
            "variant_group_id": external_id,
            "group_sku": str(detail.get("reference") or ""),
            "display_reference": str(detail.get("displayReference") or ""),
            "family": str(product.get("familyName") or ""),
            "subfamily": str(product.get("subfamilyName") or ""),
            "gender": self._section_gender(product.get("sectionName")),
            "composition": detail.get("detailedComposition") or {},
        }
        if first_variant.get("color"):
            attrs["color"] = first_variant["color"]

        total_stock = sum(int(v.get("stock_quantity") or 0) for v in variants)
        return ScrapedProduct(
            name=clean_text(str(product.get("name") or "")),
            description=description,
            price=price,
            currency=self._payload_currency(payload),
            url=self._canonical_url(product_url),
            images=list(first_variant.get("images") or []),
            category=category,
            brand="Zara",
            external_id=external_id,
            sku=str(detail.get("reference") or ""),
            is_available=any(bool(v.get("is_available")) for v in variants),
            stock_quantity=total_stock or None,
            attributes=attrs,
            source=self.get_name(),
        )

    def _extract_category_components(
        self,
        payload: Dict[str, Any],
        page: int,
    ) -> List[Dict[str, Any]]:
        components: List[Dict[str, Any]] = []
        for group in payload.get("productGroups") or []:
            if not isinstance(group, dict):
                continue
            for element in group.get("elements") or []:
                if not isinstance(element, dict):
                    continue
                for component in element.get("commercialComponents") or []:
                    if not isinstance(component, dict) or component.get("type") != "Product":
                        continue
                    server_page = component.get("serverPage")
                    # Zara на page=N может вернуть накопленный список
                    # предыдущих страниц.
                    if server_page is not None and int(server_page) != page:
                        continue
                    components.append(component)
        return components

    def _build_product_url(self, component: Dict[str, Any], source_url: str) -> str:
        seo = component.get("seo") if isinstance(component.get("seo"), dict) else {}
        keyword = str(seo.get("keyword") or "").strip(" /")
        product_id = str(seo.get("seoProductId") or "").strip()
        if not keyword or not product_id:
            return ""
        parsed = urlparse(source_url)
        path_parts = [part for part in parsed.path.split("/") if part]
        locale_prefix = "/" + "/".join(path_parts[:2]) if len(path_parts) >= 2 else "/tr/tr"
        return urlunparse(
            parsed._replace(
                path=f"{locale_prefix}/{keyword}-p{product_id}.html",
                query="",
                fragment="",
            )
        )

    @staticmethod
    def _component_identity(component: Dict[str, Any], product_url: str) -> str:
        seo = component.get("seo") if isinstance(component.get("seo"), dict) else {}
        return str(seo.get("seoProductId") or component.get("id") or product_url or "")

    def _build_variant(
        self,
        product: Dict[str, Any],
        color: Dict[str, Any],
        product_url: str,
        sort_order: int,
    ) -> Dict[str, Any]:
        status = str(color.get("availability") or "").lower()
        sizes = []
        for index, size in enumerate(color.get("sizes") or []):
            if not isinstance(size, dict) or not size.get("name"):
                continue
            size_status = str(size.get("availability") or "").lower()
            size_available = size_status in self.AVAILABLE_STATUSES
            sizes.append(
                {
                    "size": clean_text(str(size.get("name"))),
                    "is_available": size_available,
                    "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if size_available else 0,
                    "sort_order": index,
                    "sku": str(size.get("sku") or ""),
                    "availability": size_status,
                }
            )

        is_available = status in self.AVAILABLE_STATUSES or any(
            row["is_available"] for row in sizes
        )
        color_identity = str(
            color.get("productId")
            or color.get("reference")
            or color.get("id")
            or ""
        )
        images = self._extract_images(color)
        return {
            "external_id": f"zara-variant-{color_identity}",
            "sort_order": sort_order,
            "color": clean_text(str(color.get("name") or "")),
            "display_name": clean_text(
                f"{product.get('name') or ''} - {color.get('name') or ''}".strip(" -")
            ),
            "price": self._normalize_price_value(color.get("price")),
            "currency": "TRY",
            "external_url": self._canonical_url(product_url),
            "images": images,
            "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            "is_available": is_available,
            "sizes": sizes,
            "sku": str(color.get("canonicalReference") or color.get("reference") or color_identity),
            "availability": status,
        }

    def _extract_images(self, color: Dict[str, Any]) -> List[str]:
        images: List[str] = []
        seen: Set[str] = set()
        media_rows = list(color.get("xmedia") or [])
        if isinstance(color.get("pdpMedia"), dict):
            media_rows.insert(0, color["pdpMedia"])
        for media in media_rows:
            if not isinstance(media, dict) or media.get("type") not in (None, "image"):
                continue
            extra = media.get("extraInfo") if isinstance(media.get("extraInfo"), dict) else {}
            url = str(extra.get("deliveryUrl") or media.get("url") or "").strip()
            if not url:
                continue
            url = url.replace("{width}", str(self.IMAGE_WIDTH))
            identity = str(extra.get("assetId") or url.split("?", 1)[0])
            if identity in seen:
                continue
            seen.add(identity)
            images.append(url)
        return images

    def _build_list_fallback(
        self,
        component: Dict[str, Any],
        product_url: str,
        payload: Dict[str, Any],
    ) -> Optional[ScrapedProduct]:
        name = clean_text(str(component.get("name") or ""))
        identity = self._component_identity(component, product_url)
        if not name or not identity:
            return None
        detail = component.get("detail") if isinstance(component.get("detail"), dict) else {}
        colors = detail.get("colors") if isinstance(detail.get("colors"), list) else []
        images = self._extract_images(colors[0]) if colors and isinstance(colors[0], dict) else []
        availability = str(component.get("availability") or "").lower()
        category_data = payload.get("category") if isinstance(payload.get("category"), dict) else {}
        return ScrapedProduct(
            name=name,
            price=self._normalize_price_value(component.get("price")),
            currency=self._payload_currency(payload),
            url=product_url,
            images=images,
            category=clean_text(
                str(category_data.get("name") or component.get("familyName") or "")
            ),
            brand="Zara",
            external_id=f"zara-{identity}",
            sku=str(component.get("reference") or ""),
            is_available=availability in self.AVAILABLE_STATUSES,
            stock_quantity=(
                self.DEFAULT_ASSUMED_STOCK_QUANTITY
                if availability in self.AVAILABLE_STATUSES
                else 0
            ),
            attributes={"is_list_fallback": True},
            source=self.get_name(),
        )

    @staticmethod
    def _normalize_price_value(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return round(float(value) / 100, 2)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _payload_currency(payload: Dict[str, Any]) -> str:
        config = (
            payload.get("clientAppConfig")
            if isinstance(payload.get("clientAppConfig"), dict)
            else {}
        )
        formatter = (
            config.get("formatterConfig")
            if isinstance(config.get("formatterConfig"), dict)
            else {}
        )
        return str(formatter.get("currencyCode") or formatter.get("currency") or "TRY")[:5]

    @staticmethod
    def _section_gender(section_name: Any) -> str:
        normalized = str(section_name or "").strip().upper()
        if normalized == "WOMAN":
            return "women"
        if normalized == "MAN":
            return "men"
        if normalized in {"KID", "KIDS", "CHILDREN"}:
            return "kids"
        return ""

    @staticmethod
    def _extract_description(product: Dict[str, Any], colors: List[Dict[str, Any]]) -> str:
        for color in colors:
            if not isinstance(color, dict):
                continue
            value = clean_text(str(color.get("rawDescription") or color.get("description") or ""))
            if value:
                return value
        seo = product.get("seo") if isinstance(product.get("seo"), dict) else {}
        return clean_text(str(seo.get("description") or ""))

    @staticmethod
    def _extract_product_category(product: Dict[str, Any], payload: Dict[str, Any]) -> str:
        breadcrumbs = payload.get("breadCrumbs") or []
        for row in reversed(breadcrumbs):
            if isinstance(row, dict) and row.get("text"):
                return clean_text(str(row["text"]))
        seo = product.get("seo") if isinstance(product.get("seo"), dict) else {}
        for row in reversed(seo.get("breadCrumb") or []):
            if isinstance(row, dict) and row.get("text"):
                return clean_text(str(row["text"]))
        return clean_text(str(product.get("familyName") or ""))
