"""Парсер Seniorah (seniorah.com) — женская обувь своей марки, магазин на Shopify.

Shopify отдаёт каталог открытым JSON, без браузера, прокси и разбора HTML:

- ``/products.json?limit=250&page=N`` — весь каталог (255 товаров на 07.11.2026 —
  два запроса);
- ``/collections/<раздел>/products.json`` — один раздел;
- ``/products/<товар>.json`` — одна карточка;
- ``/collections.json`` — разделы сайта для режима «Весь сайт».

У Shopify каждый цвет — отдельный товар. Модель собирается по коду артикула:
``P-057-04-C-BLACK/…`` и ``P-057-04-C-TABA/…`` — одна модель ``P-057-04-C`` в
двух цветах. Цвета модели парсер берёт из всего каталога (он загружается один
раз на прогон), поэтому модель собирается целиком, с какого бы цвета или
раздела ни начался обход, и карточку отдельно открывать не нужно.

Раскладка по нашим разделам — по виду обуви в названии
(``SENIORAH_CATEGORY_ROUTES``); товар неизвестного вида не загружается и
попадает в отчёт прогона «не разложено». Решения владельца 07.11.2026 —
reports/seniorah-feasibility-2026-11-07.md.
"""

import json
import re
import threading
import time
from collections import Counter
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

from apps.catalog.utils.tr_vocab import COLOR_DETAIL_SEPARATOR, normalize_ascii_text, translate_turkish_color
from apps.http_errors import SourceRateLimitedError, raise_for_blocked_status

from ..base.catalog_state import CatalogTraversalState
from ..base.listing_snapshot import listing_fingerprint
from ..base.offers import (
    MalformedOfferResponse,
    OfferCheckContext,
    OfferCheckErrorCode,
    OfferCheckResult,
    OfferNotFound,
    OfferSourceUnavailable,
    result_from_scraped_product,
    translate_offer_check_errors,
)
from ..base.scraper import (
    BaseScraper,
    CategoryPageNotFoundError,
    ScrapedProduct,
    ScraperAccessBlockedError,
    SiteCategoriesError,
)
from ..base.utils import clean_text


class SeniorahFormatError(RuntimeError):
    """Ответ Shopify без ожидаемых ключей — сайт сменил формат, а не «каталог пуст»."""


# Вид обуви по словам названия → маршрут наших разделов (от точного к корню).
# Порядок важен: «Sabo … Mantar Terlik» — сабо, «Topuklu Bot» — ботильоны,
# «Loafer Ayakkabı … Babet» — лоферы.
SENIORAH_CATEGORY_ROUTES: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("ev terligi",), ("slippers", "home-shoes", "shoes")),
    (("sabo",), ("clogs", "sandals", "shoes")),
    (("terlik",), ("slides", "sandals", "shoes")),
    (("sandalet",), ("sandals-classic", "sandals", "shoes")),
    (("cizme", "cizmesi"), ("boots-classic", "boots", "shoes")),
    (("bot", "botu", "bootie"), ("ankle-boots", "boots", "shoes")),
    (("spor ayakkabi", "sneaker"), ("sneakers", "shoes")),
    (("loafer",), ("loafers", "dress-shoes", "shoes")),
    (("babet", "balerin"), ("ballet-flats", "casual-shoes", "shoes")),
    (("topuklu", "stiletto"), ("heels", "dress-shoes", "shoes")),
)


def resolve_seniorah_category_slugs(name: Any) -> Tuple[str, ...]:
    """Маршрут разделов по названию; () — вид не узнан."""
    text = f" {re.sub(r'[^a-z0-9]+', ' ', normalize_ascii_text(name))} "
    for markers, route in SENIORAH_CATEGORY_ROUTES:
        if any(f" {marker} " in text for marker in markers):
            return route
    return ()


