"""Парсер SuperStep (superstep.com.tr) — мультибрендовая обувь, одежда и аксессуары.

Сайт работает на платформе Akinon: любая страница с ``?format=json`` отдаёт
данные готовым JSON, без браузера и без разбора HTML.

- Список раздела — ``products`` (48 на страницу) и ``pagination``. Строка
  списка — один цвет модели; ``extra_data.variants`` — цвета модели и размеры
  этого цвета с признаком «есть/нет».
- Карточка — ``product`` и ``variants[].options[].product``: размеры со SKU и
  штрихкодом, цвета со ссылками. Размер у Akinon — отдельный «товар», модель
  объединяет ``base_code``; парсер собирает их обратно в одну карточку.

Два набора полей: свои товары (``integration_*``) и маркетплейс (код
``34-…``, ``mp_size``/``mp_color``/``mp_description``, бывают скидки «в
корзине»). Раскладка по нашим разделам — по подгруппе ``integration_alt_grup``
(``SUPERSTEP_SUBGROUP_CATEGORIES``); товар неизвестной подгруппы не
загружается и попадает в отчёт прогона «не разложено».
"""

import json
import re
from collections import Counter
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

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


class SuperstepFormatError(RuntimeError):
    """В JSON SuperStep нет ожидаемых ключей: формат сменился, а не «каталог пуст»."""


def superstep_subgroup_key(label: Any) -> str:
    """Ключ подгруппы: без регистра и турецких букв («Sırt Çantası» → «sirt cantasi»)."""
    text = str(label or "").replace("İ", "i").replace("I", "ı").lower()
    text = text.translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"\s+", " ", text).strip()


def _by_gender(women: Sequence[str], men: Sequence[str], other: Sequence[str]) -> Dict[str, Tuple[str, ...]]:
    return {"women": tuple(women), "men": tuple(men), "": tuple(other)}


_BAGS = ("bags-wallets", "accessories")

