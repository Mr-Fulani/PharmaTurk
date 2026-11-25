"""Парсер Aloparça (aloparca.com) — автозапчасти: цена, наличие, OEM-номера, применимость.

Сайт на PHP/Livewire, готового API нет, но в HTML карточки лежит снимок данных
компонента ``product-detail`` (``wire:snapshot``): характеристики (``criteria``),
применимость (``compatibleVehicles``: марка → строки «модель, кузов с годами,
двигатель с мощностью и годами») и OEM-номера с маркой (``oems``). Бренд, артикул
(«Stok Kodu»), цена, наличие и фото — в вёрстке блока товара; раздел — в снимке
компонента ``breadcrumb``.

Обход — по карте сайта: ``/sitemap.xml`` → ``/sitemaps/products-N.xml`` по 20 000
адресов ``/product/<бренд>-<артикул>-<название>`` с датой изменения. «Раздел» парсера —
файл карты сайта, выборку сужают параметры ссылки: ``?brand=bosch`` (бренд — начало
адреса карточки) и ``?q=fren-diski`` (слова в адресе карточки). Каталог ~340 тыс.
карточек: целиком не обходится, объём задаёт «Макс. товаров» задачи.

Вежливый режим: один поток, не чаще запроса в 2,5 с, честное имя робота.
403 или проверка Cloudflare — остановка с понятной ошибкой, без повторов.

Серверу прода сайт закрыт (дата-центр), поэтому с 25.11.2026 парсер ходит через
обычный прокси, если в настройке стоит «Использовать прокси» (решение владельца).
Сервис, решающий проверки (Web Unlocker), не используется; проверка — по-прежнему стоп.

Решение владельца 24.11.2026 и риски (условия сайта запрещают копирование) —
reports/auto-parts-sources-audit-2026-11-24.md.
"""

import html as html_lib
import json
import re
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

from apps.catalog.utils.part_numbers import normalize_part_number
from apps.http_errors import SourceRateLimitedError, raise_for_blocked_status

