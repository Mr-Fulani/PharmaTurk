"""Общий парсер магазинов на платформе Akinon (SuperStep, Intersport Турция, SPX).

Любая страница магазина с ``?format=json`` отдаёт данные готовым JSON, без
браузера и без разбора HTML.

- Список раздела — ``products`` и ``pagination``. Строка списка — один цвет
  модели; ``extra_data.variants`` — цвета модели и размеры этого цвета с
  признаком «есть/нет».
- Карточка — ``product`` и ``variants[].options[].product``: размеры со SKU и
  штрихкодом, цвета со ссылками. Размер у Akinon — отдельный «товар», модель
  объединяет ``base_code``; парсер собирает их обратно в одну карточку.

Поля товара — набор магазинов Eren Perakende (``integration_*``; у товаров
маркетплейса — ``mp_*``). Магазин-наследник задаёт ключ источника, адрес сайта и
раскладку по нашим разделам (``subgroup_route``); товар без маршрута не
загружается и попадает в отчёт прогона «не разложено».
"""

import json
import re
from abc import abstractmethod
from collections import Counter
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from apps.catalog.utils.tr_vocab import COLOR_DETAIL_SEPARATOR, translate_turkish_color

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


class AkinonFormatError(RuntimeError):
    """В JSON магазина нет ожидаемых ключей: формат сменился, а не «каталог пуст»."""


def akinon_key(label: Any) -> str:
    """Ключ для сравнения: без регистра и турецких букв («Sırt Çantası» → «sirt cantasi»)."""
    text = str(label or "").replace("İ", "i").replace("I", "ı").lower()
    text = text.translate(str.maketrans("çğıöşü", "cgiosu"))
    return re.sub(r"\s+", " ", text).strip()


