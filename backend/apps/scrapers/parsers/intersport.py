"""Парсер Intersport Турция (intersport.com.tr) — только спортивный инвентарь.

Тот же владелец и та же платформа Akinon, что у SuperStep: поля товара совпадают,
вся работа с сайтом — в общем ``AkinonParser`` (``akinon.py``). Здесь — своё:

- **Что берём.** Обувь и одежда Intersport — те же Nike, adidas и др., что уже
  приходят из SuperStep и FLO, поэтому загружается только инвентарь: мячи,
  ракетки, очки и шапочки для плавания, шлемы, гантели, палатки (решение
  владельца 12.11.2026, reports/empty-sections-and-decathlon-2026-11-12.md).
  Товар берётся, если его подгруппа сайта — инвентарь
  (``INTERSPORT_SUBGROUP_ROUTES``); раздел у нас — по виду товара в названии
  (``INTERSPORT_NAME_ROUTES``), а без него — раздел подгруппы. Остальное не
  загружается и попадает в отчёт прогона «не разложено».
- **Обход.** robots.txt магазина закрывает для роботов страницы ``?page=``.
  Раздел инвентаря (``/erkek-spor-ekipmanlari/`` — 600 строк, 9 страниц) режется
  фильтром подгруппы ``?attributes_integration_alt_grup=<код>``: каждая подгруппа
  помещается на одну страницу (72 строки), вторая страница не запрашивается.
  Раздел, который не поместился, останавливается с понятной причиной.
- **Двойники.** Код цвета модели (``integration_model_renk``) у Intersport и
  SuperStep один и тот же; товар, который уже есть из SuperStep, сервис не создаёт
  (``SIBLING_STORE_SOURCES`` в ``services.py``).
"""

import re
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode, urljoin

from ..base.scraper import SiteCategoriesError
from ..base.utils import clean_text
from .akinon import AkinonParser, akinon_key

_FOOTBALL = ("football", "team-sports", "sports")
_BASKETBALL = ("basketball", "team-sports", "sports")
_VOLLEYBALL = ("volleyball", "team-sports", "sports")
_TEAM = ("team-sports", "sports")
_TENNIS = ("tennis", "racket-sports", "sports")
_BADMINTON = ("badminton", "racket-sports", "sports")
_TABLE_TENNIS = ("table-tennis", "racket-sports", "sports")
_RACKET = ("racket-sports", "sports")
_SWIMMING = ("swimming", "water-sports", "sports")
_DIVING = ("diving", "water-sports", "sports")
_FITNESS = ("fitness-accessories", "fitness-gym", "sports")
_STRENGTH = ("strength-equipment", "fitness-gym", "sports")
_MARTIAL = ("martial-arts", "sports")
_WINTER = ("winter-sports", "sports")
_WINTER_GEAR = ("winter-protective-gear", *_WINTER)
_OUTDOOR = ("outdoor-hiking", "sports")
_RUNNING = ("running-walking", "sports")
_SPORTS = ("sports",)

# Подгруппа сайта (``integration_alt_grup``) → раздел, если вид товара в названии
# не распознан. Пустой маршрут — подгруппа смешанная (перчатки для бега и
# вратарские в одной «Eldiven»; в «Spor Aksesuarları» — щитки, палатки, наушники
# и свистки): без вида в названии товар не берётся.
INTERSPORT_SUBGROUP_ROUTES: Dict[str, Tuple[str, ...]] = {
    "futbol topu": ("football-balls", *_FOOTBALL),
    "basketbol topu": ("basketball-balls", *_BASKETBALL),
    "top": _TEAM,
    "pompa": _TEAM,
    "tekmelik": ("shin-guards", *_FOOTBALL),
    "dizlik": ("volleyball-knee-pads", *_VOLLEYBALL),
    "kolluk": (),
    "eldiven": (),
    "korumalik": (),
    "yuzucu gozlugu": ("swimming-goggles", *_SWIMMING),
    "bone": ("swim-caps", *_SWIMMING),
    "palet": ("swim-fins", *_SWIMMING),
    "burun tikaci": _SWIMMING,
    "kulak tikaci": _SWIMMING,
    "yuzme aksesuari": _SWIMMING,
    "snorkel": ("snorkels", *_DIVING),
    "raket": _RACKET,
    "tenis raketi": ("tennis-rackets", *_TENNIS),
    "tenis aksesuari": _TENNIS,
    "antrenman aksesuari": (),
    "spor aksesuarlari": (),
    "fitness eldiveni": ("fitness-gloves", *_FITNESS),
    "atlama ipi": ("jump-ropes", *_FITNESS),
    "mat": ("yoga-mats", *_FITNESS),
    "agirlik": _FITNESS,
    "agirlik ekipmani": (),
    "boks eldiveni": ("boxing-gloves", *_MARTIAL),
    "bandaj": ("hand-wraps", "martial-arts-protective-gear", *_MARTIAL),
    "kayak & snowboard": _WINTER,
    "kayak gozlugu": ("winter-goggles", *_WINTER_GEAR),
    "kask": _SPORTS,
    "paten": _SPORTS,
    "kaykay": _SPORTS,
    "uyku tulumu": ("sleeping-bags", *_OUTDOOR),
}

