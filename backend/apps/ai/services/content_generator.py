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
from apps.ai.models import AIProcessingLog, AIProcessingStatus, AITemplate
from apps.ai.services.llm_client import LLMClient
from apps.ai.services.media_processor import R2MediaProcessor

logger = logging.getLogger(__name__)


class ContentGenerator:
    """
    Основной сервис генерации контента для товаров.
    Оркестрирует работу LLM и R2MediaProcessor.
    """

    def __init__(self):
        self.llm = LLMClient()
        self.media_processor = R2MediaProcessor()

    def process_product(
        self, product_id: int, processing_type: str = "full", user=None, auto_apply: bool = False
    ) -> AIProcessingLog:
        """
        Запуск процесса генерации контента для товара.

        Args:
            product_id: ID товара
            processing_type: тип обработки (full, description_only, etc.)
            user: пользователь, запустивший процесс
            auto_apply: автоматически применить изменения к товару (если успешно)
        """
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

        try:
            # 1. Подготовка изображений (если нужно)
            images_data = []
            if processing_type in ["full", "image_analysis"]:
                image_urls = self._get_product_image_urls(product)
                images_data = self.media_processor.get_product_images_batch(image_urls)
                log_entry.input_images_urls = [img.get("url") for img in images_data]
                log_entry.save(update_fields=["input_images_urls"])

            # 2. Анализ изображений (Vision API)
            image_analysis_result = {}
            if processing_type in ["full", "image_analysis"] and images_data:
                vision_prompt = self._get_prompt_template(
                    "image_prompt",
                    "Опиши этот товар, укажи цвет, материал и тип. "
                    "Если это книга - укажи автора и издательство. "
                    "Если это одежда/обувь - укажи бренд. "
                    "Ответ предоставь в формате JSON.",
                )
                image_analysis_result = self.llm.analyze_images(
                    images=images_data, prompt=vision_prompt
                )
                log_entry.image_analysis = image_analysis_result.get("content", {})
                log_entry.save(update_fields=["image_analysis"])

            # 3. Генерация текстового контента
            if processing_type in ["full", "description_only", "categorization_only"]:
                # Формируем промпт
                system_prompt = self._get_system_prompt()
                user_prompt = self._construct_user_prompt(
                    product,
                    image_analysis=log_entry.image_analysis,
                    processing_type=processing_type,
                )

                # Вызов LLM
                generation_result = self.llm.generate_content(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )

                # Обработка ответа
                content = generation_result["content"]
                log_entry.raw_llm_response = generation_result
                log_entry.tokens_used = generation_result["tokens"]
                log_entry.cost_usd = generation_result["cost_usd"]
                log_entry.processing_time_ms = generation_result["processing_time_ms"]

                # Парсинг результатов
                self._parse_and_save_results(log_entry, content)

            # 4. Завершение
            log_entry.status = AIProcessingStatus.COMPLETED
            log_entry.completed_at = timezone.now()
            log_entry.save()

            # 5. Применение изменений (опционально)
            if auto_apply and log_entry.status == AIProcessingStatus.COMPLETED:
                self._apply_changes_to_product(product, log_entry)

            return log_entry

        except Exception as e:
            logger.error(f"Error processing product {product_id}: {e}")
            log_entry.status = AIProcessingStatus.FAILED
            log_entry.error_message = str(e)
            log_entry.stack_trace = traceback.format_exc()
            log_entry.save()
            raise

    def _get_product_image_urls(self, product: Product) -> List[str]:
        """Получить список URL изображений товара."""
        urls = []
        if product.main_image:
            urls.append(product.main_image)

        if hasattr(product, "images"):
            for img in product.images.all():
                if img.image_url:
                    urls.append(img.image_url)
                elif img.image_file:
                    urls.append(img.image_file.url)

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
        data = {
            "name": product.name,
            "description": product.description,
            "price": str(product.price) if product.price else None,
            "brand": product.brand.name if product.brand else None,
        }

        # Пытаемся достать сырое описание из external_data (от парсеров)
        if product.external_data:
            attributes = product.external_data.get("attributes", {})
            if attributes.get("raw_caption"):
                data["raw_description"] = attributes["raw_caption"]
                # Используем сырое описание как основное, если оно богаче
                if len(data["raw_description"]) > len(data["description"]):
                    data["description"] = data["raw_description"]

            # Добавляем существующие атрибуты в контекст, чтобы AI их знал
            if product.isbn:
                data["isbn"] = product.isbn
            if product.publisher:
                data["publisher"] = product.publisher
            if product.pages:
                data["pages"] = product.pages

        return data

    def _get_prompt_template(self, template_type: str, default: str) -> str:
        """Получение шаблона промпта из БД или дефолтного."""
        template = AITemplate.objects.filter(template_type=template_type, is_active=True).first()
        return template.content if template else default

    def _get_system_prompt(self) -> str:
        return """
        Ты - профессиональный контент-менеджер и SEO-специалист для интернет-магазина PharmaTurk.
        Твоя задача:
        1. Создавать продающие описания товаров на ДВУХ языках: Русском (RU) и Английском (EN).
        2. Генерировать SEO-теги (title, description, keywords).
        3. Определять категорию товара.
        4. Извлекать характеристики (цвет, материал, размер и т.д.).
        
        Ответ должен быть строго в формате JSON с разделением по языкам.
        """

    def _construct_user_prompt(
        self, product: Product, image_analysis: Dict, processing_type: str
    ) -> str:
        # Используем данные из input_data если они есть (собранные ранее)
        # Но здесь мы получаем product, так что лучше пересобрать или передать data
        # Для упрощения пересобираем
        input_data = self._collect_input_data(product)

        data = {
            "product_name": input_data["name"],
            "current_description": input_data["description"],  # Может быть raw_description
            "brand": input_data["brand"] or "Unknown",
            "known_attributes": {
                "isbn": input_data.get("isbn"),
                "publisher": input_data.get("publisher"),
                "pages": input_data.get("pages"),
            },
            "image_analysis": image_analysis,
        }

        prompt = f"""
        Проанализируй следующие данные о товаре:
        {json.dumps(data, ensure_ascii=False)}
        
        Твоя задача:
        1. Извлечь максимум информации из описания и изображений.
        2. Перевести описание на английский язык (поле "en").
        3. Если количество товара не указано явно, считай stock_quantity = 3.
        4. Если в known_attributes уже есть данные (ISBN, publisher, pages), используй их и не выдумывай новые.
        5. СТРОГО ЗАПРЕЩЕНО придумывать технические данные (ISBN, количество страниц, издательство), если их нет в тексте или known_attributes. 
           Если данных нет - возвращай null или не включай поле в ответ.
        
        Необходимо сгенерировать JSON следующей структуры:
        {{
            "ru": {{
                "generated_title": "Название товара на русском",
                "generated_description": "Описание на русском (HTML allowed)",
                "seo_title": "SEO Title RU",
                "seo_description": "SEO Description RU",
                "keywords": ["key", "words", "ru"]
            }},
            "en": {{
                "generated_title": "Product Name in English",
                "generated_description": "Description in English (HTML allowed)",
                "seo_title": "SEO Title EN",
                "seo_description": "SEO Description EN",
                "keywords": ["key", "words", "en"]
            }},
            "suggested_category_name": "Category Name (RU)",
            "category_confidence": 0.95,
            "attributes": {{
                "author": ["Author Name 1", "Author Name 2"],
                "pages": 123,
                "price": 10.99,
                "old_price": 12.99,
                "currency": "USD",
                "stock_quantity": 3,
                "isbn": "978-...",
                "publisher": "Publisher Name",
                "publication_date": "YYYY-MM-DD",
                "language": "Русский",
                "brand": "Brand Name",
                "cover_type": "Hardcover",
                "format_type": "Paperback",
                "images": ["http://example.com/image1.jpg", "http://example.com/image2.jpg"]
            }}
        }}
        """

        return prompt

    def _parse_and_save_results(self, log: AIProcessingLog, content: Dict):
        """Сохранение результатов из JSON ответа LLM в модель лога."""
        # Поддержка старого формата (плоский JSON) и нового (вложенный ru/en)

        # Если формат новый (есть ключ "ru"), берем данные оттуда для основных полей
        data_source = content.get("ru", content)

        if "generated_title" in data_source:
            log.generated_title = data_source["generated_title"][:255]
        if "generated_description" in data_source:
            log.generated_description = data_source["generated_description"]
        if "seo_title" in data_source:
            log.generated_seo_title = data_source["seo_title"][:70]
        if "seo_description" in data_source:
            log.generated_seo_description = data_source["seo_description"][:160]
        if "keywords" in data_source:
            log.generated_keywords = data_source["keywords"]

        if "attributes" in content:
            log.extracted_attributes = content["attributes"]

        # Сохраняем английские данные в attributes для последующего использования
        if "en" in content:
            en_data = content["en"]
            if not log.extracted_attributes:
                log.extracted_attributes = {}

            log.extracted_attributes["seo_en"] = {
                "title": en_data.get("seo_title"),
                "description": en_data.get("seo_description"),
                "keywords": en_data.get("keywords"),
                "generated_title": en_data.get("generated_title"),
                "generated_description": en_data.get("generated_description"),
            }

        # Попытка найти категорию
        if "suggested_category_name" in content:
            cat_name = content["suggested_category_name"]
            # Простой поиск по названию (можно улучшить через векторный поиск)
            category = Category.objects.filter(name__icontains=cat_name).first()
            if category:
                log.suggested_category = category

            log.category_confidence = content.get("category_confidence", 0.5)

        log.save()

    def _apply_changes_to_product(self, product: Product, log: AIProcessingLog):
        """Применение сгенерированных данных к товару."""
        with transaction.atomic():
            # 1. Применяем основные данные (RU)
            if log.generated_title and not product.name:
                product.name = log.generated_title
            if log.generated_description and not product.description:
                product.description = log.generated_description

            seo_title = (log.generated_seo_title or "").strip()
            if seo_title and not re.search("[а-яА-Я]", seo_title):
                product.seo_title = seo_title[:70]
            seo_description = (log.generated_seo_description or "").strip()
            if seo_description and not re.search("[а-яА-Я]", seo_description):
                product.seo_description = seo_description[:160]
            if log.generated_keywords:
                keywords_text = (
                    " ".join([str(item) for item in log.generated_keywords])
                    if isinstance(log.generated_keywords, list)
                    else str(log.generated_keywords)
                )
                if keywords_text and not re.search("[а-яА-Я]", keywords_text):
                    product.keywords = log.generated_keywords

            # SEO fields (EN)
            if log.extracted_attributes and "seo_en" in log.extracted_attributes:
                seo_en = log.extracted_attributes["seo_en"]
                if seo_en.get("title"):
                    product.meta_title = seo_en["title"][:255]
                    product.og_title = seo_en["title"][:255]
                if seo_en.get("description"):
                    product.meta_description = seo_en["description"][:500]
                    product.og_description = seo_en["description"][:500]
                if seo_en.get("keywords"):
                    if isinstance(seo_en["keywords"], list):
                        product.meta_keywords = ", ".join(seo_en["keywords"])[:500]
                    else:
                        product.meta_keywords = str(seo_en["keywords"])[:500]

            # Category logic
            if log.suggested_category and log.category_confidence > 0.8:
                product.category = log.suggested_category

            # Применение извлеченных атрибутов
            if log.extracted_attributes:
                attrs = log.extracted_attributes

                # Цена, Старая цена и Валюта
                price_updated = False
                if "price" in attrs and attrs["price"]:
                    try:
                        product.price = Decimal(str(attrs["price"]))
                        price_updated = True
                    except (ValueError, TypeError, Exception):
                        pass

                if "old_price" in attrs and attrs["old_price"]:
                    try:
                        product.old_price = Decimal(str(attrs["old_price"]))
                    except (ValueError, TypeError, Exception):
                        pass

                if "currency" in attrs and attrs["currency"]:
                    product.currency = str(attrs["currency"])
                    price_updated = True

                # Количество на складе (stock_quantity)
                # Если AI нашел значение - используем его.
                # Если нет, и у товара оно не установлено - ставим 3 по умолчанию.
                if "stock_quantity" in attrs and attrs["stock_quantity"] is not None:
                    try:
                        product.stock_quantity = int(attrs["stock_quantity"])
                    except (ValueError, TypeError):
                        pass
                elif product.stock_quantity is None:
                    product.stock_quantity = 3

                product.save()

                # Обновление мультивалютных цен
                if price_updated:
                    product.update_currency_prices()

                # Авторы
                if "author" in attrs and not product.book_authors.exists():
                    authors_list = attrs["author"]
                    if isinstance(authors_list, str):
                        authors_list = [authors_list]

                    if isinstance(authors_list, list):
                        # Очистка текущих авторов не производится, только добавление новых
                        for idx, auth_name in enumerate(authors_list):
                            # Пропускаем "пустые" имена
                            if not auth_name or auth_name.lower().strip() in [
                                "не указано",
                                "нет",
                                "unknown",
                                "not specified",
                                "неизвестен",
                                "нет автора",
                            ]:
                                continue

                            parts = auth_name.strip().split()
                            if len(parts) >= 2:
                                first_name = parts[0]
                                last_name = " ".join(parts[1:])
                            else:
                                first_name = auth_name
                                last_name = ""

                            author, _ = Author.objects.get_or_create(
                                first_name=first_name, last_name=last_name
                            )
                            ProductAuthor.objects.get_or_create(
                                product=product, author=author, defaults={"sort_order": idx}
                            )

                # Изображения из текста
                if "images" in attrs and isinstance(attrs["images"], list):
                    for img_url in attrs["images"]:
                        if not img_url:
                            continue
                        try:
                            # Проверяем, нет ли уже такого изображения
                            if ProductImage.objects.filter(
                                product=product, image_url=img_url
                            ).exists():
                                continue

                            resp = requests.get(img_url, timeout=10)
                            if resp.status_code == 200:
                                filename = (
                                    img_url.split("/")[-1].split("?")[0]
                                    or f"image_{timezone.now().timestamp()}.jpg"
                                )
                                img_obj = ProductImage(
                                    product=product,
                                    image_url=img_url,  # Сохраняем исходный URL
                                    is_main=not product.images.exists(),  # Если нет картинок, первая будет главной
                                )
                                img_obj.image_file.save(
                                    filename, ContentFile(resp.content), save=True
                                )
                        except Exception as e:
                            logger.error(f"Failed to download image {img_url}: {e}")

            # 2. Сохраняем переводы (EN), если они есть в raw_llm_response
            if log.raw_llm_response and "content" in log.raw_llm_response:
                content = log.raw_llm_response["content"]
                if "en" in content:
                    en_data = content["en"]
                    en_desc = en_data.get("generated_description")
                    if en_desc:
                        ProductTranslation.objects.update_or_create(
                            product=product, locale="en", defaults={"description": en_desc}
                        )

                    # Сохраняем английские SEO-поля
                    if "seo_title" in en_data and en_data["seo_title"]:
                        product.meta_title = en_data["seo_title"][:255]
                        product.og_title = en_data["seo_title"][:255]

                    if "seo_description" in en_data and en_data["seo_description"]:
                        product.meta_description = en_data["seo_description"][:500]
                        product.og_description = en_data["seo_description"][:500]

                    if "keywords" in en_data and en_data["keywords"]:
                        if isinstance(en_data["keywords"], list):
                            product.meta_keywords = ", ".join(en_data["keywords"])
                        else:
                            product.meta_keywords = str(en_data["keywords"])

                    product.save()

            # Если нет EN данных в ответе, но есть RU, переводим RU SEO для заполнения EN полей
            elif log.generated_seo_title and not product.meta_title:
                # Это fallback, если LLM не вернул структуру "en"
                pass