class SeniorahParser(BaseScraper):
    """Парсер seniorah.com по открытому JSON Shopify, без прокси."""

    SUPPORTS_PAGE_CHUNKING = True
    REPORTS_PAGES_PROCESSED = True
    REPORTS_NEXT_START_PAGE = True
    SUPPORTS_CATALOG_STATE = True
    SUPPORTS_LISTING_GUARD = True
    # Меняется при смене состава отпечатка строки — все модели загрузятся заново.
    LISTING_FINGERPRINT_VERSION = 1

    PAGE_SIZE = 250  # максимум Shopify
    # Предохранитель: столько страниц всего каталога (250 × 40 = 10 тыс. товаров).
    MAX_CATALOG_PAGES = 40
    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000
    BRAND = "Seniorah"
    PRODUCT_PATH_RE = re.compile(r"^(?:/collections/[^/]+)?/products/([^/]+?)/?$", re.IGNORECASE)
    COLLECTION_PATH_RE = re.compile(r"^/collections/([^/]+?)/?$", re.IGNORECASE)
    # Строки описания с характеристиками; остальное — реклама магазина.
    FEATURE_LABELS = (
        ("material", ("dis materyal",)),
        ("lining", ("ic materyal", "ic mataryel")),
        ("heel_height", ("topuk yuksekligi", "topuk boyu", "topuk boy")),
        ("insole", ("ic taban",)),
        ("sole", ("taban tip i", "taban tipi", "taban")),
        ("size_advice", ("kalip bilgisi",)),
    )
    MEASURE_MARKERS = ("olcusu", "olculer", "olcu ")

    # Между любыми запросами процесса — не меньше 2,5 с, на 429/503 — повтор с ожиданием
    # (Retry-After или 30/60/120 с), потом понятная остановка.
    # Представляемся честно ботом Mudaroba, без маскировки под браузер: на заголовки
    # «браузера» (случайный User-Agent, Referer google, Sec-Fetch-*) магазин отвечал 429
    # на каждый запрос, а честному боту — 200 (проба на проде 08.11.2026).
    BOT_USER_AGENT = "MudarobaBot/1.0 (+https://mudaroba.com/about-us)"
    MIN_REQUEST_INTERVAL = 2.5
    RATE_LIMIT_STATUSES = frozenset({429, 503})
    RATE_LIMIT_WAITS = (30, 60, 120)
    MAX_RETRY_AFTER = 300
    _request_lock = threading.Lock()
    _last_request_at = 0.0  # общий для процесса: проверки наличия создают парсер на каждую

    def __init__(self, base_url: str = "https://seniorah.com", **kwargs):
        super().__init__(base_url=base_url, delay_range=(2.5, 4), **kwargs)
        self.user_agent = self.BOT_USER_AGENT
        self.default_headers = {
            "User-Agent": self.BOT_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            # Shopify на «br» отвечает brotli: без пакета brotli httpx отдаёт байты
            # вместо JSON (пилот 07.11.2026 — «защита» на каждом запросе).
            "Accept-Encoding": "gzip, deflate",
        }
        # Заменяем заголовки «браузера» базового клиента целиком, а не дополняем.
        self.client.headers.clear()
        self.client.headers.update(self.default_headers)
        self.unmapped: Counter = Counter()
        self._groups: Optional[Dict[str, List[Dict[str, Any]]]] = None

    def get_name(self) -> str:
        return "seniorah"

    def get_supported_domains(self) -> List[str]:
        return ["seniorah.com", "www.seniorah.com"]

    # --- ссылки --------------------------------------------------------------

    @staticmethod
    def _is_own_host(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return not host or host in ("seniorah.com", "www.seniorah.com")

    @classmethod
    def _path(cls, url: str) -> str:
        return unquote(urlparse(url).path or "")

    @classmethod
    def is_product_url(cls, url: str) -> bool:
        return cls._is_own_host(url) and bool(cls.PRODUCT_PATH_RE.match(cls._path(url)))

    @classmethod
    def is_category_url(cls, url: str) -> bool:
        return cls._is_own_host(url) and bool(cls.COLLECTION_PATH_RE.match(cls._path(url)))

    @classmethod
    def supports_page_chunking_for_url(cls, url: str) -> bool:
        return cls.is_category_url(url)

    def _product_url(self, handle: str) -> str:
        return f"{self.base_url}/products/{quote(handle, safe='-')}"

    def _throttle(self) -> None:
        """Пауза с прошлого запроса к магазину в этом процессе: не меньше MIN_REQUEST_INTERVAL
        (или «Минимальной задержки» настроек, если она больше)."""
        interval = max(self.MIN_REQUEST_INTERVAL, float(self.delay_range[0] or 0))
        with self._request_lock:
            wait = SeniorahParser._last_request_at + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            SeniorahParser._last_request_at = time.monotonic()

    @classmethod
    def _retry_after(cls, response: httpx.Response) -> Optional[float]:
        try:
            seconds = float(response.headers.get("Retry-After", ""))
        except ValueError:
            return None
        return min(max(seconds, 0.0), cls.MAX_RETRY_AFTER)

    def _make_request(self, url: str, **kwargs) -> Optional[str]:
        """Запрос каталога: 404 — None; 429/503 — повтор с ожиданием, затем
        ``SourceRateLimitedError``; сбой сети — до ``max_retries`` повторов, как в базе."""
        if not url.startswith(("http://", "https://")):
            url = urljoin(self.base_url, url)
        network_errors = 0
        rate_limited = 0
        while True:
            self._throttle()
            self.logger.info("Запрос к %s", url)
            try:
                response = self.client.get(url, **kwargs)
            except httpx.TransportError:
                network_errors += 1
                if network_errors > self.max_retries:
                    raise
                time.sleep(2 ** network_errors)
                continue
            if response.status_code in self.RATE_LIMIT_STATUSES:
                if rate_limited >= len(self.RATE_LIMIT_WAITS):
                    raise SourceRateLimitedError(
                        source="Seniorah", status_code=response.status_code, url=url, attempts=rate_limited + 1,
                    )
                wait = self._retry_after(response)
                wait = self.RATE_LIMIT_WAITS[rate_limited] if wait is None else wait
                rate_limited += 1
                self.logger.warning(
                    "Seniorah: HTTP %s на %s — жду %s с (повтор %s из %s)",
                    response.status_code, url, wait, rate_limited, len(self.RATE_LIMIT_WAITS),
                )
                time.sleep(wait)
                continue
            raise_for_blocked_status(status_code=response.status_code, url=str(response.url or url), source="Seniorah")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            self.last_response_url = str(response.url or url)
            return response.text

    def _make_offer_request(self, url: str, **kwargs):
        """Проверка наличия — одна попытка (повторы и паузы решает сервис), но не чаще
        MIN_REQUEST_INTERVAL с прошлого запроса к магазину."""
        self._throttle()
        return super()._make_offer_request(url, **kwargs)

    def _fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        """JSON ответа; None — 404. HTML вместо JSON — защита сайта, обход останавливается."""
        text = self._make_request(url)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            self.logger.warning("Seniorah: вместо JSON пришла страница (защита?) на %s", url)
            raise ScraperAccessBlockedError(source="Seniorah", status_code=403, url=url)
        if not isinstance(data, dict):
            raise SeniorahFormatError(f"Seniorah: ответ не объект JSON: {url}")
        return data

    def _products_page(self, path: str, page: int) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}{path}?limit={self.PAGE_SIZE}&page={page}"
        data = self._fetch_json(url)
        if data is None:
            return None
        products = data.get("products")
        if not isinstance(products, list):
            raise SeniorahFormatError(f"Seniorah: в ответе нет products: {url}")
        return [row for row in products if isinstance(row, dict) and row.get("handle")]

    # --- модель из цветов ----------------------------------------------------

    # Слова цвета в конце артикула (``…-C-BLACK``, ``…-S-BEIGE-BROWN``, ``…-MO86-1RF-PLATINUM-BLACK``)
    # и приставки тона перед ними (``…-C-D-RED``, ``…-R-D.RED``, ``…-S-L-TABA``).
    SKU_COLOR_WORDS = frozenset(
        {
            "BLACK", "WHITE", "BEIGE", "BROWN", "CREAM", "CREM", "RED", "KHAKI", "TABA", "VIZON", "YELLOW",
            "PINK", "GOLD", "GOLDEN", "SILVER", "PLATINUM", "COLORS", "FUSHIA", "FUCHSIA", "ORANGE", "BLUE",
            "NAVY", "GREY", "GRAY", "GREEN", "PURPLE", "LILAC", "NUDE", "BORDO", "BURGUNDY", "CAMEL", "MINK",
            "ECRU", "IVORY", "SAND", "LEOPARD", "BRONZE", "COPPER", "TAN",
        }
    )
    SKU_TONE_PREFIXES = frozenset({"D", "L"})

    @staticmethod
    def _sku_prefix(sku: Any) -> str:
        """``P-057-09-C-BROWN/1924…`` → ``P-057-09-C-BROWN``; у одного артикула сайта
        нет «/» перед штрихкодом (``P-057-09-C-BROWN1924214362770``). İ — латинская I."""
        head = str(sku or "").strip().split("/", 1)[0]
        # «T-15-30-TAŞ-BLACK»: турецкие буквы — латиницей, иначе код модели обрезался до «TA».
        head = head.upper().translate(str.maketrans("İŞÇĞÖÜ", "ISCGOU"))
        return re.sub(r"\d{10,}$", "", head).strip("-")

    @classmethod
    def split_sku(cls, sku: Any) -> Tuple[str, str]:
        """Артикул → (код модели, код цвета): ``P-057-09-C-D-RED`` → (``P-057-09-C``, ``D-RED``).

        С конца снимаются слова цвета и тон перед ними. Незнакомое слово цвета — как
        раньше, последняя часть артикула (07.11.2026 на сайте таких нет)."""
        segments = [segment for segment in cls._sku_prefix(sku).split("-") if segment]
        color: List[str] = []
        while len(segments) > 1:
            last = segments[-1]
            if re.sub(r"^[DL]\.", "", last) in cls.SKU_COLOR_WORDS:
                color.insert(0, segments.pop())
            elif color and last in cls.SKU_TONE_PREFIXES:
                color.insert(0, segments.pop())
            else:
                break
        if not color and len(segments) > 1:
            color = [segments.pop()]
        model = re.sub(r"[^A-Z0-9-]", "", "-".join(segments))
        return model, "-".join(color)

    @classmethod
    def model_key(cls, product: Dict[str, Any]) -> str:
        """Код модели — артикул без цвета (``P-057-04-C``); без артикула — сам товар."""
        models = Counter(
            cls.split_sku(variant.get("sku"))[0]
            for variant in product.get("variants") or []
            if isinstance(variant, dict) and variant.get("sku")
        )
        models.pop("", None)
        if models:
            return models.most_common(1)[0][0]
        return f"ID{product.get('id')}"

    def _catalog_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        """Весь каталог, сгруппированный по моделям; загружается один раз на прогон."""
        if self._groups is not None:
            return self._groups
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for page in range(1, self.MAX_CATALOG_PAGES + 1):
            rows = self._products_page("/products.json", page)
            if not rows:
                if page == 1:
                    raise SeniorahFormatError("Seniorah: каталог /products.json пуст")
                break
            for row in rows:
                groups.setdefault(self.model_key(row), []).append(row)
        else:
            self.logger.warning("Seniorah: каталог длиннее %s страниц, хвост не загружен", self.MAX_CATALOG_PAGES)
        self._groups = groups
        return groups

    def _model_rows(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = self._catalog_groups().get(self.model_key(row)) or [row]
        if all(other.get("id") != row.get("id") for other in rows):
            rows = [row, *rows]
        return rows

    # --- категории сайта -----------------------------------------------------

    def parse_categories(self) -> List[Dict[str, Any]]:
        """Разделы сайта (``/collections.json``) с товарами.

        Разделы пересекаются («Yeni Sezon» — новинки всех видов): повтор модели
        не загружает её снова — отпечаток строки уже записан.
        """
        data = self._fetch_json(f"{self.base_url}/collections.json?limit={self.PAGE_SIZE}")
        collections = (data or {}).get("collections")
        if not isinstance(collections, list):
            raise SiteCategoriesError("Seniorah: список разделов /collections.json не загрузился")
        return self._site_categories(
            {
                "name": clean_text(str(row.get("title") or "")),
                "url": f"{self.base_url}/collections/{row['handle']}",
                "external_id": row.get("id"),
            }
            for row in collections
            if isinstance(row, dict) and row.get("handle") and int(row.get("products_count") or 0) > 0
        )

    # --- обход раздела -------------------------------------------------------

    def _fingerprint(self, rows: List[Dict[str, Any]]) -> str:
        """Отпечаток модели: название, цены, наличие размеров и число фото каждого цвета."""
        return listing_fingerprint(
            {
                "v": self.LISTING_FINGERPRINT_VERSION,
                "colors": sorted(
                    [
                        str(row.get("id")),
                        str(row.get("title") or ""),
                        len(row.get("images") or []),
                        [
                            [
                                str(v.get("title") or ""),
                                str(v.get("price") or ""),
                                str(v.get("compare_at_price") or ""),
                                bool(v.get("available")),
                            ]
                            for v in row.get("variants") or []
                            if isinstance(v, dict)
                        ],
                    ]
                    for row in rows
                ),
            }
        )

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
        start_page: int = 1,
    ) -> Iterator[ScrapedProduct]:
        self.has_more_pages = True
        self.pages_processed = 0
        self.next_start_page = max(1, start_page)
        self.stop_reason = ""
        self.catalog_skipped = 0
        self.unmapped = Counter()
        try:
            yield from self._iterate_listing(category_url, max_pages, start_page)
        finally:
            if self.unmapped:
                top = ", ".join(f"{name} {count}" for name, count in self.unmapped.most_common(12))
                report = f"Не разложено (не загружены): {sum(self.unmapped.values())} — {top}."
                self.stop_reason = f"{self.stop_reason} {report}".strip()

    def _collection_path(self, category_url: str) -> str:
        match = self.COLLECTION_PATH_RE.match(self._path(urljoin(self.base_url + "/", category_url)))
        if not match:
            raise CategoryPageNotFoundError(f"Seniorah: это не ссылка раздела: {category_url}")
        return f"/collections/{quote(match.group(1), safe='-')}/products.json"

    def _iterate_listing(self, category_url: str, max_pages: int, start_page: int) -> Iterator[ScrapedProduct]:
        state = getattr(self, "catalog_state", None) or CatalogTraversalState()
        self.catalog_state = state
        result_count = getattr(self, "catalog_result_count", None)
        path = self._collection_path(category_url)
        yielded = 0
        page = max(1, start_page)
        pages_done = 0

        def limit_reached() -> bool:
            return self.max_products is not None and (result_count() if result_count else yielded) >= self.max_products

        while pages_done < max(1, max_pages):
            self.next_start_page = page
            if limit_reached():
                self.has_more_pages = False
                self.stop_reason = "Достигнут лимит товаров."
                return
            rows = self._products_page(path, page)
            if rows is None and page == 1:
                raise CategoryPageNotFoundError(f"Seniorah: раздел не найден: {category_url}")
            identities = [self.model_key(row) for row in rows or []]
            if not rows or state.page_seen([str(row.get("id")) for row in rows], page):
                self.has_more_pages = False
                self.stop_reason = f"Страница {page} пуста или повторяет уже обработанную; раздел закончился."
                break

            guard = getattr(self, "listing_guard", None)
            models = {identity: self._model_rows(row) for identity, row in zip(identities, rows)}
            fingerprints = {identity: self._fingerprint(group) for identity, group in models.items()} if guard else {}
            if guard:
                guard.prefetch(list(fingerprints))
            before = result_count() if result_count else yielded
            settled_on_page = 0
            for identity in dict.fromkeys(identities):
                if state.product_seen(identity):
                    self.catalog_skipped += 1
                    continue
                group = models[identity]
                if not resolve_seniorah_category_slugs(group[0].get("title")):
                    self.unmapped[clean_text(str(group[0].get("title") or ""))[:60]] += 1
                    settled_on_page += 1
                    continue
                fingerprint = fingerprints.get(identity, "")
                if guard and fingerprint and not guard.should_open(identity, fingerprint):
                    settled_on_page += 1
                    continue
                product = self._build_product(group)
                if product and self.validate_product(product):
                    if guard and fingerprint:
                        guard.attach(product, identity, fingerprint)
                    yield product
                    yielded += 1
                    if result_count is None:
                        self.mark_catalog_product(product)
                    if limit_reached():
                        self.has_more_pages = False
                        self.stop_reason = "Достигнут лимит товаров."
                        return

            pages_done += 1
            self.pages_processed = pages_done
            self.next_start_page = page + 1
            after = result_count() if result_count else yielded
            stalled = state.finish_page([str(row.get("id")) for row in rows], page, after > before or settled_on_page > 0)
            if len(rows) < self.PAGE_SIZE or stalled:
                self.has_more_pages = False
                self.stop_reason = (
                    "Обход остановлен: три страницы подряд без новых товаров."
                    if stalled else "Достигнута последняя страница раздела."
                )
                break
            page += 1

    def mark_catalog_product(self, product):
        self.catalog_state.mark_product(product.attributes.get("seniorah_model") or product.external_id)

    # --- карточка ------------------------------------------------------------

    def parse_product_detail(
        self,
        product_url: str,
        *,
        include_sibling_variants: bool = True,
    ) -> Optional[ScrapedProduct]:
        """Модель целиком (цвета — из всего каталога, ещё 2 запроса) или, при
        ``include_sibling_variants=False`` (обновление карточки при открытии), только
        этот цвет — один запрос."""
        match = self.PRODUCT_PATH_RE.match(self._path(product_url))
        if not match:
            return None
        data = self._fetch_json(f"{self._product_url(match.group(1))}.json")
        if data is None:
            return None
        row = data.get("product")
        if not isinstance(row, dict) or not isinstance(row.get("variants"), list):
            raise SeniorahFormatError(f"Seniorah: в карточке нет product/variants: {product_url}")
        if not resolve_seniorah_category_slugs(row.get("title")):
            self.unmapped[clean_text(str(row.get("title") or ""))[:60]] += 1
            self.logger.warning("Seniorah: вид обуви не узнан по названию, товар не загружен: %s", product_url)
            return None
        return self._build_product(self._model_rows(row) if include_sibling_variants else [row])

    # --- проверка наличия ----------------------------------------------------

    @translate_offer_check_errors
    def check_offer(self, offer: OfferCheckContext) -> OfferCheckResult:
        """Один запрос ``/products/<handle>.json`` сохранённого цвета; каталог не грузится.

        404 — Shopify удалил товар (цвет), «не найден». Сменился адрес — Shopify
        переводит старый на новый, сверяется номер товара: другой товар — «не найден»,
        чужой не подставляем. Редирект не на товар — сбой источника. Наличие —
        «есть/нет» по размеру, точный остаток не храним.
        """
        match = self.PRODUCT_PATH_RE.match(self._path(offer.canonical_url))
        if not match:
            raise OfferNotFound(offer.canonical_url)
        url = f"{self._product_url(match.group(1))}.json"
        try:
            text, final_url = self._make_offer_request(url, include_final_url=True)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise OfferNotFound(offer.canonical_url) from exc
            raise
        if not self.PRODUCT_PATH_RE.match(self._path(final_url).removesuffix(".json")):
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                f"Seniorah: redirect away from product page to {final_url}",
                retryable=True,
            )
        try:
            data = json.loads(text)
        except ValueError:
            raise ScraperAccessBlockedError(source="Seniorah", status_code=403, url=url)
        row = data.get("product") if isinstance(data, dict) else None
        if not isinstance(row, dict) or not isinstance(row.get("variants"), list):
            raise MalformedOfferResponse()
        variant = self._build_color_variant(row, sort_order=0)
        if offer.variant_key and variant["external_id"] != offer.variant_key:
            raise OfferNotFound(offer.canonical_url)
        scraped = ScrapedProduct(
            name=clean_text(str(row.get("title") or "")),
            price=variant["price"],
            currency="TRY",
            url=variant["external_url"],
            external_id=offer.external_product_id,
            sku=variant["sku"],
            is_available=variant["is_available"],
            stock_quantity=variant["stock_quantity"],
            attributes={"fashion_variants": [variant]},
            source=self.get_name(),
        )
        return result_from_scraped_product(offer, scraped, exact_stock=False)

    def _build_product(self, rows: List[Dict[str, Any]]) -> Optional[ScrapedProduct]:
        first = rows[0]
        route = resolve_seniorah_category_slugs(first.get("title"))
        variants = [self._build_color_variant(row, index) for index, row in enumerate(rows)]
        variants = [variant for variant in variants if variant["sizes"]]
        if not variants:
            return None
        self._distinct_colors(variants)
        primary = next((v for v in variants if v["is_available"]), variants[0])
        all_sizes: List[str] = []
        for variant in variants:
            for size in variant["sizes"]:
                if size["size"] not in all_sizes:
                    all_sizes.append(size["size"])
        model = self.model_key(first)
        is_available = any(v["is_available"] for v in variants)
        features = self._features(first.get("body_html"))
        attributes: Dict[str, Any] = {
            "color": primary["color"],
            "gender": "women",
            "sizes": all_sizes,
            "seniorah_model": model,
            "seniorah_category_slugs": list(route),
            "seniorah_color_ids": [v["sku"] for v in variants],
            "fashion_variants": variants,
            "variant_group_id": f"seniorah-{model}",
            **{key: value for key, value in features.items() if key != "lines"},
        }
        return ScrapedProduct(
            name=self._model_name(rows),
            description="\n".join(features["lines"]),
            price=primary["price"],
            old_price=primary["old_price"],
            currency="TRY",
            url=primary["external_url"],
            images=primary["images"],
            category=route[0] if route else "",
            brand=self.BRAND,
            external_id=f"seniorah-{model}",
            sku=model,
            is_available=is_available,
            stock_quantity=self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            attributes=attributes,
            source=self.get_name(),
        )

    def _build_color_variant(self, row: Dict[str, Any], sort_order: int) -> Dict[str, Any]:
        sizes = []
        for index, variant in enumerate(v for v in row.get("variants") or [] if isinstance(v, dict)):
            size = clean_text(str(variant.get("option1") or variant.get("title") or ""))
            if not size:
                continue
            available = bool(variant.get("available"))
            sizes.append(
                {
                    "size": size,
                    "is_available": available,
                    "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if available else 0,
                    "sort_order": index,
                    "sku": str(variant.get("sku") or "")[:100],
                    "price": self._price(variant.get("price")),
                    "old_price": self._price(variant.get("compare_at_price")),
                }
            )
        priced = next((s for s in sizes if s["is_available"] and s["price"]), None) or next(
            (s for s in sizes if s["price"]), {"price": None, "old_price": None}
        )
        price = priced["price"]
        old_price = priced["old_price"] if price and priced["old_price"] and priced["old_price"] > price else None
        for size in sizes:
            size.pop("price", None)
            size.pop("old_price", None)
        is_available = any(size["is_available"] for size in sizes)
        color = self._color_name(row)
        name = clean_text(str(row.get("title") or ""))
        return {
            "external_id": f"seniorah-variant-{row.get('id')}",
            "sort_order": sort_order,
            "color": color,
            "display_name": clean_text(f"{name} - {color}".strip(" -")),
            "price": price,
            "old_price": old_price,
            "currency": "TRY",
            "external_url": self._product_url(str(row.get("handle") or "")),
            "images": self._images(row),
            "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            "is_available": is_available,
            "sizes": sizes,
            "sku": str(row.get("id") or ""),
            "mpn": self._sku_prefix(next((v.get("sku") for v in row.get("variants") or [] if v.get("sku")), ""))[:100],
        }

    @staticmethod
    def _images(row: Dict[str, Any]) -> List[str]:
        images: List[str] = []
        for image in sorted(
            (i for i in row.get("images") or [] if isinstance(i, dict) and i.get("src")),
            key=lambda i: int(i.get("position") or 0),
        ):
            url = str(image["src"]).strip()
            if url not in images:
                images.append(url)
        return images

    @staticmethod
    def _price(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            price = round(float(str(value).replace(",", ".")), 2)
        except (TypeError, ValueError):
            return None
        return price if price > 0 else None

    # --- цвет и название -----------------------------------------------------

    TONE_WORDS = frozenset({"acik", "koyu"})

    @classmethod
    def _is_color_token(cls, token: str) -> bool:
        """«Siyah», «Bej-Kahve», «Açık-Taba» — слово цвета названия."""
        parts = [part for part in re.split(r"[/-]", token) if part]
        colors = [part for part in parts if translate_turkish_color(part, "en")]
        return bool(colors) and all(part in colors or normalize_ascii_text(part) in cls.TONE_WORDS for part in parts)

    @classmethod
    def _title_color_index(cls, title: str) -> Optional[int]:
        tokens = clean_text(title).split()
        return next((index for index, token in enumerate(tokens) if cls._is_color_token(token)), None)

    @classmethod
    def _color_name(cls, row: Dict[str, Any]) -> str:
        """Цвет — первое слово-цвет названия («Siyah», «Bej-Kahve»); без него — код цвета артикула."""
        title = clean_text(str(row.get("title") or ""))
        index = cls._title_color_index(title)
        if index is not None:
            return title.split()[index]
        sku = next((v.get("sku") for v in row.get("variants") or [] if isinstance(v, dict) and v.get("sku")), "")
        return cls._sku_color_tr(cls.split_sku(sku)[1])

    # Код цвета артикула → турецкое слово словаря («GOLDEN» — «Altın»): английские слова в
    # общий словарь не добавляются, SuperStep по нему вырезает турецкие слова из расцветок.
    SKU_COLOR_TR = {
        "BLACK": "Siyah", "WHITE": "Beyaz", "BEIGE": "Bej", "BROWN": "Kahverengi", "CREAM": "Krem",
        "CREM": "Krem", "RED": "Kırmızı", "KHAKI": "Haki", "TABA": "Taba", "VIZON": "Vizon",
        "YELLOW": "Sarı", "PINK": "Pembe", "GOLD": "Altın", "GOLDEN": "Altın", "SILVER": "Gümüş",
        "PLATINUM": "Platin", "COLORS": "Renkli", "FUSHIA": "Fuşya", "FUCHSIA": "Fuşya",
        "ORANGE": "Turuncu", "BLUE": "Mavi", "NAVY": "Lacivert", "GREY": "Gri", "GRAY": "Gri",
        "GREEN": "Yeşil", "PURPLE": "Mor", "BORDO": "Bordo", "BURGUNDY": "Bordo",
    }
    SKU_TONE_TR = {"D": "Koyu", "L": "Açık"}

    @classmethod
    def _sku_color_tr(cls, code: str) -> str:
        """«D-RED» / «D.RED» → «Bordo», «L-TABA» → «Açık-Taba», «BLACK-PLATINUM» → «Siyah-Platin»."""
        parts = [part for part in re.split(r"[-.]", code) if part]
        words: List[str] = []
        tone = ""
        for part in parts:
            if part in cls.SKU_TONE_TR:
                tone = part
                continue
            word = cls.SKU_COLOR_TR.get(part, part.capitalize())
            if tone == "D" and part == "RED":
                word, tone = "Bordo", ""
            if tone:
                words.append(cls.SKU_TONE_TR[tone])
                tone = ""
            words.append(word)
        return "-".join(words)

    TONE_EN = {"acik": "Light", "koyu": "Dark"}

    @classmethod
    def _distinct_colors(cls, variants: List[Dict[str, Any]]) -> None:
        """Цвета модели, которые на сайте переводятся одинаково («Siyah», «Siyah-Bej» и
        «Siyah-Gri» — все «Черный»), получают уточнение через « · », как у SuperStep:
        основа — первый цвет составного, уточнение — все части по-английски
        («Siyah · Black-Beige» → «Черный · Black-Beige»)."""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for variant in variants:
            groups.setdefault(translate_turkish_color(variant["color"], "ru") or variant["color"], []).append(variant)
        for group in groups.values():
            if len(group) < 2:
                continue
            for variant in group:
                parts = [part for part in re.split(r"[-/]", variant["color"]) if part]
                colors = [part for part in parts if normalize_ascii_text(part) not in cls.TONE_EN]
                english = "-".join(
                    cls.TONE_EN.get(normalize_ascii_text(part)) or translate_turkish_color(part, "en") or part
                    for part in parts
                )
                base = colors[0] if colors else variant["color"]
                variant["color"] = f"{base}{COLOR_DETAIL_SEPARATOR}{english}"[:50]
            details = [variant["color"] for variant in group]
            for variant in group:
                if details.count(variant["color"]) > 1:  # два одинаковых цвета — по коду артикула
                    variant["color"] = f"{variant['color']} {variant['mpn'].rpartition('-')[2]}"[:50]
        for variant in variants:
            name = variant["display_name"].rpartition(" - ")[0] or variant["display_name"]
            variant["display_name"] = clean_text(f"{name} - {variant['color']}")

    @classmethod
    def _model_name(cls, rows: List[Dict[str, Any]]) -> str:
        """Название модели без цвета: «Kitten Siyah Cilt … Ayakkabı» → «Kitten Cilt … Ayakkabı».

        Берётся название цвета, где слово цвета узнано. Цвет убирается и у модели одного
        цвета: он есть у варианта, а составной («Mavi-Taba») правила иначе брали в модель."""
        titles = [clean_text(str(row.get("title") or "")) for row in rows]
        for title in titles:
            index = cls._title_color_index(title)
            if index is not None:
                tokens = title.split()
                return " ".join(tokens[:index] + tokens[index + 1:]) or title
        return titles[0]

    # --- описание ------------------------------------------------------------

    @staticmethod
    def _is_size_advice(line: str) -> bool:
        """«Tam kalıptır kendi numaranızı tercih ediniz.», «Tamkalıptır.» — но не реклама
        «… kalıplarıyla …» в длинном абзаце."""
        text = normalize_ascii_text(line)
        return "kalip" in text and ("numara" in text or len(text) <= 40) and len(text) <= 120

    @classmethod
    def _features(cls, html: Any) -> Dict[str, Any]:
        """Строки характеристик из описания; рекламные абзацы магазина не берутся."""
        text = re.sub(r"<(?:br|/p|/li|/div|/h\d|/tr)[^>]*>", "\n", str(html or ""), flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").replace("\xa0", " ")
        result: Dict[str, Any] = {"lines": []}
        for raw in text.split("\n"):
            line = clean_text(raw)
            if not line:
                continue
            label, colon, value = line.partition(":")
            label_key = normalize_ascii_text(label).strip()
            value = clean_text(value)
            if colon and value:
                key = next(
                    (key for key, labels in cls.FEATURE_LABELS if label_key in labels),
                    None,
                )
                if key:
                    # «Cilt - Süet», «Taş-Saten» → «Cilt/Süet»: части материала, как у FLO
                    result.setdefault(key, re.sub(r"\s*-\s*", "/", value) if key in ("material", "lining") else value)
                    result["lines"].append(f"{clean_text(label)}: {value}")
                    continue
                if any(marker in f"{label_key} " for marker in cls.MEASURE_MARKERS) or (
                    label_key == "not" and "olcu" in normalize_ascii_text(value)
                ):
                    result["lines"].append(f"{clean_text(label)}: {value}")
                    continue
            elif cls._is_size_advice(line):
                result.setdefault("size_advice", line)
                result["lines"].append(line)
        return result
