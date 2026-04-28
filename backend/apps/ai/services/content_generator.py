import logging
import json
import traceback
import re
from typing import Any, Dict, Optional, List
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
import uuid
from django.core.files.base import ContentFile
import requests
from django.utils.text import slugify
from apps.catalog.models import (
    Product,
    Category,
    ProductTranslation,
    Author,
    ProductAuthor,
    ProductImage,
    Brand,
    GlobalAttributeKey,
)
from apps.catalog.constants import ECOMMERCE_ATTRIBUTES
from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITemplate, AIModerationQueue
from apps.ai.services.llm_client import LLMClient
from apps.ai.services.media_processor import R2MediaProcessor
from apps.ai.services.variant_detector import VariantContentDetector
from apps.ai.services.vector_store import QdrantManager

logger = logging.getLogger(__name__)


class ContentGenerator:
    """
    Основной сервис генерации контента для товаров.
    Оркестрирует работу LLM, R2MediaProcessor и Qdrant (RAG).
    """

    RETRY_COUNT = 3
    COLOR_TRANSLATIONS = {
        "beyaz": {"ru": "Белый", "en": "White"},
        "lacivert": {"ru": "Темно-синий", "en": "Navy"},
        "siyah": {"ru": "Черный", "en": "Black"},
        "mavi": {"ru": "Синий", "en": "Blue"},
        "gri": {"ru": "Серый", "en": "Gray"},
        "kahverengi": {"ru": "Коричневый", "en": "Brown"},
        "bej": {"ru": "Бежевый", "en": "Beige"},
        "kirmizi": {"ru": "Красный", "en": "Red"},
        "kırmızı": {"ru": "Красный", "en": "Red"},
        "yeşil": {"ru": "Зеленый", "en": "Green"},
        "yesil": {"ru": "Зеленый", "en": "Green"},
    }
    GENERIC_PHRASES = (
        "идеально подходит для повседневной носки",
        "provide comfort throughout the day",
        "perfect for everyday wear",
        "стильный вид",
        "stylish look",
        "available in different colors and sizes",
        "доступны в разных цветах и размерах",
    )
    DYNAMIC_ATTR_SOURCE_HINTS = {
        "material": ("kumaş", "materyal", "material", "suni deri", "deri", "pamuk", "polyester", "cotton", "leather"),
        "closure-type": ("kapanma şekli", "bağcık", "fermuar", "closure", "lace", "zipper", "hook"),
        "toe-shape": ("burun şekli", "yuvarlak burun", "sivri burun", "square toe", "round toe", "pointed toe"),
        "sole-material": ("taban", "sole", "подошв"),
        "season": ("season", "sezon", "yaz", "kış", "ilkbahar", "sonbahar", "summer", "winter"),
        "gender": ("erkek", "kadın", "unisex", "male", "female", "муж", "жен"),
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.llm = LLMClient()
        self.media_processor = R2MediaProcessor()
        self.variant_detector = VariantContentDetector()
        from .result_applier import AIResultApplier
        self.result_applier = AIResultApplier()
        try:
            self.vector_store = QdrantManager()
        except Exception as e:
            logger.warning(f"Qdrant not available, RAG disabled: {e}")
            self.vector_store = None

    def _options_to_processing_type(self, options: Optional[Dict]) -> str:
        """По опциям ТЗ определить processing_type."""
        if not options:
            return "full"
        gen_desc = options.get("generate_description", True)
        categorize = options.get("categorize", True)
        analyze_images = options.get("analyze_images", True)
        if gen_desc and categorize and analyze_images:
            return "full"
        if gen_desc and categorize:
            return "full"
        if gen_desc:
            return "description_only"
        if categorize:
            return "categorization_only"
        if analyze_images:
            return "image_analysis"
        return "full"

    def process_product(
        self,
        product_id: int,
        processing_type: str = "full",
        user=None,
        auto_apply: bool = False,
        options: Optional[Dict] = None,
    ) -> AIProcessingLog:
        """
        Запуск процесса генерации контента для товара.

        Args:
            product_id: ID товара
            processing_type: тип обработки (full, description_only, etc.)
            user: пользователь, запустивший процесс
            auto_apply: автоматически применить изменения к товару (если успешно)
            options: опции в духе ТЗ — generate_description, categorize, analyze_images,
                     language, use_images (если заданы, processing_type может быть переопределён)
        """
        if options:
            processing_type = self._options_to_processing_type(options)
        
        force = (options or {}).get("force", False)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            logger.error(f"Product {product_id} not found")
            raise ValueError(f"Product {product_id} not found")

        # Проверяем, не был ли товар уже успешно обработан
        if not force:
            existing_log = AIProcessingLog.objects.filter(
                product=product,
                processing_type=processing_type,
                status__in=[
                    AIProcessingStatus.COMPLETED,
                    AIProcessingStatus.APPROVED,
                    AIProcessingStatus.MODERATION
                ]
            ).first()
            if existing_log:
                logger.info(f"Product {product_id} already processed (log {existing_log.id}), skipping.")
                return existing_log

        # Создаем лог
        log_entry = AIProcessingLog.objects.create(
            product=product,
            processed_by=user,
            processing_type=processing_type,
            status=AIProcessingStatus.PROCESSING,
            input_data=self._collect_input_data(product),
            llm_model=self.llm.model,
        )

        requested_use_images = (options or {}).get("use_images", True)
        use_images = requested_use_images and self._should_use_images_for_product(product)
        try:
            # 1. Подготовка изображений (если нужно)
            images_data = []
            if use_images and processing_type in ["full", "image_analysis"]:
                image_urls = self._get_product_image_urls(product)
                max_images = 5  # как в media_processor.get_product_images_batch
                requested_urls = [u for i, u in enumerate(image_urls) if i < max_images]
                images_data = self.media_processor.get_product_images_batch(image_urls)
                success_urls = [img.get("url") for img in images_data if img.get("url")]
                failed_urls = [u for u in requested_urls if u not in success_urls]
                log_entry.input_images_urls = [img.get("url") for img in images_data]
                if failed_urls:
                    input_data = dict(log_entry.input_data or {})
                    input_data["image_urls_failed"] = failed_urls
                    log_entry.input_data = input_data
                    log_entry.save(update_fields=["input_data", "input_images_urls"])
                else:
                    log_entry.save(update_fields=["input_images_urls"])

            # 2. Анализ изображений (Vision API)
            image_analysis_result = {}
            if use_images and processing_type in ["full", "image_analysis"] and images_data:
                default_prompt = self._get_default_image_prompt_for_product(product)
                vision_prompt = self._get_prompt_template(
                    "image_prompt",
                    default_prompt,
                    category=getattr(product, "category", None),
                )
                image_analysis_result = self.llm.analyze_images(
                    images=images_data, prompt=vision_prompt
                )
                log_entry.image_analysis = image_analysis_result.get("content", {})
                log_entry.save(update_fields=["image_analysis"])

            # 3. Генерация текстового контента
            if processing_type in ["full", "description_only", "categorization_only"]:
                # Формируем промпт (описание берётся из product или из перевода ru)
                input_for_prompt = self._collect_input_data(product)
                desc_len = len((input_for_prompt.get("description") or "").strip())
                logger.info(
                    "Product %s: description length for prompt=%s, image_analysis empty=%s",
                    product_id,
                    desc_len,
                    not log_entry.image_analysis,
                )
                system_prompt = self._get_system_prompt()
                user_prompt = self._construct_user_prompt(
                    product,
                    image_analysis=log_entry.image_analysis,
                    processing_type=processing_type,
                )

                # Вызов LLM (max_tokens=3000 — описание + SEO + en + attributes могут быть длинными)
                generation_result = self.llm.generate_content(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=3000,
                )

                # Обработка ответа
                content = generation_result["content"]
                if isinstance(content, str):
                    content = self._extract_json_from_response(content)
                log_entry.raw_llm_response = generation_result
                log_entry.tokens_used = generation_result["tokens"]
                log_entry.cost_usd = generation_result["cost_usd"]
                log_entry.processing_time_ms = generation_result["processing_time_ms"]

                # Парсинг результатов
                self._parse_and_save_results(log_entry, content)

            # 4. Завершение + применение
            log_entry.completed_at = timezone.now()

            if auto_apply:
                # Авто-применение: применяем немедленно, модерацию не проверяем —
                # администратор явно выбрал этот режим и принимает результат.
                try:
                    self._apply_changes_to_product(product, log_entry)
                    log_entry.status = AIProcessingStatus.APPROVED
                except Exception as e:
                    logger.exception(f"Error applying AI changes to product {product_id}: {e}")
                    log_entry.status = AIProcessingStatus.FAILED
                    log_entry.error_message = f"Error applying changes: {str(e)}"
            else:
                # Без авто-применения: проверяем нужна ли ручная модерация
                if self._check_needs_moderation(log_entry):
                    log_entry.status = AIProcessingStatus.MODERATION
                    log_entry.save()
                    self._create_moderation_task(log_entry)
                    return log_entry
                log_entry.status = AIProcessingStatus.COMPLETED

            log_entry.save()
            return log_entry

        except Exception as e:
            logger.error(f"Error processing product {product_id}: {e}")
            if 'log_entry' in locals():
                log_entry.status = AIProcessingStatus.FAILED
                log_entry.error_message = str(e)
                log_entry.stack_trace = traceback.format_exc()
                log_entry.save()
            raise

    # Расширения URL, которые не отправляем в Vision (видео; GIF оставляем — это изображение)
    _VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v")

    def _is_video_url(self, url: str) -> bool:
        if not url:
            return False
        path = url.split("?")[0].lower()
        return path.endswith(self._VIDEO_EXTENSIONS)

    def _get_product_image_urls(self, product: Product) -> List[str]:
        """
        Список URL изображений товара для Vision API.
        Видео-URL исключаются; приоритет: OG image, затем главное изображение (base или domain), затем галерея.
        """
        urls = []
        domain = getattr(product, "domain_item", None)
        preferred_og_image = self._get_preferred_og_image_url(product)
        if preferred_og_image and not self._is_video_url(preferred_og_image):
            urls.append(preferred_og_image)

        # Главное изображение из base Product или domain (BookProduct)
        main_image = product.main_image or (getattr(domain, "main_image", None) if domain and domain is not product else None)
        if main_image and not self._is_video_url(main_image):
            urls.append(main_image)

        # Галерея base Product (ProductImage)
        if hasattr(product, "images"):
            for img in product.images.all():
                u = img.image_url or (img.image_file.url if getattr(img, "image_file", None) else None)
                if u and not self._is_video_url(u):
                    urls.append(u)

        # Галерея domain-объекта (BookProductImage и т.д.)
        if domain and domain is not product:
            domain_images = getattr(domain, "images", None)
            if domain_images and hasattr(domain_images, "all"):
                for img in domain_images.all():
                    image_file = getattr(img, "image_file", None)
                    u = getattr(img, "image_url", None) or (getattr(image_file, "url", None) if image_file else None)
                    if u and not self._is_video_url(u):
                        urls.append(u)

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls

    def _get_preferred_og_image_url(self, product: Product) -> Optional[str]:
        """Предпочтительный OG image: сначала явное поле товара, затем доменной модели, потом None."""
        og_image_url = (getattr(product, "og_image_url", None) or "").strip()
        if og_image_url:
            return og_image_url

        domain = getattr(product, "domain_item", None)
        if domain and domain is not product:
            domain_og_image_url = (getattr(domain, "og_image_url", None) or "").strip()
            if domain_og_image_url:
                return domain_og_image_url

        return None

    def _collect_input_data(self, product: Product) -> Dict:
        """Сбор исходных данных о товаре."""
        # Описание: base Product → перевод RU → domain model (BookProduct и т.д.)
        description = product.description or ""
        if not description.strip() and hasattr(product, "get_translated_description"):
            description = (product.get_translated_description("ru") or "").strip()
        # Fallback на доменный объект (BookProduct.description может быть заполнен отдельно)
        if not description.strip():
            domain = getattr(product, "domain_item", None)
            if domain and domain is not product:
                description = getattr(domain, "description", "") or ""
        data = {
            "name": product.name,
            "description": description,
            "price": str(product.price) if product.price else None,
            "brand": product.brand.name if product.brand else None,
        }

        variant_context = self._collect_variant_context(product)
        if variant_context:
            data["variant_context"] = variant_context

        # Пытаемся достать сырое описание из external_data (от парсеров)
        if product.external_data:
            # Instagram и др.: raw_caption может быть в attributes или напрямую в external_data
            attributes = product.external_data.get("attributes") or {}
            raw_caption = attributes.get("raw_caption") or product.external_data.get("raw_caption")
            if raw_caption:
                data["raw_description"] = raw_caption
                # Используем сырое описание как основное, если оно богаче
                if len(str(raw_caption)) > len(str(data.get("description", ""))):
                    data["description"] = str(raw_caption)

        # Атрибуты по типу товара — в контекст для AI (known_attributes в промпте)
        book_item = getattr(product, "book_item", None)
        if book_item:
            if book_item.isbn:
                data["isbn"] = book_item.isbn
            if book_item.publisher:
                data["publisher"] = book_item.publisher
            if book_item.pages:
                data["pages"] = book_item.pages
        else:
            if getattr(product, "isbn", None):
                data["isbn"] = product.isbn
            if getattr(product, "publisher", None):
                data["publisher"] = product.publisher
            if getattr(product, "pages", None):
                data["pages"] = product.pages

        jewelry_item = getattr(product, "jewelry_item", None)
        if jewelry_item:
            if getattr(jewelry_item, "jewelry_type", None):
                data["jewelry_type"] = jewelry_item.jewelry_type
            if getattr(jewelry_item, "material", None):
                data["material"] = jewelry_item.material
            if getattr(jewelry_item, "metal_purity", None):
                data["metal_purity"] = jewelry_item.metal_purity
            if getattr(jewelry_item, "stone_type", None):
                data["stone_type"] = jewelry_item.stone_type
            if getattr(jewelry_item, "carat_weight", None):
                data["carat_weight"] = str(jewelry_item.carat_weight)
            if getattr(jewelry_item, "gender", None):
                data["gender"] = jewelry_item.gender

        # Медицинские атрибуты из доменной модели MedicineProduct
        medicine_item = getattr(product, "medicine_item", None)
        if medicine_item:
            for field in ("active_ingredient", "dosage_form", "administration_route",
                          "prescription_required", "volume", "origin_country"):
                val = getattr(medicine_item, field, None)
                if val is not None and val != "":
                    data[field] = val

        # Атрибуты из external_data (от парсера, например ilacfiyati)
        if product.external_data:
            raw_attrs = product.external_data.get("attributes") or {}
            medicine_keys = (
                "active_ingredient", "dosage_form", "administration_route",
                "shelf_life", "storage_conditions", "sgk_status",
                "atc_code", "nfc_code", "prescription_type", "barcode"
            )
            for k in medicine_keys:
                if k in raw_attrs and k not in data:
                    data[k] = raw_attrs[k]

        dynamic_attribute_catalog = self._collect_dynamic_attribute_catalog(product)
        if dynamic_attribute_catalog:
            data["available_dynamic_attributes"] = dynamic_attribute_catalog
        data["category_family_rules"] = self._get_category_family_rules(product)

        return data

    def _collect_dynamic_attribute_catalog(self, product: Product) -> List[Dict[str, str]]:
        """Список доступных динамических атрибутов для категории товара."""
        try:
            category = getattr(product, "category", None)
            qs = GlobalAttributeKey.objects.all().prefetch_related("translations").order_by("sort_order", "slug")
            if category is not None:
                category_ids = self._get_category_lineage_ids(category)
                filtered = qs.filter(categories__id__in=category_ids).distinct()
                if filtered.exists():
                    qs = filtered
            rows = []
            for key in qs[:30]:
                ru_name = ""
                en_name = ""
                for tr in key.translations.all():
                    if tr.locale == "ru":
                        ru_name = tr.name or ""
                    elif tr.locale == "en":
                        en_name = tr.name or ""
                rows.append(
                    {
                        "slug": key.slug,
                        "name_ru": ru_name or key.slug,
                        "name_en": en_name or key.slug,
                    }
                )
            return rows
        except Exception as e:
            logger.debug("Dynamic attribute catalog skipped: %s", e)
            return []

    def _get_category_lineage_ids(self, category) -> List[int]:
        ids = []
        current = category
        guard = 0
        while current is not None and getattr(current, "id", None) and guard < 10:
            ids.append(current.id)
            current = getattr(current, "parent", None)
            guard += 1
        return ids

    def _get_root_category_slug(self, product: Product) -> str:
        category = getattr(product, "category", None)
        current = category
        last_slug = ""
        guard = 0
        while current is not None and guard < 10:
            last_slug = getattr(current, "slug", "") or last_slug
            current = getattr(current, "parent", None)
            guard += 1
        return (last_slug or getattr(category, "slug", "") or getattr(product, "product_type", "") or "").replace("_", "-").lower()

    def _get_category_family_rules(self, product: Product) -> Dict[str, Any]:
        root_slug = self._get_root_category_slug(product)
        family_map = {
            "fashion": {
                "roots": {"clothing", "islamic-clothing", "headwear", "underwear"},
                "focus": ["material", "fit", "pattern", "season", "care instructions", "gender"],
                "forbidden": ["price", "currency", "sku", "sizes in prose"],
            },
            "shoes": {
                "roots": {"shoes"},
                "focus": ["material", "closure type", "toe shape", "sole material", "care instructions", "season"],
                "forbidden": ["price", "currency", "sku", "sizes in prose"],
            },
            "furniture": {
                "roots": {"furniture", "tableware"},
                "focus": ["material", "dimensions", "style", "room type", "assembly", "capacity/usage"],
                "forbidden": ["price", "currency", "sku"],
            },
            "books": {
                "roots": {"books"},
                "focus": ["author", "publisher", "isbn", "cover type", "language", "publication year"],
                "forbidden": ["price", "currency", "sku"],
            },
            "medicine": {
                "roots": {"medicines", "supplements", "medical-equipment"},
                "focus": ["active ingredient", "dosage", "form", "purpose", "storage", "origin", "usage instructions"],
                "forbidden": ["price", "currency", "sku"],
            },
            "perfumery": {
                "roots": {"perfumery", "incense"},
                "focus": ["volume", "ingredients", "effect", "fragrance family", "notes", "purpose"],
                "forbidden": ["price", "currency", "sku"],
            },
            "electronics": {
                "roots": {"electronics", "auto-parts", "sports"},
                "focus": ["compatibility", "power", "dimensions", "ports", "warranty", "technical specs"],
                "forbidden": ["price", "currency", "sku in title"],
            },
        }
        for family, config in family_map.items():
            if root_slug in config["roots"]:
                return {
                    "family": family,
                    "root_slug": root_slug,
                    "focus": config["focus"],
                    "forbidden": config["forbidden"],
                }
        return {
            "family": "generic",
            "root_slug": root_slug,
            "focus": ["confirmed raw facts", "material", "usage", "dimensions", "care"],
            "forbidden": ["price", "currency", "sku"],
        }

    def _collect_variant_context(self, product: Product) -> Optional[Dict]:
        """Краткий контекст по вариантам для генерации общего описания без отдельной AI-обработки каждого варианта."""
        external_data = product.external_data if isinstance(product.external_data, dict) else {}
        attrs = external_data.get("attributes") if isinstance(external_data.get("attributes"), dict) else {}

        variant_specs = None
        axis = None
        for key, current_axis in (
            ("fashion_variants", "color"),
            ("furniture_variants", "color"),
        ):
            raw = attrs.get(key)
            if isinstance(raw, list) and raw:
                variant_specs = raw
                axis = current_axis
                break

        if variant_specs is None:
            domain = getattr(product, "domain_item", None)
            variants_manager = getattr(domain, "variants", None) if domain is not None else None
            if variants_manager is not None:
                active_variants = list(
                    variants_manager.filter(is_active=True).order_by("sort_order", "id")[:12]
                )
                if active_variants:
                    variant_specs = []
                    for variant in active_variants:
                        row = {
                            "name": getattr(variant, "name", "") or "",
                            "color": getattr(variant, "color", "") or "",
                            "volume": getattr(variant, "volume", "") or "",
                            "sku": getattr(variant, "sku", "") or "",
                            "price": str(getattr(variant, "price", "") or "") or None,
                        }
                        sizes_manager = getattr(variant, "sizes", None)
                        if sizes_manager is not None:
                            row["sizes"] = [
                                {"size": size.size}
                                for size in sizes_manager.filter(is_available=True).order_by("sort_order", "id")[:8]
                                if getattr(size, "size", None)
                            ]
                        variant_specs.append(row)
                    axis = "volume" if any((row.get("volume") or "").strip() for row in variant_specs) else "color"

        if not variant_specs:
            return None

        summaries = []
        distinct_axis_values = set()
        has_variant_specific_content = False

        for spec in variant_specs[:8]:
            if not isinstance(spec, dict):
                continue

            summary = {}
            color = str(spec.get("color") or "").strip()
            volume = str(spec.get("volume") or "").strip()
            if color:
                summary["color"] = color
                distinct_axis_values.add(color.lower())
            if volume:
                summary["volume"] = volume
                distinct_axis_values.add(volume.lower())

            normalized_sizes = []
            sizes = spec.get("sizes") or []
            if isinstance(sizes, list):
                for row in sizes[:8]:
                    size_value = ""
                    if isinstance(row, dict):
                        size_value = str(row.get("size") or "").strip()
                    else:
                        size_value = str(row or "").strip()
                    if size_value:
                        normalized_sizes.append(size_value)
            if normalized_sizes:
                summary["sizes"] = normalized_sizes[:6]

            price = spec.get("price")
            if price not in (None, ""):
                summary["price"] = str(price)

            for key in ("description", "material", "dimensions", "cover_type", "format_type", "isbn", "variant_info"):
                value = spec.get(key)
                if value not in (None, "", [], {}):
                    has_variant_specific_content = True
                    break

            if summary:
                summaries.append(summary)

        variant_content = external_data.get("variant_content")
        detector_result = self.variant_detector.analyze(
            variant_specs=variant_specs,
            variant_content=variant_content if isinstance(variant_content, dict) else {},
        )
        if detector_result["needs_separate_variant_copy"]:
            has_variant_specific_content = True

        return {
            "has_variants": True,
            "variant_count": len(variant_specs),
            "variant_axis": axis or "variant",
            "distinct_variant_values": len(distinct_axis_values),
            "examples": summaries,
            "needs_separate_variant_copy": has_variant_specific_content,
            "variant_copy_candidates": detector_result["candidates"],
            "variant_copy_candidate_count": detector_result["candidate_count"],
            "content_strategy": (
                "parent_plus_variant_deltas"
                if not has_variant_specific_content
                else "parent_description_only_for_shared_facts"
            ),
        }

    def _translate_common_color(self, raw_color: str, locale: str) -> str:
        color = (raw_color or "").strip()
        if not color:
            return ""
        mapping = self.COLOR_TRANSLATIONS.get(color.lower())
        if mapping:
            return mapping.get(locale) or color
        return color

    def _strip_price_and_codes_from_title(self, title: str) -> str:
        if not title:
            return ""
        cleaned = str(title)
        cleaned = re.sub(r"\b[A-Z0-9]{2,}-[A-Z0-9]+\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b\d+[.,]\d+\s*(TL|TRY|USD|EUR|RUB|KZT|USDT)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b\d+[.,]\d+\b", "", cleaned)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        cleaned = re.sub(r"\s+-\s+$", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip(" -–—,")

    def _build_variant_suggested_titles(self, variant, preferred_parent_name: str) -> Dict[str, str]:
        base_name = self._strip_price_and_codes_from_title(preferred_parent_name or getattr(variant, "name", "") or "")
        if not base_name:
            base_name = self._normalize_product_name(getattr(variant, "name", "") or "Вариант товара")
        ru_color = self._translate_common_color(getattr(variant, "color", "") or "", "ru")
        en_color = self._translate_common_color(getattr(variant, "color", "") or "", "en")
        ru_title = f"{base_name} - {ru_color}" if ru_color else base_name
        en_base = self._strip_price_and_codes_from_title(getattr(variant, "name_en", "") or "") or base_name
        en_title = f"{en_base} - {en_color}" if en_color else en_base
        return {
            "ru": self._strip_price_and_codes_from_title(ru_title),
            "en": self._strip_price_and_codes_from_title(en_title),
        }

    def _normalize_variant_generated_titles(self, content: Dict, input_data: Dict) -> Dict:
        if not isinstance(content, dict):
            return content
        suggested_titles = input_data.get("suggested_titles") if isinstance(input_data, dict) else {}
        variant_color = input_data.get("color") if isinstance(input_data, dict) else ""

        for locale in ("ru", "en"):
            bucket = content.get(locale)
            if not isinstance(bucket, dict):
                continue
            raw_title = str(bucket.get("generated_title") or "").strip()
            cleaned_title = self._strip_price_and_codes_from_title(raw_title)
            if not cleaned_title:
                cleaned_title = str((suggested_titles or {}).get(locale) or "").strip()

            translated_color = self._translate_common_color(variant_color, locale)
            if translated_color and cleaned_title:
                for source_color, translations in self.COLOR_TRANSLATIONS.items():
                    localized_color = translations.get(locale)
                    if localized_color and source_color.lower() in cleaned_title.lower():
                        cleaned_title = re.sub(
                            re.escape(source_color),
                            localized_color,
                            cleaned_title,
                            flags=re.IGNORECASE,
                        )
                if translated_color.lower() not in cleaned_title.lower() and "(" in raw_title:
                    cleaned_title = f"{cleaned_title} - {translated_color}"

            bucket["generated_title"] = cleaned_title.strip(" -–—,")

        return content

    def process_variant_content(self, variant, force: bool = False) -> Dict:
        """Генерирует отдельный AI-черновик для варианта и сохраняет только в external_data варианта."""
        external_data = dict(variant.external_data) if isinstance(variant.external_data, dict) else {}
        existing = external_data.get("ai_variant_content")
        if isinstance(existing, dict) and existing.get("status") == "completed" and not force:
            return existing

        input_data = self._collect_variant_input_data(variant)
        if not input_data.get("variant_description") and not input_data.get("variant_snapshot") and not input_data.get("size_options"):
            payload = {
                "status": "skipped",
                "updated_at": timezone.now().isoformat(),
                "reason": "insufficient_variant_specific_data",
                "draft": {},
            }
            external_data["ai_variant_content"] = payload
            variant.external_data = external_data
            variant.save(update_fields=["external_data"])
            return payload

        generation_result = self.llm.generate_content(
            system_prompt=self._get_variant_system_prompt(),
            user_prompt=self._construct_variant_user_prompt(input_data),
            max_tokens=1800,
        )
        content = generation_result["content"]
        if isinstance(content, str):
            content = self._extract_json_from_response(content)
        if not isinstance(content, dict):
            content = {}
        content = self._sanitize_ai_content(content, input_data, variant_mode=True)
        content = self._normalize_variant_generated_titles(content, input_data)

        payload = {
            "status": "completed",
            "processed_at": timezone.now().isoformat(),
            "llm_model": self.llm.model,
            "tokens_used": generation_result["tokens"],
            "cost_usd": generation_result["cost_usd"],
            "processing_time_ms": generation_result["processing_time_ms"],
            "input_data": input_data,
            "draft": content,
        }
        external_data["ai_variant_content"] = payload
        variant.external_data = external_data
        variant.save(update_fields=["external_data"])
        return payload

    def _collect_variant_input_data(self, variant) -> Dict:
        """Собирает безопасный контекст для AI-черновика варианта."""
        parent = getattr(variant, "product", None)
        base_product = getattr(parent, "base_product", None) if parent is not None else None
        base_external_data = base_product.external_data if isinstance(getattr(base_product, "external_data", None), dict) else {}
        base_variant_content = base_external_data.get("variant_content") if isinstance(base_external_data.get("variant_content"), dict) else {}
        snapshot = base_variant_content.get(str(getattr(variant, "external_id", "") or "")) or {}

        preferred_parent_name = (
            getattr(base_product, "name", None)
            or getattr(parent, "name", None)
            or ""
        )
        data = {
            "parent_name": preferred_parent_name or "",
            "parent_description": getattr(parent, "description", "") or "",
            "variant_name": getattr(variant, "name", "") or "",
            "variant_name_en": getattr(variant, "name_en", "") or "",
            "color": getattr(variant, "color", "") or "",
            "volume": getattr(variant, "volume", "") or "",
            "cover_type": getattr(variant, "cover_type", "") or "",
            "format_type": getattr(variant, "format_type", "") or "",
            "isbn": getattr(variant, "isbn", "") or "",
            "sku": getattr(variant, "sku", "") or "",
            "price": str(getattr(variant, "price", "") or "") or None,
            "currency": getattr(variant, "currency", "") or "",
            "variant_description": str(snapshot.get("description") or "").strip(),
            "variant_snapshot": snapshot.get("attributes") if isinstance(snapshot.get("attributes"), dict) else {},
            "variant_external_data": variant.external_data if isinstance(variant.external_data, dict) else {},
        }
        data["suggested_titles"] = self._build_variant_suggested_titles(variant, preferred_parent_name)

        size_options = []
        sizes_manager = getattr(variant, "sizes", None)
        if sizes_manager is not None:
            for size in sizes_manager.filter(is_available=True).order_by("sort_order", "id")[:12]:
                size_value = str(getattr(size, "size", "") or "").strip()
                if size_value:
                    size_options.append(size_value)
        data["size_options"] = size_options
        return data

    def _get_variant_system_prompt(self) -> str:
        return """
        Ты - контент-менеджер интернет-магазина. Ты создаёшь черновик ТОЛЬКО для конкретного варианта товара.

        Правила:
        1. Не изменяй базовую карточку товара и не предлагай переносить variant-specific факты в родительскую модель.
        2. Пиши только про отличия варианта и подтверждённые общие факты из исходного описания родителя: материал, тип изделия, форму носка, тип застёжки, фактуру, уход.
        3. Никогда не включай в title или description цену, валюту, SKU, артикул, product code, TL, TRY, внешний ID, slug.
        4. Если у варианта есть размеры, НЕ перечисляй их в описании: размеры уже показаны в интерфейсе. size_options можно вернуть только в variant_attributes.
        5. Если цвет и так очевиден из UI, не делай описание банальным пересказом вроде «вариант белого цвета». Цвет допустим в названии и в attributes, но не как единственное содержание описания.
        6. Если данных мало, не выдумывай. Используй родительский товар только как фон для понимания контекста.
        7. Описание дай на двух языках: ru и en. Это должен быть короткий, но содержательный черновик варианта, а не полная общая карточка.
        8. Переводи турецкие слова и цвета в нормальный русский и английский. В title не оставляй Beyaz, Lacivert, Siyah и т.п.
        5. Ответ строго JSON.
        """

    def _construct_variant_user_prompt(self, input_data: Dict) -> str:
        payload = {
            "parent_name": input_data.get("parent_name"),
            "parent_description": input_data.get("parent_description"),
            "variant_name": input_data.get("variant_name"),
            "variant_name_en": input_data.get("variant_name_en"),
            "color": input_data.get("color"),
            "volume": input_data.get("volume"),
            "cover_type": input_data.get("cover_type"),
            "format_type": input_data.get("format_type"),
            "isbn": input_data.get("isbn"),
            "sku": input_data.get("sku"),
            "price": input_data.get("price"),
            "currency": input_data.get("currency"),
            "size_options": input_data.get("size_options"),
            "suggested_titles": input_data.get("suggested_titles"),
            "variant_description": input_data.get("variant_description"),
            "variant_snapshot": input_data.get("variant_snapshot"),
        }
        return f"""
        Данные о варианте товара:
        {json.dumps(payload, ensure_ascii=False)}

        Сгенерируй JSON:
        {{
          "ru": {{
            "generated_title": "Краткое название варианта на русском",
            "generated_description": "Краткое описание варианта на русском, только про его отличия"
          }},
          "en": {{
            "generated_title": "Short variant title in English",
            "generated_description": "Short variant description in English, only about its distinguishing details"
          }},
          "variant_attributes": {{
            "color": null,
            "volume": null,
            "cover_type": null,
            "format_type": null,
            "material": null,
            "dimensions": null,
            "size_options": []
          }},
          "shared_with_parent": true,
          "should_update_parent": false
        }}

        Важно:
        - Не переписывай общее описание родителя.
        - Не выдумывай характеристики, которых нет в данных.
        - Используй suggested_titles как ориентир для title, если они выглядят нормальными.
        - Не упоминай в title и description цену, валюту, SKU, код товара, размеры и технический мусор.
        - Если отличия варианта минимальны, описание всё равно должно быть полезным: опирайся на подтверждённые общие свойства модели из parent_description, но не копируй весь родительский текст.
        """

    def _should_use_images_for_product(self, product: Product) -> bool:
        """
        Чтобы экономить Vision-токены, анализ фото включаем только для книг.

        Для остальных категорий AI должен работать по описанию/атрибутам,
        которые пришли от парсера и уже сохранены в product.external_data.
        """
        return self._is_books_product(product)

    def _is_books_product(self, product: Product) -> bool:
        """Проверяет, что товар — книга (по product_type или категории)."""
        pt = (getattr(product, "product_type", None) or "").strip().lower()
        if pt == "books":
            return True
        cat = getattr(product, "category", None)
        if cat:
            name = (getattr(cat, "name", "") or "").lower()
            slug = (getattr(cat, "slug", "") or "").lower()
            if "книг" in name or "book" in slug or "books" in slug:
                return True
        return False

    def _get_product_type(self, product: Product) -> str:
        """Возвращает product_type товара (books, jewelry, clothing и т.д.)."""
        return (getattr(product, "product_type", None) or "").strip().lower()

    def _get_default_image_prompt_for_product(self, product: Product) -> str:
        """Промпт для анализа фото в зависимости от типа товара. Для кастомных промптов используйте AITemplate (image_prompt) по категории."""
        pt = self._get_product_type(product)
        if pt == "books":
            return self._get_books_image_prompt()
        if pt == "jewelry":
            return self._get_jewelry_image_prompt()
        if pt in ("clothing", "shoes", "underwear", "headwear"):
            return self._get_clothing_image_prompt()
        return (
            "Опиши этот товар по фото: тип, цвет, материал, ключевые характеристики. "
            "Ответ в формате JSON с полями product_type, color, material, краткое описание."
        )

    def _get_books_image_prompt(self) -> str:
        """Промпт для анализа обложки книги: название и автор на обложке."""
        return (
            "Это книга. На обложке изображения указаны название и автор — извлеки их из фото. "
            "Также укажи издательство, тип переплёта (cover_type: твердый/мягкий/суперобложка), если видно. "
            "Ответ в формате JSON: name (название с обложки), author (автор), publisher, cover_type."
        )

    def _get_jewelry_image_prompt(self) -> str:
        """Промпт для анализа фото украшения."""
        return (
            "Это ювелирное изделие или бижутерия. По фото определи: тип (ring/bracelet/necklace/earrings/pendant), "
            "материал (золото, серебро, бижутерия и т.д.), цвет металла/камней, наличие камней (stone_type), "
            "для кого (gender: женский/мужской/унисекс). Ответ в формате JSON: jewelry_type, material, metal_purity (если видно), "
            "stone_type, color, gender, краткое описание на русском."
        )

    def _get_clothing_image_prompt(self) -> str:
        """Промпт для анализа фото одежды/обуви."""
        return (
            "Это одежда или обувь. По фото определи: тип (верх/низ/обувь/аксессуар), цвет, материал, "
            "сезонность, пол (gender: мужской/женский/унисекс). Если виден бренд — укажи. "
            "Ответ в формате JSON: product_type, color, material, gender, brand (если видно), краткое описание."
        )

    def _get_prompt_template(
        self, template_type: str, default: str, category=None
    ) -> str:
        """
        Шаблон промпта из БД. Если задана category — сначала ищем шаблон для этой категории,
        иначе общий (category=None). Затем дефолт.
        """
        qs = AITemplate.objects.filter(
            template_type=template_type, is_active=True
        )
        if category is not None:
            template = qs.filter(category=category).first() or qs.filter(
                category__isnull=True
            ).first()
        else:
            template = qs.first()
        return (template.content if template else default) or default

    def _get_system_prompt(self) -> str:
        return """
        Ты - контент-менеджер и SEO-специалист для интернет-магазина Mudaroba.

        Правила:
        1. Название товара (ru.generated_title) — ОБЯЗАТЕЛЬНО заполняй. Это главное отображаемое название: короткое, без подзаголовка и лишнего текста (например: «ИСЛАМСКИЕ ФИНАНСЫ», а не «ИСЛАМСКИЕ ФИНАНСЫ концепция и инструменты»). Для книг при наличии name в image_analysis — используй его; иначе очисти product_name от подзаголовка.
        2. SEO (meta title, meta description, keywords) — ТОЛЬКО на английском, латиница. Кириллица в SEO недопустима.
        3. Описание товара — всегда на двух языках (ru и en). ru.generated_description и en.generated_description — один смысл (переводы друг друга). Исходный текст может быть на русском, английском или турецком: очисти, улучши, затем создай оба перевода. Объём каждого: от 20 до 100 слов. Если текстового описания нет или оно скудное, но есть image_analysis — пиши описание и SEO на основе изображений.
        4. Технические поля (ISBN, издательство, страницы, автор и т.д.) заполняй только если данные есть в описании или known_attributes. Не придумывай.
        5. Определяй категорию по контексту товара.
        6. Предпочитай конкретные факты из сырого текста маркетинговым штампам. Если в источнике есть материал, тип застёжки, форма носка, узор, состав, уход, назначение — используй их.
        7. Не включай цену, валюту, SKU, product code, TL/TRY, внешний ID и служебные коды в название, описание и SEO.
        8. Не пиши пустые общие фразы вроде «идеально подходит для повседневной носки», если это не следует из исходного текста.

        Ответ — строго JSON по указанной структуре.
        """

    def _construct_user_prompt(
        self, product: Product, image_analysis: Dict, processing_type: str
    ) -> str:
        input_data = self._collect_input_data(product)

        # RAG: контекст категорий и шаблонов из векторной БД
        categories_context = ""
        templates_context = ""
        if self.vector_store:
            try:
                query_text = f"{input_data.get('name', '')} {input_data.get('description', '')} {input_data.get('raw_description', '')}"
                similar_cats = self.vector_store.search_similar_categories_by_text(
                    query_text, top_k=5
                )
                if similar_cats:
                    lines = []
                    for c in similar_cats[:3]:
                        name = c.get("category_name") or c.get("payload", {}).get("category_name", "")
                        parent = c.get("parent") or c.get("payload", {}).get("parent", "")
                        examples = c.get("examples") or c.get("payload", {}).get("examples", "") or ""
                        examples_str = str(examples)
                        if len(examples_str) > 200:
                            examples_str = examples_str.replace('\n', ' ')
                            examples_str = "".join([c for i, c in enumerate(examples_str) if i < 200])
                        sim = c.get("score", 0)
                        lines.append(f"- {name} (родитель: {parent}, схожесть: {sim:.2f}). Примеры: {examples_str}")
                    categories_context = "Доступные категории из каталога (используй при выборе suggested_category_name):\n" + "\n".join(lines) + "\n\n"
            except Exception as e:
                logger.debug(f"RAG categories skipped: {e}")
            try:
                product_type = (image_analysis or {}).get("clothing_type") or (image_analysis or {}).get("product_type") or input_data.get("name", "") or "товар"
                templates = self.vector_store.get_relevant_templates_by_text(
                    str(product_type), top_k=2
                )
                if templates:
                    templates_context = "Примеры хороших описаний для похожих товаров:\n\n" + "\n\n---\n\n".join(templates) + "\n\n"
            except Exception as e:
                logger.debug(f"RAG templates skipped: {e}")

        known_attrs = {
            "isbn": input_data.get("isbn"),
            "publisher": input_data.get("publisher"),
            "pages": input_data.get("pages"),
        }
        if input_data.get("jewelry_type") is not None or input_data.get("material") is not None:
            known_attrs["jewelry_type"] = input_data.get("jewelry_type")
            known_attrs["material"] = input_data.get("material")
            known_attrs["metal_purity"] = input_data.get("metal_purity")
            known_attrs["stone_type"] = input_data.get("stone_type")
            known_attrs["carat_weight"] = input_data.get("carat_weight")
            known_attrs["gender"] = input_data.get("gender")
        
        # Медицинские атрибуты: передаём AI всё что знаем о препарате
        medicine_attrs_keys = (
            "active_ingredient", "dosage_form", "administration_route",
            "prescription_required", "prescription_type", "volume",
            "origin_country", "shelf_life", "storage_conditions",
            "sgk_status", "atc_code", "barcode", "nfc_code",
            "sgk_equivalent_code", "sgk_active_ingredient_code", "sgk_public_no"
        )
        medicine_attrs = {k: input_data[k] for k in medicine_attrs_keys if k in input_data and input_data[k]}
        if medicine_attrs:
            known_attrs.update(medicine_attrs)
        data = {
            "product_name": input_data["name"],
            "current_description": input_data["description"],
            "brand": input_data["brand"] or "Unknown",
            "known_attributes": known_attrs,
            "image_analysis": image_analysis,
        }
        # raw_description — оригинал от парсера (Instagram и др.); AI использует для извлечения цены, автора и т.д.
        if input_data.get("raw_description") and input_data["raw_description"] != input_data.get("description"):
            data["raw_description"] = input_data["raw_description"]
        if input_data.get("variant_context"):
            data["variant_context"] = input_data["variant_context"]
        if input_data.get("available_dynamic_attributes"):
            data["available_dynamic_attributes"] = input_data["available_dynamic_attributes"]
        if input_data.get("category_family_rules"):
            data["category_family_rules"] = input_data["category_family_rules"]

        # Инструкция для категории (AI шаблон с template_type=category_instruction и category=товара)
        category_instruction = ""
        product_category = getattr(product, "category", None)
        if product_category:
            raw = self._get_prompt_template(
                "category_instruction", "", category=product_category
            )
            if raw and raw.strip():
                category_instruction = (
                    f"Инструкции для категории «{product_category.name}»:\n{raw.strip()}\n\n"
                )

        prompt = f"""
        {categories_context}{templates_context}{category_instruction}
        Данные о товаре:
        {json.dumps(data, ensure_ascii=False)}

        Важно:
        - Если в current_description есть текст (например на русском), но НЕТ image_analysis (картинки не загрузились) — ОБЯЗАТЕЛЬНО переведи описание на английский в en.generated_description и заполни ВСЕ SEO-поля (en.seo_title, en.seo_description, en.keywords) на английском. Не оставляй en пустым, когда есть текст описания.
        - Если у товара НЕТ описания или оно очень короткое (мало текста), но есть image_analysis (анализ фото товара) — ОБЯЗАТЕЛЬНО сгенерируй описание на двух языках (ru и en) и заполни все SEO-поля в "en" на основе анализа изображений. Не оставляй описание и SEO пустыми, когда есть картинки.
        - Если есть и текст, и image_analysis — объединяй: описание на двух языках и SEO на английском.
        - Описание (ru.generated_description, en.generated_description) и SEO (en.seo_title, en.seo_description, en.keywords) — ВСЕГДА заполняй, когда есть хотя бы описание ИЛИ image_analysis.

        Правила:
        - Описание на русском (ru.generated_description) и на английском (en.generated_description) — ОДИН И ТОТ ЖЕ смысл; длина каждого: от 20 до 100 слов.
        - ВАЖНО: en.generated_description ДОЛЖНО БЫТЬ НА АНГЛИЙСКОМ ЯЗЫКЕ. Если исходный текст на русском — ПЕРЕВЕДИ его. Не оставляй кириллицу в en.generated_description.
        - Если есть raw_description (сырое описание от парсера, может быть на RU/EN/TR):
          • СНАЧАЛА очисти от цен, ссылок, хештегов, контактов и рекламы; улучши формулировки.
          • Если исходный язык — русский: результат → ru.generated_description; en.generated_description = перевод на АНГЛИЙСКИЙ.
          • Если исходный язык — английский: результат → en.generated_description; ru.generated_description = перевод на РУССКИЙ.
          • Если исходный язык — турецкий (или другой): переведи на русский → ru.generated_description; переведи на английский → en.generated_description.
          • Если в raw_description есть структура вроде «Ürün Tipi / Kumaş / Burun Şekli / Ayakkabı Kapanma Şekli / Bakım Bilgileri», ОБЯЗАТЕЛЬНО используй эти факты в описании. Не заменяй их общими словами.
          • Если факт в source указан прямо, передавай его прямо и точно. Пример: «Kumaş: Suni Deri» => «из искусственной кожи», а не «из материала, напоминающего искусственную кожу».
        - Если есть variant_context:
          • Пиши базовое описание только про общие свойства товара, не зависящие от конкретного варианта.
          • Не смешивай в родительское описание различия по цветам, размерам, объёмам и другим вариантам, если они не общие для всех.
          • Не пиши в родительском описании, что товар «доступен в разных цветах и размерах», если это уже видно через UI вариантов.
          • Если variant_context.needs_separate_variant_copy=true, особенно избегай добавлять variant-specific факты в общее описание.
        - В итоге ВСЕГДА заполняй оба: ru.generated_description (RU) и en.generated_description (EN).
        - Технические поля заполняй только если данные есть в current_description, raw_description, known_attributes ИЛИ image_analysis. Не придумывай.
        - Если есть available_dynamic_attributes:
          • Используй их как список допустимых динамических атрибутов для этой категории.
          • Если в source-тексте есть подтверждённый факт и ему подходит один из этих slug, добавь его в attributes.dynamic_attributes.
          • Не создавай вымышленные атрибуты и не используй slug, которых нет в available_dynamic_attributes.
        - Если есть category_family_rules:
          • family показывает семейство товара; focus — какие типы фактов особенно важны; forbidden — что нельзя тащить в описание или title.
          • Для этой карточки приоритетно раскрывай факты именно из focus, а forbidden не включай в prose/SEO.
        - Для книг: author, pages, isbn, publisher, cover_type, language, publication_year. cover_type (переплёт) можно определить по фото.
        - Для украшений (jewelry): обязательно извлекай в attributes: jewelry_type (ring/bracelet/necklace/earrings/pendant), material (серебро/silver, золото/gold), metal_purity из текста про пробу («925 пробы», «585», «проба 750» → metal_purity: «925» / «585» / «750»), stone_type, carat_weight, gender — по описанию или по фото.
        - Для медикаментов: ОЯЗАТЕЛЬНО переведи все технические поля из known_attributes на русский и английский. Если в raw_description или current_description есть инструкции по применению, побочные эффекты, противопоказания, показания (Ne İçin Kullanılır, Yan Etkileri, vs.) — ОБЯЗАТЕЛЬНО извлеки их, переведи на нужный язык (RU/EN) и заполни соответствующие поля (indications, usage_instructions, side_effects, contraindications, storage_conditions, administration_route, shelf_life, sgk_status, prescription_type, special_notes, origin_country) внутри объектов "ru" и "en". Например: "Subkütan" (TR) -> "Подкожно" (RU) / "Subcutaneous" (EN); "İthal" (TR) -> "Импортный" (RU) / "Imported" (EN).
        - Название (generated_title): только основной заголовок, без подзаголовка. Например: «ИСЛАМСКИЕ ФИНАНСЫ», а не «ИСЛАМСКИЕ ФИНАНСЫ концепция, инструменты и инфраструктура». Для книг: если в image_analysis есть name (название с обложки) — используй его; автор — из image_analysis.author.
        - Для одежды и обуви: title должен быть на языке ответа и не должен содержать турецкие цвета, цену, TL/TRY, SKU или код товара.
        - SEO в общих полях карточки можно писать на русском, если это логичнее для витрины. Английскую SEO-версию при этом тоже заполни в "en".
        - В "ru" — название и описание на русском; в "en" — название, описание (перевод ru) и SEO на английском.
        - stock_quantity: если не указано, можно 3.

        Верни JSON (опускай только технические поля без данных — не опускай описание и SEO, если есть текст или image_analysis). Описание ru и en — один смысл, перевод; каждое от 20 до 100 слов:
        {{
            "ru": {{
                "generated_title": "Название на русском",
                "generated_description": "Описание на русском, 20–100 слов (HTML allowed)",
                "indications": "Показания к применению (RU)",
                "usage_instructions": "Инструкция по применению (RU)",
                "side_effects": "Побочные эффекты (RU)",
                "contraindications": "Противопоказания (RU)",
                "storage_conditions": "Условия хранения (RU)",
                "administration_route": "Путь введения (RU)",
                "shelf_life": "Срок годности (RU)",
                "sgk_status": "Статус SGK (RU)",
                "prescription_type": "Тип рецепта (RU)",
                "special_notes": "Особые отметки (SUT / Medula) (RU)"
            }},
            "en": {{
                "generated_title": "Product name in English",
                "generated_description": "Same description in English, 20–100 words (HTML allowed)",
                "seo_title": "SEO meta title in English only",
                "seo_description": "SEO meta description in English only",
                "keywords": ["keyword1", "keyword2"],
                "indications": "Indications (EN)",
                "usage_instructions": "Usage instructions (EN)",
                "side_effects": "Side effects (EN)",
                "contraindications": "Contraindications (EN)",
                "storage_conditions": "Storage conditions (EN)",
                "administration_route": "Administration route (EN)",
                "shelf_life": "Shelf life (EN)",
                "sgk_status": "SGK status (EN)",
                "prescription_type": "Prescription type (EN)",
                "special_notes": "Special notes (SUT / Medula) (EN)"
            }},
            "suggested_category_name": "Category name (RU)",
            "category_confidence": 0.95,
            "attributes": {{
                "author": ["Only for books, if in source"],
                "pages": null,
                "isbn": null,
                "publisher": null,
                "cover_type": "Only for books: твердый/мягкий/суперобложка",
                "language": "Only for books: rus/eng/ara/tur",
                "publication_year": "Only for books: year 4 digits",
                "jewelry_type": "Only for jewelry: ring/bracelet/necklace/earrings/pendant",
                "material": "Only for jewelry: e.g. gold, silver",
                "metal_purity": "Only for jewelry: e.g. 925, 585, 750 from text like '925 пробы'",
                "stone_type": "Only for jewelry if has stones",
                "carat_weight": "Only for jewelry if applicable",
                "gender": "For jewelry/clothing: женский/мужской/унисекс",
                "stock_quantity": 3,
                "price": null,
                "currency": null,
                "dynamic_attributes": [
                    {{
                        "slug": "material",
                        "value": "искусственная кожа",
                        "value_ru": "искусственная кожа",
                        "value_en": "artificial leather"
                    }}
                ]
            }}
        }}
        """

        return prompt

    def _extract_json_from_response(self, raw: str):
        """Достать JSON из ответа (строка или обёртка в ```json ... ```)."""
        if not isinstance(raw, str) or not raw.strip():
            return {}
        text = raw.strip()
        if text.startswith("```"):
            # Убрать открывающий ```json или ```
            first = text.split("\n", 1)[0]
            if "json" in first.lower():
                text = str(text)[len(first) :].lstrip("\n")
            else:
                text = str(text)[3:].lstrip("\n")
            if text.endswith("```"):
                text = str(text)[:-3].rstrip()
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError:
            logger.warning("LLM response is not valid JSON, raw snippet: %s", text[:500])
            return {}

    def _normalize_product_name(self, name: str, product_type: Optional[str] = None) -> str:
        """
        Нормализует название: убирает подзаголовок и лишние слова в конце.
        Напр. «ИСЛАМСКИЕ ФИНАНСЫ концепция, инструменты и инфраструктура» → «ИСЛАМСКИЕ ФИНАНСЫ»
        """
        if not name or not isinstance(name, str):
            return name
        s = name.strip()
        if not s:
            return s

        # 1. Берём только первую строку (подзаголовок часто после переноса)
        first_line = s.split("\n")[0].strip()
        if first_line:
            s = first_line

        # 2. Обрезаем по запятой (формат «Название, подзаголовок»)
        if "," in s:
            s = s.split(",")[0].strip()

        # 3. Убираем служебные хвосты цен/валют/артикулов
        s = self._strip_price_and_codes_from_title(s)

        s_str = str(s)
        return s_str[:255] if len(s_str) > 255 else s_str

    def _normalize_currency(self, raw: str) -> str:
        """Нормализация валюты из ответа AI в код (RUB, USD, TRY и т.д.)."""
        if not raw or not str(raw).strip():
            return "RUB"
        s = str(raw).strip().upper()
        mapping = {
            "РУБ": "RUB", "RUB": "RUB", "₽": "RUB", "RUR": "RUB",
            "USD": "USD", "USDT": "USD", "$": "USD",
            "EUR": "EUR", "€": "EUR",
            "TRY": "TRY", "TRL": "TRY", "TL": "TRY", "ТР": "TRY",
            "KZT": "KZT", "ТГ": "KZT",
        }
        for key, code in mapping.items():
            if key in s or s == key:
                return code
        if s in ("RUB", "USD", "EUR", "TRY", "KZT"):
            return s
        return "RUB"

    def _sanitize_description_text(self, text: str, *, remove_sizes: bool = False) -> str:
        if not text:
            return ""
        normalized = str(text).strip()
        sentence_candidates = re.split(r"(?<=[.!?])\s+|\n+", normalized)
        kept = []
        for sentence in sentence_candidates:
            candidate = sentence.strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if any(phrase in lowered for phrase in self.GENERIC_PHRASES):
                continue
            if re.search(r"\b\d+[.,]\d+\s*(tl|try|usd|eur|rub|kzt|usdt)\b", lowered):
                continue
            if "sku" in lowered or "ürün kodu" in lowered or "product code" in lowered:
                continue
            if remove_sizes and ("размер" in lowered or "size options" in lowered or "sizes available" in lowered):
                continue
            kept.append(candidate)
        cleaned = " ".join(kept).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        replacements = {
            "из материала, напоминающего искусственную кожу": "из искусственной кожи",
            "made from a material resembling artificial leather": "made of artificial leather",
            "made from material resembling artificial leather": "made of artificial leather",
        }
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        return cleaned or normalized

    def _apply_confidence_gate_to_dynamic_attributes(self, dynamic_attrs: List[Dict[str, Any]], input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(dynamic_attrs, list):
            return []

        source_parts = [
            str(input_data.get("description") or ""),
            str(input_data.get("raw_description") or ""),
            json.dumps(input_data.get("known_attributes") or {}, ensure_ascii=False),
            json.dumps(input_data.get("variant_snapshot") or {}, ensure_ascii=False),
        ]
        source_blob = " ".join(source_parts).lower()

        allowed_slugs = {
            str(row.get("slug") or "").strip().lower()
            for row in (input_data.get("available_dynamic_attributes") or [])
            if isinstance(row, dict) and row.get("slug")
        }
        approved = []
        for row in dynamic_attrs:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or "").strip().lower()
            if not slug or (allowed_slugs and slug not in allowed_slugs):
                continue
            values_to_check = [
                str(row.get("value") or "").strip(),
                str(row.get("value_ru") or "").strip(),
                str(row.get("value_en") or "").strip(),
            ]
            values_to_check = [v for v in values_to_check if v]
            if not values_to_check:
                continue
            hinted = any(v.lower() in source_blob for v in values_to_check if len(v) >= 3)
            if not hinted:
                hinted = any(hint in source_blob for hint in self.DYNAMIC_ATTR_SOURCE_HINTS.get(slug, ()))
            if not hinted:
                continue
            approved.append(row)
        return approved

    def _merge_dynamic_attributes_into_top_level(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        dynamic_attrs = attrs.get("dynamic_attributes") or []
        if not isinstance(dynamic_attrs, list):
            return attrs

        slug_to_top_level = {
            "material": "material",
            "gender": "gender",
            "closure-type": "closure_type",
            "toe-shape": "toe_shape",
            "sole-material": "sole_material",
        }
        for row in dynamic_attrs:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or "").strip().lower()
            target_key = slug_to_top_level.get(slug)
            if not target_key or attrs.get(target_key):
                continue
            value = str(row.get("value_ru") or row.get("value") or row.get("value_en") or "").strip()
            if value:
                attrs[target_key] = value
        return attrs

    def _sanitize_ai_content(self, content: Dict[str, Any], input_data: Dict[str, Any], *, variant_mode: bool = False) -> Dict[str, Any]:
        if not isinstance(content, dict):
            return content

        for locale in ("ru", "en"):
            bucket = content.get(locale)
            if not isinstance(bucket, dict):
                continue
            if bucket.get("generated_description"):
                bucket["generated_description"] = self._sanitize_description_text(
                    bucket["generated_description"],
                    remove_sizes=variant_mode,
                )
            if bucket.get("generated_title"):
                bucket["generated_title"] = self._strip_price_and_codes_from_title(bucket["generated_title"])

        attrs = content.get("attributes")
        if isinstance(attrs, dict) and isinstance(attrs.get("dynamic_attributes"), list):
            attrs["dynamic_attributes"] = self._apply_confidence_gate_to_dynamic_attributes(
                attrs.get("dynamic_attributes") or [],
                input_data,
            )
            content["attributes"] = self._merge_dynamic_attributes_into_top_level(attrs)
        return content

    def _parse_and_save_results(self, log: AIProcessingLog, content):
        """Сохранение результатов из JSON ответа LLM в модель лога."""
        if not isinstance(content, dict):
            content = self._extract_json_from_response(str(content)) if content else {}
        if not content:
            logger.warning("Empty or invalid LLM content for log %s", log.id)
            log.save()
            return
        content = self._sanitize_ai_content(content, log.input_data or {}, variant_mode=False)

        # ru — название и описание на русском
        data_source = content.get("ru", content)
        if "generated_title" in data_source and data_source["generated_title"]:
            raw_title = (data_source["generated_title"] or "").strip()
            product_type = getattr(log.product, "product_type", None) if log.product_id else None
            log.generated_title = self._normalize_product_name(raw_title, product_type)
        if "generated_description" in data_source and data_source["generated_description"]:
            log.generated_description = data_source["generated_description"]

        # SEO: сохраняем в общие поля SEO в первую очередь RU, затем EN fallback.
        en_data = content.get("en") or {}
        ru_data = content.get("ru") or {}

        seo_title = ru_data.get("seo_title") or en_data.get("seo_title")
        seo_description = ru_data.get("seo_description") or en_data.get("seo_description")
        seo_keywords = ru_data.get("keywords") or en_data.get("keywords") or []

        if seo_title:
            log.generated_seo_title = str(seo_title)[:70]
        elif log.generated_title:
            log.generated_seo_title = str(log.generated_title)[:70]
        if seo_description:
            log.generated_seo_description = str(seo_description)[:160]
        elif log.generated_description:
            plain_desc = re.sub(r"<[^>]+>", " ", str(log.generated_description))
            plain_desc = re.sub(r"\s+", " ", plain_desc).strip()
            log.generated_seo_description = plain_desc[:160]
        if seo_keywords:
            log.generated_keywords = [str(k).strip() for k in seo_keywords if str(k).strip()]

        if "attributes" in content and content["attributes"]:
            log.extracted_attributes = content["attributes"]

        # Сохраняем en для применения meta_title, meta_description, meta_keywords к товару
        if en_data:
            if not log.extracted_attributes:
                log.extracted_attributes = {}
            
            seo_en_data = {
                "title": en_data.get("seo_title"),
                "description": en_data.get("seo_description"),
                "keywords": [str(k).strip() for k in en_data.get("keywords", []) if str(k).strip()],
                "generated_title": en_data.get("generated_title"),
                "generated_description": en_data.get("generated_description"),
            }
            # Авто-заполнение OG-тегов из SEO, если они есть
            if seo_en_data["title"]:
                seo_en_data["og_title"] = seo_en_data["title"]
            if seo_en_data["description"]:
                seo_en_data["og_description"] = seo_en_data["description"]
            
            log.extracted_attributes["seo_en"] = seo_en_data

        # Дополнительные поля переводов (indications, usage_instructions и т.д.)
        trans_fields = [
            'indications', 'usage_instructions', 'side_effects', 
            'contraindications', 'storage_conditions', 'administration_route',
            'shelf_life', 'sgk_status', 'prescription_type', 'special_notes',
            'origin_country'
        ]
        trans_data = {'ru': {}, 'en': {}}
        for field in trans_fields:
            if field in data_source and data_source[field]:
                trans_data['ru'][field] = data_source[field]
            if field in en_data and en_data[field]:
                trans_data['en'][field] = en_data[field]
        if trans_data['ru'] or trans_data['en']:
            if not log.extracted_attributes:
                log.extracted_attributes = {}
            log.extracted_attributes['translations_data'] = trans_data

        # Попытка найти категорию
        if "suggested_category_name" in content:
            cat_name = content["suggested_category_name"]
            category = Category.objects.filter(name__icontains=cat_name).first()
            if category:
                log.suggested_category = category
            log.category_confidence = content.get("category_confidence", 0.5)

        log.save()

        if not (log.generated_description or log.generated_seo_title):
            logger.warning(
                "Log %s: LLM did not fill description/SEO (content keys: %s). Check raw_llm_response or increase max_tokens.",
                log.id,
                list(content.keys()) if isinstance(content, dict) else "non-dict",
            )

    def _check_needs_moderation(self, log: AIProcessingLog) -> bool:
        """Определить, требуется ли ручная модерация результата."""
        # Низкая уверенность в категории
        if log.category_confidence is not None and log.category_confidence < 0.75:
            return True

        # Подозрительно низкая цена (возможна ошибка парсера)
        input_data = log.input_data or {}
        if input_data.get("price"):
            try:
                price = float(input_data["price"])
                if price < 100:
                    return True
            except (TypeError, ValueError):
                pass

        # Подозрительные слова в описании
        suspicious_words = ["реплика", "копия", "fake", "подделка", "replica", "copy"]
        desc = (log.generated_description or "").lower()
        if any(word in desc for word in suspicious_words):
            return True

        # Слишком короткое описание
        if len(log.generated_description or "") < 100:
            return True

        return False

    def _create_moderation_task(self, log: AIProcessingLog) -> None:
        """Создать запись в очереди модерации."""
        if getattr(log, "moderation_queue", None):
            return
        reason = (
            "low_confidence"
            if (log.category_confidence or 1) < 0.75
            else "manual_review"
        )
        priority = 2 if reason == "low_confidence" else 3
        AIModerationQueue.objects.get_or_create(
            log_entry=log,
            defaults={"priority": priority, "reason": reason},
        )

    def _apply_changes_to_product(self, product: Product, log: AIProcessingLog):
        """Применение сгенерированных данных к товару через AIResultApplier."""
        original_name = product.name or ""

        # Для украшений: дополняем extracted_attributes из image_analysis при применении (LLM мог не вернуть metal_purity)
        attrs = dict(log.extracted_attributes or {})
        if getattr(product, "product_type", None) == "jewelry" and log.image_analysis:
            img = log.image_analysis if isinstance(log.image_analysis, dict) else (log.image_analysis[0] if log.image_analysis else None)
            if isinstance(img, dict):
                for key in ("jewelry_type", "material", "metal_purity", "stone_type", "gender"):
                    if key not in attrs or not attrs.get(key):
                        if img.get(key):
                            attrs[key] = img[key]

        # Английское описание и название хранятся в seo_en внутри extracted_attributes
        seo_en = dict(attrs.get('seo_en') or {})
        en_description = seo_en.get('generated_description') or log.generated_description or ""
        en_name = seo_en.get('generated_title') or log.generated_title or original_name

        ai_data = {
            'generated_title': (log.generated_title or '').strip() or None,
            'generated_description': log.generated_description,
            'generated_seo_title': log.generated_seo_title,
            'generated_seo_description': log.generated_seo_description,
            'generated_keywords': log.generated_keywords,
            # OG-поля: og_title / og_description из seo_en; og_image_url из изображения товара
            'og_title': seo_en.get('og_title') or log.generated_seo_title,
            'og_description': seo_en.get('og_description') or log.generated_seo_description,
            'og_image_url': self._get_preferred_og_image_url(product)
                            or product.main_image
                            or getattr(getattr(product, 'domain_item', None), 'main_image', None),
            'extracted_attributes': attrs,
            'suggested_category': log.suggested_category,
            'category_confidence': log.category_confidence,
            'translations': {
                'ru': {
                    'name': (log.generated_title or original_name).strip(),
                    'description': log.generated_description,
                    **attrs.get('translations_data', {}).get('ru', {})
                },
                'en': {
                    'name': en_name,
                    'description': en_description,
                    **attrs.get('translations_data', {}).get('en', {})
                }
            }
        }

        # Делегируем применение результатов специализированному сервису
        self.result_applier.apply_to_product(product, ai_data)