# Подгруппа SuperStep → наши разделы: первый существующий в каталоге slug
# (дальше — родитель и корень). У сумок наш раздел зависит от пола.
SUPERSTEP_SUBGROUP_CATEGORIES: Dict[str, Any] = {
    # Обувь
    "spor ayakkabi & sneaker": ("sneakers", "shoes"),
    "kosu ayakkabisi": ("running-shoes", "sneakers", "shoes"),
    "basketbol ayakkabisi": ("basketball-shoes", "sneakers", "shoes"),
    "antrenman ayakkabisi": ("training-shoes", "sneakers", "shoes"),
    "tenis ayakkabisi": ("training-shoes", "sneakers", "shoes"),
    "voleybol ayakkabisi": ("training-shoes", "sneakers", "shoes"),
    "krampon": ("training-shoes", "sneakers", "shoes"),
    "hali saha kramponu": ("training-shoes", "sneakers", "shoes"),
    "outdoor ayakkabi": ("sneakers", "shoes"),
    "terlik": ("slides", "sandals", "shoes"),
    "sandalet": ("sandals-classic", "sandals", "shoes"),
    "havuz & deniz ayakkabisi": ("sandals", "shoes"),
    "bot": ("boots", "shoes"),
    "bot & cizme": ("boots", "shoes"),
    "babet": ("casual-shoes", "shoes"),
    "gunluk ayakkabi": ("casual-shoes", "shoes"),
    # Одежда
    "t-shirt": ("t-shirts", "tops", "clothing"),
    "polo": ("polo-shirts", "t-shirts", "tops", "clothing"),
    "forma": ("t-shirts", "tops", "clothing"),
    "atlet": ("tank-tops", "tops", "clothing"),
    "crop": ("crop-tops", "tops", "clothing"),
    "body": ("tops-items", "tops", "clothing"),
    "gomlek": ("shirts", "tops", "clothing"),
    "sweatshirt": ("knitwear", "clothing"),
    "hoodie": ("hoodies", "knitwear", "clothing"),
    "polar": ("knitwear", "clothing"),
    "triko": ("sweaters", "knitwear", "clothing"),
    "kazak": ("sweaters", "knitwear", "clothing"),
    "suveter": ("sweaters", "knitwear", "clothing"),
    "hirka": ("cardigans", "knitwear", "clothing"),
    "sort": ("shorts", "bottoms", "clothing"),
    "deniz sortu": ("shorts", "bottoms", "clothing"),
    "mayo & mayo sort": ("shorts", "bottoms", "clothing"),
    "pantolon": ("pants", "bottoms", "clothing"),
    "esofman alti": ("pants", "bottoms", "clothing"),
    "jean": ("jeans", "bottoms", "clothing"),
    "tayt": ("leggings", "bottoms", "clothing"),
    "etek": ("skirts", "bottoms", "clothing"),
    "elbise": ("dresses", "clothing"),
    "esofman ustu": ("jackets", "outerwear", "clothing"),
    "esofman takimi": ("tracksuits", "suits", "clothing"),
    "esofman": ("tracksuits", "suits", "clothing"),
    "ceket": ("jackets", "outerwear", "clothing"),
    "mont": ("jackets", "outerwear", "clothing"),
    "yelek": ("vests", "outerwear", "clothing"),
    "yagmurluk": ("windbreakers", "jackets", "outerwear", "clothing"),
    "ruzgarlik": ("windbreakers", "jackets", "outerwear", "clothing"),
    "tulum": ("clothing",),
    "pijama takimi": ("pajamas", "sleepwear", "clothing"),
    # Купальников в одежде нет — до своего раздела идут в корень «Одежда».
    "bikini": ("clothing",),
    "bikini & mayo": ("clothing",),
    # Бельё
    "boxer": ("uw-boxers", "uw-mens-underwear", "underwear"),
    "ic giyim": _by_gender(
        ("uw-womens-underwear", "underwear"),
        ("uw-mens-underwear", "underwear"),
        ("underwear",),
    ),
    "bra": ("uw-sports-bras", "uw-bras", "underwear"),
    "bra & spor sutyeni": ("uw-sports-bras", "uw-bras", "underwear"),
    "corap": ("uw-socks", "uw-socks-hosiery", "underwear"),
    # Головные уборы
    "sapka": ("hw-baseball-caps", "hw-caps", "headwear"),
    "bere": ("hw-beanies", "hw-winter-headwear", "headwear"),
    # Аксессуары
    "sirt cantasi": _by_gender(
        ("acc-womens-backpacks", "womens-bags", *_BAGS),
        ("acc-mens-backpacks", "mens-bags", *_BAGS),
        _BAGS,
    ),
    "bel cantasi": _by_gender(
        ("acc-belt-bags", "womens-bags", *_BAGS),
        ("acc-mens-belt-bags", "mens-bags", *_BAGS),
        _BAGS,
    ),
    "omuz cantasi": _by_gender(("shoulder-bags", "womens-bags", *_BAGS), _BAGS, _BAGS),
    "el cantasi": _by_gender(("womens-bags", *_BAGS), _BAGS, _BAGS),
    "postaci cantasi": ("messenger-bags", "mens-bags", *_BAGS),
    "canta": _BAGS,
    "spor cantasi": _BAGS,
    "seyahat cantasi": ("duffle-bags", "travel-bags", *_BAGS),
    "valiz": ("suitcases", "travel-bags", *_BAGS),
    "cuzdan": ("wallets", *_BAGS),
    "cuzdan & kartlik": ("wallets", *_BAGS),
    "kalem kutusu": ("accessories",),
    "anahtarlik": ("accessories",),
    "ayakkabi bakim urunu": ("accessories",),
    "bileklik": ("accessories",),
    "saat": ("watches", "accessories"),
    "atki": ("scarves", "scarves-shawls", "accessories"),
    "boyunluk": ("snoods", "scarves-shawls", "accessories"),
    "eldiven": ("acc-gloves", "accessories"),
    "sac bandi": ("acc-headbands", "hair-accessories", "accessories"),
    # Спорттовары
    "basketbol topu": ("basketball-balls", "basketball", "team-sports", "sports"),
    "dizlik": ("sports",),
    "kolluk": ("sports",),
    "tekmelik": ("shin-guards", "football", "team-sports", "sports"),
    "yuzucu gozlugu": ("swimming-goggles", "swimming", "water-sports", "sports"),
    "yuzme aksesuari": ("swimming", "water-sports", "sports"),
    "spor aksesuarlari": ("fitness-accessories", "fitness-gym", "sports"),
    "antrenman aksesuari": ("fitness-accessories", "fitness-gym", "sports"),
    "kayak eldiveni": ("winter-sports", "sports"),
    "havlu": ("sports",),
    # Посуда
    "termos": ("drinkware", "tableware"),
    "suluk": ("drinkware", "tableware"),
}

# Решение владельца 04.11.2026: фигурки (Funko, Bearbrick), шахматы и
# служебная группа «281» не загружаются, даже если для них появится раздел.
SUPERSTEP_SKIPPED_SUBGROUPS = frozenset({"figur", "satranc takimi", "281"})


def resolve_superstep_category_slugs(subgroup: Any, gender: str = "") -> Tuple[str, ...]:
    """Разделы подгруппы (от точного к корню); пусто — подгруппа не раскладывается."""
    key = superstep_subgroup_key(subgroup)
    if not key or key in SUPERSTEP_SKIPPED_SUBGROUPS:
        return ()
    route = SUPERSTEP_SUBGROUP_CATEGORIES.get(key, ())
    if isinstance(route, dict):
        route = route.get(gender) or route[""]
    return tuple(route)