# Вид товара в названии → раздел. Подгруппы сайта смешаны: в «Top» — волейбольные,
# теннисные и гимнастические мячи, в «Spor Aksesuarları» — щитки, палатки и
# лыжные маски. Побеждает самая длинная фраза («masa tenisi raketi» раньше
# «tenis raketi»); фраза ищется целыми словами в любом месте названия.
INTERSPORT_NAME_ROUTES: Dict[str, Tuple[str, ...]] = {
    # мячи
    "amerikan futbol topu": _TEAM,
    "amerikan futbolu topu": _TEAM,
    "basketbol potasi": ("basketball-hoops", *_BASKETBALL),
    "basketbol filesi": _BASKETBALL,
    "duduk": _TEAM,
    "futbol topu": ("football-balls", *_FOOTBALL),
    "basketbol topu": ("basketball-balls", *_BASKETBALL),
    "voleybol topu": ("volleyball-balls", *_VOLLEYBALL),
    "hentbol topu": _TEAM,
    "top pompasi": _TEAM,
    "pompa ucu": _TEAM,
    "masa tenisi topu": ("table-tennis-balls", *_TABLE_TENNIS),
    "masa tenis topu": ("table-tennis-balls", *_TABLE_TENNIS),
    "tenis topu": ("tennis-balls", *_TENNIS),
    "badminton topu": ("shuttlecocks", *_BADMINTON),
    "padel topu": _RACKET,
    "pilates topu": _FITNESS,
    "jimnastik topu": _FITNESS,
    "parmak topu": _FITNESS,
    # ракетки
    "masa tenisi raketi": ("table-tennis-paddles", *_TABLE_TENNIS),
    "masa tenis raketi": ("table-tennis-paddles", *_TABLE_TENNIS),
    "masa tenisi": _TABLE_TENNIS,
    "tenis raketi": ("tennis-rackets", *_TENNIS),
    "tenis raket": ("tennis-rackets", *_TENNIS),
    "tenis grip": _TENNIS,
    "badminton raketi": ("badminton-rackets", *_BADMINTON),
    "badminton seti": _BADMINTON,
    "padel raketi": _RACKET,
    "padel raket": _RACKET,
    "padel gribi": _RACKET,
    "overgrip": _TENNIS,
    # командные игры: защита
    "tekmelik": ("shin-guards", *_FOOTBALL),
    "tekmeligi": ("shin-guards", *_FOOTBALL),
    # Nike Mercurial Lite/Hardshell магазин подписывает «Futbol Dizlik» — это щитки.
    "futbol dizlik": ("shin-guards", *_FOOTBALL),
    "kaleci eldiveni": _FOOTBALL,
    "voleybol dizlik": ("volleyball-knee-pads", *_VOLLEYBALL),
    "voleybol dizligi": ("volleyball-knee-pads", *_VOLLEYBALL),
    "voleybol kollugu": _VOLLEYBALL,
    "voleybol dirsekligi": _VOLLEYBALL,
    # плавание
    "yuzucu gozlugu": ("swimming-goggles", *_SWIMMING),
    "havuz gozlugu": ("swimming-goggles", *_SWIMMING),
    "yaris gozlugu": ("swimming-goggles", *_SWIMMING),
    "deniz gozlugu": ("swimming-goggles", *_SWIMMING),
    "bonesi": ("swim-caps", *_SWIMMING),
    "yuzme paleti": ("swim-fins", *_SWIMMING),
    "snorkel": ("snorkels", *_DIVING),
    "burun tikaci": _SWIMMING,
    "kulak tikaci": _SWIMMING,
    "bugu onleyici sprey": _SWIMMING,
    "paddle board": ("surf-boards", "surfing-sup", "water-sports", "sports"),
    # фитнес
    "yoga mati": ("yoga-mats", *_FITNESS),
    "mat": ("yoga-mats", *_FITNESS),
    "agirlik": _FITNESS,
    "atlama ipi": ("jump-ropes", *_FITNESS),
    "dambil": ("dumbbells", *_STRENGTH),
    "kettlebell": ("kettlebells", *_STRENGTH),
    "bilek agirligi": _FITNESS,
    "ayak agirligi": _FITNESS,
    "antrenman eldiveni": ("fitness-gloves", *_FITNESS),
    "antreman eldiveni": ("fitness-gloves", *_FITNESS),
    "fitness eldiveni": ("fitness-gloves", *_FITNESS),
    "agirlik kaldirma kemeri": ("weightlifting-belts", *_FITNESS),
    "guc bant": ("resistance-bands", *_FITNESS),
    "fitness bandi": ("resistance-bands", *_FITNESS),
    "pilates bandi": ("resistance-bands", *_FITNESS),
    "direnc bandi": ("resistance-bands", *_FITNESS),
    "barfiks cubugu": _STRENGTH,
    "agirlik kemeri": ("weightlifting-belts", *_FITNESS),
    "pilates bant seti": ("resistance-bands", *_FITNESS),
    "pilates halkasi": _FITNESS,
    "el yayi": _FITNESS,
    "egzersiz aleti": _FITNESS,
    "sinav standi": _FITNESS,
    "masaj aksesuari": _FITNESS,
    "oturma minderi": _FITNESS,
    "pilates topu pompasi": _FITNESS,
    "sisirme pompasi": _FITNESS,
    "dirsek korumaligi": _FITNESS,
    "bilek korumaligi": _FITNESS,
    "bel korumaligi": _FITNESS,
    # единоборства
    "boks eldiveni": ("boxing-gloves", *_MARTIAL),
    "boks koc eldiveni": ("boxing-gloves", *_MARTIAL),
    "kum torbasi": ("punching-bags", *_MARTIAL),
    "el bandaji": ("hand-wraps", "martial-arts-protective-gear", *_MARTIAL),
    "bandaj": ("hand-wraps", "martial-arts-protective-gear", *_MARTIAL),
    # зимние виды
    "kayak takimi": ("skis", *_WINTER),
    "kayak baglama": ("skis", *_WINTER),
    "snowboard tahtasi": ("snowboards", *_WINTER),
    "snowboard baglama": ("snowboards", *_WINTER),
    "kayak batonu": ("ski-poles", *_WINTER),
    "kayak botu": ("ski-boots", *_WINTER),
    "snowboard botu": ("ski-boots", *_WINTER),
    "kayak kaski": ("winter-helmets", *_WINTER_GEAR),
    "snowboard kaski": ("winter-helmets", *_WINTER_GEAR),
    "ski helmet": ("winter-helmets", *_WINTER_GEAR),
    "kayak gozlugu": ("winter-goggles", *_WINTER_GEAR),
    "snowboard gozlugu": ("winter-goggles", *_WINTER_GEAR),
    "buz hokeyi pateni": ("ice-skates", *_WINTER),
    "buz pateni korumaligi": _WINTER_GEAR,
    "buz pateni": ("ice-skates", *_WINTER),
    # туризм и бег
    "uyku tulumu": ("sleeping-bags", *_OUTDOOR),
    "cadir": ("tents", *_OUTDOOR),
    "kafa lambasi": ("flashlights", *_OUTDOOR),
    "yuruyus batonu": ("trekking-poles", *_OUTDOOR),
    "kamp masasi": _OUTDOOR,
    "kosu kemeri": ("running-belts", *_RUNNING),
    "kol bandi": _RUNNING,
    "kosu kolluk": _RUNNING,
    "kosu telefon bandi": _RUNNING,
}

