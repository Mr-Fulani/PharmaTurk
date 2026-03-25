import logging
import json
import traceback
import re
from typing import Dict, Optional, List
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
)
from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITemplate, AIModerationQueue
from apps.ai.services.llm_client import LLMClient
from apps.ai.services.media_processor import R2MediaProcessor
from apps.ai.services.vector_store import QdrantManager

logger = logging.getLogger(__name__)


class ContentGenerator:
    """
    Основной сервис генерации контента для товаров.
    Оркестрирует работу LLM, R2MediaProcessor и Qdrant (RAG).
    """

    RETRY_COUNT = 3

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.llm = LLMClient()
        self.media_processor = R2MediaProcessor()
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
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            logger.error(f"Product {product_id} not found")
            raise ValueError(f"Product {product_id} not found")

        # Создаем лог
        log_entry = AIProcessingLog.objects.create(
            product=product,
            processed_by=user,
            processing_type=processing_type,
            status=AIProcessingStatus.PROCESSING,
            input_data=self._collect_input_data(product),
            llm_model=self.llm.model,
        )

        use_images = (options or {}).get("use_images", True)
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
        Видео-URL исключаются; приоритет: главное изображение (base или domain), затем галерея.
        """
        urls = []
        # Главное изображение из base Product или domain (BookProduct)
        domain = getattr(product, "domain_item", None)
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

        return data

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
        Ты - контент-менеджер и SEO-специалист для интернет-магазина PharmaTurk.

        Правила:
        1. Название товара (ru.generated_title) — ОБЯЗАТЕЛЬНО заполняй. Это главное отображаемое название: короткое, без подзаголовка и лишнего текста (например: «ИСЛАМСКИЕ ФИНАНСЫ», а не «ИСЛАМСКИЕ ФИНАНСЫ концепция и инструменты»). Для книг при наличии name в image_analysis — используй его; иначе очисти product_name от подзаголовка.
        2. SEO (meta title, meta description, keywords) — ТОЛЬКО на английском, латиница. Кириллица в SEO недопустима.
        3. Описание товара — всегда на двух языках (ru и en). ru.generated_description и en.generated_description — один смысл (переводы друг друга). Исходный текст может быть на русском, английском или турецком: очисти, улучши, затем создай оба перевода. Объём каждого: от 20 до 100 слов. Если текстового описания нет или оно скудное, но есть image_analysis — пиши описание и SEO на основе изображений.
        4. Технические поля (ISBN, издательство, страницы, автор и т.д.) заполняй только если данные есть в описании или known_attributes. Не придумывай.
        5. Определяй категорию по контексту товара.

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
        - В итоге ВСЕГДА заполняй оба: ru.generated_description (RU) и en.generated_description (EN).
        - Технические поля заполняй только если данные есть в current_description, raw_description, known_attributes ИЛИ image_analysis. Не придумывай.
        - Для книг: author, pages, isbn, publisher, cover_type, language, publication_year. cover_type (переплёт) можно определить по фото.
        - Для украшений (jewelry): обязательно извлекай в attributes: jewelry_type (ring/bracelet/necklace/earrings/pendant), material (серебро/silver, золото/gold), metal_purity из текста про пробу («925 пробы», «585», «проба 750» → metal_purity: «925» / «585» / «750»), stone_type, carat_weight, gender — по описанию или по фото.
        - Для медикаментов: если в raw_description или current_description есть инструкции по применению, побочные эффекты, противопоказания, показания (Ne İçin Kullanılır, Yan Etkileri, vs.) — ОБЯЗАТЕЛЬНО извлеки их, переведи на нужный язык и заполни соответствующие поля (indications, usage_instructions, side_effects, contraindications, storage_conditions, administration_route, shelf_life, sgk_status, prescription_type, special_notes) внутри объектов "ru" и "en".
        - Название (generated_title): только основной заголовок, без подзаголовка. Например: «ИСЛАМСКИЕ ФИНАНСЫ», а не «ИСЛАМСКИЕ ФИНАНСЫ концепция, инструменты и инфраструктура». Для книг: если в image_analysis есть name (название с обложки) — используй его; автор — из image_analysis.author.
        - SEO — только на английском (латиница). Кириллица в SEO недопустима.
        - В "ru" — название и описание на русском; в "en" — название, описание (перевод ru) и все SEO на английском.
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
                "currency": null
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

    def _parse_and_save_results(self, log: AIProcessingLog, content):
        """Сохранение результатов из JSON ответа LLM в модель лога."""
        if not isinstance(content, dict):
            content = self._extract_json_from_response(str(content)) if content else {}
        if not content:
            logger.warning("Empty or invalid LLM content for log %s", log.id)
            log.save()
            return

        # ru — название и описание на русском
        data_source = content.get("ru", content)
        if "generated_title" in data_source and data_source["generated_title"]:
            raw_title = (data_source["generated_title"] or "").strip()
            product_type = getattr(log.product, "product_type", None) if log.product_id else None
            log.generated_title = self._normalize_product_name(raw_title, product_type)
        if "generated_description" in data_source and data_source["generated_description"]:
            log.generated_description = data_source["generated_description"]

        # SEO только из en (английский, латиница). Кириллицу не записываем даже в логи.
        en_data = content.get("en") or {}
        
        def is_clean_en(text):
            if not text: return True
            return not bool(re.search("[а-яА-Я]", str(text)))

        if en_data.get("seo_title") and is_clean_en(en_data["seo_title"]):
            log.generated_seo_title = (en_data["seo_title"] or "")[:70]
        if en_data.get("seo_description") and is_clean_en(en_data["seo_description"]):
            log.generated_seo_description = (en_data["seo_description"] or "")[:160]
        if en_data.get("keywords"):
            # Фильтруем ключевые слова от кириллицы
            clean_keywords = [k for k in en_data["keywords"] if is_clean_en(k)]
            log.generated_keywords = clean_keywords

        if "attributes" in content and content["attributes"]:
            log.extracted_attributes = content["attributes"]

        # Сохраняем en для применения meta_title, meta_description, meta_keywords к товару
        if en_data:
            if not log.extracted_attributes:
                log.extracted_attributes = {}
            
            # В структуре внутри attributes фильтруем тоже
            seo_en_data = {
                "title": en_data.get("seo_title") if is_clean_en(en_data.get("seo_title")) else None,
                "description": en_data.get("seo_description") if is_clean_en(en_data.get("seo_description")) else None,
                "keywords": [k for k in en_data.get("keywords", []) if is_clean_en(k)],
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
        trans_fields = ['indications', 'usage_instructions', 'side_effects', 'contraindications', 'storage_conditions']
        trans_data = {'ru': {}, 'en': {}}
        for field in trans_fields:
            if field in data_source and data_source[field]:
                trans_data['ru'][field] = data_source[field]
            if field in en_data and en_data[field]:
                trans_data['en'][field] = en_data[field]
        if trans_data['ru'] or trans_data['en']:
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
        en_name = log.generated_seo_title or seo_en.get('generated_title') or log.generated_title or original_name

        ai_data = {
            'generated_title': (log.generated_title or '').strip() or None,
            'generated_description': log.generated_description,
            'generated_seo_title': log.generated_seo_title,
            'generated_seo_description': log.generated_seo_description,
            'generated_keywords': log.generated_keywords,
            # OG-поля: og_title / og_description из seo_en; og_image_url из изображения товара
            'og_title': seo_en.get('og_title') or log.generated_seo_title,
            'og_description': seo_en.get('og_description') or log.generated_seo_description,
            'og_image_url': product.main_image or getattr(getattr(product, 'domain_item', None), 'main_image', None),
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

