"""Сервисы для интеграции парсеров с каталогом товаров."""

import logging
import re
import hashlib
import threading
from contextlib import contextmanager
from urllib.parse import urlparse
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any, Tuple
from django.utils import timezone
from django.db import transaction
from django.contrib.contenttypes.models import ContentType

# Флаг потока — True во время активного парсинга.
# Используется ai/signals.py чтобы не запускать AI во время сохранения спарсенных товаров.
_scraping_thread_local = threading.local()


def is_scraping_in_progress() -> bool:
    """Возвращает True, если текущий поток находится в процессе парсинга."""
    return getattr(_scraping_thread_local, "in_progress", False)


@contextmanager
def scraping_in_progress_context():
    """Контекстный менеджер: устанавливает флаг парсинга на время блока."""
    _scraping_thread_local.in_progress = True
    try:
        yield
    finally:
        _scraping_thread_local.in_progress = False


from .models import ScraperConfig, ScrapingSession, ScrapedProductLog
from .parsers.registry import get_parser
from .parsers.lcw import LcwParser
from .base.scraper import ScrapedProduct, _json_safe_scraped_value
from apps.catalog.services import CatalogNormalizer, build_image_alt_text
from apps.catalog.utils.tr_vocab import (
    match_turkish_product_term,
    normalize_ascii_text as normalize_tr_ascii_text,
    translate_turkish_color,
    translate_turkish_product_term,
)
from apps.catalog.models import (
    Product,
    BookProduct,
    JewelryProduct,
    MedicineAnalog,
    MedicineProduct,
    Author,
    ProductAuthor,
    GlobalAttributeKey,
    GlobalAttributeKeyTranslation,
    ProductAttributeValue,
)
from apps.catalog.attribute_specs import extract_dynamic_attribute_candidates
from apps.catalog.seo_defaults import resolve_book_seo_value
from apps.catalog.scraper_category_mapping import resolve_category_and_product_type
from apps.catalog.utils.parser_media_handler import download_and_optimize_parsed_media
import datetime


# Типы товаров, для которых при парсинге обнуляется бренд (например книги)
BRAND_CLEAR_PRODUCT_TYPES = {"books"}
DEFAULT_ASSUMED_STOCK_QUANTITY = 1000

# Реестр: product_type → метод получения/создания доменного объекта
_DOMAIN_GETTER_NAMES = {
    "books": "_get_book_product",
    "jewelry": "_get_jewelry_product",
    "medicines": "_get_medicine_product",
    "furniture": "_get_furniture_product",
    "accessories": "_get_accessory_product",
    "perfumery": "_get_perfumery_product",
    "clothing": "_get_clothing_product",
    "shoes": "_get_shoe_product",
    "headwear": "_get_headwear_product",
    "underwear": "_get_underwear_product",
    "islamic_clothing": "_get_islamic_clothing_product",
}

# Реестр: product_type → метод обновления атрибутов доменной модели из attrs
_ATTRIBUTE_UPDATE_HANDLER_NAMES = {
    "books": "_update_book_attributes",
    "jewelry": "_update_jewelry_attributes",
    "medicines": "_update_medicine_attributes",
    "furniture": "_update_furniture_attributes",
    "accessories": "_update_accessory_attributes",
    "perfumery": "_update_perfumery_attributes",
    "clothing": "_update_clothing_attributes",
    "shoes": "_update_shoe_attributes",
    "headwear": "_update_headwear_attributes",
    "underwear": "_update_underwear_attributes",
    "islamic_clothing": "_update_islamic_clothing_attributes",
}


