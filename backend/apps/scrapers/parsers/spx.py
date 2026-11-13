"""Парсер SPX — Sport Point Extreme (spx.com.tr): спортивный инвентарь и снаряжение.

Платформа та же, что у SuperStep и Intersport (Akinon, ``?format=json``), вся работа с
сайтом — в общем ``AkinonParser`` (``akinon.py``). Здесь — своё:

- **Что берём.** Только раздел «Ekipman» (горнолыжные маски и шлемы, ракетки и струны,
  плавание, кемпинг, термосы и фляги, беговые дорожки) — решение владельца 12.11.2026
  (reports/empty-sections-and-decathlon-2026-11-12.md). Одежда, обувь и наушники не
  загружаются; товары, которые не везём (ножи, баллоны со сжатым газом, экзоскелеты с
  аккумулятором), — тоже. Раздел у нас — по группе и подгруппе магазина
  (``integration_product_group`` + ``integration_product_sub_group``): группа отличает
  велосипедный шлем от горнолыжного. Подгруппы без маршрута попадают в отчёт прогона
  «не разложено».
- **Поля.** Не ``integration_alt_grup``/``integration_alt_marka``, как у SuperStep, а
  ``integration_product_sub_group``, ``integration_brand``, ``description_sol``; штрихкод —
  ``sku`` товара; пол — код (``UNI``, ``ERK``, ``KDN``, ``U-CCK``). Кода цвета модели нет:
  карточка — артикул магазина (``integration_item_code``) и код цвета.
- **Обход.** robots.txt закрывает фильтры (``*integration_*``, ``category_ids``), но не
  страницы ``?page=``: три раздела «Ekipman» (мужской, женский, детский) читаются по
  страницам. Унисекс есть во всех трёх — повтор не открывает карточку.
- **Объём.** У термосов и фляг объём — в поле размера («0,47 LT», «21 OZ»). Он идёт в
  название («… 470 ml»): у кружек Stanley одной расцветки на 0,35 и 0,47 л иначе было бы
  одинаковое название.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from apps.catalog.utils.tr_vocab import translate_turkish_color

from ..base.scraper import ScrapedProduct, SiteCategoriesError
from ..base.utils import clean_text
from .akinon import AkinonParser, akinon_key

_FITNESS = ("fitness-accessories", "fitness-gym", "sports")
_TENNIS = ("tennis", "racket-sports", "sports")
_RACKET = ("racket-sports", "sports")
_SWIMMING = ("swimming", "water-sports", "sports")
_DIVING = ("diving", "water-sports", "sports")
_WATER = ("water-sports", "sports")
_WINTER = ("winter-sports", "sports")
_WINTER_GEAR = ("winter-protective-gear", *_WINTER)
_OUTDOOR = ("outdoor-hiking", "sports")
_CYCLING_ACCESSORIES = ("cycling-accessories", "cycling", "sports")
_THERMOSES = ("thermoses", "drinkware", "tableware")
_SPORTS = ("sports",)

# Подгруппа магазина → наш раздел. Нет в таблице — товар не загружается («не разложено»).
SPX_SUBGROUP_ROUTES: Dict[str, Tuple[str, ...]] = {
    # термосы и фляги — в «Посуду», как у SuperStep
    "termos": _THERMOSES,
    "mug": _THERMOSES,
    "matara": _THERMOSES,
    "suluk": _THERMOSES,
    "yemek termosu": ("thermal-containers", "food-storage", "tableware"),
    # зимние виды
    "goggle": ("winter-goggles", *_WINTER_GEAR),
    "kask": ("winter-helmets", *_WINTER_GEAR),
    "kask kilifi": _WINTER_GEAR,
    "koruma ekipmani": _WINTER_GEAR,
    "snowboard baglamasi": ("snowboards", *_WINTER),
    # ракетки
    "tenis raket": ("tennis-rackets", *_TENNIS),
    "tenis topu": ("tennis-balls", *_TENNIS),
    "tenis raket gribi": _TENNIS,
    "tenis top sepeti": _TENNIS,
    "tenis topu kova": _TENNIS,
    "kordaj rulo": _TENNIS,
    "kordaj paket": _TENNIS,
    "padel raket": _RACKET,
    "padel aksesuar": _RACKET,
    "pickleball raket": _RACKET,
    "pickleball raket seti": _RACKET,
    "pickleball file": _RACKET,
    "pickleball top": _RACKET,
    # плавание и вода
    "yuzucu gozlugu": ("swimming-goggles", *_SWIMMING),
    "yuzucu bonesi": ("swim-caps", *_SWIMMING),
    "palet": ("swim-fins", *_SWIMMING),
    "yuzucu tahtasi": ("kickboards", *_SWIMMING),
    "parmak paleti": _SWIMMING,
    "yuzucu el paleti": _SWIMMING,
    "pullbuoy": _SWIMMING,
    "gozluk kabi": _SWIMMING,
    "yuzme koltugu": _SWIMMING,
    "snorkel": ("snorkels", *_DIVING),
    # Madwave «Scuba Mask Full Face» — полнолицевая маска с трубкой.
    "yuzucu maskesi": ("diving-masks", *_DIVING),
    "maske ve snorkel set": ("diving-masks", *_DIVING),
    "maske palet ve snorkel set": ("diving-masks", *_DIVING),
    "wetsuit": ("wetsuits", *_DIVING),
    "can yelegi": _WATER,
    "neopren yelek": _WATER,
    # туризм и кемпинг
    "cadir": ("tents", *_OUTDOOR),
    "fener": ("flashlights", *_OUTDOOR),
    "aydinlatma": ("flashlights", *_OUTDOOR),
    "uyku tulumu": ("sleeping-bags", *_OUTDOOR),
    "sandalye": _OUTDOOR,
    "masa": _OUTDOOR,
    "mat": _OUTDOOR,
    "sisme yatak": _OUTDOOR,
    "sisme mobilya": _OUTDOOR,
    "plaj sandalyesi": _OUTDOOR,
    "portatif mutfak": _OUTDOOR,
    "barbeku": _OUTDOOR,
    "sogutucu canta": _OUTDOOR,
    "buz kutusu": _OUTDOOR,
    "elektrikli buz kutusu": _OUTDOOR,
    # фитнес и бег
    "yoga mat": ("yoga-mats", *_FITNESS),
    "fitness eldiveni": ("fitness-gloves", *_FITNESS),
    "atlama ipi": ("jump-ropes", *_FITNESS),
    "el agirligi": _FITNESS,
    "masaj aleti": _FITNESS,
    "dirsek destegi": _FITNESS,
    "ayak bilekligi": _FITNESS,
    "dizlik": _SPORTS,
    "voleybol dizligi": ("volleyball-knee-pads", "volleyball", "team-sports", "sports"),
    "kosu bandi": ("treadmills", "cardio-equipment", "fitness-gym", "sports"),
    # велоспорт
    "kilit": ("bike-locks", *_CYCLING_ACCESSORIES),
    "hiz sensoru": _CYCLING_ACCESSORIES,
    "trainer": _CYCLING_ACCESSORIES,
}

# Та же подгруппа в другой группе магазина: шлемы и фонари «Tekerlekli Sporlar» —
# велосипедные, наколенник оттуда же — велозащита.
SPX_GROUP_ROUTES: Dict[Tuple[str, str], Tuple[str, ...]] = {
    ("tekerlekli sporlar", "kask"): ("cycling-helmets", *_CYCLING_ACCESSORIES),
    ("tekerlekli sporlar", "aydinlatma"): ("bike-lights", *_CYCLING_ACCESSORIES),
    ("tekerlekli sporlar", "dizlik"): _CYCLING_ACCESSORIES,
    ("kosu/fitness", "dizlik"): _FITNESS,
}

# «Çeşitli Aksesuar» — смешанная подгруппа (ножи Victorinox, экзоскелеты, фонари, лопата):
# берётся только товар с понятным видом в названии.
SPX_MIXED_SUBGROUPS = frozenset({"cesitli aksesuar"})
SPX_NAME_ROUTES: Dict[str, Tuple[str, ...]] = {
    "kamp lambasi": ("flashlights", *_OUTDOOR),
    "kurek": _OUTDOOR,
    "sisme doga mobilyasi": _OUTDOOR,
    "guneslik": _OUTDOOR,
    "vibrasyon onleyici": _TENNIS,
    "splitboard skins": _WINTER,
}

# Не везём, в какой бы подгруппе ни лежало: складные ножи, баллоны со сжатым газом,
# экзоскелеты с аккумулятором.
SPX_SKIPPED_NAME_WORDS = frozenset({"caki", "cartridge", "exoskeleton"})
# Бренды, которые уже приходят из другого магазина без общего штрихкода: Stanley есть у
# SuperStep (103 товара на 13.11.2026), склеить одинаковые термосы нечем.
SPX_SKIPPED_BRANDS = frozenset({"stanley"})

# Разделы «за неимением точного» — видны в отчёте прогона.
SPX_PARENT_PLACEMENTS = frozenset(
    {"sports", "racket-sports", "water-sports", "winter-sports", "winter-protective-gear", "outdoor-hiking"}
)

# Пол — код магазина.
SPX_GENDERS = {
    "UNI": "unisex",
    "ERK": "men",
    "KDN": "women",
    "CCK": "kids",
    "U-CCK": "kids",
    "E-CCK": "kids",
    "K-CCK": "kids",
}

# Объём в поле размера: «0,47 LT», «0.5L», «21 OZ», «200 ml», «0.70» (литры без единицы).
_VOLUME_SIZE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(lt|l|ml|oz)?$", re.IGNORECASE)
# Объём уже в названии: «355 Ml», «0.5L», «12 Oz», «1,5 Litre».
_NAME_VOLUME_RE = re.compile(r"\d\s*(?:ml|lt|l|oz|litre)\b", re.IGNORECASE)
OUNCE_ML = 29.5735


def spx_group_key(group: Any) -> str:
    """«KAYAK/SNOWBOARD EKİPMAN» → «kayak/snowboard»: вид спорта без «Ekipman/Aksesuar»."""
    return re.sub(r"\s+(ekipman|aksesuar|tekstil)$", "", akinon_key(group))


def spx_route(group: Any, subgroup: Any, name: Any, brand: Any) -> Tuple[str, ...]:
    """Наш раздел по группе, подгруппе и названию; пусто — товар не загружается."""
    words = set(akinon_key(re.sub(r"[/,()\-]", " ", str(name or ""))).split())
    if words & SPX_SKIPPED_NAME_WORDS or akinon_key(brand) in SPX_SKIPPED_BRANDS:
        return ()
    key = akinon_key(subgroup)
    if key in SPX_MIXED_SUBGROUPS:
        text = f" {' '.join(akinon_key(re.sub(r'[/,()]', ' ', str(name or ''))).split())} "
        return next((route for phrase, route in SPX_NAME_ROUTES.items() if f" {phrase} " in text), ())
    return SPX_GROUP_ROUTES.get((spx_group_key(group), key)) or SPX_SUBGROUP_ROUTES.get(key, ())


def spx_volume_ml(size: Any) -> str:
    """Объём из поля размера в миллилитрах («0,47 LT» → «470 ml»); не объём — пусто."""
    match = _VOLUME_SIZE_RE.match(clean_text(str(size or "")))
    if not match:
        return ""
    amount = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "").lower()
    if unit == "ml":
        ml = amount
    elif unit == "oz":
        ml = amount * OUNCE_ML
    elif unit in ("l", "lt") or (amount < 5 and re.search(r"[.,]", match.group(1))):
        # Без единицы — литры, только дробь («0.70»): целое число («2» — размер ручки ракетки,
        # «50», «75») объёмом не считаем (пилот 13.11.2026: «Dunlop … 2000 ml»).
        ml = amount * 1000
    else:
        return ""
    return f"{round(ml)} ml" if ml >= 10 else ""


_GENDER_WORDS = frozenset({"unisex", "erkek", "kadin", "cocuk", "kiz"})


def spx_name_with_article(name: str, brand: Any, subgroup: Any, article: str) -> str:
    """Название без модели — с артикулом после бренда.

    «Salice Unisex Goggle» у SPX — восемь разных масок (105DARWF, 101DARWF, 915RW …):
    без артикула у них одно название на всех. В названии кроме бренда, пола, цвета и вида
    товара ничего нет — артикул магазина и есть модель: «Salice 105DARWF Unisex Goggle».
    """
    tokens = name.split()
    brand_words = akinon_key(brand).split()
    drop = set(brand_words) | _GENDER_WORDS | set(akinon_key(subgroup).split())
    if not article or any(akinon_key(t) not in drop and not translate_turkish_color(t, "en") for t in tokens):
        return name
    head = len(brand_words) if [akinon_key(t) for t in tokens[: len(brand_words)]] == brand_words else 0
    return " ".join([*tokens[:head], article, *tokens[head:]])


class SpxParser(AkinonParser):
    """Парсер spx.com.tr по JSON Akinon: спортивное снаряжение, без прокси."""

    SOURCE = "spx"
    SOURCE_TITLE = "SPX"
    SITE_URL = "https://www.spx.com.tr"
    DOMAIN = "spx.com.tr"
    PARENT_PLACEMENTS = SPX_PARENT_PLACEMENTS

    # Карточка — адрес из одного сегмента («/oakley-mod1-pro-erkek-kask-antrasit-465-s1-19764/»)
    # или «/product/<pk>/»; раздел — «/erkek/ekipman/».
    PRODUCT_PATH_RE = re.compile(r"^/(?:[a-z0-9]+(?:-[a-z0-9]+){3,}|product/\d+)/?$", re.IGNORECASE)
    COLOR_KEYS = ("integration_color_code",)
    SIZE_KEYS = ("integration_first_size",)
    SUBGROUP_KEY = "integration_product_sub_group"
    GROUP_KEY = "integration_product_group"
    BRAND_KEY = "integration_brand"
    DESCRIPTION_KEYS = ("description_sol",)
    COLOR_NAME_KEYS = ("filterable_color",)
    GENDER_KEYS = ("integration_gender",)
    FEATURE_FIELDS = (
        ("Marka", "integration_brand"),
        ("Renk", "integration_color"),
        ("Cinsiyet", "integration_gender"),
        ("Menşei", "integration_country"),
    )
    EQUIPMENT_ROOTS = ("/erkek/ekipman/", "/kadin/ekipman/", "/cocuk/ekipman/")

    @classmethod
    def subgroup_route(
        cls, subgroup: Any, name: Any, brand: Any, gender: str, kids_gender: str = ""
    ) -> Tuple[str, Tuple[str, ...]]:
        """Без группы магазина: раздел по подгруппе и названию."""
        subgroup = clean_text(str(subgroup or ""))
        return subgroup, spx_route("", subgroup, name, brand)

    def _category_route(self, product: Dict[str, Any], variants: Any = None) -> Tuple[str, Tuple[str, ...]]:
        subgroup = self._attr_label(product, self.SUBGROUP_KEY)
        group = self._attr_label(product, self.GROUP_KEY)
        return subgroup, spx_route(group, subgroup, product.get("name"), self._brand(product))

    @staticmethod
    def _map_gender(value: Any) -> str:
        return SPX_GENDERS.get(clean_text(str(value or "")).upper(), "")

    def _model_color_id(self, product: Dict[str, Any], variants: Any = None) -> str:
        """Артикул магазина и код цвета: «465-S1.19764», «SIGG-8973.80.=37».

        Размеры одного цвета у SPX — один артикул (шлем Oakley Mod1 Pro S…XL); один и тот
        же товар бывает в выдаче дважды под разными ``base_code`` — артикул их склеивает.
        """
        attrs = product.get("attributes") or {}
        item = re.sub(r"\s+", "-", clean_text(str(attrs.get("integration_item_code") or attrs.get("erp_item_code") or "")))
        color = self._color_code(product, self._color_key(variants))
        return f"{item or product.get('base_code') or product.get('sku') or ''}.{color}"

    @staticmethod
    def _manufacturer_article(model_color_id: str) -> str:
        """Артикул без кода цвета: «465-S1.19764» → «465-S1» (приставки продавца у SPX нет)."""
        return str(model_color_id or "").rsplit(".", 1)[0]

    @classmethod
    def _barcode(cls, product: Dict[str, Any]) -> str:
        """Штрихкод — ``sku`` товара (EAN-13 / UPC)."""
        value = str(product.get("sku") or "").strip()
        return value if value.isdigit() and 8 <= len(value) <= 14 else ""

    def parse_categories(self) -> List[Dict[str, Any]]:
        """Три раздела «Ekipman» — читаются по страницам."""
        rows = []
        for root in self.EQUIPMENT_ROOTS:
            url = urljoin(self.base_url + "/", root.lstrip("/"))
            data = self._fetch_json(self._json_url(url))
            if not data:
                raise SiteCategoriesError(f"{self.SOURCE_TITLE}: раздел снаряжения не загрузился: {url}")
            total = int((data.get("pagination") or {}).get("total_count") or 0)
            if total > 0:
                rows.append({"name": f"Ekipman {root.strip('/').split('/')[0]}", "url": url, "external_id": root})
        return self._site_categories(rows)

    def parse_product_detail(self, product_url: str, *, include_sibling_variants: bool = True) -> Optional[ScrapedProduct]:
        product = super().parse_product_detail(product_url, include_sibling_variants=include_sibling_variants)
        if product is None:
            return None
        product.name = spx_name_with_article(
            product.name, product.brand, product.attributes.get(f"{self.SOURCE}_subgroup"), self._manufacturer_article(product.sku)
        )
        # Объём — не размер: в название (если его там нет) и из размеров. Только у посуды
        # (термосы, кружки, фляги): у ракетки размер ручки «2» — не литры.
        if (product.attributes.get(f"{self.SOURCE}_category_slugs") or [""])[-1] != "tableware":
            return product
        sizes = product.attributes.get("sizes") or []
        volumes = {spx_volume_ml(size) for size in sizes}
        if len(sizes) == 1 and len(volumes) == 1 and "" not in volumes:
            volume = volumes.pop()
            if not _NAME_VOLUME_RE.search(product.name):
                product.name = f"{product.name} {volume}"
            product.attributes["sizes"] = []
            product.attributes["volume"] = volume
        return product
