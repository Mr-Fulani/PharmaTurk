import datetime
import hashlib
import logging
import re
from typing import Any, Dict, Optional, List
from django.db import models, transaction
from django.utils.text import slugify as django_slugify
from apps.catalog.models import Product, GlobalAttributeKey
from apps.catalog.attribute_specs import get_dynamic_attribute_spec
from apps.ai.services.medicine_reference import dosage_form_labels
from apps.ai.services.medicine_title import looks_like_source_name
from apps.ai.services.ownership import SOURCE_NAME_KEY, remember_source_name
from apps.catalog.product_semantics import looks_untranslated_turkish
from apps.ai.services.size_inventory import apply_size_inventory

logger = logging.getLogger(__name__)


def _canonical_attr_slug(slug: str) -> str:
    return str(slug or "").strip().lower().replace("_", "-")


# Поля доменной модели/Product, которые AI перезаписывает только если менеджер
# не правил их после генерации (см. build_content_snapshot).
_SNAPSHOT_TARGET_FIELDS = (
    "description",
    "meta_title", "meta_description", "meta_keywords", "og_title", "og_description",
    "seo_title", "seo_description", "keywords",
)


def _snapshot_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def build_content_snapshot(target: Any) -> Dict[str, Any]:
    """Снимок описания, SEO и переводов на момент генерации.

    Хранятся только хэши непустых значений: тексты лекарств большие, а для
    проверки «менялось ли поле после генерации» достаточно сравнить хэш.
    """
    snapshot: Dict[str, Any] = {"fields": {}, "translations": {}}
    if target is None:
        return snapshot
    for field in _SNAPSHOT_TARGET_FIELDS:
        value = getattr(target, field, None)
        if value:
            snapshot["fields"][field] = _snapshot_hash(value)
    manager = getattr(target, "translations", None)
    if manager is None:
        return snapshot
    for trans in manager.all():
        snapshot["translations"][trans.locale] = {
            f.name: _snapshot_hash(getattr(trans, f.name))
            for f in trans._meta.concrete_fields
            if isinstance(f, (models.CharField, models.TextField))
            and f.name != "locale"
            and getattr(trans, f.name)
        }
    return snapshot


def _make_unique_slug_for_domain(name: str, model_class, current_pk: Optional[int] = None, max_length: int = 500) -> str:
    """Генерирует уникальный slug из названия для доменной модели (кириллица → латиница)."""
    try:
        from transliterate import slugify as trans_slugify
        base_slug = (trans_slugify(name, language_code="ru") or django_slugify(name) or "").strip("-")[:max_length]
    except Exception:
        base_slug = (django_slugify(name) or "").strip("-")[:max_length]
    if not base_slug:
        base_slug = "product"
    slug = base_slug
    qs = model_class.objects.filter(slug=slug)
    if current_pk is not None:
        qs = qs.exclude(pk=current_pk)
    i = 2
    while qs.exists():
        suffix = f"-{i}"
        slug = f"{base_slug[:max_length - len(suffix)]}{suffix}"
        qs = model_class.objects.filter(slug=slug)
        if current_pk is not None:
            qs = qs.exclude(pk=current_pk)
        i += 1
    return slug


# Шаблон названия строится из турецкого оригинала: лекарства и БАДы (supplement_content).
SOURCE_NAME_PRODUCT_TYPES = ("medicines", "supplements")


def _remember_name_before_ai_title(item, name: Optional[str] = None) -> bool:
    """Перед первым AI-названием лекарства или БАДа запоминает турецкий оригинал.

    ``name`` — оригинал из входа лога (БАД, чьё name уже переведено прежней
    обработкой), иначе берётся name товара. Название, уже переведённое или
    обрезанное прежней обработкой, не запоминается: шаблон из него не строится
    (medicine_title.medicine_source_name).
    """
    name = name or item.name
    external = item.external_data if isinstance(item.external_data, dict) else {}
    if external.get(SOURCE_NAME_KEY) or not looks_like_source_name(name):
        return False
    item.external_data = external
    return remember_source_name(external, name)