class ScraperIntegrationService:
    """Сервис интеграции парсеров с каталогом."""

    PRODUCT_DOMAIN_RELATED_NAMES = (
        "accessory_item",
        "auto_part_item",
        "book_item",
        "clothing_item",
        "headwear_item",
        "incense_item",
        "islamic_clothing_item",
        "jewelry_item",
        "medical_equipment_item",
        "medicine_item",
        "perfumery_item",
        "shoe_item",
        "sports_item",
        "supplement_item",
        "tableware_item",
    )

    ILACFIYATI_DETAIL_TAB_EXTERNAL_IDS = {
        "ilac-bilgileri",
        "ilac-sinifi",
        "sgk-odeme-durumu",
        "recete-kurali",
        "sut-aciklama",
        "sgk-esdegeri",
        "esdegeri",
        "ac-tok-bilgisi",
        "besin-etkilesimi",
        "ozet",
        "ne-icin-kullanilir",
        "kullanmadan-dikkat-edilecekler",
        "nasil-kullanilir",
        "yan-etkileri",
        "saklanmasi",
    }

    PERFUMERY_GENDER_MAP = {
        "erkek": "men",
        "male": "men",
        "man": "men",
        "men": "men",
        "kadin": "women",
        "kadın": "women",
        "bayan": "women",
        "female": "women",
        "woman": "women",
        "women": "women",
        "unisex": "unisex",
        "unisex": "unisex",
        "cocuk": "kids",
        "çocuk": "kids",
        "kids": "kids",
        "kid": "kids",
    }
    PERFUMERY_TYPE_ALIASES = {
        "edp": "edp",
        "eau de parfum": "edp",
        "edt": "edt",
        "eau de toilette": "edt",
        "edc": "edc",
        "eau de cologne": "edc",
        "parfum": "parfum",
        "perfume": "parfum",
        "body mist": "body_mist",
        "mist": "body_mist",
    }
    PERFUMERY_FAMILY_ALIASES = {
        "floral": ("floral", "flower", "ciceksi", "çiçeksi"),
        "woody": ("woody", "wood", "odunsu"),
        "oriental": ("oriental", "amber", "dogu", "doğu", "baharatli", "baharatlı"),
        "fresh": ("fresh", "ferah", "temiz"),
        "citrus": ("citrus", "narenciye", "bergamot", "limon", "portakal", "greyfurt"),
        "aquatic": ("aquatic", "su", "marine", "okyanus", "deniz"),
        "gourmand": ("gourmand", "tatli", "tatlı", "vanilya", "karamel", "cikolata", "çikolata"),
        "aromatic": ("aromatic", "aromatik", "herbal"),
    }
    PERFUMERY_NOTE_STOP_MARKERS = (
        "üst not",
        "orta not",
        "kalp not",
        "temel not",
        "alt not",
        "base note",
        "heart note",
        "top note",
        "hacim",
        "volume",
        "türü",
        "turu",
        "ürün kodu",
        "urun kodu",
        "deodorant hacim",
        "duş jeli hacim",
        "dus jeli hacim",
        "özel hediye kutusu",
        "ozel hediye kutusu",
    )
    ACCESSORY_TYPE_TRANSLATIONS = {
        "sal": "Шаль",
        "şal": "Шаль",
        "esarp": "Платок",
        "eşarp": "Платок",
    }
    ACCESSORY_MATERIAL_TRANSLATIONS = {
        "hakiki deri": "Натуральная кожа",
        "gercek deri": "Натуральная кожа",
        "gerçek deri": "Натуральная кожа",
        "suni deri": "Искусственная кожа",
        "vegan deri": "Искусственная кожа",
        "pamuk": "Хлопок",
        "kumas": "Ткань",
        "kumaş": "Ткань",
        "metal": "Металл",
        "polar": "Флис",
        "hasir": "Соломка",
        "hasır": "Соломка",
        "tekstil": "Текстиль",
        "textile": "Текстиль",
        "rezin": "Резина",
        "rubber": "Резина",
        "kaucuk": "Каучук",
        "kauçuk": "Каучук",
        "eva": "EVA",
        "poliuretan": "Полиуретан",
        "polyurethane": "Полиуретан",
    }
    SHOE_CLOSURE_TRANSLATIONS = {
        "bagcik": "Шнуровка",
        "bağcık": "Шнуровка",
        "lace": "Шнуровка",
        "lace-up": "Шнуровка",
        "laces": "Шнуровка",
        "schnur": "Шнуровка",
        "шнур": "Шнуровка",
        "fermuar": "Молния",
        "zip": "Молния",
        "zipper": "Молния",
        "молн": "Молния",
        "cirt cirt": "Липучка",
        "cırt cırt": "Липучка",
        "velcro": "Липучка",
        "липуч": "Липучка",
        "tokali": "Пряжка",
        "tokalı": "Пряжка",
        "buckle": "Пряжка",
        "пряж": "Пряжка",
        "slip on": "Без застёжки",
        "slip-on": "Без застёжки",
        "gecirmeli": "Без застёжки",
        "geçirmeli": "Без застёжки",
        "без заст": "Без застёжки",
        "lastik": "Резинка",
        "elastic": "Резинка",
        "резин": "Резинка",
    }
    FASHION_PRODUCT_TYPES = {
        "clothing",
        "shoes",
        "headwear",
        "underwear",
        "islamic_clothing",
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.catalog_normalizer = CatalogNormalizer()

    def _normalize_and_get_author(self, name: str) -> Optional[Author]:
        lowered = name.lower().strip()
        if lowered in [
            "не указано", "нет", "unknown", "not specified", "неизвестен", "нет автора",
        ]:
            return None
        
        # Очищаем от лишних пробелов и кавычек
        clean_name = re.sub(r'[\"\'«»]', '', name)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        if not clean_name:
            return None
            
        parts = clean_name.split()
        if len(parts) >= 2:
            first_name = parts[0].title()
            last_name = " ".join(parts[1:]).title()
        else:
            first_name = clean_name.title()
            last_name = ""
            
        # Поиск независимый от регистра для предотвращения дублей
        author = Author.objects.filter(
            first_name__iexact=first_name, 
            last_name__iexact=last_name
        ).first()
        
        if not author:
            author = Author.objects.create(
                first_name=first_name, 
                last_name=last_name, 
                bio=""
            )
        return author

    def _strip_variant_noise(self, name: str) -> str:
        value = str(name or "").strip()
        if not value:
            return ""
        value = re.sub(r"\b\d[\d.,]*\s*(TL|TRY|USD|EUR|RUB|KZT)\b", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\bSKU[:\s-]*[A-Z0-9-]+\b", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+-\s+$", "", value)
        value = re.sub(r"\s{2,}", " ", value)
        return value.strip(" -")

    def _translate_variant_color(self, color: str, locale: str = "ru") -> str:
        normalized = str(color or "").strip()
        if not normalized:
            return ""
        return translate_turkish_color(normalized, locale) or normalized

    def _build_variant_names(self, base_name: str, color: str) -> Tuple[str, str]:
        cleaned_base = self._strip_variant_noise(base_name)
        ru_color = self._translate_variant_color(color, "ru")
        en_color = self._translate_variant_color(color, "en")
        ru_name = f"{cleaned_base} - {ru_color}".strip(" -") if cleaned_base and ru_color else cleaned_base or ru_color
        en_name = f"{cleaned_base} - {en_color}".strip(" -") if cleaned_base and en_color else cleaned_base or en_color
        return ru_name[:500], en_name[:500]

    def _normalize_ascii_text(self, value: str) -> str:
        return normalize_tr_ascii_text(value)

    def _normalize_perfume_gender(self, value: str) -> str:
        normalized = self._normalize_ascii_text(value)
        if not normalized:
            return ""
        for token in re.split(r"[^a-z]+", normalized):
            if token in self.PERFUMERY_GENDER_MAP:
                return self.PERFUMERY_GENDER_MAP[token]
        return ""

    def _extract_perfume_gender_candidates(self, value: str) -> List[str]:
        normalized = self._normalize_ascii_text(value)
        if not normalized:
            return []
        found: List[str] = []
        for token in re.split(r"[^a-z]+", normalized):
            mapped = self.PERFUMERY_GENDER_MAP.get(token)
            if mapped and mapped not in found:
                found.append(mapped)
        return found

    def _normalize_perfume_type(self, value: str) -> str:
        normalized = self._normalize_ascii_text(value)
        if not normalized:
            return ""
        for key, target in self.PERFUMERY_TYPE_ALIASES.items():
            if key in normalized:
                return target
        return ""

    def _normalize_perfume_family(self, value: str) -> str:
        normalized = self._normalize_ascii_text(value)
        if not normalized:
            return ""

        best_match = ("", None)
        for family, aliases in self.PERFUMERY_FAMILY_ALIASES.items():
            positions = [normalized.find(alias) for alias in aliases if alias in normalized]
            if not positions:
                continue
            position = min(positions)
            if best_match[1] is None or position < best_match[1]:
                best_match = (family, position)
        return best_match[0]

    def _normalize_volume_text(self, value: str) -> str:
        match = re.search(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*ml\b", str(value or ""), flags=re.IGNORECASE)
        if not match:
            return ""
        raw_number = match.group(1).replace(",", ".")
        if raw_number.endswith(".0"):
            raw_number = raw_number[:-2]
        return f"{raw_number} ml"

    def _extract_perfume_note_value(self, description: str, labels: Tuple[str, ...]) -> str:
        source = str(description or "")
        if not source:
            return ""
        for label in labels:
            pattern = rf"{label}\s*:\s*(.+?)(?=(?:{'|'.join(re.escape(marker) for marker in self.PERFUMERY_NOTE_STOP_MARKERS)})\s*:|$)"
            match = re.search(pattern, source, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            value = re.sub(r"\s+", " ", match.group(1)).strip(" ,;-")
            if value:
                return value[:500]
        return ""

    def _enrich_perfumery_attrs(
        self,
        attrs: Dict[str, Any],
        *,
        name: str = "",
        description: str = "",
        category: str = "",
        url: str = "",
    ) -> Dict[str, Any]:
        enriched = dict(attrs or {})
        text_parts = [
            str(name or ""),
            str(category or ""),
            str(description or ""),
            str(url or ""),
            str(enriched.get("description") or ""),
        ]
        full_text = " ".join(part for part in text_parts if part)
        normalized_text = self._normalize_ascii_text(full_text)

        gender_candidates = self._extract_perfume_gender_candidates(str(enriched.get("gender") or ""))
        if not gender_candidates:
            gender_candidates = self._extract_perfume_gender_candidates(full_text)
        if len(gender_candidates) > 1:
            enriched["gender"] = "unisex"
            enriched["gender_options"] = gender_candidates
        elif gender_candidates:
            enriched["gender"] = gender_candidates[0]

        type_candidates = []
        explicit_type = self._normalize_perfume_type(str(enriched.get("fragrance_type") or enriched.get("type") or ""))
        raw_type_match = re.search(r"(?<![A-Za-z])(?:Turu|Türü)\s*:\s*([A-Za-z ]+)", full_text, flags=re.IGNORECASE)
        if raw_type_match:
            mapped = self._normalize_perfume_type(raw_type_match.group(1))
            if mapped:
                explicit_type = mapped
        raw_component_types = re.findall(
            r"\b(edp|edt|edc|parfum|extrait|body\s*mist|vucut\s*spreyi|vücut\s*spreyi|deodorant|dus\s*jeli|duş\s*jeli)\b",
            normalized_text,
            flags=re.IGNORECASE,
        )
        normalized_component_types = []
        for raw in raw_component_types:
            normalized_component_types.append(raw.lower())
        is_mixed_set = any(keyword in normalized_text for keyword in ("set", "hediye kutusu", "gift set"))
        if any(token in normalized_text for token in ("deodorant", "dus jeli", "duş jeli")):
            is_mixed_set = True
        if explicit_type:
            type_candidates.append(explicit_type)
        inferred_component_fragrance_types = []
        for raw in normalized_component_types:
            mapped = self._normalize_perfume_type(raw)
            if mapped and mapped not in {"parfum"} and mapped not in inferred_component_fragrance_types:
                inferred_component_fragrance_types.append(mapped)
        if not explicit_type and len(inferred_component_fragrance_types) == 1:
            type_candidates.append(inferred_component_fragrance_types[0])
        unique_type_candidates = list(dict.fromkeys(candidate for candidate in type_candidates if candidate))
        if len(unique_type_candidates) == 1:
            enriched["fragrance_type"] = unique_type_candidates[0]
        elif unique_type_candidates and "fragrance_type" not in enriched:
            enriched["fragrance_type"] = ""

        if normalized_component_types:
            enriched["component_types"] = list(dict.fromkeys(normalized_component_types))
        if is_mixed_set:
            enriched["is_perfume_set"] = True

        family_source = str(enriched.get("fragrance_family") or "")
        if not family_source:
            family_match = re.search(r"\bgrup\s*:\s*([^,;\n]+)", full_text, flags=re.IGNORECASE)
            if family_match:
                family_source = family_match.group(1)
        normalized_family = self._normalize_perfume_family(family_source or full_text)
        if normalized_family:
            enriched["fragrance_family"] = normalized_family

        all_volume_matches = [
            self._normalize_volume_text(match)
            for match in re.findall(r"\b\d{1,4}(?:[.,]\d{1,2})?\s*ml\b", full_text, flags=re.IGNORECASE)
        ]
        unique_volumes = list(dict.fromkeys(volume for volume in all_volume_matches if volume))
        if len(unique_volumes) > 1:
            enriched["volume_options"] = unique_volumes

        if not enriched.get("volume"):
            explicit_volume_match = re.search(
                r"(?<![A-Za-z])(?:Hacim|Volume)\s*:\s*(\d{1,4}(?:[.,]\d{1,2})?\s*ml\b)",
                full_text,
                flags=re.IGNORECASE,
            )
            if explicit_volume_match:
                normalized_volume = self._normalize_volume_text(explicit_volume_match.group(1))
                if normalized_volume:
                    enriched["volume"] = normalized_volume
        if not enriched.get("volume"):
            if len(unique_volumes) == 1 and not is_mixed_set:
                enriched["volume"] = unique_volumes[0]
            elif len(unique_volumes) > 1 and is_mixed_set:
                enriched["volume"] = " / ".join(unique_volumes)[:50]

        note_fields = {
            "top_notes": ("üst notalar", "ust notalar", "top notes"),
            "heart_notes": ("orta notalar", "heart notes", "kalp notalar"),
            "base_notes": ("temel notalar", "alt notalar", "base notes"),
        }
        for field_name, labels in note_fields.items():
            if enriched.get(field_name):
                continue
            note_value = self._extract_perfume_note_value(full_text, labels)
            if note_value:
                enriched[field_name] = note_value

        return enriched

    def _normalize_accessory_type(self, value: str) -> str:
        raw_value = str(value or "").strip()
        if not raw_value:
            return ""
        translated_term = translate_turkish_product_term(raw_value, "ru")
        if translated_term in {"Сумка", "Кошелек", "Ремень", "Часы", "Очки", "Шапка", "Кепка", "Берет"}:
            if translated_term == "Ремень":
                return "Пояс / ремень"
            return translated_term
        normalized = self._normalize_ascii_text(raw_value)
        for key, label in self.ACCESSORY_TYPE_TRANSLATIONS.items():
            if key in normalized:
                return label
        return raw_value[:100]

    def _normalize_accessory_material(self, value: str) -> str:
        raw_value = str(value or "").strip()
        if not raw_value:
            return ""
        normalized = self._normalize_ascii_text(raw_value)
        for key, label in self.ACCESSORY_MATERIAL_TRANSLATIONS.items():
            if key in normalized:
                return label
        cleaned = re.sub(r"\s+", " ", raw_value).strip(" ,.;-")
        return cleaned[:100]

    def _find_attribute_value(self, attrs: Dict[str, Any], keys: tuple[str, ...], contains: tuple[str, ...] = ()) -> str:
        for key in keys:
            value = attrs.get(key)
            if value:
                clean = str(value).strip()
                if clean:
                    return clean
        if not contains:
            return ""
        for raw_key, value in attrs.items():
            normalized_key = self._normalize_ascii_text(str(raw_key or "")).replace(" ", "_")
            if any(marker in normalized_key for marker in contains):
                clean = str(value or "").strip()
                if clean:
                    return clean
        return ""

    def _normalize_shoe_closure_type(self, value: str) -> str:
        raw_value = str(value or "").strip()
        if not raw_value:
            return ""
        normalized = self._normalize_ascii_text(raw_value)
        for key, label in self.SHOE_CLOSURE_TRANSLATIONS.items():
            if key in normalized:
                return label
        cleaned = re.sub(r"\s+", " ", raw_value).strip(" ,.;-")
        return cleaned[:100]

    def _apply_dynamic_attribute_specs(
        self,
        *,
        target: Any,
        product_type: str,
        attrs: Dict[str, Any],
    ) -> bool:
        updated = False
        for candidate in extract_dynamic_attribute_candidates(product_type, attrs):
            updated = self._upsert_product_dynamic_attribute(
                target,
                slug=candidate.slug,
                value=candidate.value,
                name_ru=candidate.name_ru,
                name_en=candidate.name_en,
                sort_order=candidate.sort_order,
                value_ru=candidate.value_ru,
                value_en=candidate.value_en,
            ) or updated
        return updated

    def _ensure_global_attribute_key(
        self,
        *,
        slug: str,
        name_ru: str,
        name_en: str,
        category=None,
        sort_order: int = 0,
    ) -> GlobalAttributeKey:
        key, created = GlobalAttributeKey.objects.get_or_create(
            slug=slug,
            defaults={"sort_order": sort_order},
        )
        if not created and key.sort_order != sort_order and sort_order:
            key.sort_order = sort_order
            key.save(update_fields=["sort_order"])

        for locale, name in (("ru", name_ru), ("en", name_en)):
            if not name:
                continue
            GlobalAttributeKeyTranslation.objects.get_or_create(
                key_obj=key,
                locale=locale,
                defaults={"name": name},
            )

        if category is not None:
            cat = category
            while cat is not None:
                key.categories.add(cat)
                cat = getattr(cat, "parent", None)

        return key

    def _upsert_product_dynamic_attribute(
        self,
        target: Any,
        *,
        slug: str,
        value: str,
        name_ru: str,
        name_en: str,
        sort_order: int = 0,
        value_ru: Optional[str] = None,
        value_en: Optional[str] = None,
    ) -> bool:
        clean_value = str(value or "").strip()
        if not clean_value:
            return False

        key = self._ensure_global_attribute_key(
            slug=slug,
            name_ru=name_ru,
            name_en=name_en,
            category=getattr(target, "category", None),
            sort_order=sort_order,
        )

        content_type = ContentType.objects.get_for_model(type(target))
        dynamic_attr, created = ProductAttributeValue.objects.get_or_create(
            content_type=content_type,
            object_id=target.pk,
            attribute_key=key,
            defaults={
                "value": clean_value[:500],
                "value_ru": (value_ru or clean_value)[:500] if (value_ru or clean_value) else None,
                "value_en": value_en[:500] if value_en else None,
                "sort_order": sort_order,
            },
        )
        if created:
            return True

        changed = False
        next_value = clean_value[:500]
        next_value_ru = (value_ru or clean_value)[:500] if (value_ru or clean_value) else None
        next_value_en = value_en[:500] if value_en else None

        if dynamic_attr.value != next_value:
            dynamic_attr.value = next_value
            changed = True
        if (dynamic_attr.value_ru or None) != next_value_ru:
            dynamic_attr.value_ru = next_value_ru
            changed = True
        if (dynamic_attr.value_en or None) != next_value_en:
            dynamic_attr.value_en = next_value_en
            changed = True
        if dynamic_attr.sort_order != sort_order:
            dynamic_attr.sort_order = sort_order
            changed = True

        if changed:
            dynamic_attr.save(update_fields=["value", "value_ru", "value_en", "sort_order"])
        return changed

    def _enrich_accessory_attrs(
        self,
        attrs: Dict[str, Any],
        *,
        name: str = "",
        description: str = "",
        category: str = "",
    ) -> Dict[str, Any]:
        enriched = dict(attrs or {})
        full_text = " ".join(
            part for part in (str(name or ""), str(category or ""), str(description or "")) if part
        )
        normalized_text = self._normalize_ascii_text(full_text)

        accessory_type_source = (
            enriched.get("accessory_type")
            or enriched.get("urun_tipi")
            or enriched.get("ürün_tipi")
            or category
        )
        accessory_type = self._normalize_accessory_type(str(accessory_type_source or ""))
        if accessory_type:
            enriched["accessory_type"] = accessory_type

        material_source = (
            enriched.get("material")
            or enriched.get("malzeme")
            or enriched.get("kumaş")
            or enriched.get("kumas")
        )
        if not material_source:
            material_match = re.search(
                r"\b(hakiki deri|gercek deri|gerçek deri|suni deri|vegan deri|pamuk|metal|polar|hasir|hasır)\b",
                normalized_text,
                flags=re.IGNORECASE,
            )
            if material_match:
                material_source = material_match.group(1)
        material = self._normalize_accessory_material(str(material_source or ""))
        if material:
            enriched["material"] = material

        inferred_gender = self._normalize_perfume_gender(
            " ".join(
                part
                for part in (
                    str(enriched.get("gender") or ""),
                    str(enriched.get("cinsiyet") or ""),
                    str(name or ""),
                    str(category or ""),
                    str(description or ""),
                )
                if part
            )
        )
        if inferred_gender:
            enriched["gender"] = inferred_gender

        return enriched

    def _extract_single_size_from_variant_payload(self, attrs: Dict[str, Any]) -> str:
        variants = attrs.get("fashion_variants") or []
        if not isinstance(variants, list):
            return ""
        unique_sizes: List[str] = []
        seen = set()
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            for row in variant.get("sizes") or []:
                if isinstance(row, dict):
                    raw_size = row.get("size")
                else:
                    raw_size = row
                size_value = re.sub(r"\s+", " ", str(raw_size or "")).strip()
                if not size_value or size_value in seen:
                    continue
                seen.add(size_value)
                unique_sizes.append(size_value)
        return unique_sizes[0] if len(unique_sizes) == 1 else ""

    def _enrich_gendered_fashion_attrs(
        self,
        attrs: Dict[str, Any],
        *,
        name: str = "",
        description: str = "",
        category: str = "",
        product_type: str = "",
    ) -> Dict[str, Any]:
        enriched = dict(attrs or {})
        full_text = " ".join(
            part
            for part in (
                str(name or ""),
                str(category or ""),
                str(description or ""),
                str(enriched.get("cinsiyet") or ""),
            )
            if part
        )
        normalized_gender = self._normalize_perfume_gender(
            str(enriched.get("gender") or enriched.get("cinsiyet") or full_text)
        )
        if normalized_gender:
            enriched["gender"] = normalized_gender

        if product_type in {"headwear", "underwear"} and not enriched.get("default_size"):
            default_size = self._extract_single_size_from_variant_payload(enriched)
            if default_size:
                enriched["default_size"] = default_size[:50]

        return enriched

    def _prepare_scraped_attributes(
        self,
        scraped_product: ScrapedProduct,
        product_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        attrs = dict(scraped_product.attributes or {})
        effective_type = product_type
        if not effective_type and scraped_product.category:
            _, effective_type = resolve_category_and_product_type(scraped_product.category)
        if effective_type == "perfumery":
            attrs = self._enrich_perfumery_attrs(
                attrs,
                name=scraped_product.name,
                description=scraped_product.description or "",
                category=scraped_product.category or "",
                url=scraped_product.url or "",
            )
        elif effective_type == "accessories":
            attrs = self._enrich_accessory_attrs(
                attrs,
                name=scraped_product.name,
                description=scraped_product.description or "",
                category=scraped_product.category or "",
            )
        elif effective_type in self.FASHION_PRODUCT_TYPES:
            attrs = self._enrich_gendered_fashion_attrs(
                attrs,
                name=scraped_product.name,
                description=scraped_product.description or "",
                category=scraped_product.category or "",
                product_type=effective_type,
            )
        return attrs

    def run_scraper(
        self,
        scraper_config: ScraperConfig,
        start_url: Optional[str] = None,
        max_pages: int = None,
        max_products: int = None,
        max_images_per_product: int = None,
        target_category=None,
    ) -> ScrapingSession:
        """Запускает парсер и создает сессию.

        Args:
            scraper_config: Конфигурация парсера
            start_url: Начальный URL (если не указан, берется из конфигурации)
            max_pages: Максимальное количество страниц
            max_products: Максимальное количество товаров
            target_category: Категория для сохранения товаров (переопределяет default_category)

        Returns:
            Сессия парсинга
        """
        # Создаем сессию
        session = ScrapingSession.objects.create(
            scraper_config=scraper_config,
            start_url=start_url or scraper_config.base_url,
            max_pages=max_pages or scraper_config.max_pages_per_run,
            max_products=max_products or scraper_config.max_products_per_run,
            max_images_per_product=max_images_per_product or scraper_config.max_images_per_product,
            target_category=target_category,
            status="running",
            started_at=timezone.now(),
        )

        try:
            # Получаем класс парсера
            parser_class = get_parser(scraper_config.parser_class)
            if not parser_class:
                raise ValueError(f"Парсер {scraper_config.parser_class} не найден")

            # Создаем экземпляр парсера
            with parser_class(
                base_url=scraper_config.base_url,
                timeout=scraper_config.timeout,
                max_retries=scraper_config.max_retries,
                use_proxy=scraper_config.use_proxy,
                username=scraper_config.scraper_username,
                password=scraper_config.scraper_password,
            ) as parser:

                # Устанавливаем задержки после создания
                parser.delay_range = (scraper_config.delay_min, scraper_config.delay_max)

                # Устанавливаем дополнительные настройки
                if scraper_config.user_agent:
                    parser.user_agent = scraper_config.user_agent

                # Запускаем парсинг
                # Передаем лимит товаров в парсер
                if session.max_products:
                    parser.max_products = session.max_products

                scraped_products, incremental_results = self._run_parser_scraping(
                    parser, session, start_url or scraper_config.base_url
                )

                # Если _run_parser_scraping обработал товары инкрементально, берём его счётчики;
                # иначе обрабатываем накопленный список как раньше.
                if incremental_results is not None:
                    results = incremental_results
                else:
                    results = self._process_scraped_products(session, scraped_products)

                # Обновляем сессию
                session.status = "completed"
                session.finished_at = timezone.now()
                session.products_found = results["found"]
                session.products_created = results["created"]
                session.products_updated = results["updated"]
                session.products_skipped = results["skipped"]
                session.save()

                # Обновляем статистику конфигурации
                self._update_scraper_stats(scraper_config, session, success=True)

        except Exception as e:
            self.logger.error(f"Ошибка при запуске парсера {scraper_config.name}: {e}")

            # Обновляем сессию с ошибкой
            session.status = "failed"
            session.finished_at = timezone.now()
            session.error_message = str(e)
            session.save()

            # Обновляем статистику конфигурации
            self._update_scraper_stats(scraper_config, session, success=False)

            raise

        return session

    @staticmethod
    def _extend_from_product_detail(scraped_products: List[ScrapedProduct], detail_result) -> None:
        """Результат parse_product_detail: один товар, список вариантов (IKEA) или None."""
        if detail_result is None:
            return
        if isinstance(detail_result, list):
            scraped_products.extend(p for p in detail_result if p is not None)
        else:
            scraped_products.append(detail_result)

    def _run_parser_scraping(
        self, parser, session: ScrapingSession, start_url: str
    ):
        """Выполняет парсинг с помощью парсера.

        Returns:
            (scraped_products, incremental_results): для категорий — пустой список и словарь
            со счётчиками (товары уже сохранены); для остальных — список товаров и None.
        """
        scraped_products = []
        incremental_results = None

        try:
            # Анализируем URL
            parsed_url = urlparse(start_url)
            path_parts = [p for p in parsed_url.path.strip('/').split('/') if p]

            host = (parsed_url.netloc or "").lower()
            is_ikea_host = host == "ikea.com.tr" or host.endswith(".ikea.com.tr")
            is_lcw_host = host == "lcw.com" or host.endswith(".lcw.com")

            is_category = (
                "/category/" in start_url or "/kategori/" in start_url or
                (len(path_parts) == 1 and path_parts[0] in ('ilaclar', 'takviye-edici-gida')) or
                (is_lcw_host and LcwParser.is_lcw_category_url(start_url))
            )
            is_search = "/search" in start_url or "/arama" in start_url
            # IKEA TR/COM: карточка товара — /urun/, /product/ или /p/
            is_ikea_product = (
                is_ikea_host
                and any(p in path_parts for p in ("urun", "product", "p"))
            )
            is_lcw_product = is_lcw_host and LcwParser.is_lcw_product_url(start_url)
            is_product = (
                "/product/" in start_url or
                ("/p/" in start_url and "instagram.com" not in start_url) or
                (len(path_parts) >= 2 and path_parts[0] in ('ilaclar', 'takviye-edici-gida')) or
                is_ikea_product or
                is_lcw_product
            )

            # Определяем тип парсинга по URL
            if is_category:
                # Парсинг категории — инкрементальная обработка: каждый товар
                # сохраняется в БД сразу после парсинга, не накапливается в памяти.
                incremental_results = {"found": 0, "created": 0, "updated": 0, "skipped": 0, "errors": 0}
                checkpoint = 0
                for product in parser.parse_product_list(start_url, max_pages=session.max_pages):
                    r = self._process_scraped_products(session, [product])
                    for k in incremental_results:
                        incremental_results[k] += r.get(k, 0)
                    checkpoint += 1
                    if checkpoint % 10 == 0:
                        session.products_found = incremental_results["found"]
                        session.products_created = incremental_results["created"]
                        session.products_updated = incremental_results["updated"]
                        session.products_skipped = incremental_results["skipped"]
                        session.errors_count = incremental_results["errors"]
                        session.save()
                session.pages_processed += incremental_results["found"] // 20 + 1

            elif is_search:
                # Поиск товаров
                query = self._extract_search_query(start_url)
                if query:
                    products = parser.search_products(query, session.max_products)
                    scraped_products.extend(products)
                    session.pages_processed += 1

            elif is_product:
                # Парсинг отдельного товара (не Instagram); IKEA может вернуть список цветов
                detail_result = parser.parse_product_detail(start_url)
                self._extend_from_product_detail(scraped_products, detail_result)
                session.pages_processed += 1

            elif "instagram.com" in start_url:
                # --- Instagram: три варианта URL ---
                # 1. Конкретный пост:  instagram.com/p/SHORTCODE/
                # 2. Reels:            instagram.com/reel/SHORTCODE/
                # 3. Профиль:          instagram.com/username/
                # 4. Хештег:           instagram.com/explore/tags/tag/
                if "/p/" in start_url or "/reel/" in start_url:
                    # Парсим один пост
                    self.logger.info("Instagram: парсинг отдельного поста %s", start_url)
                    detail_result = parser.parse_product_detail(start_url)
                    self._extend_from_product_detail(scraped_products, detail_result)
                else:
                    # Парсим профиль или хештег — возвращает список постов
                    self.logger.info(
                        "Instagram: парсинг профиля/хештега %s (макс. %d постов)",
                        start_url,
                        session.max_pages,
                    )
                    products = parser.parse_product_list(start_url, max_pages=session.max_pages)
                    scraped_products.extend(products)
                session.pages_processed += 1

            else:
                # Парсинг всех категорий
                categories = parser.parse_categories()
                for category in categories[
                    : session.max_pages
                ]:  # Ограничиваем количество категорий
                    try:
                        products = parser.parse_product_list(
                            category["url"], max_pages=max(1, session.max_pages // len(categories))
                        )
                        scraped_products.extend(products)
                        session.pages_processed += 1

                        # Проверяем лимиты
                        if len(scraped_products) >= session.max_products:
                            break

                    except Exception as e:
                        self.logger.warning(f"Ошибка парсинга категории {category['url']}: {e}")
                        session.errors_count += 1

            # Обновляем сессию
            session.save()

        except Exception as e:
            self.logger.error(f"Ошибка при парсинге: {e}")
            session.errors_count += 1
            session.save()
            raise

        return scraped_products, incremental_results

    def _process_scraped_products(
        self, session: ScrapingSession, products: List[ScrapedProduct]
    ) -> Dict[str, int]:
        """Обрабатывает спарсенные товары и сохраняет в каталог."""
        results = {"found": len(products), "created": 0, "updated": 0, "skipped": 0, "errors": 0}

        for scraped_product in products:
            try:
                self._apply_category_mapping(session, scraped_product)
                self._apply_brand_mapping(session, scraped_product)
                self._normalize_scraped_media(session, scraped_product)
                # Блокируем авто-запуск AI во время сохранения — используем потоковый контекст
                with scraping_in_progress_context():
                    action, product = self._process_single_product(session, scraped_product)

                # Обновляем счетчики
                if action == "created":
                    results["created"] += 1
                elif action == "updated":
                    results["updated"] += 1
                elif action == "skipped":
                    results["skipped"] += 1

                # Логируем результат
                ScrapedProductLog.objects.create(
                    session=session,
                    product=product,
                    external_id=scraped_product.external_id,
                    external_url=scraped_product.url,
                    product_name=scraped_product.name,
                    action=action,
                    message=f"Товар {action}",
                    scraped_data=scraped_product.to_dict(),
                )

            except Exception as e:
                self.logger.error(f"Ошибка обработки товара {scraped_product.name}: {e}")
                results["errors"] += 1

                # Логируем ошибку
                ScrapedProductLog.objects.create(
                    session=session,
                    external_id=scraped_product.external_id,
                    external_url=scraped_product.url,
                    product_name=scraped_product.name,
                    action="error",
                    message=str(e),
                    scraped_data=scraped_product.to_dict(),
                )

        return results

    def _apply_category_mapping(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        """
        Устанавливает категорию товара по выбору администратора.
        Приоритет:
        1. session.target_category — категория из конкретной задачи
        2. scraper_config.default_category — категория по умолчанию из конфигурации парсера
        Авто-определение категории по атрибутам товара отключено.
        """
        # Приоритет 1: категория из задачи (task.target_category сохраняется в session)
        category = session.target_category
        # Приоритет 2: категория по умолчанию из конфигурации парсера
        if not category:
            category = session.scraper_config.default_category

        if category:
            scraped_product.category = category.slug or category.name

    def _apply_brand_mapping(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        """
        Устанавливает бренд товара.
        Приоритет:
        1. scraper_config.default_brand — бренд по умолчанию из конфигурации (самый надежный)
        2. scraped_product.brand — бренд, найденный парсером на странице
        """
        # Приоритет 1: бренд из конфигурации парсера
        default_brand = session.scraper_config.default_brand
        
        if default_brand:
            scraped_product.brand = default_brand.name
        # Если в конфигурации пусто, используем то что нашел парсер (уже в scraped_product.brand)

    def _get_first_image_url(self, media_urls: List[str]) -> Optional[str]:
        for media_url in media_urls or []:
            if self.catalog_normalizer._resolve_media_type(media_url) == "image":
                return media_url
        return media_urls[0] if media_urls else None

    @staticmethod
    def _lcw_canonical_media_url(url: str) -> str:
        canonical = re.sub(r"/mnpadding/\d+/\d+/ffffff/", "/", str(url or ""))
        canonical = re.sub(r"/mnpadding/\d+/\d+/", "/", canonical)
        return canonical

    @staticmethod
    def _lcw_media_resolution_score(url: str) -> int:
        match = re.search(r"/mnpadding/(\d+)/(\d+)/", str(url or ""))
        if not match:
            return 0
        return int(match.group(1)) * int(match.group(2))

    def _collapse_lcw_media_urls(self, urls: List[str]) -> List[str]:
        """Убирает LCW preview/OG-дубли и оставляет самую крупную версию изображения."""
        result: List[str] = []
        index_by_key: Dict[str, int] = {}
        score_by_key: Dict[str, int] = {}

        for raw_url in urls or []:
            if not isinstance(raw_url, str) or not raw_url:
                continue
            parsed = urlparse(raw_url)
            host = (parsed.netloc or "").lower()
            if "img-lcwaikiki.mncdn.com" not in host:
                if raw_url not in result:
                    result.append(raw_url)
                continue

            key = self._lcw_canonical_media_url(raw_url)
            score = self._lcw_media_resolution_score(raw_url)
            if key not in index_by_key:
                index_by_key[key] = len(result)
                score_by_key[key] = score
                result.append(raw_url)
                continue

            if score > score_by_key.get(key, -1):
                result[index_by_key[key]] = raw_url
                score_by_key[key] = score

        return result

    def _download_parsed_media_urls(
        self,
        session: ScrapingSession,
        *,
        source_urls: List[str],
        parser_name: str,
        product_id: str,
        sub_folder: Optional[str],
        reuse_map: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Скачивает внешние URL в хранилище parsed-медиа (как у основной карточки).

        Возвращает (список URL в порядке обработки, карта исходный_URL → итоговый_URL),
        чтобы синхронизировать attributes (video_url и т.д.) с R2 и не дублировать файлы в main/.

        reuse_map — уже скачанные в этом же проходе нормализации пары исходный→R2: те же URL
        не качаются повторно с другим product_id (иначе дублируется первая картинка у вариантов).
        """
        scraper_config = session.scraper_config
        max_images = session.max_images_per_product or scraper_config.max_images_per_product or 0
        urls = list(source_urls)
        if (parser_name or "").strip().lower() == "lcw":
            urls = self._collapse_lcw_media_urls(urls)
        if max_images:
            urls = urls[:max_images]
        headers = dict(scraper_config.headers or {})
        if scraper_config.user_agent:
            headers.setdefault("User-Agent", scraper_config.user_agent)
        out: List[str] = []
        url_map: Dict[str, str] = {}
        reuse_map = reuse_map or {}
        for index, url in enumerate(urls):
            if not isinstance(url, str) or not url:
                continue
            if url in url_map:
                out.append(url_map[url])
                continue
            if url in reuse_map:
                resolved = reuse_map[url]
                out.append(resolved)
                url_map[url] = resolved
                continue
            parsed = urlparse(url)
            if "/products/parsed/" in parsed.path:
                out.append(url)
                url_map[url] = url
                continue
            r2_url = download_and_optimize_parsed_media(
                url=url,
                parser_name=parser_name,
                product_id=product_id,
                index=index,
                headers=headers or None,
                sub_folder=sub_folder,
            )
            if r2_url:
                out.append(r2_url)
                url_map[url] = r2_url
        return out, url_map

    @staticmethod
    def _remap_attribute_urls(attributes: dict, url_map: Dict[str, str]) -> None:
        """Подменяет в attributes известные медиа-URL на версии из R2 (после парсерной загрузки)."""
        if not url_map:
            return
        vu = attributes.get("video_url")
        if isinstance(vu, str) and vu in url_map:
            attributes["video_url"] = url_map[vu]
        vus = attributes.get("video_urls")
        if isinstance(vus, list):
            attributes["video_urls"] = [
                url_map.get(x, x) for x in vus if isinstance(x, str)
            ]
        for key in ("main_video_url", "main_media_url"):
            val = attributes.get(key)
            if isinstance(val, str) and val in url_map:
                attributes[key] = url_map[val]

    def _normalize_scraped_media(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> None:
        if not isinstance(scraped_product.attributes, dict):
            scraped_product.attributes = dict(scraped_product.attributes or {})
        attributes = scraped_product.attributes

        media_urls = list(scraped_product.images or [])
        video_url = attributes.get("video_url")
        if isinstance(video_url, str) and video_url:
            media_urls.append(video_url)
        video_urls = attributes.get("video_urls")
        if isinstance(video_urls, list):
            media_urls.extend([url for url in video_urls if isinstance(url, str) and url])
        video_posters = attributes.get("video_posters") or attributes.get("video_poster")
        poster_urls = []
        if isinstance(video_posters, list):
            poster_urls.extend([url for url in video_posters if isinstance(url, str) and url])
        elif isinstance(video_posters, str) and video_posters:
            poster_urls.append(video_posters)

        if poster_urls and (video_url or video_urls):
            media_urls = [url for url in media_urls if url not in set(poster_urls)]

        unique_media_urls = []
        seen_urls = set()
        for url in media_urls:
            if not isinstance(url, str) or not url:
                continue
            if url in seen_urls:
                continue
            unique_media_urls.append(url)
            seen_urls.add(url)
        media_urls = unique_media_urls

        # Определяем sub_folder для группировки медиа (Instagram: username)
        sub_folder = attributes.get("username")

        if not sub_folder and scraped_product.category:
            sub_folder = scraped_product.category

        scraper_config = session.scraper_config
        parser_name = scraped_product.source or scraper_config.parser_class

        product_id = scraped_product.external_id or ""
        if not product_id:
            parsed_url = urlparse(scraped_product.url or "")
            last_segment = parsed_url.path.rstrip("/").split("/")[-1]
            if last_segment:
                product_id = last_segment
            else:
                raw_hash = hashlib.md5(
                    (scraped_product.url or scraped_product.name or "").encode("utf-8")
                ).hexdigest()
                product_id = raw_hash[:12]

        # Общая карта исходный_URL→R2: корень карточки и все варианты делят одни файлы при совпадении URL.
        shared_source_to_r2: Dict[str, str] = {}

        if media_urls:
            new_images, url_map = self._download_parsed_media_urls(
                session,
                source_urls=media_urls,
                parser_name=parser_name,
                product_id=product_id,
                sub_folder=sub_folder,
            )
            scraped_product.images = new_images
            shared_source_to_r2.update(url_map)
            self._remap_attribute_urls(attributes, url_map)

        # Медиа цветовых вариантов IKEA (отдельные sprCode, одна карточка FurnitureProduct)
        fv = attributes.get("furniture_variants")
        if isinstance(fv, list):
            for spec in fv:
                if not isinstance(spec, dict):
                    continue
                vid = str(spec.get("external_id") or product_id).strip() or product_id
                raw_imgs = spec.get("images") or []
                if not raw_imgs:
                    continue
                variant_images, variant_map = self._download_parsed_media_urls(
                    session,
                    source_urls=list(raw_imgs),
                    parser_name=parser_name,
                    product_id=vid,
                    sub_folder=sub_folder,
                    reuse_map=shared_source_to_r2,
                )
                spec["images"] = variant_images
                shared_source_to_r2.update(variant_map)

    def _process_single_product(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> Tuple[str, Optional[Product]]:
        """Обрабатывает один товар."""
        # Проверяем, есть ли товар с таким external_id из API
        api_product = Product.objects.filter(
            external_id=scraped_product.external_id, external_data__source="api"  # Только из API
        ).first()

        if api_product:
            # Товар уже есть из API - пропускаем или обновляем дополнительные данные
            return self._handle_api_conflict(scraped_product, api_product)

        # Для парсеров (не API) тоже привязываемся по external_id, если он уже есть
        if scraped_product.external_id:
            existing_by_external_id = Product.objects.filter(
                external_id=scraped_product.external_id
            ).first()

            if not existing_by_external_id:
                from apps.catalog.models import FurnitureVariant
                variant = FurnitureVariant.objects.filter(
                    external_id=scraped_product.external_id
                ).select_related('product__base_product').first()
                if variant and variant.product and variant.product.base_product:
                    existing_by_external_id = variant.product.base_product

            if existing_by_external_id:
                return self._update_existing_product(
                    session,
                    scraped_product,
                    existing_by_external_id,
                )

        existing_by_ilacfiyati_url = self._find_ilacfiyati_medicine_product_by_source_url(scraped_product)
        if existing_by_ilacfiyati_url:
            return self._update_existing_product(
                session,
                scraped_product,
                existing_by_ilacfiyati_url,
            )

        legacy_ilacfiyati_product = self._find_legacy_ilacfiyati_medicine_product(scraped_product)
        if legacy_ilacfiyati_product:
            return self._update_existing_product(
                session,
                scraped_product,
                legacy_ilacfiyati_product,
            )

        # Проверяем дубликаты по названию и бренду
        similar_products = Product.objects.filter(
            name__iexact=scraped_product.name, brand__name__iexact=scraped_product.brand
        )[
            :5
        ]  # Ограничиваем поиск

        for similar_product in similar_products:
            similarity = self._calculate_product_similarity(scraped_product, similar_product)
            if similarity > 0.8:  # 80% похожести
                # Если external_id точно разные, значит это РАЗНЫЕ товары с одинаковым именем. Не сливаем.
                if scraped_product.external_id and similar_product.external_id and scraped_product.external_id != similar_product.external_id:
                    continue
                # Обновляем существующий товар
                return self._update_existing_product(
                    session,
                    scraped_product,
                    similar_product,
                )

        # Создаем новый товар
        return self._create_new_product(session, scraped_product)

    def _find_ilacfiyati_medicine_product_by_source_url(
        self, scraped_product: ScrapedProduct
    ) -> Optional[Product]:
        """Находит medicine-заглушку по исходному ilacfiyati URL, даже если external_id пустой."""
        if scraped_product.source != "ilacfiyati" or not scraped_product.external_id:
            return None
        source_slug = str(scraped_product.external_id or "").strip()
        if not source_slug:
            return None
        url_marker = f"/ilaclar/{source_slug}"
        return Product.objects.filter(
            product_type="medicines",
            external_url__contains=url_marker,
        ).first()

    def _find_legacy_ilacfiyati_medicine_product(
        self, scraped_product: ScrapedProduct
    ) -> Optional[Product]:
        """Находит старую medicine-запись, если раньше external_id был slug вкладки."""
        if scraped_product.source != "ilacfiyati" or not scraped_product.external_id:
            return None
        source_slug = str(scraped_product.external_id or "").strip()
        if source_slug:
            url_marker = f"/ilaclar/{source_slug}"
            by_source_url = Product.objects.filter(
                product_type="medicines",
                external_id__in=self.ILACFIYATI_DETAIL_TAB_EXTERNAL_IDS,
                external_url__contains=url_marker,
            ).first()
            if by_source_url:
                return by_source_url

        if not scraped_product.name:
            return None
        return Product.objects.filter(
            product_type="medicines",
            name__iexact=scraped_product.name,
            external_id__in=self.ILACFIYATI_DETAIL_TAB_EXTERNAL_IDS,
        ).first()

    def _handle_api_conflict(
        self, scraped_product: ScrapedProduct, api_product: Product
    ) -> Tuple[str, Product]:
        """Обрабатывает конфликт с товаром из API."""
        # API данные имеют приоритет, но можем обновить дополнительную информацию
        updated = False

        # Обновляем изображения, если их нет
        if not api_product.main_image and scraped_product.images:
            main_image_url = self._get_first_image_url(scraped_product.images)
            if main_image_url:
                api_product.main_image = main_image_url
                updated = True

        # Обновляем описание, если его нет
        if not api_product.description and scraped_product.description:
            api_product.description = scraped_product.description
            updated = True

        # Добавляем информацию о парсере в external_data
        if "scraped_sources" not in api_product.external_data:
            api_product.external_data["scraped_sources"] = []

        source_info = {
            "source": scraped_product.source,
            "url": scraped_product.url,
            "last_seen": timezone.now().isoformat(),
        }

        if source_info not in api_product.external_data["scraped_sources"]:
            api_product.external_data["scraped_sources"].append(source_info)
            updated = True

        if updated:
            api_product.save()
            return "updated", api_product
        else:
            return "skipped", api_product

    def _calculate_product_similarity(
        self, scraped_product: ScrapedProduct, existing_product: Product
    ) -> float:
        """Вычисляет похожесть товаров."""
        if (
            scraped_product.external_id 
            and existing_product.external_id 
            and scraped_product.external_id != existing_product.external_id
        ):
            # Если внешние ID присутствуют и различаются - это разные товары
            return 0.0

        score = 0.0

        # Сравниваем названия
        if scraped_product.name.lower() == existing_product.name.lower():
            score += 0.4
        elif scraped_product.name.lower() in existing_product.name.lower():
            score += 0.2

        # Сравниваем бренды
        if (
            scraped_product.brand
            and existing_product.brand
            and scraped_product.brand.lower() == existing_product.brand.name.lower()
        ):
            score += 0.3

        # Сравниваем цены (если есть)
        if (
            scraped_product.price
            and existing_product.price
            and abs(float(scraped_product.price) - float(existing_product.price)) < 100
        ):
            score += 0.2

        # Сравниваем категории
        if (
            scraped_product.category
            and existing_product.category
            and scraped_product.category.lower() in existing_product.category.name.lower()
        ):
            score += 0.1

        return score

    def _contains_cyrillic(self, value: str) -> bool:
        return bool(re.search("[а-яА-Я]", value or ""))

    def _is_ai_content_ready(self, product: Product) -> bool:
        has_description = bool((product.description or "").strip())
        meta_title = (resolve_book_seo_value(product, "meta_title", lang="en") or "").strip()
        meta_description = (resolve_book_seo_value(product, "meta_description", lang="en") or "").strip()
        meta_keywords = (resolve_book_seo_value(product, "meta_keywords", lang="en") or "").strip()
        if not meta_title or not meta_description or not meta_keywords:
            return False
        if self._contains_cyrillic(meta_title) or self._contains_cyrillic(meta_description):
            return False
        return has_description

    def _is_ai_enabled_for_session(
        self,
        session: ScrapingSession,
        action: str,
    ) -> bool:
        config = session.scraper_config
        if action == "created":
            return bool(getattr(config, "ai_on_create_enabled", True))
        if action == "updated":
            return bool(getattr(config, "ai_on_update_enabled", True))
        return True

    def _get_furniture_product(self, product: Product) -> "FurnitureProduct":
        """Находит или создаёт FurnitureProduct для Product с product_type='furniture'."""
        from apps.catalog.models import FurnitureProduct
        item = getattr(product, "furniture_item", None)
        if item:
            return item
            
        # Создаём FurnitureProduct, привязанный к shadow Product
        from django.utils.text import slugify
        import uuid

        base_slug = product.slug or slugify(product.name)
        slug = f"furn-{base_slug}"
        if len(slug) > 490:
            slug = slug[:490]
        
        i = 2
        while FurnitureProduct.objects.filter(slug=slug).exists():
            suffix = f"-{i}"
            slug = f"{slug[:500-len(suffix)]}{suffix}"
            i += 1
            
        # Базовые поля от Product
        item = FurnitureProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            gender=getattr(product, "gender", None) or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        item.save()
        # Обновляем кеш
        product.furniture_item = item
        return item

    def _get_perfumery_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="perfumery_item",
            model_path="apps.catalog.models.PerfumeryProduct",
            slug_prefix="perfumery",
        )

    def _get_accessory_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="accessory_item",
            model_path="apps.catalog.models.AccessoryProduct",
            slug_prefix="accessory",
        )

    def _get_or_create_domain_product(
        self,
        product: Product,
        *,
        cache_attr: str,
        model_path: str,
        slug_prefix: str,
    ):
        item = getattr(product, cache_attr, None)
        if item:
            return item

        module_path, class_name = model_path.rsplit(".", 1)
        module = __import__(module_path, fromlist=[class_name])
        DomainModel = getattr(module, class_name)

        from django.utils.text import slugify

        base_slug = product.slug or slugify(product.name)
        slug = f"{slug_prefix}-{base_slug}"
        if len(slug) > 490:
            slug = slug[:490]

        i = 2
        while DomainModel.objects.filter(slug=slug).exists():
            suffix = f"-{i}"
            slug = f"{slug[:500-len(suffix)]}{suffix}"
            i += 1

        item = DomainModel(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            gender=getattr(product, "gender", None) or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        if hasattr(item, "stock_quantity"):
            item.stock_quantity = product.stock_quantity
        item.save()
        setattr(product, cache_attr, item)
        return item

    def _get_clothing_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="clothing_item",
            model_path="apps.catalog.models.ClothingProduct",
            slug_prefix="clothing",
        )

    def _get_shoe_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="shoe_item",
            model_path="apps.catalog.models.ShoeProduct",
            slug_prefix="shoe",
        )

    def _get_headwear_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="headwear_item",
            model_path="apps.catalog.models.HeadwearProduct",
            slug_prefix="headwear",
        )

    def _get_underwear_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="underwear_item",
            model_path="apps.catalog.models.UnderwearProduct",
            slug_prefix="underwear",
        )

    def _get_islamic_clothing_product(self, product: Product):
        return self._get_or_create_domain_product(
            product,
            cache_attr="islamic_clothing_item",
            model_path="apps.catalog.models.IslamicClothingProduct",
            slug_prefix="islamic-clothing",
        )

    def _safe_decimal(self, val: Any) -> Optional[Decimal]:
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _sync_furniture_color_variants(
        self, furniture_product: "FurnitureProduct", product: Product, variants: List[Dict[str, Any]]
    ) -> bool:
        """Создаёт/обновляет FurnitureVariant (цвета) под одной карточкой мебели — как при ручном вводе."""
        from apps.catalog.models import FurnitureProductImage, FurnitureVariant, FurnitureVariantImage

        changed = False
        for spec in variants:
            if not isinstance(spec, dict):
                continue
            ext = str(spec.get("external_id") or "").strip()
            if not ext:
                continue
            avail = bool(spec.get("is_available", True))
            raw_sq = spec.get("stock_quantity")
            if raw_sq is not None:
                try:
                    v_stock = int(raw_sq)
                except (TypeError, ValueError):
                    v_stock = DEFAULT_ASSUMED_STOCK_QUANTITY if avail else 0
            else:
                v_stock = DEFAULT_ASSUMED_STOCK_QUANTITY if avail else 0

            price_dec = self._safe_decimal(spec.get("price"))
            raw_color = (spec.get("color") or "").strip()
            if not raw_color:
                from apps.catalog.services.ikea_service import extract_ikea_color_from_variant_info

                raw_color = extract_ikea_color_from_variant_info(spec.get("variant_info"))
            defaults = {
                "name": (spec.get("display_name") or furniture_product.name or "")[:500],
                "color": raw_color[:50],
                "sku": ext[:100],
                "price": price_dec,
                "currency": (spec.get("currency") or furniture_product.currency or "TRY")[:5],
                "external_url": (spec.get("external_url") or "")[:2000],
                "sort_order": int(spec.get("sort_order") or 0),
                "stock_quantity": v_stock,
                "is_available": bool(avail and v_stock > 0),
                "is_active": True,
            }

            variant, created = FurnitureVariant.objects.get_or_create(
                product=furniture_product,
                external_id=ext,
                defaults=defaults,
            )
            if not created:
                for field in (
                    "name",
                    "color",
                    "sku",
                    "price",
                    "currency",
                    "external_url",
                    "sort_order",
                    "is_available",
                    "stock_quantity",
                    "is_active",
                ):
                    nv = defaults.get(field)
                    if nv is not None and getattr(variant, field) != nv:
                        setattr(variant, field, nv)
                        changed = True
                variant.save()

            imgs = [u for u in (spec.get("images") or []) if isinstance(u, str) and u]
            if imgs:
                variant.images.all().delete()
                bulk = [
                    FurnitureVariantImage(
                        variant=variant,
                        image_url=u,
                        alt_text=build_image_alt_text(
                            variant.name or furniture_product.name or product.name or "",
                            index=i,
                            color=raw_color,
                        ),
                        sort_order=i,
                        is_main=(i == 0),
                    )
                    for i, u in enumerate(imgs)
                ]
                FurnitureVariantImage.objects.bulk_create(bulk)
                if variant.main_image != imgs[0]:
                    variant.main_image = imgs[0]
                    variant.save(update_fields=["main_image"])
                changed = True

            vinfo = spec.get("variant_info")
            if vinfo is not None:
                ed = dict(variant.external_data) if isinstance(variant.external_data, dict) else {}
                if ed.get("ikea_variant_info") != vinfo:
                    ed["ikea_variant_info"] = vinfo
                    variant.external_data = ed
                    variant.save(update_fields=["external_data"])
                    changed = True

            changed = changed or created

        # Дубликат галереи на товаре: убираем строки с теми же URL, что уже на вариантах (в т.ч. без /products/parsed/).
        qs = furniture_product.variants.filter(is_active=True)
        variant_urls = set()
        for v in qs:
            for u in v.images.values_list("image_url", flat=True):
                s = (u or "").strip()
                if s:
                    variant_urls.add(s)
        n_rm = 0
        if variant_urls:
            n_rm, _ = FurnitureProductImage.objects.filter(
                product=furniture_product,
                image_url__in=list(variant_urls),
            ).delete()
        elif any(v.images.exists() for v in qs):
            n_rm, _ = FurnitureProductImage.objects.filter(
                product=furniture_product,
                image_url__contains="/products/parsed/",
            ).delete()
        if n_rm:
            changed = True

        default_v = qs.order_by("sort_order", "id").first()
        if default_v:
            if furniture_product.price != default_v.price:
                furniture_product.price = default_v.price
                changed = True
            if (default_v.currency or "") and furniture_product.currency != default_v.currency:
                furniture_product.currency = default_v.currency
                changed = True
            if default_v.main_image and furniture_product.main_image != default_v.main_image:
                furniture_product.main_image = default_v.main_image
                changed = True

        any_avail = qs.filter(is_available=True).exists()
        total_stock = sum((v.stock_quantity or 0) for v in qs if v.stock_quantity)
        if furniture_product.is_available != any_avail:
            furniture_product.is_available = any_avail
            changed = True
        new_sq = DEFAULT_ASSUMED_STOCK_QUANTITY if any_avail else (total_stock if total_stock > 0 else None)
        if default_v and new_sq is None and default_v.stock_quantity:
            new_sq = default_v.stock_quantity
        if furniture_product.stock_quantity != new_sq:
            furniture_product.stock_quantity = new_sq
            changed = True

        if changed:
            furniture_product.save()
        product_dirty = False
        if product.price != furniture_product.price:
            product.price = furniture_product.price
            product_dirty = True
        if product.currency != furniture_product.currency:
            product.currency = furniture_product.currency
            product_dirty = True
        if product.is_available != furniture_product.is_available:
            product.is_available = furniture_product.is_available
            product_dirty = True
        if product.stock_quantity != furniture_product.stock_quantity:
            product.stock_quantity = furniture_product.stock_quantity
            product_dirty = True
        if furniture_product.main_image and product.main_image != furniture_product.main_image:
            product.main_image = furniture_product.main_image
            product_dirty = True
        if product_dirty:
            product.save()
        return changed or product_dirty

    def _fashion_model_config(self, product_type: str) -> Optional[Dict[str, Any]]:
        from apps.catalog import models as catalog_models

        configs = {
            "clothing": {
                "getter": self._get_clothing_product,
                "variant_model": catalog_models.ClothingVariant,
                "variant_image_model": catalog_models.ClothingVariantImage,
                "variant_size_model": catalog_models.ClothingVariantSize,
                "product_size_model": catalog_models.ClothingProductSize,
            },
            "shoes": {
                "getter": self._get_shoe_product,
                "variant_model": catalog_models.ShoeVariant,
                "variant_image_model": catalog_models.ShoeVariantImage,
                "variant_size_model": catalog_models.ShoeVariantSize,
                "product_size_model": catalog_models.ShoeProductSize,
            },
            "headwear": {
                "getter": self._get_headwear_product,
                "variant_model": catalog_models.HeadwearVariant,
                "variant_image_model": catalog_models.HeadwearVariantImage,
                "variant_size_model": catalog_models.HeadwearVariantSize,
                "product_size_model": catalog_models.HeadwearProductSize,
            },
            "underwear": {
                "getter": self._get_underwear_product,
                "variant_model": catalog_models.UnderwearVariant,
                "variant_image_model": catalog_models.UnderwearVariantImage,
                "variant_size_model": catalog_models.UnderwearVariantSize,
                "product_size_model": catalog_models.UnderwearProductSize,
            },
            "islamic_clothing": {
                "getter": self._get_islamic_clothing_product,
                "variant_model": catalog_models.IslamicClothingVariant,
                "variant_image_model": catalog_models.IslamicClothingVariantImage,
                "variant_size_model": catalog_models.IslamicClothingVariantSize,
                "product_size_model": catalog_models.IslamicClothingProductSize,
            },
        }
        return configs.get(product_type)

    def _normalize_variant_sizes_payload(self, raw_sizes: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not raw_sizes:
            return normalized

        for idx, raw in enumerate(raw_sizes):
            if isinstance(raw, dict):
                size_value = str(raw.get("size") or "").strip()
                if not size_value:
                    continue
                normalized.append(
                    {
                        "size": size_value[:50],
                        "is_available": bool(raw.get("is_available", True)),
                        "stock_quantity": raw.get("stock_quantity"),
                        "sort_order": int(raw.get("sort_order") or idx),
                    }
                )
                continue

            if isinstance(raw, str):
                size_value = raw.strip()
                if not size_value:
                    continue
                normalized.append(
                    {
                        "size": size_value[:50],
                        "is_available": True,
                        "stock_quantity": None,
                        "sort_order": idx,
                    }
                )
        return normalized

    def _sync_product_size_rows(
        self,
        product_item,
        product_size_model,
        *,
        variants: List[Any],
    ) -> bool:
        aggregate: Dict[str, Dict[str, Any]] = {}
        for variant in variants:
            for size_row in variant.sizes.all().order_by("sort_order", "id"):
                size_key = (size_row.size or "").strip()
                if not size_key:
                    continue
                bucket = aggregate.setdefault(
                    size_key,
                    {
                        "size": size_key,
                        "is_available": False,
                        "stock_quantity": 0,
                        "sort_order": len(aggregate),
                    },
                )
                bucket["is_available"] = bucket["is_available"] or bool(size_row.is_available)
                if size_row.stock_quantity is not None:
                    bucket["stock_quantity"] = (bucket["stock_quantity"] or 0) + size_row.stock_quantity

        product_item.sizes.all().delete()
        bulk = []
        for idx, row in enumerate(aggregate.values()):
            stock_value = row["stock_quantity"] if row["stock_quantity"] > 0 else None
            bulk.append(
                product_size_model(
                    product=product_item,
                    size=row["size"],
                    is_available=bool(row["is_available"] or stock_value),
                    stock_quantity=stock_value,
                    sort_order=idx,
                )
            )
        if bulk:
            product_size_model.objects.bulk_create(bulk)
        return bool(bulk)

    def _sync_fashion_variants(
        self,
        product: Product,
        *,
        variants: List[Dict[str, Any]],
    ) -> bool:
        config = self._fashion_model_config(product.product_type)
        if not config:
            return False

        domain_product = config["getter"](product)
        VariantModel = config["variant_model"]
        VariantImageModel = config["variant_image_model"]
        VariantSizeModel = config["variant_size_model"]
        ProductSizeModel = config["product_size_model"]

        changed = False
        seen_external_ids: List[str] = []

        for idx, spec in enumerate(variants):
            if not isinstance(spec, dict):
                continue

            ext = str(spec.get("external_id") or "").strip()
            if not ext:
                continue
            seen_external_ids.append(ext)

            avail = bool(spec.get("is_available", True))
            raw_stock = spec.get("stock_quantity")
            if raw_stock is not None:
                try:
                    stock_quantity = int(raw_stock)
                except (TypeError, ValueError):
                    stock_quantity = DEFAULT_ASSUMED_STOCK_QUANTITY if avail else 0
            else:
                stock_quantity = DEFAULT_ASSUMED_STOCK_QUANTITY if avail else 0

            price_dec = self._safe_decimal(spec.get("price"))
            color_value = str(spec.get("color") or "").strip()[:50]
            variant_name_ru, variant_name_en = self._build_variant_names(
                str(domain_product.name or ""),
                color_value,
            )
            defaults = {
                "name": variant_name_ru or self._strip_variant_noise(spec.get("display_name") or domain_product.name or "")[:500],
                "name_en": variant_name_en,
                "color": color_value,
                "sku": str(spec.get("sku") or ext)[:100],
                "barcode": str(spec.get("barcode") or "")[:100],
                "gtin": str(spec.get("gtin") or "")[:100],
                "mpn": str(spec.get("mpn") or "")[:100],
                "price": price_dec,
                "currency": (spec.get("currency") or domain_product.currency or "TRY")[:5],
                "external_url": (spec.get("external_url") or "")[:2000],
                "sort_order": int(spec.get("sort_order") or idx),
                "stock_quantity": stock_quantity,
                "is_available": bool(avail and stock_quantity > 0),
                "is_active": True,
            }

            variant, created = VariantModel.objects.get_or_create(
                product=domain_product,
                external_id=ext,
                defaults=defaults,
            )
            if not created:
                for field, value in defaults.items():
                    if value is not None and getattr(variant, field) != value:
                        setattr(variant, field, value)
                        changed = True
                variant.save()
            changed = changed or created

            images = [u for u in (spec.get("images") or []) if isinstance(u, str) and u]
            if images:
                variant.images.all().delete()
                VariantImageModel.objects.bulk_create(
                    [
                        VariantImageModel(
                            variant=variant,
                            image_url=url,
                            alt_text=build_image_alt_text(
                                defaults["name"] or getattr(domain_product, "name", "") or getattr(product, "name", ""),
                                index=image_idx,
                                color=color_value,
                            ),
                            sort_order=image_idx,
                            is_main=(image_idx == 0),
                        )
                        for image_idx, url in enumerate(images)
                    ]
                )
                if variant.main_image != images[0]:
                    variant.main_image = images[0]
                    variant.save(update_fields=["main_image"])
                changed = True

            size_payload = self._normalize_variant_sizes_payload(spec.get("sizes") or [])
            variant.sizes.all().delete()
            if size_payload:
                VariantSizeModel.objects.bulk_create(
                    [
                        VariantSizeModel(
                            variant=variant,
                            size=row["size"],
                            is_available=row["is_available"],
                            stock_quantity=row["stock_quantity"],
                            sort_order=row["sort_order"],
                        )
                        for row in size_payload
                    ]
                )
                changed = True

            variant_external = dict(variant.external_data) if isinstance(variant.external_data, dict) else {}
            next_external = {
                "source": "scraper",
                "source_variant_id": ext,
                "sizes_payload": size_payload,
            }
            if color_value:
                next_external["color"] = color_value
            if variant_external != next_external:
                variant.external_data = next_external
                variant.save(update_fields=["external_data"])
                changed = True

        stale_qs = domain_product.variants.exclude(external_id__in=seen_external_ids)
        if stale_qs.filter(is_active=True).exists():
            stale_qs.update(is_active=False, is_available=False, stock_quantity=0)
            changed = True

        active_variants = list(domain_product.variants.filter(is_active=True).order_by("sort_order", "id"))
        if active_variants:
            default_variant = next(
                (row for row in active_variants if row.price is not None),
                active_variants[0],
            )
            if domain_product.price != default_variant.price:
                domain_product.price = default_variant.price
                changed = True
            if (default_variant.currency or "") and domain_product.currency != default_variant.currency:
                domain_product.currency = default_variant.currency
                changed = True
            if default_variant.main_image and domain_product.main_image != default_variant.main_image:
                domain_product.main_image = default_variant.main_image
                changed = True

            any_avail = any(v.is_available for v in active_variants)
            total_stock = sum((v.stock_quantity or 0) for v in active_variants if v.stock_quantity)
            new_sq = DEFAULT_ASSUMED_STOCK_QUANTITY if any_avail else (total_stock if total_stock > 0 else None)
            if domain_product.is_available != any_avail:
                domain_product.is_available = any_avail
                changed = True
            if getattr(domain_product, "stock_quantity", None) != new_sq:
                domain_product.stock_quantity = new_sq
                changed = True

        if changed:
            domain_product.save()

        self._sync_product_size_rows(
            domain_product,
            ProductSizeModel,
            variants=active_variants if active_variants else [],
        )

        product_dirty = False
        if product.price != domain_product.price:
            product.price = domain_product.price
            product_dirty = True
        if product.currency != domain_product.currency:
            product.currency = domain_product.currency
            product_dirty = True
        if product.is_available != domain_product.is_available:
            product.is_available = domain_product.is_available
            product_dirty = True
        if getattr(product, "stock_quantity", None) != getattr(domain_product, "stock_quantity", None):
            product.stock_quantity = getattr(domain_product, "stock_quantity", None)
            product_dirty = True
        if domain_product.main_image and product.main_image != domain_product.main_image:
            product.main_image = domain_product.main_image
            product_dirty = True
        if product_dirty:
            product.save()

        return changed or product_dirty

    def _update_furniture_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,  # зарезервировано для единообразия вызова
    ) -> bool:
        """Обновляет специфичные поля FurnitureProduct из атрибутов парсера."""
        item = self._get_furniture_product(product)
        updated = False
        has_color_variants = bool(
            isinstance(attrs.get("furniture_variants"), list) and attrs.get("furniture_variants")
        )

        # Синхронизация базовых полей, которые могли измениться в Product (через default_brand или парсер)
        if not item.brand and product.brand != item.brand:
            item.brand = product.brand
            updated = True
        if not item.category and product.category != item.category:
            item.category = product.category
            updated = True
        if product.name and not item.name:
            item.name = product.name
            updated = True
        if product.description and not item.description:
            item.description = product.description or ""
            updated = True
        if product.external_url != item.external_url:
            item.external_url = product.external_url or ""
            updated = True

        if "dimensions" in attrs and attrs["dimensions"] and not item.dimensions:
            item.dimensions = attrs["dimensions"]
            updated = True
        if "material" in attrs and attrs["material"] and not item.material:
            item.material = attrs["material"]
            updated = True
        if "furniture_type" in attrs and attrs["furniture_type"] and not item.furniture_type:
            item.furniture_type = attrs["furniture_type"]
            updated = True

        # Остаток с shadow Product — только если нет цветовых вариантов (иначе считаем из вариантов)
        if not has_color_variants:
            if product.is_available != item.is_available:
                item.is_available = product.is_available
                updated = True
            if product.stock_quantity != item.stock_quantity:
                item.stock_quantity = product.stock_quantity
                item.is_available = (item.stock_quantity or 0) > 0
                updated = True

        # Если есть видео
        if "video_url" in attrs and attrs["video_url"]:
            # Сохраняем в external_data или если есть поле video_url в модели
            if hasattr(item, "video_url") and not item.video_url:
                item.video_url = attrs["video_url"]
                updated = True

        # Если есть информация о вариантах от IKEA, сохраняем в external_data
        if "variant_info" in attrs and attrs["variant_info"]:
            if not isinstance(item.external_data, dict):
                item.external_data = {}
            if "variants" not in item.external_data:
                item.external_data["variants"] = attrs["variant_info"]
                updated = True

        if updated:
            item.save()

        if has_color_variants:
            if self._sync_furniture_color_variants(item, product, attrs["furniture_variants"]):
                updated = True

        return updated

    def _update_fashion_attributes_common(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        color_variants_key: str = "fashion_variants",
    ) -> bool:
        domain_config = self._fashion_model_config(product.product_type)
        if not domain_config:
            return False

        domain_product = domain_config["getter"](product)
        updated = False

        if not domain_product.brand and product.brand != domain_product.brand:
            domain_product.brand = product.brand
            updated = True
        if not domain_product.category and product.category != domain_product.category:
            domain_product.category = product.category
            updated = True
        if product.name and not domain_product.name:
            domain_product.name = product.name
            updated = True
        if product.description and not domain_product.description:
            domain_product.description = product.description or ""
            updated = True
        if product.external_url != domain_product.external_url:
            domain_product.external_url = product.external_url or ""
            updated = True

        color_value = str(attrs.get("color") or "").strip()
        if color_value and not getattr(domain_product, "color", ""):
            domain_product.color = color_value[:50]
            updated = True

        gender_value = self._normalize_perfume_gender(str(attrs.get("gender") or attrs.get("cinsiyet") or ""))
        if gender_value and not getattr(domain_product, "gender", ""):
            domain_product.gender = gender_value
            updated = True

        default_size = str(attrs.get("default_size") or "").strip()
        if (
            default_size
            and product.product_type in {"headwear", "underwear"}
            and hasattr(domain_product, "size")
            and not getattr(domain_product, "size", "")
        ):
            domain_product.size = default_size[:20]
            updated = True

        if "video_url" in attrs and attrs["video_url"] and not getattr(domain_product, "video_url", ""):
            domain_product.video_url = attrs["video_url"]
            updated = True

        if updated:
            domain_product.save()

        variants = attrs.get(color_variants_key) or []
        if isinstance(variants, list) and variants:
            if self._sync_fashion_variants(product, variants=variants):
                updated = True

        return updated

    def _update_clothing_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        return self._update_fashion_attributes_common(product, attrs)

    def _update_shoe_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        updated = self._update_fashion_attributes_common(product, attrs)
        shoe_product = self._get_shoe_product(product)
        updated = self._apply_dynamic_attribute_specs(
            target=shoe_product,
            product_type="shoes",
            attrs=attrs,
        ) or updated
        return updated

    def _update_headwear_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        return self._update_fashion_attributes_common(product, attrs)

    def _update_underwear_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        return self._update_fashion_attributes_common(product, attrs)

    def _update_islamic_clothing_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        return self._update_fashion_attributes_common(product, attrs)

    def _update_existing_product(
        self,
        session: ScrapingSession,
        scraped_product: ScrapedProduct,
        existing_product: Product,
    ) -> Tuple[str, Product]:
        """Обновляет существующий товар."""
        updated = False
        prepared_attrs = self._prepare_scraped_attributes(scraped_product, existing_product.product_type)
        should_repair_ilacfiyati_external_id = self._should_repair_ilacfiyati_external_id(
            existing_product,
            scraped_product,
        )
        external_id_for_variant_check = (
            scraped_product.external_id
            if should_repair_ilacfiyati_external_id
            else existing_product.external_id
        )

        # Флаг, указывающий, что мы обновляем базовый товар пришедшими данными его варианта
        # В этом случае мы НЕ должны перезатирать общие поля базового товара (фото, цену, url)
        # специфичными данными конкретного варианта (цвета/ножек), чтобы не "создавать дублей/миксов"
        is_variant_update = bool(
            scraped_product.external_id 
            and external_id_for_variant_check
            and str(scraped_product.external_id) != str(external_id_for_variant_check)
        )

        if should_repair_ilacfiyati_external_id:
            existing_product.external_id = scraped_product.external_id
            updated = True

        if not is_variant_update:
            # Обновляем цену, если она изменилась (только для базового товара)
            if scraped_product.price and scraped_product.price != existing_product.price:
                existing_product.old_price = existing_product.price
                existing_product.price = scraped_product.price
                existing_product.currency = scraped_product.currency
                updated = True

            # Обновляем наличие
            if scraped_product.is_available != existing_product.is_available:
                existing_product.is_available = scraped_product.is_available
                updated = True
                
            # Обновляем количество на складе
            if scraped_product.stock_quantity is not None and scraped_product.stock_quantity != existing_product.stock_quantity:
                existing_product.stock_quantity = scraped_product.stock_quantity
                existing_product.is_available = (existing_product.stock_quantity or 0) > 0
                updated = True

        # Бренд после обогащения/ручной правки не перетираем повторным парсом:
        # при повторной синхронизации только дозаполняем пустое поле.
        if scraped_product.brand:
            from apps.catalog.models import Brand
            brand_name = scraped_product.brand.strip()
            if not existing_product.brand:
                brand, _ = Brand.objects.get_or_create(name=brand_name)
                existing_product.brand = brand
                updated = True

        if scraped_product.description is not None:
            next_description = str(scraped_product.description).strip()
            current_description = (existing_product.description or "").strip()
            if (
                next_description
                and (
                    not current_description
                    or self._should_replace_existing_description(
                        existing_product,
                        scraped_product,
                        current_description,
                        next_description,
                    )
                )
                and (not is_variant_update or not current_description)
            ):
                existing_product.description = next_description
                updated = True

        if not is_variant_update:
            # Обновляем изображения, если их нет
            if not existing_product.main_image and scraped_product.images:
                main_image_url = self._get_first_image_url(scraped_product.images)
                if main_image_url:
                    existing_product.main_image = main_image_url
                    updated = True

            # Обновляем video_url: приоритет R2 из images, иначе attributes
            if not existing_product.video_url:
                first_vid = None
                if scraped_product.images:
                    first_vid = self.catalog_normalizer._first_video_url_from_images(scraped_product.images)
                if first_vid:
                    existing_product.video_url = first_vid
                    updated = True
                    self.logger.info(
                        "Updated video_url for existing product %s from gallery images",
                        existing_product.id,
                    )
                elif prepared_attrs and prepared_attrs.get("video_url"):
                    existing_product.video_url = prepared_attrs["video_url"]
                    updated = True
                    self.logger.info(
                        f"Updated video_url for existing product {existing_product.id} to {existing_product.video_url}"
                    )
            if scraped_product.url and scraped_product.url != existing_product.external_url:
                existing_product.external_url = scraped_product.url
                updated = True

        if scraped_product.category:
            category, product_type = resolve_category_and_product_type(scraped_product.category)
            if category is not None and not existing_product.category_id:
                existing_product.category = category
                updated = True
            if product_type is not None and not existing_product.product_type:
                existing_product.product_type = product_type
                updated = True

        # Обновляем external_data
        if not isinstance(existing_product.external_data, dict):
            existing_product.external_data = {}
        if "scraped_sources" not in existing_product.external_data:
            existing_product.external_data["scraped_sources"] = []

        if scraped_product.source:
            existing_product.external_data.setdefault("source", scraped_product.source)
        if scraped_product.scraped_at:
            existing_product.external_data["scraped_at"] = scraped_product.scraped_at
        if prepared_attrs:
            if is_variant_update:
                variant_content = existing_product.external_data.get("variant_content") or {}
                if not isinstance(variant_content, dict):
                    variant_content = {}
                snapshot = dict(variant_content.get(str(scraped_product.external_id)) or {})
                safe_attrs = _json_safe_scraped_value(prepared_attrs)
                if snapshot.get("attributes") != safe_attrs:
                    snapshot["attributes"] = safe_attrs
                if scraped_product.description:
                    next_description = str(scraped_product.description).strip()
                    if next_description and snapshot.get("description") != next_description:
                        snapshot["description"] = next_description
                if scraped_product.url and snapshot.get("url") != scraped_product.url:
                    snapshot["url"] = scraped_product.url
                snapshot["updated_at"] = timezone.now().isoformat()
                if variant_content.get(str(scraped_product.external_id)) != snapshot:
                    variant_content[str(scraped_product.external_id)] = snapshot
                    existing_product.external_data["variant_content"] = variant_content
                    updated = True
            else:
                existing_product.external_data["attributes"] = _json_safe_scraped_value(
                    prepared_attrs
                )
                if (
                    existing_product.product_type == "medicines"
                    and scraped_product.source == "ilacfiyati"
                    and not prepared_attrs.get("is_stub")
                    and existing_product.external_data.get("is_stub")
                ):
                    existing_product.external_data["is_stub"] = False
                    updated = True

        source_info = {
            "source": scraped_product.source,
            "url": scraped_product.url,
            # Цена из normalize_price() может быть Decimal — JSONField не сериализует её.
            "price": float(scraped_product.price)
            if scraped_product.price is not None
            else None,
            "last_updated": timezone.now().isoformat(),
        }

        existing_product.external_data["scraped_sources"].append(source_info)
        existing_product.last_synced_at = timezone.now()
        updated = True

        # Сначала сохраняем базовую карточку. Доменные модели при save()
        # синхронизируют себя обратно в Product, поэтому им нужно видеть уже
        # обновленные общие поля, иначе старая заглушка может затереть описание/цену.
        if updated:
            existing_product.save()
            self._clear_product_domain_cache(existing_product)
            updated = False

        # Обновляем доменные и общие атрибуты (ISBN, medicine-коды и т.д.)
        if prepared_attrs:
            if self._update_product_attributes(
                existing_product, prepared_attrs, session=session
            ):
                updated = True

        if updated:
            existing_product.save()

        # Обрабатываем аналоги, если это медицина
        if existing_product.product_type == "medicines" and getattr(scraped_product, "analogs", None):
            self._process_medicine_analogs(existing_product, scraped_product, session)

        # Всегда нормализуем медиа (обновляем галереи) независимо от того,
        # поменялись ли текстовые атрибуты, так как могли измениться лимиты или тип продукта
        if scraped_product.images:
            try:
                self.catalog_normalizer._normalize_product_images(
                    existing_product, scraped_product.images
                )
            except Exception as e:
                self.logger.warning(
                    f"Ошибка при нормализации изображений для товара {existing_product.id}: {e}"
                )

            # Обновляем авторов, только если их сейчас нет (или перенесли на проверку)
            if (
                prepared_attrs
                and "author" in prepared_attrs
                and existing_product.product_type == "books"
            ):
                try:
                    book_product = self._get_book_product(existing_product)
                    if not book_product.book_authors.exists():
                        author_str = prepared_attrs["author"]
                        if author_str:
                            author_names = [a.strip() for a in author_str.split(",") if a.strip()]
                            for idx, name in enumerate(author_names):
                                author = self._normalize_and_get_author(name)
                                if author:
                                    # Связываем с BookProduct
                                    ProductAuthor.objects.create(
                                        product=book_product, author=author, sort_order=idx
                                    )
                except Exception as e:
                    self.logger.error(
                        f"Ошибка при обновлении авторов для товара {existing_product.id}: {e}"
                )

        return "updated", existing_product

    def _clear_product_domain_cache(self, product: Product) -> None:
        fields_cache = getattr(getattr(product, "_state", None), "fields_cache", None)
        if not isinstance(fields_cache, dict):
            return
        for related_name in self.PRODUCT_DOMAIN_RELATED_NAMES:
            fields_cache.pop(related_name, None)

    def _should_repair_ilacfiyati_external_id(
        self,
        existing_product: Product,
        scraped_product: ScrapedProduct,
    ) -> bool:
        if existing_product.product_type != "medicines":
            return False
        if scraped_product.source != "ilacfiyati" or not scraped_product.external_id:
            return False
        current_external_id = str(existing_product.external_id or "").strip()
        if not current_external_id:
            return True
        return (
            current_external_id in self.ILACFIYATI_DETAIL_TAB_EXTERNAL_IDS
            and current_external_id != str(scraped_product.external_id).strip()
        )

    def _should_replace_existing_description(
        self,
        existing_product: Product,
        scraped_product: ScrapedProduct,
        current_description: str,
        next_description: str,
    ) -> bool:
        """Разрешает безопасно обновить source-описание для расширенных medicine tabs."""
        if existing_product.product_type != "medicines":
            return False
        if scraped_product.source != "ilacfiyati":
            return False
        attrs = scraped_product.attributes if isinstance(scraped_product.attributes, dict) else {}
        if not isinstance(attrs.get("source_tabs"), dict) or not attrs["source_tabs"]:
            return False

        tab_titles = (
            "Ne İçin Kullanılır:",
            "Kullanmadan Dikkat Edilecekler:",
            "Nasıl Kullanılır:",
            "Yan Etkileri:",
            "Saklanması:",
        )
        next_tab_count = sum(1 for title in tab_titles if title in next_description)
        current_tab_count = sum(1 for title in tab_titles if title in current_description)
        if next_tab_count <= current_tab_count:
            return False

        source_markers = (
            "İLAÇ DURUMU:",
            "SGK Ödeme Durumu:",
            "İLAÇ FİYATI:",
            "Özet:",
            "KULLANMA TALİMATI",
        )
        current_looks_like_source = any(marker in current_description for marker in source_markers)
        next_is_much_richer = len(next_description) > max(len(current_description) + 500, len(current_description) * 2)
        return current_looks_like_source or next_is_much_richer

    def _get_book_product(self, product: Product) -> "BookProduct":
        """Находит или создаёт BookProduct для Product с product_type='books'."""
        book = getattr(product, "book_item", None)
        if book:
            return book
        # Создаём BookProduct, привязанный к shadow Product
        from django.utils.text import slugify

        base_slug = product.slug or slugify(product.name)
        slug = f"book-{base_slug}"
        i = 2
        while BookProduct.objects.filter(slug=slug).exists():
            slug = f"book-{base_slug}-{i}"
            i += 1
        book = BookProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        book.save()
        # Обновляем кеш, чтобы product.book_item возвращал созданный объект
        product.book_item = book
        return book

    def _get_jewelry_product(self, product: Product) -> JewelryProduct:
        """Находит или создаёт JewelryProduct для Product с product_type='jewelry'."""
        jewelry = getattr(product, "jewelry_item", None)
        if jewelry:
            return jewelry
        from django.utils.text import slugify

        base_slug = product.slug or slugify(product.name)
        slug = f"jewelry-{base_slug}"
        i = 2
        while JewelryProduct.objects.filter(slug=slug).exists():
            slug = f"jewelry-{base_slug}-{i}"
            i += 1
        jewelry = JewelryProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        jewelry.save()
        product.jewelry_item = jewelry
        return jewelry

    def _get_medicine_product(self, product: Product) -> "MedicineProduct":
        """Находит или создаёт MedicineProduct для Product с product_type='medicines'."""
        from apps.catalog.models import MedicineProduct
        from django.utils.text import slugify

        medicine = getattr(product, "medicine_item", None)
        if medicine:
            return medicine

        base_slug = product.slug or slugify(product.name)
        slug = f"medicine-{base_slug}"
        i = 2
        while MedicineProduct.objects.filter(slug=slug).exists():
            slug = f"medicine-{base_slug}-{i}"
            i += 1
            
        medicine = MedicineProduct(
            base_product=product,
            name=product.name,
            slug=slug,
            description=product.description or "",
            category=product.category,
            brand=product.brand,
            price=product.price,
            currency=product.currency or "RUB",
            old_price=product.old_price,
            external_id=product.external_id or "",
            external_url=product.external_url or "",
            external_data=product.external_data or {},
            is_active=product.is_active,
            is_available=product.is_available,
            main_image=product.main_image or "",
            video_url=product.video_url or "",
        )
        medicine.save()
        product.medicine_item = medicine
        return medicine

    def _update_book_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        """Обновляет книжные атрибуты в BookProduct."""
        if not any(
            k in attrs
            for k in ("isbn", "publisher", "pages", "cover_type", "language", "publication_year")
        ):
            return False
        book_product = self._get_book_product(product)
        updated = False
        if "isbn" in attrs and attrs["isbn"]:
            new_isbn = str(attrs["isbn"]).strip()
            digits = re.sub(r"\D", "", new_isbn)
            if (
                len(digits) in (10, 13)
                and "00000" not in new_isbn
                and "..." not in new_isbn
                and not book_product.isbn
            ):
                book_product.isbn = new_isbn
                updated = True
        if "publisher" in attrs and attrs["publisher"] and not book_product.publisher:
            book_product.publisher = attrs["publisher"]
            updated = True
        if "pages" in attrs and not book_product.pages:
            try:
                pages_val = int(attrs["pages"])
                if 0 < pages_val < 10000:
                    book_product.pages = pages_val
                    updated = True
            except (ValueError, TypeError):
                pass
        if "cover_type" in attrs and attrs["cover_type"] and not book_product.cover_type:
            book_product.cover_type = attrs["cover_type"]
            updated = True
        if "language" in attrs and attrs["language"] and not book_product.language:
            book_product.language = attrs["language"]
            updated = True
        if "publication_year" in attrs and attrs["publication_year"] and not book_product.publication_date:
            try:
                year = int(attrs["publication_year"])
                new_date = datetime.date(year, 1, 1)
                book_product.publication_date = new_date
                updated = True
            except (ValueError, TypeError):
                pass
        if updated:
            book_product.save()
        return updated

    def _update_jewelry_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        """Обновляет атрибуты украшений в JewelryProduct."""
        if not any(
            k in attrs
            for k in (
                "jewelry_type",
                "material",
                "metal_purity",
                "stone_type",
                "carat_weight",
                "gender",
            )
        ):
            return False
        jewelry_product = self._get_jewelry_product(product)
        updated = False
        from decimal import Decimal

        valid_types = {"ring", "bracelet", "necklace", "earrings", "pendant"}
        if "jewelry_type" in attrs and attrs["jewelry_type"] and not jewelry_product.jewelry_type:
            v = str(attrs["jewelry_type"]).strip().lower()
            if v in valid_types:
                jewelry_product.jewelry_type = v
                updated = True
        if (
            "material" in attrs
            and attrs["material"]
            and not jewelry_product.material
        ):
            jewelry_product.material = str(attrs["material"]).strip()[:100]
            updated = True
        if (
            "metal_purity" in attrs
            and attrs["metal_purity"]
            and not jewelry_product.metal_purity
        ):
            jewelry_product.metal_purity = str(attrs["metal_purity"]).strip()[:50]
            updated = True
        if (
            "stone_type" in attrs
            and attrs["stone_type"]
            and not jewelry_product.stone_type
        ):
            jewelry_product.stone_type = str(attrs["stone_type"]).strip()[:100]
            updated = True
        if "carat_weight" in attrs and attrs["carat_weight"] is not None and jewelry_product.carat_weight is None:
            try:
                v = Decimal(str(attrs["carat_weight"]).strip().replace(",", "."))
                if v >= 0:
                    jewelry_product.carat_weight = v
                    updated = True
            except (ValueError, TypeError):
                pass
        if (
            "gender" in attrs
            and attrs["gender"]
            and not jewelry_product.gender
        ):
            jewelry_product.gender = str(attrs["gender"]).strip()[:10]
            updated = True
        if updated:
            jewelry_product.save()
        return updated

    def _update_medicine_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        """Обновляет медицинские атрибуты в MedicineProduct."""
        medicine_keys = (
            "dosage_form", "active_ingredient", "prescription_required", "volume", 
            "origin_country", "sgk_status", "administration_route", "prescription_type",
            "barcode", "atc_code", "nfc_code", "sgk_equivalent_code",
            "sgk_active_ingredient_code", "sgk_public_no", "shelf_life",
            "storage_conditions", "special_notes"
        )
        if not any(k in attrs for k in medicine_keys):
            return False
            
        medicine_product = self._get_medicine_product(product)
        updated = False

        field_mapping = [
            ("dosage_form", "dosage_form", 100),
            ("active_ingredient", "active_ingredient", 300),
            ("volume", "volume", 100),
            ("origin_country", "origin_country", 500),
            ("sgk_status", "sgk_status", 500),
            ("administration_route", "administration_route", 500),
            ("prescription_type", "prescription_type", 500),
            ("barcode", "barcode", 100),
            ("atc_code", "atc_code", 100),
            ("nfc_code", "nfc_code", 100),
            ("sgk_equivalent_code", "sgk_equivalent_code", 100),
            ("sgk_active_ingredient_code", "sgk_active_ingredient_code", 100),
            ("sgk_public_no", "sgk_public_no", 100),
            ("shelf_life", "shelf_life", 200),
            ("storage_conditions", "storage_conditions", 500),
            ("special_notes", "special_notes", None),
        ]
        for attr_key, model_field, max_len in field_mapping:
            if attr_key not in attrs or not attrs[attr_key]:
                continue
            v = str(attrs[attr_key]).strip()
            if max_len:
                v = v[:max_len]
            if v and not getattr(medicine_product, model_field):
                setattr(medicine_product, model_field, v)
                updated = True

        if "prescription_required" in attrs:
            val = bool(attrs["prescription_required"])
            if val != medicine_product.prescription_required:
                medicine_product.prescription_required = val
                updated = True
                
        if updated:
            medicine_product.save()
        return updated

    def _update_perfumery_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        perfumery_keys = (
            "volume",
            "fragrance_type",
            "fragrance_family",
            "gender",
            "top_notes",
            "heart_notes",
            "base_notes",
        )
        if not any(attrs.get(key) for key in perfumery_keys):
            return False

        perfumery_product = self._get_perfumery_product(product)
        updated = False

        simple_fields = {
            "volume": 50,
            "top_notes": 500,
            "heart_notes": 500,
            "base_notes": 500,
        }
        for field_name, max_length in simple_fields.items():
            value = str(attrs.get(field_name) or "").strip()
            if value and not getattr(perfumery_product, field_name):
                setattr(perfumery_product, field_name, value[:max_length])
                updated = True

        fragrance_type = self._normalize_perfume_type(str(attrs.get("fragrance_type") or ""))
        if fragrance_type and not perfumery_product.fragrance_type:
            perfumery_product.fragrance_type = fragrance_type
            updated = True

        fragrance_family = self._normalize_perfume_family(str(attrs.get("fragrance_family") or ""))
        if fragrance_family and not perfumery_product.fragrance_family:
            perfumery_product.fragrance_family = fragrance_family
            updated = True

        gender = self._normalize_perfume_gender(str(attrs.get("gender") or ""))
        if gender and not perfumery_product.gender:
            perfumery_product.gender = gender
            updated = True

        if attrs.get("volume_options") or attrs.get("component_types") or attrs.get("is_perfume_set") or attrs.get("gender_options"):
            external_data = (
                dict(perfumery_product.external_data)
                if isinstance(perfumery_product.external_data, dict)
                else {}
            )
            perfumery_meta = dict(external_data.get("perfumery_meta") or {})
            changed = False
            if attrs.get("volume_options") and perfumery_meta.get("volume_options") != attrs.get("volume_options"):
                perfumery_meta["volume_options"] = attrs.get("volume_options")
                changed = True
            if attrs.get("component_types") and perfumery_meta.get("component_types") != attrs.get("component_types"):
                perfumery_meta["component_types"] = attrs.get("component_types")
                changed = True
            if attrs.get("is_perfume_set") and perfumery_meta.get("is_perfume_set") is not True:
                perfumery_meta["is_perfume_set"] = True
                changed = True
            if attrs.get("gender_options") and perfumery_meta.get("gender_options") != attrs.get("gender_options"):
                perfumery_meta["gender_options"] = attrs.get("gender_options")
                changed = True
            if changed:
                external_data["perfumery_meta"] = perfumery_meta
                perfumery_product.external_data = external_data
                updated = True

        if updated:
            perfumery_product.save()
        return updated

    def _update_accessory_attributes(
        self, product: Product, attrs: Dict[str, Any], *, session: Optional[ScrapingSession] = None
    ) -> bool:
        if not any(attrs.get(key) for key in ("accessory_type", "material", "gender", "cinsiyet")):
            return False

        accessory_product = self._get_accessory_product(product)
        updated = False

        gender_value = self._normalize_perfume_gender(str(attrs.get("gender") or attrs.get("cinsiyet") or ""))
        if gender_value and not accessory_product.gender:
            accessory_product.gender = gender_value
            accessory_product.save(update_fields=["gender"])
            updated = True
        updated = self._apply_dynamic_attribute_specs(
            target=accessory_product,
            product_type="accessories",
            attrs=attrs,
        ) or updated
        return updated

    def _upsert_medicine_analog_reference(
        self,
        product: MedicineProduct,
        *,
        name: str,
        barcode: str,
        atc_code: str,
        sgk_equivalent_code: str,
        external_id: str,
        source: str,
        source_tab: str,
        analog_product: Optional[MedicineProduct] = None,
    ) -> MedicineAnalog:
        """Сохраняет явную строку аналога из Eşdeğeri / SGK Eşdeğeri."""
        barcode = str(barcode or "").strip()
        external_id = str(external_id or "").strip()
        source = str(source or "").strip()
        atc_code = str(atc_code or "").strip()
        sgk_equivalent_code = str(sgk_equivalent_code or "").strip()
        source_tab = str(source_tab or "").strip()
        name = str(name or "").strip()

        qs = MedicineAnalog.objects.filter(product=product, source=source[:100])
        analog = None
        if external_id:
            analog = qs.filter(external_id=external_id[:200]).first()
        if analog is None and barcode:
            analog = qs.filter(barcode=barcode[:50]).first()
        if analog is None and name:
            analog = qs.filter(name=name[:500], source_tab=source_tab[:100]).first()
        if analog is None:
            analog = MedicineAnalog(product=product, source=source[:100])

        changed = False
        field_values = {
            "name": name[:500],
            "barcode": barcode[:50],
            "atc_code": atc_code[:20],
            "sgk_equivalent_code": sgk_equivalent_code[:100],
            "external_id": external_id[:200],
            "source_tab": source_tab[:100],
        }
        if analog_product is not None:
            field_values["analog_product"] = analog_product

        for field_name, value in field_values.items():
            if value and getattr(analog, field_name) != value:
                setattr(analog, field_name, value)
                changed = True

        if analog.pk is None:
            analog.save()
        elif changed:
            analog.save(
                update_fields=[
                    "name",
                    "barcode",
                    "atc_code",
                    "sgk_equivalent_code",
                    "external_id",
                    "source_tab",
                    "analog_product",
                ]
            )
        return analog

    def _link_medicine_analog_reference(
        self,
        analog: MedicineAnalog,
        analog_product: MedicineProduct,
        *,
        barcode: str,
        atc_code: str,
        sgk_equivalent_code: str,
    ) -> None:
        changed = False
        if analog.analog_product_id != analog_product.pk:
            analog.analog_product = analog_product
            changed = True
        if barcode and not analog.barcode:
            analog.barcode = barcode[:50]
            changed = True
        if atc_code and not analog.atc_code:
            analog.atc_code = atc_code[:20]
            changed = True
        if sgk_equivalent_code and not analog.sgk_equivalent_code:
            analog.sgk_equivalent_code = sgk_equivalent_code[:100]
            changed = True
        if changed:
            analog.save(update_fields=["analog_product", "barcode", "atc_code", "sgk_equivalent_code"])

    def _find_existing_medicine_analog_product(
        self,
        *,
        name: str,
        barcode: str,
        external_id: str,
        url: str = "",
    ) -> Optional[Product]:
        if barcode:
            med = MedicineProduct.objects.filter(barcode=barcode).select_related("base_product").first()
            if med and med.base_product:
                return med.base_product
            product = Product.objects.filter(barcode=barcode, product_type="medicines").first()
            if product:
                return product

        if external_id:
            product = Product.objects.filter(external_id=external_id, product_type="medicines").first()
            if product:
                return product
            med = MedicineProduct.objects.filter(external_id=external_id).select_related("base_product").first()
            if med and med.base_product:
                return med.base_product
            url_marker = f"/ilaclar/{external_id}"
            product = Product.objects.filter(
                product_type="medicines",
                external_url__contains=url_marker,
            ).first()
            if product:
                return product

        if url:
            product = Product.objects.filter(
                product_type="medicines",
                external_url=url,
            ).first()
            if product:
                return product

        return Product.objects.filter(name__iexact=name, product_type="medicines").first()

    def _process_medicine_analogs(
        self, product: Product, scraped_product: ScrapedProduct, session: ScrapingSession
    ) -> None:
        """Обрабатывает спарсенные аналоги (создает заглушки, если их нет)."""
        if not getattr(scraped_product, 'analogs', None):
            return
            
        medicine_product = self._get_medicine_product(product)
        active_ingredient = medicine_product.active_ingredient
        atc_code = medicine_product.atc_code
        
        # Если у основного препарата нет ни active_ingredient, ни atc_code, мы не сможем их неявно связать
        if not active_ingredient and not atc_code:
            return
            
        for analog_data in scraped_product.analogs:
            analog_name = analog_data.get('name')
            if not analog_name:
                continue

            analog_url = analog_data.get('url', '')
            analog_external_id = str(
                analog_data.get("external_id")
                or (urlparse(analog_url).path.rstrip("/").split("/")[-1] if analog_url else "")
                or ""
            ).strip()
            analog_barcode = str(analog_data.get("barcode") or "").strip()
            analog_atc_code = str(analog_data.get("atc_code") or "").strip()
            analog_sgk_code = str(analog_data.get("sgk_equivalent_code") or "").strip()
            analog_source_tab = str(analog_data.get("source_tab") or "").strip()

            analog_ref = self._upsert_medicine_analog_reference(
                medicine_product,
                name=analog_name,
                barcode=analog_barcode,
                atc_code=analog_atc_code or atc_code,
                sgk_equivalent_code=analog_sgk_code,
                external_id=analog_external_id,
                source=scraped_product.source,
                source_tab=analog_source_tab,
            )

            # Проверяем, существует ли уже такой препарат. Коды надежнее названия:
            # названия на ilacfiyati часто отличаются процентами, пробелами и упаковкой.
            existing = self._find_existing_medicine_analog_product(
                name=analog_name,
                barcode=analog_barcode,
                external_id=analog_external_id,
                url=analog_url,
            )
            if existing:
                med = self._get_medicine_product(existing)
                updated = False
                if analog_barcode and not med.barcode:
                    med.barcode = analog_barcode[:100]
                    updated = True
                if active_ingredient and not med.active_ingredient:
                    med.active_ingredient = active_ingredient
                    updated = True
                if (analog_atc_code or atc_code) and not med.atc_code:
                    med.atc_code = (analog_atc_code or atc_code)[:100]
                    updated = True
                if analog_sgk_code and not med.sgk_equivalent_code:
                    med.sgk_equivalent_code = analog_sgk_code[:100]
                    updated = True
                if updated:
                    med.save()
                self._link_medicine_analog_reference(
                    analog_ref,
                    med,
                    barcode=analog_barcode,
                    atc_code=analog_atc_code or atc_code,
                    sgk_equivalent_code=analog_sgk_code,
                )
                continue
                
            # Если не существует, создаем базовую заглушку
            # Парсер затем сможет ее обновить при прямом парсинге
            analog_price = analog_data.get('price')
            
            stub_scraped = ScrapedProduct(
                name=analog_name,
                price=analog_price,
                url=analog_url,
                category=scraped_product.category,
                source=scraped_product.source,
                external_id=analog_external_id,
                barcode=analog_barcode,
                is_available=True,
                attributes={
                    'is_stub': True,
                    'active_ingredient': active_ingredient,
                    'atc_code': analog_atc_code or atc_code,
                    'barcode': analog_barcode,
                    'sgk_equivalent_code': analog_sgk_code,
                }
            )
            # Чтобы избежать зацикливания, не передаем analogs
            try:
                _, created_product = self._create_new_product(session, stub_scraped)
                created_med = self._get_medicine_product(created_product)
                self._link_medicine_analog_reference(
                    analog_ref,
                    created_med,
                    barcode=analog_barcode,
                    atc_code=analog_atc_code or atc_code,
                    sgk_equivalent_code=analog_sgk_code,
                )
            except Exception as e:
                self.logger.error(f"Ошибка создания аналога {analog_name}: {e}")

    def _update_product_attributes(
        self,
        product: Product,
        attrs: Dict[str, Any],
        *,
        session: Optional[ScrapingSession] = None,
    ) -> bool:
        """Обновляет атрибуты товара из словаря.

        Специфичные поля типа (книги, украшения) — через реестр _ATTRIBUTE_UPDATE_HANDLER_NAMES.
        Общие поля (weight, SEO, OG) записываются в Product.
        """
        updated = False
        handler_name = _ATTRIBUTE_UPDATE_HANDLER_NAMES.get(product.product_type)
        if handler_name:
            handler = getattr(self, handler_name, None)
            if handler:
                updated = handler(product, attrs, session=session)

        # --- Общие поля → Product ---

        # Weight (e.g. "0,441" kg from ummaland)
        if "weight" in attrs and attrs["weight"] and product.weight_value is None:
            try:
                weight_str = str(attrs["weight"]).strip().replace(",", ".")
                weight_val = float(weight_str)
                if weight_val >= 0:
                    product.weight_value = weight_val
                    product.weight_unit = "kg"
                    updated = True
            except (ValueError, TypeError):
                pass

        gender_value = self._normalize_perfume_gender(str(attrs.get("gender") or attrs.get("cinsiyet") or ""))
        if gender_value and not product.gender:
            product.gender = gender_value
            updated = True

        # SEO Fields
        # Внимание: Спарсенные SEO данные обычно на языке источника (Русский для Ummaland).
        # Поля meta_title, meta_description в модели предназначены для АНГЛИЙСКОГО (EN).
        # Поэтому спарсенные данные сохраняем в русские поля (seo_title, seo_description)
        # или игнорируем, если они дублируют название/описание.

        ru_translation_defaults = {}

        # Meta Title -> seo_title (RU)
        if (
            "meta_title" in attrs
            and attrs["meta_title"]
            and not product.seo_title
        ):
            product.seo_title = attrs["meta_title"][:70]
            updated = True
        if "meta_title" in attrs and attrs["meta_title"]:
            ru_translation_defaults["meta_title"] = str(attrs["meta_title"])[:255]

        # Meta Description -> seo_description (RU)
        if (
            "meta_description" in attrs
            and attrs["meta_description"]
            and not product.seo_description
        ):
            product.seo_description = attrs["meta_description"][:160]
            updated = True
        if "meta_description" in attrs and attrs["meta_description"]:
            ru_translation_defaults["meta_description"] = str(attrs["meta_description"])[:500]

        # Keywords -> keywords (RU) - JSON field
        if "meta_keywords" in attrs and attrs["meta_keywords"] and not product.keywords:
            keywords_list = [k.strip() for k in attrs["meta_keywords"].split(",") if k.strip()]
            product.keywords = keywords_list
            updated = True
        if "meta_keywords" in attrs and attrs["meta_keywords"]:
            ru_translation_defaults["meta_keywords"] = str(attrs["meta_keywords"])[:500]

        if ru_translation_defaults:
            ru_translation, _ = product.translations.get_or_create(locale="ru")
            translation_updated_fields = []
            for field_name, value in ru_translation_defaults.items():
                if value and not getattr(ru_translation, field_name, ""):
                    setattr(ru_translation, field_name, value)
                    translation_updated_fields.append(field_name)
            if translation_updated_fields:
                ru_translation.save(update_fields=translation_updated_fields + ["updated_at"])
                updated = True

        # OG-данные от источника (на языке источника) — сохраняем в external_data для справки AI,
        # но `og_image_url` сохраняем и в модель, чтобы AI/SEO могли использовать исходное фото товара.
        # Текстовые OG-поля по-прежнему оставляем только как source-* для справки AI.
        og_keys = {
            "og_image_url": "source_og_image_url",
            "og_title": "source_og_title",
            "og_description": "source_og_description",
        }
        og_has_data = any(k in attrs and attrs[k] for k in og_keys)
        if og_has_data:
            if "seo_data" not in product.external_data:
                product.external_data["seo_data"] = {}
            for attr_key, data_key in og_keys.items():
                if attr_key in attrs and attrs[attr_key] and data_key not in product.external_data["seo_data"]:
                    product.external_data["seo_data"][data_key] = attrs[attr_key]
                    updated = True

        if attrs.get("og_image_url") and not product.og_image_url:
            product.og_image_url = str(attrs["og_image_url"])[:2000]
            updated = True
            domain_item = getattr(product, "domain_item", None)
            if domain_item is not None and hasattr(domain_item, "og_image_url") and not getattr(domain_item, "og_image_url", ""):
                domain_item.og_image_url = product.og_image_url
                domain_item.save(update_fields=["og_image_url"])

        return updated

    def _create_new_product(
        self, session: ScrapingSession, scraped_product: ScrapedProduct
    ) -> Tuple[str, Product]:
        """Создает новый товар."""
        # Преобразуем в формат ProductData для CatalogNormalizer
        from apps.vapi.client import ProductData

        resolved_product_type = None
        if scraped_product.category:
            _, resolved_product_type = resolve_category_and_product_type(scraped_product.category)
        prepared_attrs = self._prepare_scraped_attributes(scraped_product, resolved_product_type)

        product_data = ProductData(
            id=scraped_product.external_id,
            name=scraped_product.name,
            description=scraped_product.description,
            price=float(scraped_product.price) if scraped_product.price else None,
            currency=scraped_product.currency,
            category=scraped_product.category,
            brand=scraped_product.brand,
            images=scraped_product.images,
            url=scraped_product.url,
            availability=scraped_product.is_available,
            metadata={
                "source": scraped_product.source,
                "scraped_at": scraped_product.scraped_at,
                "attributes": prepared_attrs,
                "stock_quantity": scraped_product.stock_quantity,
            },
            barcode=scraped_product.barcode,
        )

        # Создаем товар через CatalogNormalizer
        product = self.catalog_normalizer.normalize_product(product_data)

        if product.product_type == "medicines" and prepared_attrs.get("is_stub"):
            if not isinstance(product.external_data, dict):
                product.external_data = {}
            if product.external_data.get("is_stub") is not True:
                product.external_data["is_stub"] = True
                product.save(update_fields=["external_data"])

        # Свежеспарсенный товар — отмечаем как новинку
        if not product.is_new:
            product.is_new = True
            product.save(update_fields=["is_new"])

        # Дефолтный остаток для parser-driven товаров: 1000, если парсер не передал точный stock.
        if product.is_available and not product.stock_quantity:
            product.stock_quantity = DEFAULT_ASSUMED_STOCK_QUANTITY
            product.save(update_fields=["stock_quantity"])

        # Для типов из BRAND_CLEAR_PRODUCT_TYPES убираем бренд, если проставился
        if product.product_type in BRAND_CLEAR_PRODUCT_TYPES and product.brand:
            product.brand = None
            product.save(update_fields=["brand"])

        # Обновляем дополнительные атрибуты (ISBN, SEO, вес и т.д.)
        # normalize_product уже вызвал _sync_product_fields_from_metadata, но
        # _update_product_attributes дополнительно заполняет SEO поля и вес,
        # а также создаёт доменные объекты (BookProduct, JewelryProduct и т.д.).
        if prepared_attrs:
            if self._update_product_attributes(product, prepared_attrs, session=session):
                product.save()

        # Обрабатываем аналоги, если это медицина
        if product.product_type == "medicines" and getattr(scraped_product, "analogs", None):
            self._process_medicine_analogs(product, scraped_product, session)

        # После создания доменной модели нужно переназначить галерею на неё, а не на Product.
        # normalize_product вызывал _normalize_product_images до появления domain_item,
        # поэтому изображения могли сохраниться как ProductImage и быть невидимыми для BookProduct и др.
        # Здесь повторно вызываем нормализацию медиа: теперь product.domain_item указывает
        # на конкретную доменную модель, и все изображения попадут в её gallery (BookProductImage и т.п.).
        if scraped_product.images:
            try:
                self.catalog_normalizer._normalize_product_images(product, scraped_product.images)
            except Exception as e:
                self.logger.warning(
                    "Failed to re-normalize media for new product %s (external_id=%s): %s",
                    product.pk,
                    scraped_product.external_id,
                    e,
                )

        # Авторы привязаны к BookProduct — сохраняем всегда, не зависит от updated
        if (
            prepared_attrs
            and "author" in prepared_attrs
            and product.product_type == "books"
        ):
            try:
                author_str = prepared_attrs["author"]
                if author_str:
                    book_product = self._get_book_product(product)
                    book_product.book_authors.all().delete()

                    author_names = [a.strip() for a in author_str.split(",") if a.strip()]
                    for idx, name in enumerate(author_names):
                        author = self._normalize_and_get_author(name)
                        if author:
                            ProductAuthor.objects.create(
                                product=book_product, author=author, sort_order=idx
                            )
            except Exception as e:
                self.logger.error(
                    f"Ошибка при добавлении авторов для нового товара {product.id}: {e}"
                )

        return "created", product

    def _update_scraper_stats(self, config: ScraperConfig, session: ScrapingSession, success: bool):
        """Обновляет статистику парсера."""
        config.total_runs += 1
        config.last_run_at = timezone.now()

        if success:
            config.successful_runs += 1
            config.last_success_at = timezone.now()
            config.total_products_scraped += session.products_found
            config.status = "active"
        else:
            config.last_error_at = timezone.now()
            config.last_error_message = session.error_message
            config.status = "error"

        config.save()

    def _extract_search_query(self, url: str) -> Optional[str]:
        """Извлекает поисковый запрос из URL."""
        from urllib.parse import urlparse, parse_qs

        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Пробуем разные параметры поиска
            for param in ["q", "query", "search", "searchTerm", "arama"]:
                if param in query_params:
                    return query_params[param][0]
        except Exception:
            pass

        return None


class DeduplicationService:
    """Сервис дедупликации товаров между API и парсерами."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Находит потенциальные дубликаты товаров."""
        duplicates = []

        # Ищем товары с одинаковыми названиями
        products_by_name = {}
        for product in Product.objects.all():
            name_key = product.name.lower().strip()
            if name_key not in products_by_name:
                products_by_name[name_key] = []
            products_by_name[name_key].append(product)

        for name, products in products_by_name.items():
            if len(products) > 1:
                # Группируем по источникам
                api_products = [p for p in products if p.external_data.get("source") == "api"]
                scraped_products = [p for p in products if p.external_data.get("source") != "api"]

                if api_products and scraped_products:
                    duplicates.append(
                        {
                            "name": name,
                            "api_products": [{"id": p.id, "name": p.name} for p in api_products],
                            "scraped_products": [
                                {
                                    "id": p.id,
                                    "name": p.name,
                                    "source": p.external_data.get("source"),
                                }
                                for p in scraped_products
                            ],
                        }
                    )

        return duplicates

    def merge_duplicates(self, api_product_id: int, scraped_product_ids: List[int]) -> bool:
        """Объединяет дубликаты, оставляя API товар."""
        try:
            with transaction.atomic():
                api_product = Product.objects.get(id=api_product_id)
                scraped_products = Product.objects.filter(id__in=scraped_product_ids)

                # Собираем дополнительную информацию из спарсенных товаров
                additional_images = []
                additional_sources = []

                for scraped_product in scraped_products:
                    # Собираем изображения
                    if (
                        scraped_product.main_image
                        and scraped_product.main_image != api_product.main_image
                    ):
                        additional_images.append(scraped_product.main_image)

                    # Собираем информацию об источниках
                    additional_sources.append(
                        {
                            "source": scraped_product.external_data.get("source"),
                            "url": scraped_product.external_url,
                            "last_seen": scraped_product.updated_at.isoformat(),
                        }
                    )

                    # Удаляем спарсенный товар
                    scraped_product.delete()

                # Обновляем API товар дополнительной информацией
                if "additional_images" not in api_product.external_data:
                    api_product.external_data["additional_images"] = []
                api_product.external_data["additional_images"].extend(additional_images)

                if "scraped_sources" not in api_product.external_data:
                    api_product.external_data["scraped_sources"] = []
                api_product.external_data["scraped_sources"].extend(additional_sources)

                api_product.save()

                self.logger.info(f"Объединены дубликаты для товара {api_product.name}")
                return True

        except Exception as e:
            self.logger.error(f"Ошибка при объединении дубликатов: {e}")
            return False