class SuperstepParser(BaseScraper):
    """Парсер superstep.com.tr по JSON Akinon (``?format=json``), без прокси."""

    SUPPORTS_PAGE_CHUNKING = True
    REPORTS_PAGES_PROCESSED = True
    REPORTS_NEXT_START_PAGE = True
    SUPPORTS_CATALOG_STATE = True
    SUPPORTS_LISTING_GUARD = True
    # Меняется при смене состава отпечатка строки — все карточки откроются заново.
    LISTING_FINGERPRINT_VERSION = 1

    PRODUCT_PATH_RE = re.compile(r"^/(?:urun/[^/]+/[^/]+|product/\d+)/?$", re.IGNORECASE)
    # Любая страница списка: из её фильтра «Kategoriler» берутся корни каталога.
    ROOTS_DISCOVERY_PATH = "/erkek/"
    COLOR_KEYS = ("integration_renk", "mp_color")
    SIZE_KEYS = ("integration_beden", "mp_size")
    BARCODE_KEYS = ("integration_yurt_disi_barkod", "mp_yurtdisi_barkod")
    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000
    # Корни, у которых есть модели вариантов цвета (остальные — цвет = карточка).
    VARIANT_ROOTS = frozenset({"shoes", "clothing", "underwear", "headwear"})
    # Предохранитель: максимум цветов на одну карточку (защита от аномалий).
    MAX_COLOR_VARIANTS = 12

    def __init__(self, base_url: str = "https://www.superstep.com.tr", **kwargs):
        super().__init__(base_url=base_url, delay_range=(1.5, 3), **kwargs)
        self.client.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                "Referer": "https://www.superstep.com.tr/",
            }
        )
        self.unmapped: Counter = Counter()

    def get_name(self) -> str:
        return "superstep"

    def get_supported_domains(self) -> List[str]:
        return ["superstep.com.tr", "www.superstep.com.tr"]

    # --- ссылки --------------------------------------------------------------

    @classmethod
    def _is_superstep_host(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return not host or host == "superstep.com.tr" or host.endswith(".superstep.com.tr")

    @classmethod
    def is_product_url(cls, url: str) -> bool:
        return cls._is_superstep_host(url) and bool(cls.PRODUCT_PATH_RE.match(urlparse(url).path or ""))

    @classmethod
    def is_category_url(cls, url: str) -> bool:
        """Раздел — любой не-товарный путь сайта, кроме главной."""
        path = urlparse(url).path or ""
        return (
            cls._is_superstep_host(url)
            and path.strip("/") != ""
            and not cls.is_product_url(url)
        )

    @classmethod
    def supports_page_chunking_for_url(cls, url: str) -> bool:
        """Авточепочка по страницам — только у раздела, не у одиночного товара."""
        return cls.is_category_url(url)

    @staticmethod
    def _canonical_url(url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))

    def _json_url(self, url: str, page: int = 1) -> str:
        parsed = urlparse(urljoin(self.base_url + "/", url))
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["format"] = "json"
        if page > 1:
            query["page"] = str(page)
        else:
            query.pop("page", None)
        return urlunparse(parsed._replace(query=urlencode(query), fragment=""))

    def _fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        """JSON страницы; None — 404. HTML вместо JSON — защита сайта, обход останавливается."""
        text = self._make_request(url)
        if text is None:
            return None
        try:
            data = json.loads(text)
        except ValueError:
            self.logger.warning("SuperStep: вместо JSON пришла страница (защита?) на %s", url)
            raise ScraperAccessBlockedError(source="SuperStep", status_code=403, url=url)
        if not isinstance(data, dict):
            raise SuperstepFormatError(f"SuperStep: ответ не объект JSON: {url}")
        return data

    # --- категории сайта -----------------------------------------------------

    def parse_categories(self) -> List[Dict[str, Any]]:
        """Корни каталога (Erkek, Kadın, Çocuk, Heartbeat) — фильтр «Kategoriler».

        Разделы внутри корня пересекаются (у Çocuk подразделы «Kız/Erkek
        Çocuk» дублируют обувь и одежду), а корень отдаёт все свои товары.
        Унисекс есть и в Erkek, и в Kadın: повтор не открывает карточку —
        отпечаток строки уже записан.
        """
        url = self._json_url(self.ROOTS_DISCOVERY_PATH)
        data = self._fetch_json(url)
        if not data:
            raise SiteCategoriesError(f"SuperStep: список разделов не загрузился: {url}")
        facet = next(
            (row for row in data.get("facets") or [] if isinstance(row, dict) and row.get("key") == "category_ids"),
            None,
        )
        choices = ((facet or {}).get("data") or {}).get("choices") or []
        rows = [
            {
                "name": clean_text(str(choice.get("label") or "")),
                "url": self._canonical_url(urljoin(self.base_url, str(choice.get("url") or ""))),
                "external_id": choice.get("value"),
            }
            for choice in choices
            if isinstance(choice, dict)
            and choice.get("depth") == 0
            and choice.get("url")
            and int(choice.get("quantity") or 0) > 0
        ]
        return self._site_categories(rows)

    # --- обход раздела -------------------------------------------------------

    @staticmethod
    def _variant_options(variants: Any, keys: Sequence[str]) -> List[Dict[str, Any]]:
        for group in variants or []:
            if isinstance(group, dict) and group.get("attribute_key") in keys:
                return [option for option in group.get("options") or [] if isinstance(option, dict)]
        return []

    def _model_color_id(self, product: Dict[str, Any], variants: Any = None) -> str:
        """Код цвета модели (``396464.01``, ``B75806.-``) — строка списка и вариант цвета.

        Без ``integration_model_renk`` — base_code и код цвета по тому же
        атрибуту, по которому сайт группирует цвета (``_color_key``).
        """
        attrs = product.get("attributes") or {}
        value = str(attrs.get("integration_model_renk") or "").strip()
        if value:
            return value
        color = self._color_code(product, self._color_key(variants))
        return f"{product.get('base_code') or product.get('sku') or ''}.{color}"

    @staticmethod
    def _attr_label(product: Dict[str, Any], key: str) -> str:
        """Подпись атрибута: у ``integration_alt_grup`` значение — код («088»), подпись — имя."""
        row = (product.get("attributes_kwargs") or {}).get(key)
        if isinstance(row, dict) and row.get("label"):
            return clean_text(str(row["label"]))
        return clean_text(str((product.get("attributes") or {}).get(key) or ""))

    def _category_route(self, product: Dict[str, Any]) -> Tuple[str, Tuple[str, ...]]:
        subgroup = self._attr_label(product, "integration_alt_grup")
        gender = self._map_gender((product.get("attributes") or {}).get("integration_cinsiyet"))
        return subgroup, resolve_superstep_category_slugs(subgroup, gender)

    def _tile_fingerprint(self, tile: Dict[str, Any]) -> str:
        """Отпечаток строки списка: то, что меняется между обходами.

        Цена, обе цены для зачёркивания, наличие, размеры этого цвета с наличием,
        цвета модели с наличием и ценой, число фото и скидки «в корзине».
        Точный остаток ``stock`` не входит: парсер его не сохраняет.
        """
        variants = (tile.get("extra_data") or {}).get("variants")
        return listing_fingerprint(
            {
                "v": self.LISTING_FINGERPRINT_VERSION,
                "name": tile.get("name"),
                "price": tile.get("price"),
                "retail_price": tile.get("retail_price"),
                "previous_price": (tile.get("price_extra_field") or {}).get("previous_price"),
                "in_stock": tile.get("in_stock"),
                "sizes": [
                    [str(option.get("label") or ""), bool(option.get("in_stock"))]
                    for option in self._variant_options(variants, self.SIZE_KEYS)
                ],
                "colors": sorted(
                    [
                        str(option.get("label") or ""),
                        bool(option.get("in_stock")),
                        str((option.get("product") or {}).get("price") or ""),
                    ]
                    for option in self._variant_options(variants, self.COLOR_KEYS)
                ),
                "images": len(tile.get("productimage_set") or []),
                "offers": sorted(
                    str(offer.get("label") or "")
                    for offer in tile.get("basket_offers") or []
                    if isinstance(offer, dict)
                ),
            }
        )

    def _unmapped_report(self) -> str:
        if not self.unmapped:
            return ""
        top = ", ".join(f"{name or 'без подгруппы'} {count}" for name, count in self.unmapped.most_common(12))
        return f"Не разложено (не загружены): {sum(self.unmapped.values())} строк — {top}."

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
            report = self._unmapped_report()
            if report:
                self.stop_reason = f"{self.stop_reason} {report}".strip()

    def _iterate_listing(self, category_url: str, max_pages: int, start_page: int) -> Iterator[ScrapedProduct]:
        state = getattr(self, "catalog_state", None) or CatalogTraversalState()
        self.catalog_state = state
        result_count = getattr(self, "catalog_result_count", None)
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
            page_url = self._json_url(category_url, page)
            data = self._fetch_json(page_url)
            if not data:
                if page == 1:
                    raise CategoryPageNotFoundError(f"SuperStep: раздел не найден: {category_url}")
                self.has_more_pages = False
                self.stop_reason = f"SuperStep вернул пустую страницу раздела: {page_url}"
                break
            tiles = data.get("products")
            pagination = data.get("pagination")
            if not isinstance(tiles, list) or not isinstance(pagination, dict):
                raise SuperstepFormatError(f"SuperStep: в списке нет products/pagination: {page_url}")
            tiles = [tile for tile in tiles if isinstance(tile, dict) and tile.get("absolute_url")]
            has_next = int(pagination.get("current_page") or page) < int(pagination.get("num_pages") or 0)
            identities = [
                self._model_color_id(tile, (tile.get("extra_data") or {}).get("variants")) for tile in tiles
            ]
            if not tiles or state.page_seen(identities, page):
                self.has_more_pages = False
                self.stop_reason = f"Страница {page} пуста или повторяет уже обработанную выдачу; раздел закончился."
                break

            guard = getattr(self, "listing_guard", None)
            fingerprints = {identity: self._tile_fingerprint(tile) for identity, tile in zip(identities, tiles)} if guard else {}
            if guard:
                guard.prefetch(list(fingerprints))
            before = result_count() if result_count else yielded
            attempted = set()
            settled_on_page = 0
            for identity, tile in zip(identities, tiles):
                fingerprint = fingerprints.get(identity, "")
                if identity in attempted or state.product_seen(identity):
                    self.catalog_skipped += 1
                    if guard:
                        guard.remember_covered(identity, fingerprint)
                    continue
                attempted.add(identity)
                subgroup, route = self._category_route(tile)
                if not route:
                    # Не загружаем, но строка обработана — иначе страница из одних
                    # фигурок считалась бы «без новых товаров».
                    self.unmapped[subgroup] += 1
                    settled_on_page += 1
                    continue
                if guard and fingerprint and not guard.should_open(identity, fingerprint):
                    # Строка списка не изменилась: карточку (и все её цвета) не открываем.
                    settled_on_page += 1
                    continue

                product = self.parse_product_detail(urljoin(self.base_url, str(tile["absolute_url"])))
                if product and self.validate_product(product):
                    if guard and fingerprint:
                        guard.attach(
                            product,
                            identity,
                            fingerprint,
                            covers=product.attributes.get("superstep_color_ids") or [],
                        )
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
            stalled = state.finish_page(identities, page, after > before or settled_on_page > 0)
            if not has_next or stalled:
                self.has_more_pages = False
                self.stop_reason = (
                    "Обход остановлен: три страницы подряд без новых товаров."
                    if stalled else "Достигнута последняя страница раздела."
                )
                break
            page += 1

    def mark_catalog_product(self, product):
        """Помнит только сохранённые карточки — вместе с уже загруженными цветами."""
        for color_id in product.attributes.get("superstep_color_ids") or []:
            self.catalog_state.mark_product(color_id)

    # --- карточка ------------------------------------------------------------

    def _card(self, url: str) -> Optional[Dict[str, Any]]:
        data = self._fetch_json(self._json_url(self._canonical_url(url)))
        if data is None:
            return None
        if not isinstance(data.get("product"), dict) or not isinstance(data.get("variants"), list):
            raise SuperstepFormatError(f"SuperStep: в карточке нет product/variants: {url}")
        return data

    def parse_product_detail(
        self,
        product_url: str,
        *,
        include_sibling_variants: bool = True,
    ) -> Optional[ScrapedProduct]:
        card = self._card(product_url)
        if not card:
            return None
        product = card["product"]
        if not product.get("name"):
            return None
        subgroup, route = self._category_route(product)
        if not route:
            self.unmapped[subgroup] += 1
            self.logger.warning(
                "SuperStep: не разложено — подгруппы «%s» нет в таблице раскладки (или она не загружается "
                "по решению владельца), товар не загружен: %s",
                subgroup,
                product_url,
            )
            return None

        color_key = self._color_key(card["variants"])
        self_color = self._color_code(product, color_key)
        color_options = self._variant_options(card["variants"], (color_key,))
        # Порядок цветов — как на сайте, с какого бы цвета ни начали обход.
        color_order = {self._option_value(option): index for index, option in enumerate(color_options)}
        color_rows = [(self_color, card)]
        # Цвета вариантами умеют только обувь, одежда, бельё и головные уборы
        # (``ScraperIntegrationService._fashion_model_config``). У аксессуаров,
        # посуды и спорттоваров каждый цвет — своя карточка: соседние цвета не
        # открываются, их фото не качаются, у каждой строки списка свой товар.
        with_variants = route[-1] in self.VARIANT_ROOTS
        if include_sibling_variants and with_variants:
            for option in color_options:
                code = self._option_value(option)
                url = str((option.get("product") or {}).get("absolute_url") or "")
                # Распроданный цвет не открываем: его вариант выключится как исчезнувший.
                if code == self_color or not url or not option.get("in_stock"):
                    continue
                if len(color_rows) >= self.MAX_COLOR_VARIANTS:
                    break
                sibling = self._card(urljoin(self.base_url, url))
                if not sibling or self._color_code(sibling["product"], color_key) != code:
                    self.logger.warning("SuperStep: цвет %s не открылся по %s", code, url)
                    continue
                color_rows.append((code, sibling))

        variants = [
            self._build_color_variant(color_card, color_order.get(code, len(color_order)))
            for code, color_card in color_rows
        ]
        # Открытый цвет главный, если он есть в наличии: иначе цена и ссылка
        # товара были бы от распроданного цвета.
        primary = next((v for v in variants if v["is_available"]), variants[0])
        variants.sort(key=lambda variant: variant["sort_order"])
        all_sizes: List[str] = []
        for variant in variants:
            for row in variant["sizes"]:
                if row["size"] not in all_sizes:
                    all_sizes.append(row["size"])

        attrs = product.get("attributes") or {}
        is_available = any(v["is_available"] for v in variants)
        attributes: Dict[str, Any] = {
            "color": primary["color"],
            "gender": self._map_gender(attrs.get("integration_cinsiyet")),
            "sizes": all_sizes,
            "superstep_subgroup": subgroup,
            "superstep_category_slugs": list(route),
            "superstep_color_ids": [v["sku"] for v in variants],
        }
        if with_variants:
            external_id = f"superstep-{product.get('base_code') or product.get('sku')}"
            sku = str(product.get("base_code") or "")
            attributes.update({"fashion_variants": variants, "variant_group_id": external_id})
        else:
            external_id = f"superstep-{primary['sku']}"
            sku = primary["sku"]
        attributes.update(self._extra_attributes(product))

        return ScrapedProduct(
            name=clean_text(str(product.get("name") or "")),
            description=self._description(product) or self._features_description(product),
            price=primary["price"],
            old_price=primary["old_price"],
            currency="TRY",
            url=primary["external_url"],
            images=primary["images"],
            category=route[0],
            brand=self._attr_label(product, "integration_alt_marka"),
            external_id=external_id,
            sku=sku,
            is_available=is_available,
            stock_quantity=self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            attributes=attributes,
            source=self.get_name(),
        )

    # --- проверка наличия ----------------------------------------------------

    @translate_offer_check_errors
    def check_offer(self, offer: OfferCheckContext) -> OfferCheckResult:
        """Один запрос JSON сохранённого цвета; соседние цвета не открываются.

        «Не найден» закрепляется надолго, поэтому ставится только при уверенности:
        ссылка цвета — это ссылка одного из размеров, и её 404 (или
        ``{"detail": "Bulunamadı."}`` у ``/product/<pk>/``) ещё не значит, что
        снят весь цвет. Тогда цвет ищется в поиске сайта по коду модели: нашёлся
        по другой ссылке — проверяется по ней, нет в поиске — «не найден».
        Редирект не на товар (главная на техработах) — сбой источника. Карточка
        другой модели или цвета — «не найден»: чужой товар не подставляем.
        Наличие — «есть/нет» по размеру, точный остаток не храним.
        """
        card = self._offer_card(offer.canonical_url) or self._relocated_offer_card(offer)
        variant = self._build_color_variant(card, sort_order=0)
        if offer.variant_key:
            same_offer = variant["external_id"] == offer.variant_key
        else:
            same_offer = not offer.external_sku or variant["sku"] == offer.external_sku
        if not same_offer:
            raise OfferNotFound(offer.canonical_url)
        scraped = ScrapedProduct(
            name=clean_text(str(card["product"].get("name") or "")),
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

    def _offer_json(self, url: str) -> Tuple[Dict[str, Any], str]:
        text, final_url = self._make_offer_request(url, include_final_url=True)
        try:
            data = json.loads(text)
        except ValueError:
            raise ScraperAccessBlockedError(source="SuperStep", status_code=403, url=url)
        if not isinstance(data, dict):
            raise MalformedOfferResponse()
        return data, final_url

    def _offer_card(self, product_url: str) -> Optional[Dict[str, Any]]:
        """JSON карточки для проверки; None — сайт ответил «нет такой страницы»."""
        try:
            card, final_url = self._offer_json(self._json_url(self._canonical_url(product_url)))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        if not self.is_product_url(final_url):
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                f"SuperStep: redirect away from product page to {final_url}",
                retryable=True,
            )
        if "product" not in card and card.get("detail"):
            return None
        if not isinstance(card.get("product"), dict) or not isinstance(card.get("variants"), list):
            raise MalformedOfferResponse()
        return card

    def _relocated_offer_card(self, offer: OfferCheckContext) -> Dict[str, Any]:
        """Карточка цвета, чья ссылка не открылась, — через поиск по коду модели."""
        model_color = (
            offer.variant_key.removeprefix("superstep-variant-")
            if offer.variant_key
            else offer.external_sku
        )
        base_code = model_color.rpartition(".")[0]
        if not base_code:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                "SuperStep: product page is missing and offer has no model code",
                retryable=False,
            )
        search_url = self._json_url("/list/?" + urlencode({"search_text": base_code}))
        try:
            data, _ = self._offer_json(search_url)
        except httpx.HTTPStatusError as exc:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                f"SuperStep: search returned HTTP {exc.response.status_code}",
                retryable=True,
                http_status=exc.response.status_code,
            ) from exc
        tiles = data.get("products")
        if not isinstance(tiles, list):
            raise MalformedOfferResponse()
        for tile in tiles:
            if not isinstance(tile, dict):
                continue
            variants = (tile.get("extra_data") or {}).get("variants")
            if self._model_color_id(tile, variants) != model_color:
                continue
            moved_url = urljoin(self.base_url, str(tile.get("absolute_url") or ""))
            if self._canonical_url(moved_url) != self._canonical_url(offer.canonical_url):
                card = self._offer_card(moved_url)
                if card:
                    return card
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                "SuperStep: color is listed in search but its page is missing",
                retryable=True,
            )
        if int((data.get("pagination") or {}).get("num_pages") or 1) > 1:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                "SuperStep: color is not on the first search page",
                retryable=True,
            )
        raise OfferNotFound(offer.canonical_url)

    def _color_key(self, variants: Any) -> str:
        """Атрибут, по которому сайт группирует цвета модели.

        У части товаров маркетплейса есть и ``integration_renk`` («01»), и
        ``mp_color`` («SİYAH»), а группа цветов — по ``mp_color``.
        """
        for group in variants or []:
            if isinstance(group, dict) and group.get("attribute_key") in self.COLOR_KEYS:
                return str(group["attribute_key"])
        return self.COLOR_KEYS[0]

    @staticmethod
    def _color_code(product: Dict[str, Any], color_key: str) -> str:
        return str((product.get("attributes") or {}).get(color_key) or "-")

    @staticmethod
    def _option_value(option: Dict[str, Any]) -> str:
        """Код варианта: ``label`` бывает подписью («Siyah»), ``value`` — кодом («SİYAH»)."""
        return str(option.get("value") or option.get("label") or "")

    def _build_color_variant(self, card: Dict[str, Any], sort_order: int) -> Dict[str, Any]:
        product = card["product"]
        color_key = self._color_key(card["variants"])
        color_code = self._color_code(product, color_key)
        sizes = self._build_sizes(card["variants"], color_key, color_code)
        price, old_price = self._selling_and_old_price(product)
        color = self._color_name(product)
        is_available = any(row["is_available"] for row in sizes) if sizes else bool(product.get("in_stock"))
        variant = {
            "external_id": f"superstep-variant-{self._model_color_id(product, card['variants'])}",
            "sort_order": sort_order,
            "color": color,
            "display_name": clean_text(f"{product.get('name') or ''} - {color}".strip(" -")),
            "price": price,
            "old_price": old_price,
            "currency": "TRY",
            "external_url": self._color_url(product, card["variants"], color_key, color_code),
            "images": self._extract_images(product),
            "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if is_available else 0,
            "is_available": is_available,
            "sizes": sizes,
            "sku": self._model_color_id(product, card["variants"]),
        }
        offers = self._basket_offers(product)
        if offers:
            variant["basket_offers"] = offers
        return variant

    def _build_sizes(self, variants: Any, color_key: str, color_code: str) -> List[Dict[str, Any]]:
        """Размеры одного цвета. Akinon кладёт в список и размеры других цветов
        (тех, что есть только у них) — их отсекаем по коду цвета."""
        options = []
        for index, option in enumerate(self._variant_options(variants, self.SIZE_KEYS)):
            size_product = option.get("product") or {}
            if self._color_code(size_product, color_key) != color_code or not option.get("label"):
                continue
            options.append((self._size_sort_key(option, index), option, size_product))
        options.sort(key=lambda row: row[0])
        sizes = []
        for sort_order, (_, option, size_product) in enumerate(options):
            available = bool(option.get("in_stock"))
            sizes.append(
                {
                    "size": self._normalize_size(option["label"]),
                    "is_available": available,
                    "stock_quantity": self.DEFAULT_ASSUMED_STOCK_QUANTITY if available else 0,
                    "sort_order": sort_order,
                    "sku": str(size_product.get("sku") or ""),
                    "barcode": self._barcode(size_product),
                }
            )
        return sizes

    @classmethod
    def _size_sort_key(cls, option: Dict[str, Any], index: int) -> tuple:
        """Числовые размеры («28,5», «32-33») — по числу: ``order`` у Akinon
        бывает из разных систем (у детской обуви 2850, 3500, 200180…).
        Буквенные (XS…XXL) — по ``order`` сайта."""
        match = re.match(r"^(\d+(?:\.\d+)?)(?:-\d+)?$", cls._normalize_size(option.get("label")))
        if match:
            return (0, float(match.group(1)), index)
        try:
            return (1, int(option.get("order")), index)
        except (TypeError, ValueError):
            return (1, index, index)

    @staticmethod
    def _normalize_size(value: Any) -> str:
        """«42,5» → «42.5»: полуразмеры хранятся с точкой, как у FLO."""
        return re.sub(r"(\d),(\d)", r"\1.\2", clean_text(str(value)))

    @classmethod
    def _barcode(cls, product: Dict[str, Any]) -> str:
        """EAN производителя; внутренние коды вида «1K35052T0HFXS» штрихкодом не считаем."""
        attrs = product.get("attributes") or {}
        value = next((str(attrs[key]).strip() for key in cls.BARCODE_KEYS if attrs.get(key)), "")
        return value if value.isdigit() and 8 <= len(value) <= 14 else ""

    def _color_url(self, product: Dict[str, Any], variants: Any, color_key: str, color_code: str) -> str:
        """Ссылка цвета: у части размеров адрес вида /product/<pk>/ — берём /urun/…"""
        urls = [str(product.get("absolute_url") or "")] + [
            str((option.get("product") or {}).get("absolute_url") or "")
            for option in self._variant_options(variants, self.SIZE_KEYS)
            if self._color_code(option.get("product") or {}, color_key) == color_code
        ]
        url = next((u for u in urls if u.startswith("/urun/")), urls[0])
        return self._canonical_url(urljoin(self.base_url, url))

    @staticmethod
    def _extract_images(product: Dict[str, Any]) -> List[str]:
        rows = [
            row for row in product.get("productimage_set") or []
            if isinstance(row, dict) and row.get("image") and row.get("status", "active") == "active"
        ]
        rows.sort(key=lambda row: int(row.get("order") or 0))
        images: List[str] = []
        for row in rows:
            url = str(row["image"]).strip()
            if url not in images:
                images.append(url)
        return images

    @staticmethod
    def _basket_offers(product: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Скидка «в корзине» — только для менеджера; на витрине цена витрины."""
        offers = []
        for offer in product.get("basket_offers") or []:
            if not isinstance(offer, dict) or not offer.get("label"):
                continue
            kwargs = offer.get("listing_kwargs") or {}
            offers.append(
                {
                    "label": clean_text(str(offer["label"])),
                    "basket_price": SuperstepParser._price(kwargs.get("discounted_total_price")),
                }
            )
        return offers

    def _color_name(self, product: Dict[str, Any]) -> str:
        """Название цвета; капс («MAVİ», «SİYAH») — в обычный вид, как у остальных."""
        attrs = product.get("attributes") or {}
        keys = ("integration_renk_detay", "integration_hos_renk_detay", "integration_renk_tonu", "mp_color")
        color = next((clean_text(str(attrs[key])) for key in keys if attrs.get(key) not in (None, "", "-")), "")
        if color.isupper():
            lowered = color.replace("İ", "i").replace("I", "ı").lower()
            color = lowered[:1].upper() + lowered[1:]
        return color

    def _extra_attributes(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """Характеристики для правил/AI; служебное (скидка в корзине) на витрину не идёт."""
        attrs = product.get("attributes") or {}
        mapping = {
            "material": attrs.get("integration_erp_icerik"),
            "country_of_origin": attrs.get("integration_erp_mensei"),
            "season": attrs.get("integration_erp_sezon"),
            "collar": attrs.get("integration_yaka"),
            "size_advice": attrs.get("product_size_info"),
            "max_bag_limit": attrs.get("max_bag_limit"),
        }
        extra = {key: clean_text(str(value)) for key, value in mapping.items() if value not in (None, "", "-")}
        offers = self._basket_offers(product)
        if offers:
            extra["superstep_basket_offers"] = offers
        return extra

    @staticmethod
    def _description(product: Dict[str, Any]) -> str:
        attrs = product.get("attributes") or {}
        html = attrs.get("integration_kalem_icerik") or attrs.get("mp_description") or ""
        text = re.sub(r"<[^>]+>", " ", str(html))
        return clean_text(text)

    # Поля блока характеристик карточки SuperStep.
    FEATURE_FIELDS = (
        ("Marka", "integration_alt_marka"),
        ("Model", "integration_urun_detay"),
        ("Renk", "integration_renk_detay"),
        ("Cinsiyet", "integration_cinsiyet"),
        ("İçerik", "integration_erp_icerik"),
        ("Menşei", "integration_erp_mensei"),
        ("Yaka", "integration_yaka"),
    )

    @classmethod
    def _features_description(cls, product: Dict[str, Any]) -> str:
        """Описание из характеристик, если текста у источника нет."""
        parts = []
        for label, key in cls.FEATURE_FIELDS:
            value = cls._attr_label(product, key)
            if value and value != "-":
                parts.append(f"{label}: {value}")
        return "; ".join(parts)

    @staticmethod
    def _price(value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return round(float(str(value).replace(",", ".")), 2)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _selling_and_old_price(cls, product: Dict[str, Any]):
        """Цена витрины ``price`` и зачёркнутая цена, которую показывает сайт.

        Сайт зачёркивает «прежнюю цену» ``price_extra_field.previous_price``
        (турецкое правило о самой низкой цене за последние дни), а не
        ``retail_price``: Nautica 999,60 — зачёркнуто 1 249,50, не 2 499;
        Puma 401744 4 799 при previous 3 599 — не зачёркнуто ничего, хотя
        retail 5 999. Без ``previous_price`` зачёркнута ``retail_price``
        (Quiksilver 4 899 / 6 999). Сверено на сайте 04.11.2026.
        """
        price = cls._price(product.get("price"))
        extra = product.get("price_extra_field")
        if isinstance(extra, dict) and extra.get("previous_price") not in (None, ""):
            shown = cls._price(extra.get("previous_price"))
        else:
            shown = cls._price(product.get("retail_price"))
        return price, (shown if price and shown and shown > price else None)

    @staticmethod
    def _map_gender(value: Any) -> str:
        normalized = superstep_subgroup_key(value)
        return {"erkek": "men", "kadin": "women", "unisex": "unisex", "cocuk": "kids"}.get(normalized, "")
