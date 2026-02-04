import logging
import json
import traceback
from typing import Dict, Optional, List
from django.db import transaction
from django.utils import timezone
from apps.catalog.models import Product, Category, ProductTranslation
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
        self, 
        product_id: int, 
        processing_type: str = 'full',
        user=None,
        auto_apply: bool = False
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
            llm_model=self.llm.model
        )

        try:
            # 1. Подготовка изображений (если нужно)
            images_data = []
            if processing_type in ['full', 'image_analysis']:
                image_urls = self._get_product_image_urls(product)
                images_data = self.media_processor.get_product_images_batch(image_urls)
                log_entry.input_images_urls = [img.get('url') for img in images_data]
                log_entry.save(update_fields=['input_images_urls'])

            # 2. Анализ изображений (Vision API)
            image_analysis_result = {}
            if processing_type in ['full', 'image_analysis'] and images_data:
                vision_prompt = self._get_prompt_template('image_prompt', "Опиши этот товар, укажи цвет, материал и тип. Ответ предоставь в формате JSON.")
                image_analysis_result = self.llm.analyze_images(
                    images=images_data,
                    prompt=vision_prompt
                )
                log_entry.image_analysis = image_analysis_result.get('content', {})
                log_entry.save(update_fields=['image_analysis'])

            # 3. Генерация текстового контента
            if processing_type in ['full', 'description_only', 'categorization_only']:
                # Формируем промпт
                system_prompt = self._get_system_prompt()
                user_prompt = self._construct_user_prompt(
                    product, 
                    image_analysis=log_entry.image_analysis,
                    processing_type=processing_type
                )
                
                # Вызов LLM
                generation_result = self.llm.generate_content(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt
                )
                
                # Обработка ответа
                content = generation_result['content']
                log_entry.raw_llm_response = generation_result
                log_entry.tokens_used = generation_result['tokens']
                log_entry.cost_usd = generation_result['cost_usd']
                log_entry.processing_time_ms = generation_result['processing_time_ms']

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
        
        if hasattr(product, 'images'):
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
            'name': product.name,
            'description': product.description,
            'price': str(product.price) if product.price else None,
            'brand': product.brand.name if product.brand else None,
        }
        
        # Пытаемся достать сырое описание из external_data (от парсеров)
        if product.external_data:
            attributes = product.external_data.get('attributes', {})
            if attributes.get('raw_caption'):
                data['raw_description'] = attributes['raw_caption']
                # Используем сырое описание как основное, если оно богаче
                if len(data['raw_description']) > len(data['description']):
                    data['description'] = data['raw_description']
                    
        return data

    def _get_prompt_template(self, template_type: str, default: str) -> str:
        """Получение шаблона промпта из БД или дефолтного."""
        template = AITemplate.objects.filter(
            template_type=template_type, 
            is_active=True
        ).first()
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

    def _construct_user_prompt(self, product: Product, image_analysis: Dict, processing_type: str) -> str:
        # Используем данные из input_data если они есть (собранные ранее)
        # Но здесь мы получаем product, так что лучше пересобрать или передать data
        # Для упрощения пересобираем
        input_data = self._collect_input_data(product)
        
        data = {
            "product_name": input_data['name'],
            "current_description": input_data['description'], # Может быть raw_description
            "brand": input_data['brand'] or "Unknown",
            "image_analysis": image_analysis
        }
        
        prompt = f"""
        Проанализируй следующие данные о товаре:
        {json.dumps(data, ensure_ascii=False)}
        
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
            "attributes": {{ "key": "value" }}
        }}
        """
        
        return prompt

    def _parse_and_save_results(self, log: AIProcessingLog, content: Dict):
        """Сохранение результатов из JSON ответа LLM в модель лога."""
        # Поддержка старого формата (плоский JSON) и нового (вложенный ru/en)
        
        # Если формат новый (есть ключ "ru"), берем данные оттуда для основных полей
        data_source = content.get('ru', content)
        
        if 'generated_title' in data_source:
            log.generated_title = data_source['generated_title']
        if 'generated_description' in data_source:
            log.generated_description = data_source['generated_description']
        if 'seo_title' in data_source:
            log.generated_seo_title = data_source['seo_title']
        if 'seo_description' in data_source:
            log.generated_seo_description = data_source['seo_description']
        if 'keywords' in data_source:
            log.generated_keywords = data_source['keywords']
            
        if 'attributes' in content:
            log.extracted_attributes = content['attributes']
            
        # Попытка найти категорию
        if 'suggested_category_name' in content:
            cat_name = content['suggested_category_name']
            # Простой поиск по названию (можно улучшить через векторный поиск)
            category = Category.objects.filter(name__icontains=cat_name).first()
            if category:
                log.suggested_category = category
            
            log.category_confidence = content.get('category_confidence', 0.5)
            
        log.save()

    def _apply_changes_to_product(self, product: Product, log: AIProcessingLog):
        """Применение сгенерированных данных к товару."""
        with transaction.atomic():
            # 1. Применяем основные данные (RU)
            if log.generated_title:
                product.name = log.generated_title
            if log.generated_description:
                product.description = log.generated_description
            
            # SEO fields (RU)
            if log.generated_seo_title:
                product.seo_title = log.generated_seo_title
            if log.generated_seo_description:
                product.seo_description = log.generated_seo_description
            if log.generated_keywords:
                product.keywords = log.generated_keywords
            
            # Category logic
            if log.suggested_category and log.category_confidence > 0.8:
                product.category = log.suggested_category
                
            product.save()
            
            # 2. Сохраняем переводы (EN), если они есть в raw_llm_response
            if log.raw_llm_response and 'content' in log.raw_llm_response:
                content = log.raw_llm_response['content']
                if 'en' in content:
                    en_data = content['en']
                    en_desc = en_data.get('generated_description')
                    if en_desc:
                        ProductTranslation.objects.update_or_create(
                            product=product,
                            locale='en',
                            defaults={'description': en_desc}
                        )
                    
                    # Если нужно сохранить английское название или SEO, 
                    # это потребовало бы расширения моделей перевода.
                    # Пока сохраняем только описание, как поддерживается моделью.