class AkinonParser(BaseScraper):
    """Парсер магазина Akinon по JSON (``?format=json``), без прокси."""

    # Задаёт наследник: ключ источника (имя парсера, приставка external_id и
    # атрибутов), название для сообщений, адрес и домен сайта.
    SOURCE = ""
    SOURCE_TITLE = ""
    SITE_URL = ""
    DOMAIN = ""
    # Разделы, куда подгруппа кладётся за неимением точного, — видны в отчёте прогона.
    PARENT_PLACEMENTS: frozenset = frozenset()

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
    # Подгруппа, бренд, описание и название цвета: у SPX свои поля.
    SUBGROUP_KEY = "integration_alt_grup"
    BRAND_KEY = "integration_alt_marka"
    DESCRIPTION_KEYS: Tuple[str, ...] = ("integration_kalem_icerik", "mp_description")
    COLOR_NAME_KEYS: Tuple[str, ...] = (
        "integration_renk_detay", "integration_hos_renk_detay", "integration_renk_tonu", "mp_color",
    )
    DEFAULT_ASSUMED_STOCK_QUANTITY = 1000
    # Корни, у которых есть модели вариантов цвета (остальные — цвет = карточка).
    VARIANT_ROOTS = frozenset({"shoes", "clothing", "underwear", "headwear"})
    # Предохранитель: максимум цветов на одну карточку (защита от аномалий).
    MAX_COLOR_VARIANTS = 12
    # False — магазин закрыл страницы ``?page=`` в robots.txt: раздел читается
    # одной страницей, а не поместившийся останавливается с причиной.
    FOLLOW_PAGINATION = True

    def __init__(self, base_url: str = "", **kwargs):
        super().__init__(base_url=base_url or self.SITE_URL, delay_range=(1.5, 3), **kwargs)
        self.client.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                "Referer": f"{self.SITE_URL}/",
            }
        )
        self.unmapped: Counter = Counter()
        self.parent_placed: Counter = Counter()

    def get_name(self) -> str:
        return self.SOURCE

    def get_supported_domains(self) -> List[str]:
        return [self.DOMAIN, f"www.{self.DOMAIN}"]

    # --- ссылки --------------------------------------------------------------

    @classmethod
    def _is_site_host(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return not host or host == cls.DOMAIN or host.endswith(f".{cls.DOMAIN}")

    @classmethod
    def is_product_url(cls, url: str) -> bool:
        return cls._is_site_host(url) and bool(cls.PRODUCT_PATH_RE.match(urlparse(url).path or ""))

    @classmethod
    def is_category_url(cls, url: str) -> bool:
        """Раздел — любой не-товарный путь сайта, кроме главной."""
        path = urlparse(url).path or ""
        return (
            cls._is_site_host(url)
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
            self.logger.warning("%s: вместо JSON пришла страница (защита?) на %s", self.SOURCE_TITLE, url)
            raise ScraperAccessBlockedError(source=self.SOURCE_TITLE, status_code=403, url=url)
        if not isinstance(data, dict):
            raise AkinonFormatError(f"{self.SOURCE_TITLE}: ответ не объект JSON: {url}")
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
            raise SiteCategoriesError(f"{self.SOURCE_TITLE}: список разделов не загрузился: {url}")
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
    def _manufacturer_article(model_color_id: str) -> str:
        """Артикул производителя с цветом — запасной признак того же товара у FLO.

        «396464.01» → «396464.01», «34-IH9166.-» → «IH9166»: приставка продавца
        маркетплейса («34-», «265-») и пустой цвет «-» к артикулу не относятся.
        """
        value = re.sub(r"^\d{1,4}-(?=[0-9A-Za-z])", "", str(model_color_id or "").strip())
        return re.sub(r"\.-?$", "", value)

    @staticmethod
    def _attr_label(product: Dict[str, Any], key: str) -> str:
        """Подпись атрибута: у ``integration_alt_grup`` значение — код («088»), подпись — имя."""
        row = (product.get("attributes_kwargs") or {}).get(key)
        if isinstance(row, dict) and row.get("label"):
            return clean_text(str(row["label"]))
        return clean_text(str((product.get("attributes") or {}).get(key) or ""))

    def _category_route(self, product: Dict[str, Any], variants: Any = None) -> Tuple[str, Tuple[str, ...]]:
        """Подгруппа и маршрут. У части товаров маркетплейса нет
        ``integration_alt_grup`` (Nike 265-FN2713, зелёный цвет): тогда — подгруппа
        другого цвета той же модели (без запросов, из вариантов карточки), а
        если и её нет — по окончанию названия."""
        subgroup = self._attr_label(product, self.SUBGROUP_KEY)
        if not subgroup:
            for option in self._variant_options(variants, self.COLOR_KEYS):
                row = ((option.get("product") or {}).get("attributes_kwargs") or {}).get(self.SUBGROUP_KEY)
                label = clean_text(str((row or {}).get("label") or "")) if isinstance(row, dict) else ""
                if label and not label.isdigit():
                    subgroup = label
                    break
        attrs = product.get("attributes") or {}
        gender = self._gender(attrs)
        kids_gender = {"BOYS": "boys", "GIRLS": "girls"}.get(str(attrs.get("integration_erp_cinsiyet") or "").upper(), "")
        return self.subgroup_route(subgroup, product.get("name"), self._brand(product), gender, kids_gender)

    @classmethod
    @abstractmethod
    def subgroup_route(
        cls, subgroup: Any, name: Any, brand: Any, gender: str, kids_gender: str = ""
    ) -> Tuple[str, Tuple[str, ...]]:
        """Подгруппа и маршрут (наши разделы от точного к корню) — без запросов.

        Пустой маршрут — товар не загружается и попадает в отчёт «не разложено».
        """
        raise NotImplementedError

    # Модификаторы перед цветом в названии: «Açık Mavi», «Koyu Gri», «Çok Renkli».
    NAME_COLOR_MODIFIERS = frozenset({"koyu", "acik", "kirik", "cok"})
    # Слова после цвета, которые относятся к нему: «Kum Rengi».
    NAME_COLOR_SUFFIXES = frozenset({"rengi", "renk", "tonu"})
    # Цвет перед этими словами — узор, а не цвет варианта: «Kamuflaj Desenli».
    NAME_PATTERN_WORDS = frozenset({"desenli", "desen", "baskili", "baski"})

    @classmethod
    def _model_name(cls, product: Dict[str, Any], colors_count: int, brand: str = "") -> str:
        """Название модели без цвета варианта: «Nautica Erkek Gri Slim Fit … T-Shirt»
        → «Nautica Erkek Slim Fit … T-Shirt». Иначе карточка модели называлась бы
        по цвету, с которого начался обход, и у белого цвета в Списке заявки было
        «Nautica … Gri … — Белый». У модели одного цвета название не меняется.
        Убираются только цвета словаря (и «Açık/Koyu/Çok» перед ними, «Rengi» после),
        а не слова вроде «Baskılı», которые описывают сам товар. Не трогаются бренд,
        совпадающий с цветом («Mavi»), и узор («Kamuflaj Desenli»)."""
        name = clean_text(str(product.get("name") or ""))
        if colors_count < 2:
            return name
        tokens = name.split()

        def is_color(token: str) -> bool:
            parts = [part for part in re.split(r"[/-]", token) if part]
            return bool(parts) and all(
                part.lower() not in cls.EN_COLOR_WORDS and translate_turkish_color(part, "en") for part in parts
            )

        keys = [akinon_key(token) for token in tokens]
        brand_keys = akinon_key(brand).split()
        # Бренд, совпадающий с цветом («Mavi»): защищён в начале названия, а если
        # названия с бренда не начинается — любое слово бренда.
        if brand_keys and keys[: len(brand_keys)] == brand_keys:
            protected = set(range(len(brand_keys)))
        else:
            protected = {index for index, key in enumerate(keys) if key in brand_keys}
        drop = {
            index for index, token in enumerate(tokens)
            if is_color(token)
            and index not in protected
            and (index + 1 >= len(tokens) or keys[index + 1] not in cls.NAME_PATTERN_WORDS)
        }
        drop |= {index - 1 for index in drop if index > 0 and keys[index - 1] in cls.NAME_COLOR_MODIFIERS}
        drop |= {index + 1 for index in drop if index + 1 < len(tokens) and keys[index + 1] in cls.NAME_COLOR_SUFFIXES}
        neutral = " ".join(token for index, token in enumerate(tokens) if index not in drop)
        return neutral or name

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
        parts = []
        if self.unmapped:
            top = ", ".join(f"{name or 'без подгруппы'} {count}" for name, count in self.unmapped.most_common(12))
            parts.append(f"Не разложено (не загружены): {sum(self.unmapped.values())} строк — {top}.")
        if self.parent_placed:
            top = ", ".join(f"{name} {count}" for name, count in self.parent_placed.most_common(12))
            parts.append(
                f"В родительском разделе (точного нет): {sum(self.parent_placed.values())} товаров — {top}."
            )
        return " ".join(parts)

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
        self.parent_placed = Counter()
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
                    raise CategoryPageNotFoundError(f"{self.SOURCE_TITLE}: раздел не найден: {category_url}")
                self.has_more_pages = False
                self.stop_reason = f"{self.SOURCE_TITLE} вернул пустую страницу раздела: {page_url}"
                break
            tiles = data.get("products")
            pagination = data.get("pagination")
            if not isinstance(tiles, list) or not isinstance(pagination, dict):
                raise AkinonFormatError(f"{self.SOURCE_TITLE}: в списке нет products/pagination: {page_url}")
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
                subgroup, route = self._category_route(tile, (tile.get("extra_data") or {}).get("variants"))
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
                            covers=product.attributes.get(f"{self.SOURCE}_color_ids") or [],
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
            if has_next and not self.FOLLOW_PAGINATION:
                self.has_more_pages = False
                self.stop_reason = (
                    f"Раздел не поместился на одну страницу: всего {pagination.get('total_count')} строк, "
                    f"загружены первые {len(tiles)}. Нужна более узкая ссылка раздела."
                )
                break
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
        for color_id in product.attributes.get(f"{self.SOURCE}_color_ids") or []:
            self.catalog_state.mark_product(color_id)

    # --- карточка ------------------------------------------------------------

    def _card(self, url: str) -> Optional[Dict[str, Any]]:
        data = self._fetch_json(self._json_url(self._canonical_url(url)))
        if data is None:
            return None
        if not isinstance(data.get("product"), dict) or not isinstance(data.get("variants"), list):
            raise AkinonFormatError(f"{self.SOURCE_TITLE}: в карточке нет product/variants: {url}")
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
        subgroup, route = self._category_route(product, card["variants"])
        if not route:
            self.unmapped[subgroup] += 1
            self.logger.warning(
                "%s: не разложено — подгруппы «%s» нет в таблице раскладки (или она не загружается "
                "по решению владельца), товар не загружен: %s",
                self.SOURCE_TITLE,
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
                    self.logger.warning("%s: цвет %s не открылся по %s", self.SOURCE_TITLE, code, url)
                    continue
                color_rows.append((code, sibling))

        variants = [
            self._build_color_variant(color_card, color_order.get(code, len(color_order)))
            for code, color_card in color_rows
        ]
        details = self._color_details(card, {code: color_card["product"] for code, color_card in color_rows})
        for (code, color_card), variant in zip(color_rows, variants):
            if code in details:
                variant["color"] = f"{variant['color']}{COLOR_DETAIL_SEPARATOR}{details[code]}"[:50]
                name = clean_text(str(color_card["product"].get("name") or ""))
                variant["display_name"] = clean_text(f"{name} - {variant['color']}".strip(" -"))
        if route[0] in self.PARENT_PLACEMENTS:
            self.parent_placed[f"{subgroup} → {route[0]}"] += 1
        variants.sort(key=lambda variant: variant["sort_order"])
        # Главный — первый по порядку сайта цвет в наличии, как в сервисе
        # (``default_fashion_variant``): цена товара не зависит от того, с какого
        # цвета начали разбор, и не берётся у распроданного цвета.
        primary = next((v for v in variants if v["is_available"]), variants[0])
        all_sizes: List[str] = []
        for variant in variants:
            for row in variant["sizes"]:
                if row["size"] not in all_sizes:
                    all_sizes.append(row["size"])

        attrs = product.get("attributes") or {}
        is_available = any(v["is_available"] for v in variants)
        attributes: Dict[str, Any] = {
            "color": primary["color"],
            "gender": self._gender(attrs),
            "sizes": all_sizes,
            f"{self.SOURCE}_subgroup": subgroup,
            f"{self.SOURCE}_category_slugs": list(route),
            f"{self.SOURCE}_color_ids": [v["sku"] for v in variants],
        }
        if with_variants:
            external_id = f"{self.SOURCE}-{product.get('base_code') or product.get('sku')}"
            sku = str(product.get("base_code") or "")
            attributes.update({"fashion_variants": variants, "variant_group_id": external_id})
        else:
            external_id = f"{self.SOURCE}-{primary['sku']}"
            sku = primary["sku"]
        attributes.update(self._extra_attributes(product))

        return ScrapedProduct(
            name=(
                self._model_name(product, len(color_options), self._brand(product))
                if with_variants
                else clean_text(str(product.get("name") or ""))
            ),
            description=self._description(product) or self._features_description(product),
            price=primary["price"],
            old_price=primary["old_price"],
            currency="TRY",
            url=primary["external_url"],
            images=primary["images"],
            category=route[0],
            brand=self._brand(product),
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
            raise ScraperAccessBlockedError(source=self.SOURCE_TITLE, status_code=403, url=url)
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
                f"{self.SOURCE_TITLE}: redirect away from product page to {final_url}",
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
            offer.variant_key.removeprefix(f"{self.SOURCE}-variant-")
            if offer.variant_key
            else offer.external_sku
        )
        base_code = model_color.rpartition(".")[0]
        if not base_code:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                f"{self.SOURCE_TITLE}: product page is missing and offer has no model code",
                retryable=False,
            )
        search_url = self._json_url("/list/?" + urlencode({"search_text": base_code}))
        try:
            data, _ = self._offer_json(search_url)
        except httpx.HTTPStatusError as exc:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                f"{self.SOURCE_TITLE}: search returned HTTP {exc.response.status_code}",
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
                f"{self.SOURCE_TITLE}: color is listed in search but its page is missing",
                retryable=True,
            )
        if int((data.get("pagination") or {}).get("num_pages") or 1) > 1:
            raise OfferSourceUnavailable(
                OfferCheckErrorCode.TRANSPORT_ERROR,
                f"{self.SOURCE_TITLE}: color is not on the first search page",
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
            "external_id": f"{self.SOURCE}-variant-{self._model_color_id(product, card['variants'])}",
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
            "mpn": self._manufacturer_article(self._model_color_id(product, card["variants"])),
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

    AGE_SIZE_RE = re.compile(r"^(\d+)(?:-(\d+))?\s*(yas|ay)$")

    @classmethod
    def _size_sort_key(cls, option: Dict[str, Any], index: int) -> tuple:
        """Детские «10K…13.5K» — первыми, затем числовые («1.5», «28,5»,
        «32-33») по числу: ``order`` у Akinon бывает из разных систем (у
        детской обуви 2850, 3500, 200180…). Возрастные («18-24 Ay», «6 Yaş»,
        «13-14 Yaş») — по возрасту, месяцы раньше лет. Буквенные (XS…XXL) — по ``order``."""
        raw = clean_text(str(option.get("label") or ""))
        age = cls.AGE_SIZE_RE.match(akinon_key(raw))
        if age:
            months = int(age.group(1)) * (1 if age.group(3) == "ay" else 12)
            return (2, months, index)
        label = cls._normalize_size(raw)
        match = re.match(r"^(\d+(?:\.\d+)?)K$", label, re.IGNORECASE)
        if match:
            return (0, float(match.group(1)), index)
        match = re.match(r"^(\d+(?:\.\d+)?)(?:-\d+)?$", label)
        if match:
            return (1, float(match.group(1)), index)
        try:
            return (3, int(option.get("order")), index)
        except (TypeError, ValueError):
            return (3, index, index)

    @classmethod
    def _normalize_size(cls, value: Any) -> str:
        """«42,5» → «42.5»: полуразмеры хранятся с точкой, как у FLO.
        Возраст по-русски: «13-14 Yaş» → «13-14 лет», «2 Yaş» → «2 года»,
        «18-24 Ay» → «18-24 мес.» — турецкого слова в размере не остаётся."""
        text = clean_text(str(value))
        age = cls.AGE_SIZE_RE.match(akinon_key(text))
        if age:
            numbers = "-".join(n for n in age.group(1, 2) if n)
            unit = "мес." if age.group(3) == "ay" else cls._years_word(int(age.group(2) or age.group(1)))
            return f"{numbers} {unit}"
        return re.sub(r"(\d),(\d)", r"\1.\2", text)

    @staticmethod
    def _years_word(number: int) -> str:
        if number % 10 == 1 and number % 100 != 11:
            return "год"
        if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
            return "года"
        return "лет"

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

    @classmethod
    def _basket_offers(cls, product: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Скидка «в корзине» — только для менеджера; на витрине цена витрины."""
        offers = []
        for offer in product.get("basket_offers") or []:
            if not isinstance(offer, dict) or not offer.get("label"):
                continue
            kwargs = offer.get("listing_kwargs") or {}
            offers.append(
                {
                    "label": clean_text(str(offer["label"])),
                    "basket_price": cls._price(kwargs.get("discounted_total_price")),
                }
            )
        return offers

    def _color_name(self, product: Dict[str, Any]) -> str:
        """Название цвета; капс («MAVİ», «SİYAH») — в обычный вид, как у остальных."""
        attrs = product.get("attributes") or {}
        keys = self.COLOR_NAME_KEYS
        color = next((clean_text(str(attrs[key])) for key in keys if attrs.get(key) not in (None, "", "-")), "")
        if color.isupper():
            lowered = color.replace("İ", "i").replace("I", "ı").lower()
            color = lowered[:1].upper() + lowered[1:]
        return color

    def _color_details(self, card: Dict[str, Any], opened: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """Уточнения одинаковых названий цветов модели: код цвета → уточнение.

        У Puma 399025 два «Beyaz», у UGG 1173891 три «Kahverengi» — покупатель
        видел бы одинаковые цвета. Группы считаются по всем цветам модели, а не
        только по открытым, — уточнение не зависит от того, распродан ли соседний
        цвет. Название и расцветка — из карточки открытого цвета, а для
        неоткрытого — из его варианта в карточке: у собственных товаров магазина
        (``integration_*``) там полные атрибуты. У маркетплейса (``mp_*``) в
        вариантах названий нет, но цвета там группирует ``mp_color`` — одинаковых
        названий у разных вариантов не бывает.
        Уточнение — расцветка без турецких слов (``_colorway``), а если у группы
        она пустая или совпадает — код цвета (``integration_renk``: «CHE»).
        """
        color_key = self._color_key(card["variants"])
        options = self._variant_options(card["variants"], (color_key,))
        products = [opened.get(self._option_value(option)) or option.get("product") or {} for option in options]
        # Слова названий модели (Palermo, Lth, PUMA) — не уточнение цвета.
        model_words = {
            akinon_key(word)
            for product in [*products, *opened.values()]
            for word in re.findall(r"[^\W\d_]+", str(product.get("name") or ""))
        }
        groups: Dict[str, List[Tuple[str, str, str]]] = {}
        for option, product in zip(options, products):
            code = self._option_value(option)
            name = self._color_name(product)
            if name:
                fallback = str((product.get("attributes") or {}).get("integration_renk") or code)
                groups.setdefault(name.casefold(), []).append((code, self._colorway(product, model_words), fallback))
        details: Dict[str, str] = {}
        for rows in groups.values():
            if len(rows) < 2:
                continue
            colorways = [colorway for _, colorway, _ in rows]
            use_colorway = all(colorways) and len({c.casefold() for c in colorways}) == len(colorways)
            for code, colorway, fallback in rows:
                details[code] = colorway if use_colorway else fallback
        return details

    # Английские слова цвета: расцветка без них («TOZLU KAKAO») может быть
    # турецкой, а турецких слов на витрине и в фиде ВК быть не должно.
    EN_COLOR_WORDS = frozenset(
        """white black gray grey brown blue navy green red pink purple violet orange yellow
        beige cream ivory gold silver bronze chestnut sand olive khaki burgundy maroon teal
        turquoise charcoal tan camel mint lilac lavender coral rose multi multicolor natural
        nude stone taupe mocha espresso cinnamon rust wine sky sage moss slate graphite smoke
        indigo""".split()
    )
    # Оттенки сами по себе цветом не считаются: «Light Kakao» — турецкое «Kakao».
    EN_SHADE_WORDS = frozenset({"dark", "light", "pale", "bright", "deep"})
    # Турецкие модификаторы цвета (не цвета словаря): «KOYU GRI-Black» → «Black».
    TR_COLOR_MODIFIERS = frozenset(
        {
            "koyu", "acik", "kirik", "parlak", "mat", "tozlu", "cok", "renkli", "desenli", "melanj",
            "renk", "rengi", "tonu", "tonlu", "desen", "baskili", "cizgili", "metalik", "simli", "fume",
        }
    )

    @classmethod
    def _colorway(cls, product: Dict[str, Any], model_words: frozenset = frozenset()) -> str:
        """Расцветка производителя без турецких слов и названия модели или пусто.

        «BEYAZ-Velvet Moss» → «Velvet Moss» (турецкие цвета словаря убираются),
        «Palermo Lth PUMA White-Vapor Gray-Gum» → «White-Vapor Gray-Gum» (слова
        из названий модели ``model_words``, кроме английских цветов),
        «TOZLU KAKAO» → «» (латиница без английского цвета — не берём).
        """

        def keep(match):
            word = match.group(0)
            if cls._is_turkish_color_word(word):
                return ""
            if akinon_key(word) in model_words and word.lower() not in cls.EN_COLOR_WORDS:
                return ""
            return word

        text = clean_text(str((product.get("attributes") or {}).get("integration_erp_renk_aciklama") or ""))
        text = re.sub(r"[^\W\d_]+", keep, text)
        text = re.sub(r"\(\s*\)", "", text)
        text = re.sub(r"\s*([/-])\s*", r"\1", text)
        text = re.sub(r"([/-])(?:[/-])+", r"\1", text)
        text = clean_text(text).strip(" -/")
        words = re.findall(r"[^\W\d_]+", text)
        if not words or not all(word.isascii() for word in words):
            return ""
        if not any(word.lower() in cls.EN_COLOR_WORDS for word in words):
            return ""
        return text

    @classmethod
    def _is_turkish_color_word(cls, word: str) -> bool:
        """Турецкое слово цвета или модификатор; английские цвета, совпадающие со
        словарём («INDIGO»), остаются — иначе «INDIGO-White» терял бы смысл."""
        if word.lower() in cls.EN_COLOR_WORDS | cls.EN_SHADE_WORDS:
            return False
        return bool(translate_turkish_color(word, "en")) or akinon_key(word) in cls.TR_COLOR_MODIFIERS

    # Аббревиатуры брендов, которые пишутся капсом.
    BRAND_ABBREVIATIONS = frozenset({"UGG", "EA7", "DC", "HUF", "ASICS", "DKNY", "BOSS", "NBA", "NFL", "MLB"})
    # Подпись бренда у магазина → как пишет производитель (и как бренд записан в каталоге).
    BRAND_ALIASES = {"mc kinley": "McKinley"}

    def _brand(self, product: Dict[str, Any]) -> str:
        """Бренд; капс («STANLEY», «LEVI'S») — в обычный регистр без турецкой
        замены I→ı (было бы «Nıke», «Tımberland»). Аббревиатуры (DKNY, UGG,
        ASICS) не трогаем. Существующий бренд каталог находит без учёта
        регистра (``get_or_create_scraped_brand``) и пишет как в базе."""
        brand = self._attr_label(product, self.BRAND_KEY)
        brand = self.BRAND_ALIASES.get(akinon_key(brand), brand)
        if not brand.isupper():
            return brand
        words = []
        for word in brand.split():
            keep = word in self.BRAND_ABBREVIATIONS or (len(word) <= 4 and not re.search(r"[AEIOUİÖÜ]", word))
            # «KİNETİX»: İ → I до capitalize(), иначе «Ki̇neti̇x» с комбинируемой точкой.
            words.append(word if keep else word.replace("İ", "I").capitalize())
        return " ".join(words)

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
            extra[f"{self.SOURCE}_basket_offers"] = offers
        return extra

    @classmethod
    def _description(cls, product: Dict[str, Any]) -> str:
        attrs = product.get("attributes") or {}
        html = next((attrs[key] for key in cls.DESCRIPTION_KEYS if attrs.get(key)), "")
        text = re.sub(r"<[^>]+>", " ", str(html))
        return clean_text(text)

    # Поля блока характеристик карточки.
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

    # Атрибуты пола по порядку: у Intersport ``integration_cinsiyet`` пуст, пол — в фильтре.
    GENDER_KEYS: Tuple[str, ...] = ("integration_cinsiyet",)

    @classmethod
    def _gender(cls, attrs: Dict[str, Any]) -> str:
        return next((gender for gender in (cls._map_gender(attrs.get(key)) for key in cls.GENDER_KEYS) if gender), "")

    @staticmethod
    def _map_gender(value: Any) -> str:
        normalized = akinon_key(value)
        return {"erkek": "men", "kadin": "women", "unisex": "unisex", "cocuk": "kids"}.get(normalized, "")
