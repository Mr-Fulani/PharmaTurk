"""Общий контракт витрин Inditex, отличных от Zara (Bershka, Pull&Bear, Massimo Dutti).

В отличие от Zara, эти витрины не встраивают ``viewPayload`` в HTML: карточки и
листинги приходят из JSON API витрины ``/itxrest`` (тот же API использует их
собственный фронтенд). Akamai на первом запросе сессии отдаёт промежуточную
страницу ``bm-verify`` (HTTP 200 и meta refresh через ~5 с). Её проходим как
браузер без JavaScript: ждём паузу из refresh и открываем указанную ссылку,
после чего cookies сессии действуют и для API.
"""

import json
import re
import time
from abc import abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

from celery.exceptions import SoftTimeLimitExceeded
from curl_cffi import requests as curl_requests

from ..base.offers import MalformedOfferResponse, OfferGone, OfferNotFound
from ..base.scraper import ScrapedProduct, ScraperAccessBlockedError
from ..base.utils import clean_text
from .zara import ZaraParser


HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


class InditexSiblingParser(ZaraParser):
    """Переиспользует транспортные правила Zara, данные берёт из ``/itxrest``."""

    PRODUCT_PATH_RE = re.compile(
        r"(?:-c\d+p\d+(?:\.html)?|-l\d+)(?:$|[?#])",
        re.IGNORECASE,
    )
    CATEGORY_PATH_RE = re.compile(r"-n(\d+)(?:\.html)?(?:$|[?#])", re.IGNORECASE)
    MARKETING_PATH_RE = re.compile(r"(?!x)x")
    PRODUCT_URL_STYLE = "c0p"
    AJAX_REQUEST_EXCEPTIONS = (curl_requests.RequestsError,)

    # Турецкий магазин витрины; каталог магазина узнаём у API при первом запросе.
    STORE_ID = 0
    LANGUAGE_ID = -43
    # Сколько карточек запрашивается одним productsArray (= одна «страница» чанка).
    API_PAGE_SIZE = 12
    # 402 Akamai отдаёт на некоторых редиректах вместо 403 — это тот же отказ.
    BLOCKED_STATUS_CODES = (401, 402, 403)
    INTERSTITIAL_REFRESH_RE = re.compile(
        r"http-equiv=[\"']refresh[\"']\s+content=[\"'](\d+);\s*URL='([^']*bm-verify[^']*)'",
        re.IGNORECASE,
    )
    MAX_INTERSTITIAL_ROUNDS = 2
    MAX_INTERSTITIAL_DELAY_SECONDS = 10
    PRODUCT_ID_HTML_RE = re.compile(r"iProductId[\"']?\s*[:=]\s*[\"']?(\d+)")
    CATEGORY_ID_HTML_RES = (
        re.compile(r"rel=\"canonical\"\s+href=\"[^\"]*[?&]celement=(\d+)"),
        re.compile(r"iCategoryId[\"']?\s*[:=]\s*[\"']?(\d+)"),
    )
    # Основная галерея карточки (порядок как на сайте); прочие location —
    # миниатюры листинга, ховеры и служебные кадры.
    GALLERY_LOCATION = 1
    IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
    SECTION_GENDERS = {
        "WOMEN": "women",
        "WOMAN": "women",
        "MEN": "men",
        "MAN": "men",
        "KIDS": "kids",
        "KID": "kids",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Эти три витрины отклоняют стандартный TLS fingerprint requests даже
        # через residential proxy. curl-cffi воспроизводит Chrome handshake,
        # оставаясь лёгкой HTTP-сессией без Chromium/Selenium-процесса.
        self.ajax_session.close()
        session_kwargs = {
            "impersonate": "chrome",
            "headers": {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            },
        }
        if self.proxies:
            session_kwargs.update(
                {"proxies": self.proxies, "verify": self.proxy_tls_verify}
            )
        self.ajax_session = curl_requests.Session(**session_kwargs)
        self._catalog_id: Optional[str] = None

    @abstractmethod
    def get_name(self) -> str:
        raise NotImplementedError

    @classmethod
    def is_zara_product_url(cls, url: str) -> bool:
        parsed = urlparse(url)
        return bool(cls.PRODUCT_PATH_RE.search(parsed.path or url)) or bool(
            "pelement" in parsed.query and re.search(r"-l\d+", parsed.path, re.I)
        )

    @classmethod
    def is_zara_category_url(cls, url: str) -> bool:
        return bool(cls.CATEGORY_PATH_RE.search(urlparse(url).path or url))

    # --- транспорт ---------------------------------------------------------

    def _interstitial_refresh(self, response) -> Optional[Tuple[float, str]]:
        """Пауза и ссылка из промежуточной страницы Akamai или ``None``."""
        if response.status_code != 200:
            return None
        match = self.INTERSTITIAL_REFRESH_RE.search((response.text or "")[:4000])
        if not match:
            return None
        delay = min(int(match.group(1)), self.MAX_INTERSTITIAL_DELAY_SECONDS) + 0.5
        return delay, match.group(2)

    def _get_through_interstitial(self, url: str, *, accept: str):
        for _ in range(self.MAX_INTERSTITIAL_ROUNDS + 1):
            self._wait_before_ajax_request()
            response = self.ajax_session.get(
                url,
                headers={"Accept": accept},
                timeout=self.timeout,
                allow_redirects=True,
            )
            self._ajax_request_count += 1
            self._last_ajax_response_at = time.monotonic()
            refresh = self._interstitial_refresh(response)
            if refresh is None:
                return response
            delay, target = refresh
            self.logger.info(
                "%s: проверка Akamai bm-verify, повтор через %.1f сек.",
                self.SOURCE_LABEL,
                delay,
            )
            time.sleep(delay)
            url = urljoin(str(response.url or url), target)
        raise ScraperAccessBlockedError(
            f"{self.SOURCE_LABEL}: Akamai не пропустил проверку bm-verify "
            f"({urlparse(url).netloc}). Повторите позже или смените IP прокси.",
            source=self.SOURCE_LABEL,
            status_code=403,
            url=url,
        )

    def _fetch_text(self, url: str, *, accept: str = "application/json") -> Optional[str]:
        """GET с проходом bm-verify, повторами 429/5xx и понятными ошибками."""
        for attempt in range(self.max_retries + 1):
            response = None
            try:
                response = self._get_through_interstitial(url, accept=accept)
            except SoftTimeLimitExceeded:
                raise
            except self.AJAX_REQUEST_EXCEPTIONS as exc:
                self.logger.warning("%s: сетевая ошибка %s: %s", self.SOURCE_LABEL, url, exc)
            else:
                status = response.status_code
                final_url = str(response.url or url)
                if status < 400:
                    return response.text
                if status in self.BLOCKED_STATUS_CODES:
                    raise ScraperAccessBlockedError(
                        source=self.SOURCE_LABEL,
                        status_code=status,
                        url=final_url,
                    )
                if status == 404:
                    raise OfferNotFound(final_url)
                if status == 410:
                    raise OfferGone(final_url)
                self.logger.warning("%s: HTTP %s на %s", self.SOURCE_LABEL, status, final_url)
                if status not in self.RETRYABLE_STATUS_CODES:
                    return None
            if attempt >= self.max_retries:
                break
            retry_after = self._retry_after_seconds(response)
            backoff = retry_after or min(120.0, (2 ** attempt) * 3.0)
            self.logger.info("%s: повторный запрос через %.1f сек.", self.SOURCE_LABEL, backoff)
            time.sleep(backoff)
        return None

    def _warm_session(self) -> None:
        """Проходит bm-verify на главной один раз за сессию."""
        if self._session_warmed:
            return
        self._session_warmed = True
        self._fetch_text(self.WARMUP_URL, accept=HTML_ACCEPT)

    def _origin(self) -> str:
        parsed = urlparse(self.WARMUP_URL)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _api_json(self, path: str, **params: Any) -> Optional[Dict[str, Any]]:
        self._warm_session()
        query = urlencode({"languageId": self.LANGUAGE_ID, "appId": 1, **params})
        url = f"{self._origin()}/itxrest/{path}?{query}"
        text = self._fetch_text(url)
        if not text:
            return None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MalformedOfferResponse(
                f"{self.SOURCE_LABEL}: API вернул не JSON на {url}: {exc}"
            ) from exc
        return data if isinstance(data, dict) else None

    def _resolve_catalog_id(self) -> str:
        if self._catalog_id:
            return self._catalog_id
        data = self._api_json(f"2/catalog/store/{self.STORE_ID}") or {}
        for row in data.get("catalogs") or []:
            if isinstance(row, dict) and str(row.get("type")) == "1" and row.get("id"):
                self._catalog_id = str(row["id"])
                return self._catalog_id
        raise MalformedOfferResponse(
            f"{self.SOURCE_LABEL}: API магазина {self.STORE_ID} не вернул каталог"
        )

    # --- идентификаторы из URL --------------------------------------------

    def _product_id_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        pelement = dict(parse_qsl(parsed.query)).get("pelement", "")
        if pelement.isdigit():
            return pelement
        match = re.search(r"-c\d+p(\d+)(?:\.html)?$", parsed.path, re.IGNORECASE)
        if match:
            return match.group(1)
        html = self._fetch_text(url, accept=HTML_ACCEPT) or ""
        match = self.PRODUCT_ID_HTML_RE.search(html)
        return match.group(1) if match else ""

    def _category_id_from_url(self, url: str) -> str:
        celement = dict(parse_qsl(urlparse(url).query)).get("celement", "")
        if celement.isdigit():
            return celement
        html = self._fetch_text(url, accept=HTML_ACCEPT) or ""
        for pattern in self.CATEGORY_ID_HTML_RES:
            match = pattern.search(html)
            if match:
                return match.group(1)
        return ""

    # --- обход -------------------------------------------------------------

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
        start_page: int = 1,
    ) -> Iterator[ScrapedProduct]:
        self.has_more_pages = True
        category_id = self._category_id_from_url(category_url)
        if not category_id:
            self.has_more_pages = False
            # Ссылки меню вида «…-n3294.html» без ?celement= сайт отдаёт
            # 301 сам на себя, id категории из них не достать.
            raise MalformedOfferResponse(
                f"{self.SOURCE_LABEL}: не удалось определить id категории на {category_url}. "
                "Откройте категорию на сайте и вставьте адрес целиком, вместе с ?celement=…"
            )
        catalog_id = self._resolve_catalog_id()
        listing = self._api_json(
            f"3/catalog/store/{self.STORE_ID}/{catalog_id}/category/{category_id}/product",
            showProducts="false",
        ) or {}
        product_ids = list(
            dict.fromkeys(
                str(value)
                for value in (listing.get("sortedProductIds") or listing.get("productIds") or [])
                if str(value).isdigit()
            )
        )

        yielded = 0
        page = max(1, start_page)
        pages_done = 0
        while pages_done < max(1, max_pages):
            chunk = product_ids[(page - 1) * self.API_PAGE_SIZE: page * self.API_PAGE_SIZE]
            if not chunk:
                self.has_more_pages = False
                break
            data = self._api_json(
                f"3/catalog/store/{self.STORE_ID}/{catalog_id}/productsArray",
                productIds=",".join(chunk),
            ) or {}
            for row in data.get("products") or []:
                product = self._scraped_from_api(row, category_url)
                if product and self.validate_product(product):
                    yield product
                    yielded += 1
                    if self.max_products and yielded >= self.max_products:
                        return
            pages_done += 1
            if page * self.API_PAGE_SIZE >= len(product_ids):
                self.has_more_pages = False
                break
            page += 1

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        product_id = self._product_id_from_url(product_url)
        if not product_id:
            return None
        catalog_id = self._resolve_catalog_id()
        data = self._api_json(
            f"2/catalog/store/{self.STORE_ID}/{catalog_id}/category/0/product/{product_id}/detail"
        )
        if not data:
            return None
        return self._scraped_from_api(data, product_url)

    # --- разбор ответа API -------------------------------------------------

    def _scraped_from_api(self, row: Any, source_url: str) -> Optional[ScrapedProduct]:
        if not isinstance(row, dict):
            return None
        name = clean_text(str(row.get("name") or ""))
        product_id = str(row.get("id") or "").strip()
        if not name or not product_id:
            return None
        summaries = [
            item for item in row.get("bundleProductSummaries") or [] if isinstance(item, dict)
        ]
        summary = summaries[0] if summaries else row
        detail = summary.get("detail") if isinstance(summary.get("detail"), dict) else {}
        colors = [color for color in detail.get("colors") or [] if isinstance(color, dict)]
        galleries = self._galleries_by_color(detail)
        product_url = self._api_product_url(row, summary, source_url)
        external_id = f"{self.SOURCE_PREFIX}-{product_id}"

        variants = [
            self._api_variant(name, product_id, color, galleries, product_url, index)
            for index, color in enumerate(colors)
        ]
        variants = [variant for variant in variants if variant]
        first_variant = variants[0] if variants else {}

        description = ""
        top_detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        for value in (
            detail.get("longDescription"),
            detail.get("description"),
            *(color.get("longDescription") for color in colors),
            top_detail.get("longDescription"),
            top_detail.get("description"),
        ):
            description = clean_text(str(value or ""))
            if description:
                break

        subfamily_info = (
            detail.get("subfamilyInfo") if isinstance(detail.get("subfamilyInfo"), dict) else {}
        )
        subfamily = clean_text(
            str(summary.get("subFamilyName") or subfamily_info.get("subFamilyName") or "")
        )
        family = clean_text(str(summary.get("familyName") or row.get("familyName") or ""))
        section = str(summary.get("sectionNameEN") or row.get("sectionNameEN") or "").upper()

        attrs: Dict[str, Any] = {
            "fashion_variants": variants,
            "variant_group_id": external_id,
            "group_sku": str(detail.get("reference") or ""),
            "display_reference": str(detail.get("displayReference") or ""),
            "family": family,
            "subfamily": subfamily,
            "gender": self.SECTION_GENDERS.get(section, ""),
            "composition": detail.get("compositionDetail") or {},
        }
        if first_variant.get("color"):
            attrs["color"] = first_variant["color"]

        total_stock = sum(int(v.get("stock_quantity") or 0) for v in variants)
        return ScrapedProduct(
            name=name,
            description=description,
            price=first_variant.get("price"),
            old_price=first_variant.get("old_price"),
            currency="TRY",
            url=product_url,
            images=list(first_variant.get("images") or []),
            category=subfamily or family,
            brand=self.BRAND_NAME,
            external_id=external_id,
            sku=str(detail.get("reference") or ""),
            is_available=any(bool(v.get("is_available")) for v in variants),
            stock_quantity=total_stock or None,
            attributes=attrs,
            source=self.get_name(),
        )

    def _api_variant(
        self,
        product_name: str,
        product_id: str,
        color: Dict[str, Any],
        galleries: Dict[str, List[str]],
        product_url: str,
        sort_order: int,
    ) -> Optional[Dict[str, Any]]:
        color_id = str(color.get("id") or "").strip()
        if not color_id:
            return None
        sizes = []
        prices = []
        old_prices = []
        for index, size in enumerate(color.get("sizes") or []):
            if not isinstance(size, dict) or not size.get("name"):
                continue
            visibility = str(size.get("visibilityValue") or "").upper()
            available = visibility == "SHOW" and bool(size.get("isBuyable", True))
            price = self._normalize_price_value(size.get("price"))
            if price is not None:
                prices.append(price)
            # Зачёркнутая цена распродажи (oldPrice размера, в курушах как price).
            old_price = self._normalize_price_value(size.get("oldPrice"))
            if old_price is not None:
                old_prices.append(old_price)
            sizes.append(
                {
                    "size": clean_text(str(size.get("name"))),
                    "is_available": available,
                    "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if available else 0,
                    "sort_order": index,
                    "sku": str(size.get("partnumber") or size.get("sku") or ""),
                    "availability": visibility.lower(),
                }
            )
        is_available = any(row["is_available"] for row in sizes)
        color_name = clean_text(str(color.get("name") or ""))
        return {
            "external_id": f"{self.SOURCE_PREFIX}-variant-{product_id}-{color_id}",
            "sort_order": sort_order,
            "color": color_name,
            "display_name": clean_text(f"{product_name} - {color_name}".strip(" -")),
            "price": min(prices) if prices else None,
            "old_price": max(old_prices) if old_prices else None,
            "currency": "TRY",
            "external_url": product_url,
            "images": galleries.get(color_id, []),
            "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            "is_available": is_available,
            "sizes": sizes,
            "sku": str(color.get("reference") or color_id),
            "availability": "in_stock" if is_available else "out_of_stock",
        }

    def _galleries_by_color(self, detail: Dict[str, Any]) -> Dict[str, List[str]]:
        default_set = detail.get("xmediaDefaultSet") or 0
        galleries: Dict[str, List[str]] = {}
        for entry in detail.get("xmedia") or []:
            if not isinstance(entry, dict):
                continue
            color_code = str(entry.get("colorCode") or "")
            items = [item for item in entry.get("xmediaItems") or [] if isinstance(item, dict)]
            if not color_code or not items:
                continue
            item = next((row for row in items if row.get("set") == default_set), items[0])
            medias = {
                str(media.get("idMedia")): media
                for media in item.get("medias") or []
                if isinstance(media, dict)
            }
            order: List[str] = []
            for location_set in entry.get("xmediaLocations") or []:
                if not isinstance(location_set, dict) or location_set.get("set") != item.get("set"):
                    continue
                for location in location_set.get("locations") or []:
                    if isinstance(location, dict) and location.get("location") == self.GALLERY_LOCATION:
                        order = [str(value) for value in location.get("mediaLocations") or []]
            rows = [medias[media_id] for media_id in order if media_id in medias] or [
                media for media in medias.values() if media.get("clazz") == 1
            ]
            urls: List[str] = []
            seen = set()
            for media in rows:
                extra = media.get("extraInfo") if isinstance(media.get("extraInfo"), dict) else {}
                url = str(extra.get("deliveryUrl") or media.get("url") or "").strip()
                extension = url.split("?", 1)[0].rsplit(".", 1)[-1].lower()
                if not url or extension not in self.IMAGE_EXTENSIONS:
                    continue
                identity = str(extra.get("assetId") or url.split("?", 1)[0])
                if identity in seen:
                    continue
                seen.add(identity)
                urls.append(url)
            galleries[color_code] = urls
        return galleries

    def _api_product_url(
        self,
        row: Dict[str, Any],
        summary: Dict[str, Any],
        source_url: str,
    ) -> str:
        product_id = str(row.get("id") or "")
        slug = str(row.get("productUrl") or summary.get("productUrl") or "").strip(" /")
        locale_prefix = urlparse(self.WARMUP_URL).path.rstrip("/") or "/tr"
        if not slug:
            # Без slug остаётся исходная ссылка; из query сохраняем только id товара.
            parsed = urlparse(source_url)
            pelement = dict(parse_qsl(parsed.query)).get("pelement")
            query = urlencode({"pelement": pelement}) if pelement else ""
            return urlunparse(parsed._replace(query=query, fragment=""))
        if self.PRODUCT_URL_STYLE == "l":
            return (
                f"{self._origin()}{locale_prefix}/{quote(slug, safe='-')}"
                f"?{urlencode({'pelement': product_id})}"
            )
        keyword = re.sub(r"-l\d+$", "", slug)
        return f"{self._origin()}{locale_prefix}/{quote(keyword, safe='-')}-c0p{product_id}.html"