_NAME_PHRASES = sorted(INTERSPORT_NAME_ROUTES, key=lambda phrase: (-len(phrase.split()), -len(phrase)))

# Разделы «за неимением точного» — видны в отчёте прогона.
INTERSPORT_PARENT_PLACEMENTS = frozenset(
    {"sports", "team-sports", "racket-sports", "water-sports", "winter-sports", "martial-arts", "fitness-gym"}
)


def intersport_name_route(name: Any) -> Tuple[str, ...]:
    """Раздел по виду товара в названии или пусто.

    «Nike Streak Unisex Beyaz Voleybol Dizliği» → наколенники,
    «Oakley Mod5 Erkek Gri Kayak/Snowboard Kaskı» → шлемы («/» — как пробел).
    """
    words = f" {akinon_key(re.sub(r'[/,()]', ' ', str(name or '')))} "
    for phrase in _NAME_PHRASES:
        if f" {phrase} " in words:
            return INTERSPORT_NAME_ROUTES[phrase]
    return ()


class IntersportParser(AkinonParser):
    """Парсер intersport.com.tr по JSON Akinon: спортивный инвентарь, без прокси."""

    SOURCE = "intersport"
    SOURCE_TITLE = "Intersport"
    SITE_URL = "https://www.intersport.com.tr"
    DOMAIN = "intersport.com.tr"
    PARENT_PLACEMENTS = INTERSPORT_PARENT_PLACEMENTS
    # robots.txt закрывает ``?page=`` — раздел читается одной страницей.
    FOLLOW_PAGINATION = False

    # Разделы инвентаря: мужской, женский (унисекс есть в обоих — повтор не
    # открывает карточку) и детский.
    EQUIPMENT_ROOTS = (
        "/erkek-spor-ekipmanlari/",
        "/kadin-spor-ekipmanlari/",
        "/cocuk-spor-ekipmanlari/",
    )
    GENDER_KEYS = ("integration_cinsiyet", "filterable_cinsiyet")
    SUBGROUP_FACET = "integration_alt_grup"
    SUBGROUP_FILTER = "attributes_integration_alt_grup"

    @classmethod
    def subgroup_route(
        cls, subgroup: Any, name: Any, brand: Any, gender: str, kids_gender: str = ""
    ) -> Tuple[str, Tuple[str, ...]]:
        """Инвентарь — по подгруппе сайта, раздел — по виду товара в названии."""
        subgroup = clean_text(str(subgroup or ""))
        key = akinon_key(subgroup)
        if key not in INTERSPORT_SUBGROUP_ROUTES:
            return subgroup, ()
        return subgroup, intersport_name_route(name) or INTERSPORT_SUBGROUP_ROUTES[key]

    def parse_categories(self) -> List[Dict[str, Any]]:
        """Подгруппы инвентаря трёх разделов — ссылками с фильтром подгруппы.

        Список подгрупп и их коды — из фильтра «Kategori» самой страницы раздела;
        берутся только подгруппы из таблицы раскладки, в которых есть товары.
        """
        rows: List[Dict[str, Any]] = []
        for root in self.EQUIPMENT_ROOTS:
            root_url = urljoin(self.base_url + "/", root.lstrip("/"))
            data = self._fetch_json(self._json_url(root_url))
            if not data:
                raise SiteCategoriesError(f"{self.SOURCE_TITLE}: раздел инвентаря не загрузился: {root_url}")
            facet = next(
                (
                    row for row in data.get("facets") or []
                    if isinstance(row, dict) and row.get("key") == self.SUBGROUP_FACET
                ),
                None,
            )
            if facet is None:
                raise SiteCategoriesError(f"{self.SOURCE_TITLE}: в разделе нет фильтра подгрупп: {root_url}")
            section = clean_text(str((data.get("category") or {}).get("name") or ""))
            for choice in ((facet.get("data") or {}).get("choices")) or []:
                if not isinstance(choice, dict) or not choice.get("value"):
                    continue
                label = clean_text(str(choice.get("label") or ""))
                if akinon_key(label) not in INTERSPORT_SUBGROUP_ROUTES or int(choice.get("quantity") or 0) <= 0:
                    continue
                rows.append(
                    {
                        "name": f"{section} {root.strip('/').split('-')[0]}: {label}".strip(),
                        "url": f"{root_url}?{urlencode({self.SUBGROUP_FILTER: choice['value']})}",
                        "external_id": f"{root.strip('/')}:{choice['value']}",
                    }
                )
        return self._site_categories(rows)
