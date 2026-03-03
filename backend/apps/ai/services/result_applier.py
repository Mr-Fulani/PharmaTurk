import datetime
import logging
import re
from typing import Any, Dict, Optional, List
from django.db import transaction
from apps.catalog.models import Product

logger = logging.getLogger(__name__)

class BaseAIApplier:
    """Базовый класс для применения результатов AI к любым товарам."""
    
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
        if new_desc and getattr(target, 'description', None) != new_desc:
            target.description = new_desc
            updated = True
            
        # 3. Переводы
        translations = ai_data.get('translations', {})
        if translations:
            updated |= self.apply_translations(target, translations)
            
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
                
            if val and not re.search("[а-яА-Я]", str(val)):
                if getattr(target, model_key, None) != val:
                    if model_key in ['seo_title', 'meta_title']: val = str(val)[:70]
                    if model_key in ['seo_description', 'meta_description']: val = str(val)[:160]
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
                if val and getattr(trans, field, None) != val:
                    setattr(trans, field, val)
                    trans_updated = True
            
            if trans_updated or created:
                trans.save()
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

        # Количество на складе: если не задано у товара — ставим из AI или дефолт 3
        if hasattr(target, 'stock_quantity') and not target.stock_quantity:
            stock_qty = attrs.get('stock_quantity') or 3
            try:
                target.stock_quantity = int(stock_qty)
                book_updated = True
            except (TypeError, ValueError):
                target.stock_quantity = 3
                book_updated = True

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

class AIResultApplier:
    """Сервис-диспетчер для применения результатов AI."""
    
    _type_handlers = {
        'books': BookAIApplier,
    }
    
    _site_handlers = {
        # 'ummaland.uz': UmmalandAIApplier,
    }
    
    def apply_to_product(self, product: Product, ai_data: Dict[str, Any]) -> bool:
        """
        Главная точка входа для применения данных к продукту.
        Автоматически определяет домен и нужный обработчик.
        """
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
        logger.info(f"Applying AI results to {product} (type: {product_type}, site: {site}) via {handler.__class__.__name__}")

        # Применяем сгенерированное название к базовому товару (name показывается на сайте)
        with transaction.atomic():
            new_title = (ai_data.get("generated_title") or "").strip()
            if new_title:
                product.name = new_title[:500]
                product.save(update_fields=["name"])
            return handler.apply(target, ai_data)