from ..base.listing_snapshot import listing_fingerprint
from ..base.offers import (
    MalformedOfferResponse,
    OfferCheckContext,
    OfferCheckResult,
    OfferNotFound,
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


class AloparcaFormatError(RuntimeError):
    """В ответе нет ожидаемого блока — сайт сменил вёрстку, а не «товара нет»."""


AUTO_PARTS_ROOT = "auto-parts"

# Раздел Aloparça (первый уровень адреса /yedek-parcalar/kategori/<раздел>/<подраздел>)
# → наш раздел второго уровня. Чего у нас нет (масла и жидкости) — в корень «Автозапчасти».
ALOPARCA_SECTION_ROUTES: Dict[str, str] = {
    "atesleme-sistemi": "electrical-system",
    "aydinlatma": "lighting",
    "debriyaj": "transmission",
    "direksiyon": "steering-system",
    "dis-kaporta-aksami": "body-parts",
    "elektrik": "electrical-system",
    "filtreler": "filters",
    "fren": "brake-system",
    "motor": "engine-parts",
    "panjur-ve-panel": "body-parts",
    "sanziman": "transmission",
    "sogutma": "cooling-system",
    "suspansiyon": "suspension",
    "tampon-ve-aksami": "body-parts",
    "triger-zincir-ve-rulman": "engine-parts",
    "yakit-sistemi": "engine-parts",
}

# Подраздел Aloparça → наш раздел третьего уровня (и его родитель, если он не тот,
# что у раздела Aloparça: «Rot Başı» лежит у них в подвеске, у нас — в рулевом).
ALOPARCA_SUBSECTION_ROUTES: Dict[str, Tuple[str, ...]] = {
    # тормоза
    "fren-balatasi": ("brake-pads",),
    "el-fren-balatasi": ("brake-pads",),
    "fren-pabuclu-balata": ("brake-pads",),
    "fren-disk": ("brake-discs",),
    "fren-kaliper": ("brake-calipers",),
    "fren-hortumu": ("brake-hoses",),
    "fren-ana-merkez": ("brake-master-cylinder",),
    "abs-sensoru": ("sensors", "electrical-system"),
    # подвеска и рулевое
    "amortisor": ("shock-absorbers",),
    "helezon-yayi": ("springs",),
    "salincak": ("control-arms",),
    "viraj-demiri": ("stabilizer-bars",),
    "viraj-demir-aski-rotu": ("stabilizer-bars",),
    "salincak-burcu": ("bushings",),
    "viraj-demir-lastigi": ("bushings",),
    "rot-basi": ("tie-rod-ends", "steering-system"),
    "rot-mili": ("tie-rods", "steering-system"),
    "aks-kafasi": ("cv-joints", "transmission"),
    "direksiyon-kutusu": ("steering-rack",),
    "direksiyon-pompasi": ("power-steering-pump",),
    # трансмиссия
    "debriyaj-seti": ("clutch-kits",),
    "saft-kardan-mili": ("drive-shaft",),
    # электрика и датчики
    "alternator": ("alternators",),
    "mars-dinamosu": ("starters",),
    "sigorta": ("fuses",),
    "park-sensoru": ("sensors",),
    "dis-hava-sicaklik-sensoru": ("sensors",),
    "krank-sensoru": ("sensors", "electrical-system"),
    "map-sensoru": ("sensors", "electrical-system"),
    "nox-sensoru": ("sensors", "electrical-system"),
    "oksijen-lambda-sensoru": ("sensors", "electrical-system"),
    "vuruntu-sensoru": ("sensors", "electrical-system"),
    "eksantrik-devir-sensoru": ("sensors", "electrical-system"),
    "kilometre-hiz-sensoru": ("sensors", "electrical-system"),
    "lastik-basinc-sensoru": ("sensors", "electrical-system"),
    "egzoz-sicaklik-sensoru": ("sensors", "electrical-system"),
    # охлаждение
    "su-radyatoru": ("radiators",),
    "devirdaim-su-pompasi": ("water-pumps",),
    "termostat": ("thermostats",),
    "sogutma-fani-fan-termik": ("cooling-fans",),
    "radyator-fan-ve-motoru": ("cooling-fans",),
    # кузов и свет
    "tampon": ("bumpers",),
    "dikiz-aynasi": ("mirrors", "body-parts"),
    "ayna-cami": ("mirrors", "body-parts"),
    "ayna-kapagi": ("mirrors", "body-parts"),
    "far": ("headlights",),
    "stop-lambasi": ("tail-lights",),
    "sis-fari": ("fog-lights",),
    "ampul": ("bulbs",),
    # фильтры
    "yag-filtresi": ("oil-filters",),
    "hava-filtresi": ("air-filters",),
    "yakit-filtresi": ("fuel-filters",),
    "polen-filtresi": ("cabin-filters",),
    # двигатель
    "piston-segman": ("piston-rings",),
    "segman": ("piston-rings",),
    "krank": ("crankshaft",),
    "eksantrik-mili": ("camshaft",),
    "supap": ("valves",),
    "silindir-kapak-contasi": ("engine-gaskets",),
    "karter-contasi": ("engine-gaskets",),
    "cesitli-conta": ("engine-gaskets",),
    "conta-ve-kece": ("engine-gaskets",),
    "takim-conta": ("engine-gaskets",),
    "manifolt-conta": ("engine-gaskets",),
    "eksantrik-kapak-contasi": ("engine-gaskets",),
    "ust-kapak-contasi-kulbutor": ("engine-gaskets",),
    "turbo-sarj": ("turbochargers",),
}


def resolve_aloparca_category_slugs(section: str, subsection: str = "") -> Tuple[str, ...]:
    """Маршрут наших разделов от точного к корню; корень «Автозапчасти» есть всегда."""
    route: List[str] = list(ALOPARCA_SUBSECTION_ROUTES.get(subsection, ()))
    parent = ALOPARCA_SECTION_ROUTES.get(section)
    if parent and len(route) < 2:
        route.append(parent)
    route.append(AUTO_PARTS_ROOT)
    return tuple(route)


_DATE = r"(?:\d{2}\.\d{4}|\.\.\.)"
_PERIOD_RE = re.compile(rf"\(\s*({_DATE})\s*-\s*({_DATE})\s*\)\s*$")
_ENGINE_RE = re.compile(
    rf"^(?P<engine>.*?)\s*\(\s*(?P<kw>\d+(?:[.,]\d+)?)\s*kW\s*/\s*(?P<hp>\d+(?:[.,]\d+)?)\s*PS\s*\)"
    rf"\s*\(\s*(?P<start>{_DATE})\s*-\s*(?P<end>{_DATE})\s*\)\s*$"
)


def _month_year(value: str) -> Tuple[Optional[int], Optional[int]]:
    """«03.2005» → (3, 2005); «...» (нет даты) → (None, None)."""
    if not value or value == "...":
        return None, None
    month, year = value.split(".")
    return int(month), int(year)


def parse_fitment_row(make: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Строка применимости источника → поля ``AutoPartFitment``.

    ``model_name`` — кузов с годами («Passat B6 (3C2) (03.2005 - 07.2010)»),
    ``vehicle_name`` — двигатель («2.0 TDI (103 kW / 140 PS) (03.2005 - 05.2009)»).
    Годы строки — годы двигателя, без них — годы кузова. Строка двигателя, которую не
    удалось разобрать, целиком уходит в примечание (``unparsed`` — для отчёта прогона).
    """
    body = clean_text(str(row.get("model_name") or ""))
    vehicle = clean_text(str(row.get("vehicle_name") or ""))
    result: Dict[str, Any] = {
        # «CITROЁN» у источника написан с кириллической «Ё».
        "make": clean_text(str(make or "")).replace("Ё", "Ë")[:64],
        "model": clean_text(str(row.get("label") or ""))[:64],
        "generation": body[:160],
        "year_from": None,
        "month_from": None,
        "year_to": None,
        "month_to": None,
        "engine": "",
        "power_kw": None,
        "power_hp": None,
        "note": "",
        "unparsed": False,
    }
    start = end = ""
    engine = _ENGINE_RE.match(vehicle)
    if engine:
        result["engine"] = engine.group("engine").strip()[:128]
        result["power_kw"] = round(float(engine.group("kw").replace(",", ".")))
        result["power_hp"] = round(float(engine.group("hp").replace(",", ".")))
        start, end = engine.group("start"), engine.group("end")
    else:
        result["unparsed"] = True
        result["note"] = vehicle[:255] or body[:255]
    if not start or start == "...":
        period = _PERIOD_RE.search(body)
        if period:
            start, end = period.group(1), period.group(2)
    result["month_from"], result["year_from"] = _month_year(start)
    result["month_to"], result["year_to"] = _month_year(end)
    return result


def unwrap_livewire(value: Any) -> Any:
    """Снимок Livewire → обычные списки и словари.

    Livewire хранит составные значения парой ``[данные, {"s": "<тип>", …}]``; модель из
    базы — ``[null, {"s": "mdl", "key": <номер>}]`` (остаётся только номер).
    """
    if isinstance(value, list):
        if len(value) == 2 and isinstance(value[1], dict) and "s" in value[1]:
            if value[1]["s"] == "mdl":
                return {"key": value[1].get("key")}
            return unwrap_livewire(value[0])
        return [unwrap_livewire(item) for item in value]
    if isinstance(value, dict):
        return {key: unwrap_livewire(item) for key, item in value.items()}
    return value


class AloparcaParser(BaseScraper):
    """Парсер aloparca.com: карта сайта → карточка, один поток, без прокси."""

    SUPPORTS_PAGE_CHUNKING = True
    REPORTS_PAGES_PROCESSED = True
    REPORTS_NEXT_START_PAGE = True
    SUPPORTS_LISTING_GUARD = True
    # Меняется при смене состава отпечатка строки — все карточки откроются заново.
    LISTING_FINGERPRINT_VERSION = 1

    # Карточек на «страницу» обхода: 20 карточек ≈ 1 минута при паузе 2,5 с.
    PAGE_SIZE = 20
    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000
    IMAGE_BASE = "https://googlecdn.aloparca.com/yedek-parca-resimleri/"
    PRODUCT_PATH_RE = re.compile(r"^/product/([^/?#]+)/?$", re.IGNORECASE)
    SITEMAP_PATH_RE = re.compile(r"^/sitemaps/(products-\d+)\.xml$", re.IGNORECASE)
    # Столько карточек подряд без блока данных — вёрстка сменилась, обход останавливается.
    MAX_FORMAT_ERRORS_IN_ROW = 5

    # Честное имя робота: сайт отвечает ему так же, как браузеру (проверено 24.11.2026),
    # robots.txt разрешает всем, кроме роботов обучения ИИ.
    BOT_USER_AGENT = "MudarobaBot/1.0 (+https://mudaroba.com/about-us)"
    MIN_REQUEST_INTERVAL = 2.5
    RATE_LIMIT_STATUSES = frozenset({429, 503})
    RATE_LIMIT_WAITS = (60, 180)
    # Страница проверки Cloudflare вместо товара: её не обходим, а останавливаемся.
    CHALLENGE_MARKERS = ("challenge-platform", "cf-chl-", "Just a moment...")
    # Фото (googlecdn.aloparca.com) серверу закрыты так же, как сайт: при включённом
    # прокси конвейер медиа качает их через него и с этим же именем робота.
    MEDIA_PROXY_USER_AGENT = BOT_USER_AGENT
    _request_lock = threading.Lock()
    _last_request_at = 0.0  # общий для процесса

    def __init__(self, base_url: str = "https://aloparca.com", **kwargs):
        super().__init__(base_url=base_url, delay_range=(2.5, 4), **kwargs)
        self.user_agent = self.BOT_USER_AGENT
        self.default_headers = {
            "User-Agent": self.BOT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        # Заголовки «браузера» базового клиента заменяются целиком.
        self.client.headers.clear()
        self.client.headers.update(self.default_headers)
        self.item_errors = 0
        self.stop_reason = ""
        self.next_start_page = 1
        self.unparsed_fitments = 0

    def get_name(self) -> str:
        return "aloparca"

    def get_supported_domains(self) -> List[str]:
        return ["aloparca.com", "www.aloparca.com"]

    # --- ссылки --------------------------------------------------------------

    @staticmethod
    def _is_own_host(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return not host or host in ("aloparca.com", "www.aloparca.com")

    @classmethod
    def is_product_url(cls, url: str) -> bool:
        return cls._is_own_host(url) and bool(cls.PRODUCT_PATH_RE.match(urlparse(url).path or ""))

    @classmethod
    def is_category_url(cls, url: str) -> bool:
        return cls._is_own_host(url) and bool(cls.SITEMAP_PATH_RE.match(urlparse(url).path or ""))

    @classmethod
    def supports_page_chunking_for_url(cls, url: str) -> bool:
        return cls.is_category_url(url)

    @classmethod
    def _slug(cls, url: str) -> str:
        match = cls.PRODUCT_PATH_RE.match(unquote(urlparse(url).path or ""))
        return match.group(1).lower() if match else ""

    # --- запросы -------------------------------------------------------------

    def _throttle(self) -> None:
        """Не чаще запроса в MIN_REQUEST_INTERVAL (или «Минимальной задержки» настроек, если она больше)."""
        interval = max(self.MIN_REQUEST_INTERVAL, float(self.delay_range[0] or 0))
        with self._request_lock:
            wait = AloparcaParser._last_request_at + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            AloparcaParser._last_request_at = time.monotonic()

    def _make_request(self, url: str, patient: bool = True, **kwargs) -> Optional[str]:
        """Страница сайта; None — 404/410 (карточку сняли).

        403 и страница проверки Cloudflare — ``ScraperAccessBlockedError`` сразу, без
        повторов. 429/503 — два ожидания, затем ``SourceRateLimitedError``;
        ``patient=False`` (проверка при открытии карточки) — без ожиданий.
        """
        if not url.startswith(("http://", "https://")):
            url = urljoin(self.base_url + "/", url)
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
            challenged = response.headers.get("cf-mitigated", "").lower() == "challenge" or (
                response.status_code in (403, 503) and any(m in response.text for m in self.CHALLENGE_MARKERS)
            )
            if challenged:
                raise ScraperAccessBlockedError(
                    f"Aloparça показал проверку Cloudflare (HTTP {response.status_code}) — обход остановлен, "
                    "защиту не обходим. Повторите позже или уменьшите объём.",
                    source="Aloparça", status_code=response.status_code, url=url,
                )
            raise_for_blocked_status(status_code=response.status_code, url=str(response.url or url), source="Aloparça")
            if response.status_code in self.RATE_LIMIT_STATUSES:
                if not patient or rate_limited >= len(self.RATE_LIMIT_WAITS):
                    raise SourceRateLimitedError(
                        source="Aloparça", status_code=response.status_code, url=url, attempts=rate_limited + 1,
                    )
                wait = self.RATE_LIMIT_WAITS[rate_limited]
                rate_limited += 1
                self.logger.warning("Aloparça: HTTP %s на %s — жду %s с", response.status_code, url, wait)
                time.sleep(wait)
                continue
            if response.status_code in (404, 410):
                return None
            response.raise_for_status()
            self.last_response_url = str(response.url or url)
            return response.text

    # --- карта сайта ---------------------------------------------------------

    _SITEMAP_ROW_RE = re.compile(r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]*)</lastmod>)?", re.IGNORECASE)

    def parse_categories(self) -> List[Dict[str, Any]]:
        """Файлы карты сайта с карточками (``products-N.xml``) — «разделы» режима «Весь сайт»."""
        text = self._make_request(f"{self.base_url}/sitemap.xml")
        files = re.findall(r"<loc>\s*([^<\s]+/sitemaps/products-\d+\.xml)\s*</loc>", text or "")
        if not files:
            raise SiteCategoriesError("Aloparça: в /sitemap.xml нет файлов products-N.xml")
        return self._site_categories(
            {"name": f"Карта сайта: {url.rsplit('/', 1)[-1]}", "url": url, "external_id": url.rsplit("/", 1)[-1]}
            for url in files
        )

    @staticmethod
    def _filters(category_url: str) -> Tuple[str, List[str]]:
        """Выборка из ссылки: ``?brand=bosch`` и ``?q=fren-diski`` (несколько слов — через запятую или пробел)."""
        query = parse_qs(urlparse(category_url).query)
        brand = "-".join(re.findall(r"[a-z0-9]+", (query.get("brand") or [""])[0].lower()))
        words = [word for value in query.get("q") or [] for word in re.split(r"[,\s]+", value.lower()) if word]
        return brand, words

    def _sitemap_rows(self, category_url: str) -> List[Tuple[str, str]]:
        """Адреса карточек файла карты сайта с датой изменения, с учётом выборки ссылки."""
        absolute = urljoin(self.base_url + "/", category_url)
        match = self.SITEMAP_PATH_RE.match(urlparse(absolute).path or "")
        if not match:
            raise CategoryPageNotFoundError(
                f"Aloparça: это не ссылка файла карты сайта (нужна …/sitemaps/products-N.xml): {category_url}"
            )
        text = self._make_request(f"{self.base_url}/sitemaps/{match.group(1)}.xml")
        if text is None:
            raise CategoryPageNotFoundError(f"Aloparça: файла карты сайта нет: {category_url}")
        rows = [
            (html_lib.unescape(url.strip()), (lastmod or "").strip())
            for url, lastmod in self._SITEMAP_ROW_RE.findall(text)
            if self.is_product_url(url.strip())
        ]
        if not rows:
            raise AloparcaFormatError(f"Aloparça: в файле карты сайта нет адресов карточек: {category_url}")
        brand, words = self._filters(category_url)
        if brand:
            rows = [row for row in rows if self._slug(row[0]).startswith(f"{brand}-")]
        if words:
            rows = [row for row in rows if all(word in self._slug(row[0]) for word in words)]
        return rows

    def _fingerprint(self, lastmod: str) -> str:
        return listing_fingerprint({"v": self.LISTING_FINGERPRINT_VERSION, "lastmod": lastmod})

    def parse_product_list(
        self,
        category_url: str,
        max_pages: int = 10,
        start_page: int = 1,
    ) -> Iterator[ScrapedProduct]:
        """Карточки файла карты сайта «страницами» по PAGE_SIZE адресов.

        Карточка открывается, если её нет в базе или дата изменения в карте сайта другая
        (``ListingGuard``). Снятая карточка (404/410) пропускается.
        """
        self.has_more_pages = True
        self.pages_processed = 0
        self.item_errors = 0
        self.unparsed_fitments = 0
        self.stop_reason = ""
        page = max(1, start_page)
        self.next_start_page = page
        rows = self._sitemap_rows(category_url)
        guard = getattr(self, "listing_guard", None)
        yielded = 0
        format_errors_in_row = 0
        try:
            for _ in range(max(1, max_pages)):
                chunk = rows[(page - 1) * self.PAGE_SIZE: page * self.PAGE_SIZE]
                if not chunk:
                    self.has_more_pages = False
                    self.stop_reason = (
                        "По выборке ссылки (brand, q) в этом файле карты сайта карточек нет."
                        if not rows else "Файл карты сайта пройден до конца."
                    )
                    return
                self.next_start_page = page
                if guard:
                    guard.prefetch([self._slug(url) for url, _ in chunk])
                for url, lastmod in chunk:
                    if self.max_products is not None and yielded >= self.max_products:
                        self.has_more_pages = False
                        self.stop_reason = "Достигнут лимит товаров."
                        return
                    identity = self._slug(url)
                    fingerprint = self._fingerprint(lastmod) if lastmod else ""
                    if guard and fingerprint and not guard.should_open(identity, fingerprint):
                        continue
                    try:
                        product = self.parse_product_detail(url)
                    except AloparcaFormatError as exc:
                        self.item_errors += 1
                        format_errors_in_row += 1
                        self.logger.warning("Aloparça: карточка не разобрана: %s", exc)
                        if format_errors_in_row >= self.MAX_FORMAT_ERRORS_IN_ROW:
                            raise
                        continue
                    format_errors_in_row = 0
                    if product is None or not self.validate_product(product):
                        continue
                    if guard and fingerprint:
                        guard.attach(product, identity, fingerprint)
                    yield product
                    yielded += 1
                self.pages_processed += 1
                page += 1
                self.next_start_page = page
            if (page - 1) * self.PAGE_SIZE >= len(rows):
                self.has_more_pages = False
                self.stop_reason = "Файл карты сайта пройден до конца."
        finally:
            if self.unparsed_fitments:
                self.stop_reason = (
                    f"{self.stop_reason} Строк применимости не разобрано по полям "
                    f"(сохранены в примечании): {self.unparsed_fitments}."
                ).strip()

    # --- карточка ------------------------------------------------------------

    _SNAPSHOT_RE = re.compile(r'wire:snapshot="([^"]*)"')

    @classmethod
    def _snapshots(cls, page: str) -> Dict[str, Tuple[int, Dict[str, Any]]]:
        """Снимки компонентов Livewire страницы: имя → (позиция в HTML, данные)."""
        found: Dict[str, Tuple[int, Dict[str, Any]]] = {}
        for match in cls._SNAPSHOT_RE.finditer(page):
            raw = match.group(1)
            if "product-detail" not in raw and "breadcrumb" not in raw:
                continue  # меню и корзина: сотни килобайт, которые не нужны
            try:
                snapshot = json.loads(html_lib.unescape(raw))
            except ValueError:
                continue
            name = str((snapshot.get("memo") or {}).get("name") or "")
            if name in ("product-detail", "breadcrumb") and name not in found:
                found[name] = (match.start(), unwrap_livewire(snapshot.get("data") or {}))
        return found

    @staticmethod
    def _price(text: str) -> Optional[float]:
        """«8.291,87 TL» → 8291.87; 0 — цена не опубликована."""
        match = re.search(r"(\d[\d.]*)(?:,(\d{1,2}))?\s*TL", text)
        if not match:
            return None
        price = float(f"{match.group(1).replace('.', '')}.{match.group(2) or '0'}")
        return round(price, 2) if price > 0 else None

    @staticmethod
    def _text(pattern: str, block: str) -> str:
        match = re.search(pattern, block, re.IGNORECASE | re.DOTALL)
        return clean_text(html_lib.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))) if match else ""

    @staticmethod
    def _rows(value: Any) -> List[Any]:
        """Список Livewire приходит то списком, то словарём с номерами-ключами."""
        if isinstance(value, dict):
            return list(value.values())
        return value if isinstance(value, list) else []

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        if not self.is_product_url(product_url):
            return None
        url = urljoin(self.base_url + "/", product_url).split("?")[0].split("#")[0]
        page = self._make_request(url)
        if page is None:
            return None
        return self._build_product(page, url)

    # --- проверка цены и наличия ---------------------------------------------

    @translate_offer_check_errors
    def check_offer(self, offer: OfferCheckContext) -> OfferCheckResult:
        """Один запрос страницы сохранённой карточки: цена и «есть/нет».

        404/410 — «не найден». Страница открылась, но номер товара другой — тоже
        «не найден», чужой товар не подставляем. Нет блока данных — сбой формата.
        """
        if not self.is_product_url(offer.canonical_url):
            raise OfferNotFound(offer.canonical_url)
        url = offer.canonical_url.split("?")[0].split("#")[0]
        page = self._make_request(url, patient=False)
        if page is None:
            raise OfferNotFound(offer.canonical_url)
        try:
            product = self._build_product(page, url)
        except AloparcaFormatError as exc:
            raise MalformedOfferResponse(str(exc)) from exc
        if offer.external_product_id and product.external_id != offer.external_product_id:
            raise OfferNotFound(offer.canonical_url)
        return result_from_scraped_product(offer, product)

    def _build_product(self, page: str, url: str) -> ScrapedProduct:
        snapshots = self._snapshots(page)
        if "product-detail" not in snapshots:
            raise AloparcaFormatError(f"нет блока данных product-detail: {url}")
        position, data = snapshots["product-detail"]
        # Блок товара — от его компонента до рассрочки: в шапке и подвале те же классы и слова.
        end = page.find("<!-- Taksit Seçenekleri", position)
        block = page[position: end if end > 0 else len(page)]

        brand = self._text(r"Marka:\s*</span>\s*<span[^>]*>(.*?)</span>", block)
        part_number = self._text(r"Stok Kodu:\s*</span>\s*<span[^>]*>(.*?)</span>", block)
        kind = self._text(r"<h1[^>]*>(.*?)</h1>", block)
        source_title = self._text(r"</h1>\s*<p[^>]*>(.*?)</p>", block)
        if not part_number or not (kind or source_title):
            raise AloparcaFormatError(f"нет артикула («Stok Kodu») или названия: {url}")

        price_start = block.find("<!-- Masaüstü için fiyat alanı")
        price_end = block.find("<!-- Ürün Özellikleri", max(price_start, 0))
        price_block = block[max(price_start, 0): price_end if price_end > 0 else len(block)]
        if "Stokta var" in price_block:
            is_available = True
        elif "Stokta yok" in price_block:
            is_available = False
        else:
            raise AloparcaFormatError(f"нет отметки наличия («Stokta var» / «Stokta yok»): {url}")
        price = self._price(self._text(r'text-3xl font-bold text-gray-900[^"]*"[^>]*>(.*?)</span>', price_block))

        images: List[str] = []
        images_match = re.search(r"images:\s*(\[.*?\])\s*,", block, re.DOTALL)
        if images_match is None:
            raise AloparcaFormatError(f"нет списка фото (images): {url}")
        for path in json.loads(html_lib.unescape(images_match.group(1))):
            image_url = urljoin(self.IMAGE_BASE, str(path).lstrip("/"))
            if path and image_url not in images:
                images.append(image_url)

        crumbs = [
            row for row in self._rows((snapshots.get("breadcrumb") or (0, {}))[1].get("breadcrumbs"))
            if isinstance(row, dict)
        ]
        section = subsection = ""
        for crumb in crumbs:
            parts = [p for p in urlparse(str(crumb.get("url") or "")).path.split("/") if p]
            if parts[:2] == ["yedek-parcalar", "kategori"] and len(parts) > 2:
                section, subsection = parts[2], (parts[3] if len(parts) > 3 else "")
        route = resolve_aloparca_category_slugs(section, subsection)
        breadcrumb_titles = [clean_text(str(crumb.get("title") or "")) for crumb in crumbs]

        specs: Dict[str, str] = {}
        for row in self._rows(data.get("criteria")):
            if not isinstance(row, dict):
                continue
            label = clean_text(str(row.get("CRITERIA_NAME") or ""))
            value = clean_text(str(row.get("CRITERIA_VALUES") or "")).rstrip("; ")
            if label and value:
                specs[label] = f"{specs[label]}; {value}" if label in specs else value

        numbers: List[Dict[str, str]] = []
        seen_numbers = set()
        for row in self._rows(data.get("oems")):
            if not isinstance(row, dict):
                continue
            number = clean_text(str(row.get("oem") or ""))
            normalized = normalize_part_number(number)
            if not normalized or normalized in seen_numbers:
                continue
            seen_numbers.add(normalized)
            makers = [clean_text(str(m)) for m in self._rows(row.get("brands")) if m]
            numbers.append({"number": number[:100], "kind": "oem", "maker": ", ".join(makers)[:255]})

        fitments: List[Dict[str, Any]] = []
        vehicles = data.get("compatibleVehicles")
        for make, rows in (vehicles.items() if isinstance(vehicles, dict) else ()):
            for row in self._rows(rows):
                if isinstance(row, dict):
                    fitments.append(parse_fitment_row(make, row))
        unparsed = sum(1 for row in fitments if row.pop("unparsed"))
        self.unparsed_fitments += unparsed
        makes = list(dict.fromkeys(row["make"] for row in fitments))

        product_key = (data.get("product") or {}).get("key") if isinstance(data.get("product"), dict) else None
        slug = self._slug(url)
        description_lines = [source_title or kind, *(f"{label}: {value}" for label, value in specs.items())]
        if numbers:
            description_lines.append("OEM: " + ", ".join(row["number"] for row in numbers[:30]))
        if makes:
            description_lines.append("Uyumlu markalar: " + ", ".join(makes))
        product = ScrapedProduct(
            name=clean_text(f"{kind or source_title} {brand} {part_number}")[:255],
            description="\n".join(line for line in description_lines if line),
            price=price,
            currency="TRY",
            url=url,
            images=images,
            category=route[0],
            brand=brand,
            external_id=f"aloparca-{product_key}" if product_key else f"aloparca-{slug}"[:255],
            sku=part_number[:100],
            is_available=is_available,
            stock_quantity=self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            attributes={
                "part_number": part_number,
                "part_kind_tr": kind,
                "source_title": source_title,
                "specs": specs,
                "aloparca_slug": slug,
                "aloparca_breadcrumbs": breadcrumb_titles,
                "aloparca_subgroup": " → ".join(breadcrumb_titles[2:]) or kind,
                "aloparca_category_slugs": list(route),
                "oem_count": len(numbers),
                "fitment_count": len(fitments),
                "fitment_unparsed": unparsed,
                "fitment_makes": makes,
            },
            source=self.get_name(),
        )
        # Номера и применимость — в свои таблицы (apps/scrapers/auto_parts.py), а не в
        # attributes: до ~900 строк на деталь раздули бы external_data и журнал товаров.
        product.auto_part = {"part_number": part_number, "numbers": numbers, "fitments": fitments}
        return product