class BaseAIApplier:
    """Базовый класс для применения результатов AI к любым товарам."""

    # Снимок build_content_snapshot из input_data лога. None — защита выключена
    # (прямой вызов или старый лог без снимка).
    content_snapshot: Optional[Dict[str, Any]] = None

    def _may_overwrite(self, current: Any, *path: str) -> bool:
        """Можно ли перезаписать значение: оно пустое или не менялось с генерации."""
        if not current or self.content_snapshot is None:
            return True
        node: Any = self.content_snapshot
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        return node == _snapshot_hash(current)

    def apply(self, target: Any, ai_data: Dict[str, Any]) -> bool:
        """Применяет данные к объекту (Product или доменному объекту).

        Базовое имя (name) НЕ перезаписывается — оригинальное scraped-название
        сохраняется. AI заполняет описание, SEO и переводы.
        """
        updated = False
        
        # 1. SEO & Metadata
        updated |= self._apply_seo(target, ai_data)
        
        # 2. Описание (имя не трогаем — сохраняем оригинал)
        new_desc = ai_data.get('generated_description')
        current_desc = getattr(target, 'description', None)
        if new_desc and current_desc != new_desc and self._may_overwrite(current_desc, "fields", "description"):
            target.description = new_desc
            updated = True
            
        # 3. Переводы
        translations = ai_data.get('translations', {})
        if translations:
            updated |= self.apply_translations(target, translations)

        # 4. Динамические атрибуты
        updated |= self._apply_dynamic_attributes(target, ai_data)

        # 5. Размерный ряд для поддерживаемых apparel-доменов. Остатки не
        # меняются; товары с вариантами отсекаются семантической проверкой.
        attrs = ai_data.get("extracted_attributes") or {}
        updated |= apply_size_inventory(
            target,
            attrs.get("sizes") if isinstance(attrs, dict) else [],
            getattr(type(target), "_domain_product_type", None),
        )
            
        if updated:
            target.save()
        return updated

    def _apply_seo(self, target: Any, ai_data: Dict[str, Any]) -> bool:
        """Применяет SEO мета-данные."""
        updated = False
        # Разные именования в Product и доменных моделях
        is_domain = hasattr(target, 'meta_title')
        
        mapping = {
            'generated_seo_title': 'meta_title' if is_domain else 'seo_title',
            'generated_seo_description': 'meta_description' if is_domain else 'seo_description',
            'generated_keywords': 'meta_keywords' if is_domain else 'keywords',
        }
        
        # Добавляем маппинг для OG text-тегов (только для доменных моделей)
        if is_domain:
            mapping.update({
                'og_title': 'og_title',
                'og_description': 'og_description',
            })
        
        for ai_key, model_key in mapping.items():
            val = ai_data.get(ai_key)
            if not val:
                continue
                
            if isinstance(val, list):
                val = ", ".join(map(str, val))
                
            current = getattr(target, model_key, None)
            if val and current != val and self._may_overwrite(current, "fields", model_key):
                if model_key in ['seo_title', 'meta_title']:
                    val = str(val)[:70]
                if model_key in ['seo_description', 'meta_description']:
                    val = str(val)[:160]
                setattr(target, model_key, val)
                updated = True

        # og_image_url — URL, не проверяем на кириллицу
        if is_domain:
            og_img = ai_data.get('og_image_url')
            if og_img and not getattr(target, 'og_image_url', None):
                target.og_image_url = og_img
                updated = True

        return updated

    def apply_translations(self, target: Any, translations_data: Dict[str, Any]) -> bool:
        """Применяет переводы через related name или связанные модели."""
        if not hasattr(target, 'translations'):
            return False
            
        updated = False
        for locale, data in translations_data.items():
            if not isinstance(data, dict):
                continue
            
            trans = target.translations.filter(locale=locale).first()
            created = False
            if not trans:
                # Пытаемся создать через related manager
                trans = target.translations.model(product=target, locale=locale)
                created = True
            
            trans_updated = False
            for field in ['name', 'description']:
                val = data.get(f'generated_{field}') or data.get(field)
                current = getattr(trans, field, None)
                if val and current != val and self._may_overwrite(current, "translations", locale, field):
                    setattr(trans, field, val)
                    trans_updated = True

            seo_map = {
                'meta_title': ['meta_title', 'seo_title', 'generated_seo_title'],
                'meta_description': ['meta_description', 'seo_description', 'generated_seo_description'],
                'meta_keywords': ['meta_keywords', 'keywords', 'generated_keywords'],
                'og_title': ['og_title'],
                'og_description': ['og_description'],
            }
            for model_field, source_keys in seo_map.items():
                if not hasattr(trans, model_field):
                    continue
                val = None
                for key in source_keys:
                    raw = data.get(key)
                    if raw:
                        val = raw
                        break
                if not val:
                    continue
                if isinstance(val, list):
                    val = ", ".join(str(item).strip() for item in val if str(item).strip())
                val = str(val).strip()
                if not val:
                    continue
                if model_field in ['meta_title', 'og_title']:
                    val = val[:255]
                elif model_field in ['meta_description', 'og_description']:
                    val = val[:500]
                elif model_field == 'meta_keywords':
                    val = val[:500]
                current = getattr(trans, model_field, None)
                if current != val and self._may_overwrite(current, "translations", locale, model_field):
                    setattr(trans, model_field, val)
                    trans_updated = True
            
            if trans_updated or created:
                trans.save()
                updated = True
        return updated

    def _apply_dynamic_attributes(self, target: Any, ai_data: Dict[str, Any]) -> bool:
        """Применяет динамические атрибуты из AI к товару/доменной модели."""
        if not hasattr(target, "dynamic_attributes"):
            return False

        attrs = ai_data.get("extracted_attributes") or {}
        raw_dynamic = attrs.get("dynamic_attributes")
        if not isinstance(raw_dynamic, list) or not raw_dynamic:
            return False

        updated = False
        existing = {
            _canonical_attr_slug(pav.attribute_key.slug): pav
            for pav in target.dynamic_attributes.select_related("attribute_key").all()
            if pav.attribute_key_id and pav.attribute_key and pav.attribute_key.slug
        }

        for row in raw_dynamic:
            if not isinstance(row, dict):
                continue
            slug = _canonical_attr_slug(row.get("slug") or "")
            if not slug:
                continue
            product_type = getattr(type(target), "_domain_product_type", None)
            if get_dynamic_attribute_spec(product_type, slug) is None:
                continue
            key = GlobalAttributeKey.objects.filter(slug=slug).first()
            if not key:
                legacy_slug = slug.replace("-", "_")
                key = GlobalAttributeKey.objects.filter(slug=legacy_slug).first()
            if not key:
                continue

            value = str(row.get("value") or row.get("value_ru") or row.get("value_en") or "").strip()
            value_ru = str(row.get("value_ru") or value or "").strip() or None
            value_en = str(row.get("value_en") or "").strip() or None
            if not value:
                continue
            if looks_untranslated_turkish(value_ru) or looks_untranslated_turkish(value_en):
                continue

            value = value[:500]
            value_ru = value_ru[:500] if value_ru else None
            value_en = value_en[:500] if value_en else None
            sort_order = key.sort_order
            current = existing.get(slug)
            if current is None:
                # get_or_create опирается на DB constraint и остаётся безопасным,
                # если два воркера одновременно применяют результат к одному товару.
                current, created = target.dynamic_attributes.get_or_create(
                    attribute_key=key,
                    defaults={
                        "value": value,
                        "value_ru": value_ru,
                        "value_en": value_en,
                        "sort_order": sort_order,
                    },
                )
                existing[slug] = current
                if created:
                    updated = True
                    continue

            changed = False
            if current.value != value:
                current.value = value
                changed = True
            # Не обнуляем перевод, который AI не вернул: он мог быть заполнен вручную.
            if value_ru is not None and (current.value_ru or None) != value_ru:
                current.value_ru = value_ru
                changed = True
            if value_en is not None and (current.value_en or None) != value_en:
                current.value_en = value_en
                changed = True
            if current.sort_order != sort_order:
                current.sort_order = sort_order
                changed = True
            if changed:
                current.save(update_fields=["value", "value_ru", "value_en", "sort_order"])
                updated = True

        return updated

