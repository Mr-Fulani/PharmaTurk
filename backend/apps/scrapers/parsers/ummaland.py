"""Парсер для Ummaland.com - книги и исламские товары."""

import json
import logging
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.utils import clean_text, normalize_price, extract_currency


class UmmalandParser(BaseScraper):
    """Парсер для сайта Ummaland.com."""
    
    API_URL = "https://umma-land.com/wp-json/filters/products/"
    
    def get_name(self) -> str:
        """Возвращает имя парсера."""
        return "ummaland"
    
    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        return ["ummaland.com", "www.ummaland.com"]
    
    def parse_categories(self) -> List[Dict[str, Any]]:
        """Парсит список категорий."""
        # Возвращаем основные категории
        return [
            {
                'name': 'Книги',
                'url': 'https://umma-land.com/product-category/books',
            }
        ]

    def parse_product_list(self, 
                          category_url: str, 
                          max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из категории."""
        products = []
        
        try:
            self.logger.info(f"Парсинг категории: {category_url}")
            
            # 1. Получаем ID категории со страницы
            category_id = self._get_category_id(category_url)
            if not category_id:
                self.logger.error(f"Не удалось найти ID категории на странице {category_url}")
                return []
            
            self.logger.info(f"Найден ID категории: {category_id}")
            
            # 2. Запрашиваем товары через API
            api_products = self._fetch_products_from_api(category_id)
            self.logger.info(f"Получено {len(api_products)} товаров из API")
            
            if max_pages:
                per_page = 20
                api_products = api_products[:max_pages * per_page]
                self.logger.info(f"Ограничено до {max_pages} страниц")

            if hasattr(self, 'max_products') and self.max_products:
                api_products = api_products[:self.max_products]
                self.logger.info(f"Ограничено до {self.max_products} товаров")

            # 3. Обрабатываем каждый товар (парсим детальную страницу)
            for item in api_products:
                try:
                    # Базовые данные из API
                    api_product = self._parse_api_item(item)
                    if not api_product or not api_product.url:
                        continue
                        
                    self.logger.info(f"Парсинг деталей товара: {api_product.name}")
                    
                    # Получаем детали со страницы товара
                    detail_product = self.parse_product_detail(api_product.url)
                    
                    if detail_product:
                        # Объединяем данные
                        # API данные имеют приоритет для цены и наличия (обычно точнее/свежее)
                        # Детальная страница нужна для описания, доп. картинок и характеристик
                        
                        # Обновляем описание и атрибуты из детальной страницы
                        api_product.description = detail_product.description
                        api_product.attributes.update(detail_product.attributes)
                        
                        # Объединяем изображения (убираем дубликаты)
                        all_images = []
                        seen_urls = set()
                        
                        # Сначала изображения с детальной страницы (там их больше)
                        for img in detail_product.images:
                            if img and img not in seen_urls:
                                all_images.append(img)
                                seen_urls.add(img)
                                
                        # Потом изображение из API (если его еще нет)
                        for img in api_product.images:
                            if img and img not in seen_urls:
                                all_images.append(img)
                                seen_urls.add(img)
                                
                        api_product.images = all_images
                        
                        # Устанавливаем категорию и количество
                        api_product.category = "books"
                        api_product.stock_quantity = 3
                        
                        if self.validate_product(api_product):
                            products.append(api_product)
                            
                except Exception as e:
                    self.logger.error(f"Ошибка при обработке товара {item.get('name')}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге списка товаров: {e}")
        
        return products
    
    def _get_category_id(self, url: str) -> Optional[int]:
        """Получает ID категории из HTML страницы."""
        html = self._make_request(url)
        if not html:
            return None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Ищем hidden input с ID категории
        input_elem = soup.select_one('#current_category_id')
        if input_elem and input_elem.get('value'):
            try:
                return int(input_elem['value'])
            except ValueError:
                pass
                
        # Альтернативный способ: из link rel="alternate"
        # <link rel="alternate" type="application/json" href="https://umma-land.com/wp-json/wp/v2/product_cat/16" />
        link_elem = soup.find('link', attrs={'type': 'application/json', 'href': re.compile(r'product_cat/\d+')})
        if link_elem:
            match = re.search(r'product_cat/(\d+)', link_elem['href'])
            if match:
                return int(match.group(1))
                
        return None

    def _fetch_products_from_api(self, category_id: int) -> List[Dict]:
        """Получает список товаров через API."""
        payload = {
            "current_category": category_id,
            # Можно добавить другие фильтры, если нужно
            # "price": [0, 10000],
            # "sort": "date" 
        }
        
        try:
            response = self.client.post(
                self.API_URL, 
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Ошибка API запроса: {e}")
            return []

    def _parse_api_item(self, item: Dict) -> Optional[ScrapedProduct]:
        """Преобразует элемент API в ScrapedProduct."""
        name = clean_text(item.get('name', ''))
        url = item.get('link', '')
        
        if not name or not url:
            return None
            
        price_str = str(item.get('price', ''))
        price = normalize_price(price_str)
        
        image_url = item.get('image', '')
        images = [image_url] if image_url else []
        
        sku = str(item.get('sku', ''))
        external_id = str(item.get('id', ''))
        is_available = bool(item.get('in_stock', False))
        
        # Рейтинг и метки
        attributes = {}
        if item.get('rating'):
            attributes['rating'] = item['rating']
        if item.get('sale_text'):
            attributes['sale_label'] = item['sale_text']
            
        return ScrapedProduct(
            name=name,
            price=price,
            currency="RUB",
            url=url,
            images=images,
            sku=sku,
            external_id=external_id,
            is_available=is_available,
            attributes=attributes,
            source="ummaland"
        )

    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит детальную страницу товара для получения характеристик."""
        try:
            html = self._make_request(product_url)
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Название
            name_elem = soup.select_one('.product-block__heading')
            name = clean_text(name_elem.text) if name_elem else ""
            
            # 2. Описание
            # Пытаемся найти описание в разных блоках
            attributes: Dict[str, Any] = {}
            description = ""
            desc_candidates = [
                '.product-content-description',
                '#tab-description',
                '.woocommerce-product-details__short-description',
                '.product-description'
            ]

            desc_parts: List[str] = []
            for selector in desc_candidates:
                desc_elem = soup.select_one(selector)
                if not desc_elem:
                    continue
                lines = [
                    line.strip()
                    for line in desc_elem.get_text(separator='\n').splitlines()
                    if line.strip()
                ]
                text = '\n'.join(lines)
                if not text:
                    continue
                if text not in desc_parts:
                    desc_parts.append(text)

            if desc_parts:
                description = '\n\n'.join(desc_parts)

            if not description:
                try:
                    json_ld_scripts = soup.find_all('script', type='application/ld+json')
                    for script in json_ld_scripts:
                        if not script.string:
                            continue
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if isinstance(item, dict) and item.get('description'):
                                text = clean_text(item.get('description', ''))
                                if len(text) > len(description):
                                    description = text
                except Exception:
                    pass

            api_item = None
            try:
                slug = product_url.rstrip('/').split('/')[-1]
                api_url = f"https://umma-land.com/wp-json/wc/store/products?slug={slug}"
                api_json = self._make_request(api_url)
                if api_json:
                    data = json.loads(api_json)
                    if isinstance(data, list) and data:
                        api_item = data[0]
            except Exception:
                api_item = None

            if api_item:
                api_desc = api_item.get('description') or api_item.get('short_description') or ''
                if api_desc:
                    api_text = BeautifulSoup(api_desc, 'html.parser').get_text(separator='\n')
                    api_text = clean_text(api_text)
                    if len(api_text) > len(description):
                        description = api_text
                api_attrs = api_item.get('attributes') or []
                for attr in api_attrs:
                    name = clean_text(attr.get('name', '')).lower()
                    terms = attr.get('terms') or []
                    value = ''
                    if terms:
                        value = clean_text(terms[0].get('name', ''))
                    if not value:
                        continue
                    if 'author' not in attributes and 'автор' in name:
                        attributes['author'] = value
                    elif 'publisher' not in attributes and 'издатель' in name:
                        attributes['publisher'] = value
                    elif 'pages' not in attributes and ('объем' in name or 'стр' in name):
                        pages_match = re.search(r'\d+', value)
                        if pages_match:
                            attributes['pages'] = pages_match.group()
                    elif 'isbn' not in attributes and ('исбн' in name or 'isbn' in name):
                        attributes['isbn'] = value
                    elif 'circulation' not in attributes and 'тираж' in name:
                        circulation_match = re.search(r'\d+', value)
                        if circulation_match:
                            attributes['circulation'] = circulation_match.group()
                    elif 'age_limit' not in attributes and 'возраст' in name:
                        attributes['age_limit'] = value
            
            # 3. Характеристики
            # SEO Meta tags
            meta_title = soup.find('title')
            if meta_title:
                attributes['meta_title'] = clean_text(meta_title.text)

            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc:
                attributes['meta_description'] = clean_text(meta_desc.get('content', ''))

            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords:
                attributes['meta_keywords'] = clean_text(meta_keywords.get('content', ''))

            og_title = soup.find('meta', attrs={'property': 'og:title'})
            if og_title:
                attributes['og_title'] = clean_text(og_title.get('content', ''))

            og_desc = soup.find('meta', attrs={'property': 'og:description'})
            if og_desc:
                attributes['og_description'] = clean_text(og_desc.get('content', ''))

            og_image = soup.find('meta', attrs={'property': 'og:image'})
            if og_image:
                attributes['og_image_url'] = og_image.get('content', '')
            
            # Перебираем .product-property
            properties = soup.select('.product-property')
            for prop in properties:
                key_elem = prop.select_one('.product-property__key')
                val_elem = prop.select_one('.product-property__value')
                
                if key_elem and val_elem:
                    key = clean_text(key_elem.text).lower()
                    value = clean_text(val_elem.text)
                    
                    if 'автор' in key:
                        attributes['author'] = value
                    elif 'издательство' in key:
                        attributes['publisher'] = value
                    elif 'объем' in key or 'стр' in key:
                        # Извлекаем только цифры
                        pages_match = re.search(r'\d+', value)
                        if pages_match:
                            attributes['pages'] = pages_match.group()
                    elif 'исбн' in key or 'isbn' in key:
                        attributes['isbn'] = value
                    elif 'переплет' in key or 'обложка' in key:
                        attributes['cover_type'] = value
                    elif 'год' in key:
                        attributes['publication_year'] = value
                    elif 'возраст' in key:
                        attributes['age_limit'] = value
                    elif 'тираж' in key:
                        attributes['circulation'] = value

            isbn_candidates = []
            current_isbn = attributes.get('isbn')
            if current_isbn:
                isbn_candidates.append(current_isbn)
            text_content = soup.get_text()
            matches = re.finditer(r'(?:ISBN|ИСБН|Isbn)[\s:]+([0-9-]{10,25})', text_content, re.IGNORECASE)
            for match in matches:
                candidate = match.group(1).strip()
                candidate = candidate.rstrip('-.,')
                isbn_candidates.append(candidate)
            isbn_meta = soup.find('meta', attrs={'property': 'book:isbn'}) or \
                       soup.find('meta', attrs={'name': 'isbn'}) or \
                       soup.find('meta', attrs={'itemprop': 'isbn'})
            if isbn_meta and isbn_meta.get('content'):
                isbn_candidates.append(clean_text(isbn_meta.get('content')))
            try:
                json_ld_scripts = soup.find_all('script', type='application/ld+json')
                for script in json_ld_scripts:
                    if not script.string:
                        continue
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if isinstance(item, dict) and 'isbn' in item:
                            isbn_candidates.append(str(item['isbn']))
                        if isinstance(item, dict) and '@graph' in item:
                            for node in item['@graph']:
                                if 'isbn' in node:
                                    isbn_candidates.append(str(node['isbn']))
            except Exception:
                pass
            valid_isbns = []
            for candidate in isbn_candidates:
                candidate_str = str(candidate).strip()
                if not candidate_str:
                    continue
                lowered = candidate_str.lower()
                if "..." in candidate_str or "…" in candidate_str or "xxxx" in lowered or "00000" in candidate_str:
                    continue
                cand_digits = re.sub(r'\D', '', candidate_str)
                if len(cand_digits) in [10, 13]:
                    valid_isbns.append((len(cand_digits), candidate_str))
            if valid_isbns:
                valid_isbns.sort(key=lambda item: item[0], reverse=True)
                attributes['isbn'] = valid_isbns[0][1]
            else:
                attributes.pop('isbn', None)

            pages_value = attributes.get('pages')
            if pages_value:
                pages_match = re.search(r'\d+', str(pages_value))
                if pages_match:
                    pages_int = int(pages_match.group())
                    if 0 < pages_int < 10000:
                        attributes['pages'] = str(pages_int)
                    else:
                        attributes.pop('pages', None)
                else:
                    attributes.pop('pages', None)
            else:
                pages_match = re.search(r'(\d{2,4})\s*(?:стр\.|страниц)', text_content, re.IGNORECASE)
                if pages_match:
                    attributes['pages'] = pages_match.group(1)

            # 4. Изображения
            images = []
            
            # Главное изображение
            main_img = soup.select_one('.product-gallery__image')
            if main_img:
                src = main_img.get('data-src') or main_img.get('src')
                if src:
                    images.append(src)
                
            # Галерея
            gallery_previews = soup.select('.product-gallery__preview-image')
            for img in gallery_previews:
                src = img.get('data-src') or img.get('src')
                if src and src not in images:
                    images.append(src)
            
            # 5. Цена и наличие
            price_elem = soup.select_one('.product-price')
            price = None
            if price_elem:
                price_text = clean_text(price_elem.text)
                price = normalize_price(price_text)
            
            is_available = True
            stock_elem = soup.select_one('.product-available__text')
            if stock_elem:
                stock_text = stock_elem.text.lower()
                if 'нет в наличии' in stock_text or 'недоступно' in stock_text:
                    is_available = False
            
            # Кнопка покупки
            buy_btn = soup.select_one('.product-buy-button')
            if buy_btn and buy_btn.has_attr('disabled'):
                is_available = False

            return ScrapedProduct(
                name=name,
                description=description,
                price=price,
                currency="RUB",
                url=product_url,
                images=images,
                is_available=is_available,
                attributes=attributes,
                source="ummaland"
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге детальной страницы {product_url}: {e}")
            return None
