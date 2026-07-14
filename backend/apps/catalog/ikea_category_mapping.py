"""Детерминированное сопоставление категорий IKEA с деревом Mudaroba."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse


@dataclass(frozen=True)
class IkeaCategoryMatch:
    category_slug: str
    reason: str
    confidence: str = "high"


def _normalize(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(
        str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})
    )
    return re.sub(r"[^a-zа-я0-9]+", "-", text).strip("-")


# Точные категории/функции IKEA TR и EN. Здесь намеренно нет слишком общих
# значений вроде ``mobilya``/``furniture``: они не определяют конечную ветку.
IKEA_CATEGORY_ALIASES = {
    "sofas": "sofas", "kanepeler": "sofas", "kanepe": "sofas",
    "sofa-beds": "sofa-beds", "yatakli-kanepeler": "sofa-beds", "yatakli-kanepe": "sofa-beds",
    "modular-sofas": "modular-sofas", "moduler-kanepeler": "modular-sofas",
    "armchairs": "armchairs", "koltuklar": "armchairs", "berjerler": "armchairs",
    "rocking-chairs": "rocking-armchairs", "sallanan-sandalyeler": "rocking-armchairs",
    "pouffes": "pouffes", "puflar": "pouffes",
    "coffee-and-side-tables": "coffee-tables", "sehpalar": "coffee-tables", "orta-sehpalar": "coffee-tables",
    "tv-units": "tv-stands", "tv-uniteleri": "tv-stands",
    "sideboards": "sideboards", "konsollar-ve-bufeler": "sideboards", "bufeler": "sideboards",
    "console-tables": "console-tables", "konsol-masalar": "console-tables",
    "beds": "beds", "karyolalar": "beds", "karyola": "beds",
    "beds-with-storage": "storage-beds", "depolamali-karyolalar": "storage-beds",
    "day-beds": "day-beds", "divanlar-ve-sedirler": "day-beds", "divan": "day-beds",
    "mattresses": "mattresses", "yataklar": "mattresses", "yatak": "mattresses",
    "slatted-bed-base": "bed-bases", "karyola-latasi": "bed-bases", "bazalar": "bed-bases",
    "nightstands": "nightstands", "komodinler": "nightstands", "komodin": "nightstands",
    "chest-of-drawers": "dressers", "sifonyerler": "dressers", "sifonyer": "dressers",
    "wardrobes": "wardrobes", "gardiroplar": "wardrobes", "gardiroplar-ve-dolaplar": "wardrobes",
    "dressing-tables": "dressing-tables", "makyaj-masalari": "dressing-tables",
    "bedroom-furniture-sets": "bedroom-sets", "yatak-odasi-mobilya-takimlari": "bedroom-sets",
    "dining-tables": "dining-tables", "yemek-masalari": "dining-tables",
    "kitchen-tables": "kitchen-tables", "mutfak-masalari": "kitchen-tables",
    "dining-room-chairs": "dining-chairs", "yemek-odasi-sandalyeleri": "dining-chairs",
    "table-chair-sets": "dining-sets", "masa-sandalye-takimlari": "dining-sets",
    "bar-tables": "bar-tables", "bar-masalari": "bar-tables",
    "bar-stools": "bar-stools", "bar-sandalyeleri": "bar-stools", "bar-tabureleri": "bar-stools",
    "stools": "stools", "tabureler": "stools",
    "service-trolleys": "service-trolleys", "servis-arabalari": "service-trolleys",
    "kitchen-cabinets": "kitchen-cabinets", "mutfak-dolaplari": "kitchen-cabinets",
    "desks": "office-desks", "calisma-masalari": "office-desks",
    "desk-chairs": "office-chairs", "calisma-sandalyeleri": "office-chairs",
    "drawer-units": "drawer-units", "kesonlar": "drawer-units",
    "filing-cabinets": "filing-cabinets", "dosya-dolaplari": "filing-cabinets",
    "bookcases": "bookcases", "kitapliklar": "bookcases", "acik-kitapliklar": "bookcases",
    "gaming-desks": "gaming-desks", "oyuncu-masalari": "gaming-desks",
    "gaming-chairs": "gaming-chairs", "oyuncu-koltuklari": "gaming-chairs",
    "kids-beds": "kids-beds", "cocuk-karyolalari": "kids-beds",
    "bunk-beds": "bunk-beds", "ranzalar": "bunk-beds",
    "kids-desks": "kids-desks", "cocuk-calisma-masalari": "kids-desks",
    "kids-chairs": "kids-chairs", "cocuk-sandalyeleri": "kids-chairs",
    "kids-wardrobes": "kids-wardrobes", "cocuk-dolap-ve-gardiroplari": "kids-wardrobes",
    "kids-dressers": "kids-dressers", "cocuk-sifonyerleri-ve-komodinleri": "kids-dressers",
    "kids-bookcases": "kids-bookcases", "cocuk-kitapliklari": "kids-bookcases",
    "toy-storage": "toy-storage", "oyuncak-dolaplari": "toy-storage",
    "cabinets": "storage-cabinets", "dolaplar": "storage-cabinets",
    "shelves": "shelves", "raflar": "shelves",
    "open-shelving-units": "open-shelving", "acik-raf-uniteleri": "open-shelving",
    "shoe-cabinets": "shoe-cabinets", "ayakkabiliklar": "shoe-cabinets",
    "coat-racks": "coat-racks", "portmanto-ve-vestiyer": "coat-racks",
    "room-divider-solutions": "room-dividers", "oda-ayirici-cozumler": "room-dividers",
    "bathroom-cabinets": "bathroom-cabinets", "banyo-dolaplari": "bathroom-cabinets",
    "bathroom-tall-cabinets": "bathroom-tall-cabinets", "banyo-boy-dolaplari": "bathroom-tall-cabinets",
    "wash-basin-cabinets": "wash-basin-cabinets", "lavabo-dolaplari": "wash-basin-cabinets",
    "wall-mounted-bathroom-cabinets": "wall-mounted-bathroom-cabinets",
    "bathroom-furniture-sets": "bathroom-furniture-sets", "banyo-mobilyasi-setleri": "bathroom-furniture-sets",
    "outdoor-tables": "garden-tables", "bahce-masalari": "garden-tables",
    "outdoor-chairs": "garden-chairs", "bahce-sandalyeleri": "garden-chairs",
    "outdoor-sofas": "outdoor-sofas", "bahce-kanepeleri": "outdoor-sofas",
    "outdoor-benches": "outdoor-benches", "bahce-banklari": "outdoor-benches",
    "sun-loungers": "sun-loungers", "sezlonglar": "sun-loungers",
    "outdoor-furniture-sets": "patio-sets", "bahce-mobilyasi-setleri": "patio-sets",
}

CANONICAL_FURNITURE_CATEGORY_SLUGS = frozenset(IKEA_CATEGORY_ALIASES.values())


# Только однозначные старые категории. Команда аудита показывает их, но не
# деактивирует и не удаляет автоматически.
LEGACY_FURNITURE_CATEGORY_ALIASES = {
    "wall-units": "tv-stands",
}


def _dict_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for key in ("slug", "name", "title", "code"):
            if value.get(key):
                yield value[key]
    elif value:
        yield value


def category_slug_from_url(url: str) -> str:
    parts = [part for part in urlparse(str(url or "")).path.split("/") if part]
    if len(parts) >= 2 and parts[-2] in {"kategori", "category"}:
        return _normalize(parts[-1])
    return ""


def resolve_ikea_category(
    *,
    source_category_slug: str = "",
    raw_category: Any = None,
    raw_function: Any = None,
    furniture_type: str = "",
    external_url: str = "",
) -> IkeaCategoryMatch | None:
    candidates = [
        (source_category_slug, "slug категории запуска IKEA"),
        (category_slug_from_url(external_url), "URL категории IKEA"),
    ]
    candidates.extend((value, "category из API IKEA") for value in _dict_values(raw_category))
    candidates.extend((value, "function из API IKEA") for value in _dict_values(raw_function))
    candidates.append((furniture_type, "тип мебели IKEA"))

    for value, reason in candidates:
        normalized = _normalize(value)
        target = IKEA_CATEGORY_ALIASES.get(normalized)
        if target:
            return IkeaCategoryMatch(target, reason)

    # Старые карточки IKEA часто сохранили только конкретный турецкий function,
    # например ``2'li yataklı kanepe``. Используем лишь однозначные сочетания.
    function_text = _normalize(furniture_type)
    if "yatakli" in function_text and ({"kanepe", "koltuk"} & set(function_text.split("-"))):
        return IkeaCategoryMatch("sofa-beds", "тип мебели IKEA: спальное место")
    if "moduler" in function_text and "kanepe" in function_text:
        return IkeaCategoryMatch("modular-sofas", "тип мебели IKEA: модульный диван")
    if "sehpa" in function_text:
        return IkeaCategoryMatch("coffee-tables", "тип мебели IKEA: столик")
    if "berjer" in function_text:
        return IkeaCategoryMatch("armchairs", "тип мебели IKEA: кресло")
    if "kanepe" in function_text:
        return IkeaCategoryMatch("sofas", "тип мебели IKEA: диван")
    return None


def resolve_ikea_product_category(product: Any) -> IkeaCategoryMatch | None:
    external_data = product.external_data if isinstance(product.external_data, dict) else {}
    raw = external_data.get("raw") if isinstance(external_data.get("raw"), dict) else {}
    attributes = external_data.get("attributes") if isinstance(external_data.get("attributes"), dict) else {}
    match = resolve_ikea_category(
        source_category_slug=(
            external_data.get("source_category_slug", "")
            or attributes.get("ikea_source_category_slug", "")
        ),
        raw_category=raw.get("category") or attributes.get("ikea_category"),
        raw_function=raw.get("function") or attributes.get("ikea_function"),
        furniture_type=product.furniture_type or attributes.get("furniture_type", ""),
        external_url=product.external_url,
    )
    if match:
        return match
    current_slug = getattr(getattr(product, "category", None), "slug", "")
    if current_slug in CANONICAL_FURNITURE_CATEGORY_SLUGS:
        return IkeaCategoryMatch(current_slug, "уже назначенная каноническая категория")
    return None