class BookAIApplier(BaseAIApplier):
    """Специфичный апплайер для книжной тематики."""
    
    def apply(self, target: Any, ai_data: Dict[str, Any]) -> bool:
        # Сначала базовые поля
        updated = super().apply(target, ai_data)
        
        # Специфичные книжные атрибуты из экстракции
        attrs = ai_data.get('extracted_attributes', {})
        if not attrs:
            return updated
            
        book_updated = False
        
        # ISBN
        isbn = attrs.get('isbn')
        if isbn and hasattr(target, 'isbn'):
            target.isbn = str(isbn)[:20]
            book_updated = True
            
        # Издательство
        publisher = attrs.get('publisher')
        if publisher and hasattr(target, 'publisher'):
            target.publisher = str(publisher)[:200]
            book_updated = True
            
        # Авторы
        authors_raw = attrs.get('authors')
        if authors_raw and hasattr(target, 'book_authors'):
            updated_authors = self._apply_authors(target, authors_raw)
            if updated_authors:
                book_updated = True

        # Тип переплёта (если AI определил по обложке, а при скрапинге не было)
        cover_type = attrs.get('cover_type')
        if cover_type and hasattr(target, 'cover_type') and not target.cover_type:
            target.cover_type = str(cover_type)[:50]
            book_updated = True

        # Язык книги
        language = attrs.get('language')
        if language and hasattr(target, 'language') and not target.language:
            target.language = str(language)[:50]
            book_updated = True

        # Год издания (только если не задано)
        pub_year = attrs.get('publication_year')
        if pub_year and hasattr(target, 'publication_date') and not target.publication_date:
            try:
                target.publication_date = datetime.date(int(pub_year), 1, 1)
                book_updated = True
            except (TypeError, ValueError):
                pass

        if book_updated:
            target.save()
            updated = True
            
        return updated

    def _apply_authors(self, book_product: Any, authors_data: Any) -> bool:
        """Привязывает авторов к книге."""
        from apps.catalog.models import Author, ProductAuthor
        
        if isinstance(authors_data, str):
            author_names = [a.strip() for a in authors_data.split(",") if a.strip()]
        elif isinstance(authors_data, list):
            author_names = [str(a).strip() for a in authors_data if str(a).strip()]
        else:
            return False

        if not author_names:
            return False

        # Очищаем старые связи (или обновляем, если нужно по-умному)
        # Для простоты пока просто пересоздаем, если список изменился
        current_authors = list(book_product.book_authors.select_related('author').values_list('author__first_name', 'author__last_name'))
        current_author_names = [f"{fn} {ln}".strip() for fn, ln in current_authors]
        
        if set(current_author_names) == set(author_names):
            return False

        with transaction.atomic():
            # Удаляем старые связи через промежуточную таблицу
            ProductAuthor.objects.filter(product=book_product).delete()
            
            for idx, full_name in enumerate(author_names):
                parts = full_name.split(None, 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""
                
                author, _ = Author.objects.get_or_create(
                    first_name=first_name, 
                    last_name=last_name
                )
                ProductAuthor.objects.create(product=book_product, author=author, sort_order=idx)
        
        return True


class JewelryAIApplier(BaseAIApplier):
    """Применяет результаты AI к украшениям: SEO, переводы + атрибуты (jewelry_type, material, gender и т.д.)."""

    _valid_jewelry_types = {"ring", "bracelet", "necklace", "earrings", "pendant"}

    def apply(self, target: Any, ai_data: Dict[str, Any]) -> bool:
        updated = super().apply(target, ai_data)
        attrs = ai_data.get("extracted_attributes") or {}
        if not attrs:
            return updated
        jewelry_updated = False
        if attrs.get("jewelry_type"):
            v = str(attrs["jewelry_type"]).strip().lower()
            if v in self._valid_jewelry_types and hasattr(target, "jewelry_type"):
                if (target.jewelry_type or "") != v:
                    target.jewelry_type = v
                    jewelry_updated = True
        for field in ("material", "metal_purity", "stone_type", "gender"):
            if field not in attrs or not hasattr(target, field):
                continue
            v = str(attrs[field]).strip()
            if not v:
                continue
            max_len = {"material": 100, "metal_purity": 50, "stone_type": 100, "gender": 10}.get(field, 100)
            v = v[:max_len]
            if (getattr(target, field) or "") != v:
                setattr(target, field, v)
                jewelry_updated = True
        if attrs.get("carat_weight") is not None and hasattr(target, "carat_weight"):
            try:
                from decimal import Decimal
                v = Decimal(str(attrs["carat_weight"]).strip().replace(",", "."))
                if v >= 0 and (target.carat_weight is None or target.carat_weight != v):
                    target.carat_weight = v
                    jewelry_updated = True
            except (ValueError, TypeError):
                pass
        if jewelry_updated:
            target.save()
            updated = True
        return updated


class MedicineAIApplier(BaseAIApplier):
    """Применяет AI-результаты к медицинским препаратам.

    Помимо базовых SEO/переводов, заполняет специфические поля:
    barcode, atc_code, shelf_life, storage_conditions, administration_route,
    sgk_status, prescription_type, special_notes.
    Для переводов также заполняет: indications, usage_instructions,
    side_effects, contraindications, storage_conditions.
    """

    # Ссылка: имя поля в attrs → (имя в модели, max_len | None)
    _MEDICINE_FIELDS = [
        ('barcode', 'barcode', 100),
        ('atc_code', 'atc_code', 100),
        ('nfc_code', 'nfc_code', 100),
        ('sgk_equivalent_code', 'sgk_equivalent_code', 100),
        ('sgk_active_ingredient_code', 'sgk_active_ingredient_code', 100),
        ('sgk_public_no', 'sgk_public_no', 100),
        ('dosage_form', 'dosage_form', 20),
        ('active_ingredient', 'active_ingredient', 300),
        ('volume', 'volume', 100),
        ('origin_country', 'origin_country', 500),
        ('administration_route', 'administration_route', 500),
        ('shelf_life', 'shelf_life', 200),
        ('storage_conditions', 'storage_conditions', 500),
        ('sgk_status', 'sgk_status', 500),
        ('prescription_type', 'prescription_type', 500),
        ('special_notes', 'special_notes', None),
    ]

    _DOSAGE_FORM_ALIASES = {
        'tablet': 'tablet',
        'tabletler': 'tablet',
        'kapsül': 'capsule',
        'kapsul': 'capsule',
        'capsule': 'capsule',
        'şurup': 'syrup',
        'surup': 'syrup',
        'syrup': 'syrup',
        'damla': 'drops',
        'drops': 'drops',
        'merhem': 'ointment',
        'ointment': 'ointment',
        'krem': 'cream',
        'cream': 'cream',
        'jel': 'gel',
        'gel': 'gel',
        'enjeksiyon': 'injection',
        'injection': 'injection',
        'toz': 'powder',
        'powder': 'powder',
        'sprey': 'spray',
        'spray': 'spray',
        'fitil': 'suppository',
        'suppository': 'suppository',
    }

    # Поля перевода MedicineProductTranslation
    _TRANSLATION_FIELDS = [
        'indications', 'usage_instructions', 'side_effects',
        'contraindications', 'storage_conditions',
        'administration_route', 'shelf_life', 'sgk_status', 
        'prescription_type', 'special_notes', 'origin_country',
        'dosage_form', 'active_ingredient', 'volume'
    ]

    def apply(self, target: Any, ai_data: Dict[str, Any]) -> bool:
        updated = super().apply(target, ai_data)
        attrs = ai_data.get('extracted_attributes') or {}
        medicine_updated = False

        # Применяем медицинские поля из extracted_attributes
        for attr_key, model_field, max_len in self._MEDICINE_FIELDS:
            val = attrs.get(attr_key)
            if not val:
                continue
            val = str(val).strip()
            if model_field == 'dosage_form':
                val = self._DOSAGE_FORM_ALIASES.get(val.casefold(), val.casefold())
                valid_values = {
                    choice[0]
                    for choice in target._meta.get_field('dosage_form').choices
                }
                if val not in valid_values:
                    continue
            if max_len:
                val = val[:max_len]
            # Не перезаписываем если в модели уже есть значение
            if hasattr(target, model_field) and not getattr(target, model_field, None):
                setattr(target, model_field, val)
                medicine_updated = True

        if medicine_updated:
            target.save()
            updated = True

        # Переводы уже обработаны в super().apply -> apply_translations.
        # Больше ничего здесь делать не нужно для MedicineProductTranslation.
        return updated

    def apply_translations(self, target: Any, translations_data: Dict[str, Any]) -> bool:
        """Override: добавляем медицинские поля, сохраняя базовое применение SEO."""
        if not hasattr(target, 'translations'):
            return False

        updated = super().apply_translations(target, translations_data)

        for locale, data in translations_data.items():
            if not isinstance(data, dict):
                continue
            trans = target.translations.filter(locale=locale).first()
            created = False
            if not trans:
                trans = target.translations.model(product=target, locale=locale)
                created = True
            trans_updated = False
            # Медицинские поля
            # Маппинг для обрезания длины в переводах
            limits = {
                'administration_route': 500,
                'shelf_life': 200,
                'sgk_status': 500,
                'prescription_type': 500,
                'origin_country': 500,
            }
            for field in self._TRANSLATION_FIELDS:
                if field not in data:
                    continue
                val = data[field]
                val_str = str(val).strip() if val is not None else ""
                # dosage_form — varchar(20): только подпись из справочника форм,
                # свободный текст модели («таблетки, покрытые…») не пишем.
                if field == "dosage_form" and val_str not in dosage_form_labels(locale):
                    continue
                if field in limits:
                    val_str = val_str[:limits[field]]
                current = getattr(trans, field, None)
                if current != val_str and self._may_overwrite(current, "translations", locale, field):
                    setattr(trans, field, val_str)
                    trans_updated = True
            if trans_updated or created:
                trans.save()
                updated = True
        return updated


class SupplementAIApplier(BaseAIApplier):
    """БАД: кроме названия, описания и SEO — «Состав» и «Порция» в переводах (собирает код)."""

    _TRANSLATION_FIELDS = (("active_ingredient", 500), ("serving_size", 200))

    def apply_translations(self, target: Any, translations_data: Dict[str, Any]) -> bool:
        if not hasattr(target, "translations"):
            return False
        updated = super().apply_translations(target, translations_data)
        for locale, data in translations_data.items():
            if not isinstance(data, dict):
                continue
            values = {
                field: str(data.get(field) or "").strip()[:limit]
                for field, limit in self._TRANSLATION_FIELDS
                if str(data.get(field) or "").strip()
            }
            if not values:
                continue
            trans = target.translations.filter(locale=locale).first() or target.translations.model(
                product=target, locale=locale
            )
            changed = False
            for field, value in values.items():
                current = getattr(trans, field, None)
                if current != value and self._may_overwrite(current, "translations", locale, field):
                    setattr(trans, field, value)
                    changed = True
            if changed:
                trans.save()
                updated = True
        return updated


class AIResultApplier:
    """Сервис-диспетчер для применения результатов AI."""
    
    _type_handlers = {
        "books": BookAIApplier,
        "jewelry": JewelryAIApplier,
        "medicines": MedicineAIApplier,
        "supplements": SupplementAIApplier,
    }
    
    _site_handlers = {
        # 'ummaland.uz': UmmalandAIApplier,
    }
    
    def apply_to_product(
        self,
        product: Product,
        ai_data: Dict[str, Any],
        *,
        rejected_fields: set[str] | None = None,
        content_snapshot: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Главная точка входа для применения данных к продукту.
        Автоматически определяет домен и нужный обработчик.

        content_snapshot — снимок из input_data лога: описание, SEO и переводы,
        изменённые после генерации, не перезаписываются.
        """
        rejected_fields = rejected_fields or set()
        target = product.domain_item
        product_type = getattr(target, '_domain_product_type', product.product_type)
        
        # Определение сайта для специфичной логики (если потребуется)
        site = None
        if product.external_url:
            from urllib.parse import urlparse
            site = urlparse(product.external_url).netloc
            
        handler_class = self._site_handlers.get(site)
        if not handler_class:
            handler_class = self._type_handlers.get(product_type, BaseAIApplier)
            
        handler = handler_class()
        handler.content_snapshot = content_snapshot
        logger.info(f"Applying AI results to {product} (type: {product_type}, site: {site}) via {handler.__class__.__name__}")

        # Применяем сгенерированное название к товару: обновляем доменную модель (только name), sync скопирует в Product
        with transaction.atomic():
            suggested_category = ai_data.get("suggested_category")
            try:
                category_confidence = float(ai_data.get("category_confidence") or 0)
            except (TypeError, ValueError):
                category_confidence = 0
            if (
                suggested_category is not None
                and getattr(suggested_category, "is_active", False)
                and category_confidence >= 0.75
            ):
                # Категория определяет наценку и цену: AI только заполняет пустую.
                # Несовпадение с заданной категорией уходит в модерацию
                # (SemanticValidator.validate_log → category_change_suggested).
                if product.category_id is None:
                    product.category = suggested_category
                    product.save(update_fields=["category"])
                if target is not None and hasattr(target, "category_id") and target.category_id is None:
                    target.category = suggested_category
                    target.save(update_fields=["category"])

            new_title = "" if "title" in rejected_fields else (ai_data.get("generated_title") or "").strip()
            if new_title and target is not None:
                update_fields = ["name"]
                if product_type in SOURCE_NAME_PRODUCT_TYPES and _remember_name_before_ai_title(
                    target, ai_data.get("source_name")
                ):
                    update_fields.append("external_data")
                # Slug не меняем: старые URL товара должны продолжать открываться.
                target.name = new_title[:500]
                if not getattr(target, "slug", None):
                    target.slug = _make_unique_slug_for_domain(
                        new_title,
                        target.__class__,
                        current_pk=getattr(target, "pk", None),
                    )
                    update_fields.append("slug")
                target.save(update_fields=update_fields)
            elif new_title:
                update_fields = ["name"]
                if product_type in SOURCE_NAME_PRODUCT_TYPES and _remember_name_before_ai_title(
                    product, ai_data.get("source_name")
                ):
                    update_fields.append("external_data")
                product.name = new_title[:500]
                product.save(update_fields=update_fields)
            cleaned_data = dict(ai_data)
            attrs = dict(cleaned_data.get("extracted_attributes") or {})
            dynamic = attrs.get("dynamic_attributes")
            if isinstance(dynamic, list):
                attrs["dynamic_attributes"] = [
                    row for row in dynamic
                    if not isinstance(row, dict)
                    or f"dynamic_attributes:{_canonical_attr_slug(row.get('slug') or 'unknown')}"
                    not in rejected_fields
                ]
            if "sizes" in rejected_fields:
                attrs.pop("sizes", None)
            cleaned_data["extracted_attributes"] = attrs
            translations = cleaned_data.get("translations")
            if isinstance(translations, dict):
                moderator_decisions = attrs.get("medicine_moderator_decisions")
                moderator_kept_fields = {
                    field_name
                    for field_name, decision in (
                        moderator_decisions.items()
                        if isinstance(moderator_decisions, dict)
                        else ()
                    )
                    if decision == "keep_current"
                }
                rejected_medicine_fields = {
                    field_name.split(":", 1)[1]
                    for field_name in rejected_fields
                    if field_name.startswith("medicine_translation:")
                    and ":" in field_name
                } | moderator_kept_fields
                for locale_payload in translations.values():
                    if not isinstance(locale_payload, dict):
                        continue
                    for field_name in rejected_medicine_fields:
                        locale_payload.pop(field_name, None)
            return handler.apply(target, cleaned_data)
