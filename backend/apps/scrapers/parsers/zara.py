"""Парсер для сайта zara.com - одежда и аксессуары."""

import re
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.selectors import DataSelector, SelectorConfig
from ..base.utils import clean_text, normalize_price, extract_currency


class ZaraParser(BaseScraper):
    """Парсер для сайта zara.com."""
    
    def __init__(self, base_url="https://www.zara.com", **kwargs):
        """Инициализация парсера zara.com."""
        super().__init__(
            base_url=base_url,
            delay_range=(3, 5),  # Больше задержка для защиты от блокировки
            **kwargs
        )
        
        # Zara часто использует JavaScript и API, поэтому селекторы могут отличаться
        self.product_list_selectors = {
            'name': SelectorConfig(
                selector='.product-info-item .product-title, .product-name, [data-testid="product-title"]',
                attribute='text',
                transformations=['clean', 'strip'],
                required=True
            ),
            'price': SelectorConfig(
                selector='.price, .product-price, [data-testid="product-price"]',
                attribute='text',
                transformations=['clean', 'price'],
                default=None
            ),
            'url': SelectorConfig(
                selector='a',
                attribute='href',
                required=True
            ),
            'image': SelectorConfig(
                selector='img',
                attribute='src',
                default=''
            ),
        }
        
        self.product_detail_selectors = {
            'name': SelectorConfig(
                selector='h1, .product-detail-info h1, [data-testid="product-title"]',
                attribute='text',
                transformations=['clean', 'strip'],
                required=True
            ),
            'description': SelectorConfig(
                selector='.product-detail-description, .expandable-text, .product-description',
                attribute='text',
                transformations=['clean'],
                default=''
            ),
            'price': SelectorConfig(
                selector='.product-detail-info .price, .money-amount, [data-testid="current-price"]',
                attribute='text',
                transformations=['clean', 'price'],
                default=None
            ),
            'old_price': SelectorConfig(
                selector='.price-old, .old-price, [data-testid="old-price"]',
                attribute='text',
                transformations=['clean', 'price'],
                default=None
            ),
            'images': SelectorConfig(
                selector='.product-detail-images img, .media-image img, [data-testid="product-image"]',
                attribute='src',
                all_elements=True,
                default=[]
            ),
            'brand': SelectorConfig(
                selector='.brand-name',
                attribute='text',
                transformations=['clean', 'strip'],
                default='Zara'
            ),
            'category': SelectorConfig(
                selector='.breadcrumb-item:last-child, .breadcrumbs a:last-of-type',
                attribute='text',
                transformations=['clean', 'strip'],
                default=''
            ),
            'sku': SelectorConfig(
                selector='[data-productid], .product-reference, .reference-number',
                attribute='data-productid',
                transformations=['clean', 'strip'],
                default=''
            ),
            'colors': SelectorConfig(
                selector='.color-selector .color-item, .product-colors .color',
                attribute='title',
                all_elements=True,
                default=[]
            ),
            'sizes': SelectorConfig(
                selector='.size-selector .size-item, .product-sizes .size',
                attribute='text',
                all_elements=True,
                default=[]
            ),
            'availability': SelectorConfig(
                selector='.product-availability, .stock-info',
                attribute='text',
                transformations=['clean', 'lower'],
                default='available'
            ),
        }
    
    def get_name(self) -> str:
        """Возвращает имя парсера."""
        return "zara"
    
    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        return [
            "zara.com", 
            "www.zara.com",
            "tr.zara.com",  # Турецкая версия
            "ru.zara.com"   # Российская версия
        ]
    
    def parse_categories(self) -> List[Dict[str, Any]]:
        """Парсит категории одежды."""
        try:
            # Пробуем разные локали
            locales = ["tr", "ru", "en"]
            categories = []
            
            for locale in locales:
                try:
                    url = f"/{locale}/woman" if locale != "en" else "/woman"
                    html = self._make_request(url)
                    if not html:
                        continue
                    
                    selector = self._parse_page(html, urljoin(self.base_url, url))
                    
                    # Селекторы для категорий
                    category_configs = {
                        'name': SelectorConfig(
                            selector='text',
                            transformations=['clean', 'strip']
                        ),
                        'url': SelectorConfig(
                            selector='href',
                            attribute='href'
                        ),
                    }
                    
                    # Пробуем разные селекторы для меню категорий
                    category_selectors = [
                        '.category-menu a',
                        '.navigation-menu a',
                        '.main-menu .menu-item a',
                        '.categories-list a',
                        'nav a[href*="category"]'
                    ]
                    
                    for cat_selector in category_selectors:
                        try:
                            items = selector.extract_product_list(cat_selector, category_configs)
                            if items:
                                for item in items:
                                    if item.get('name') and item.get('url') and 'category' in item['url']:
                                        categories.append({
                                            'name': item['name'],
                                            'url': urljoin(self.base_url, item['url']),
                                            'external_id': self._extract_id_from_url(item['url']),
                                            'source': self.get_name(),
                                            'locale': locale
                                        })
                                break
                        except:
                            continue
                    
                    if categories:
                        break
                        
                except Exception as e:
                    self.logger.warning(f"Ошибка при парсинге категорий для локали {locale}: {e}")
                    continue
            
            self.logger.info(f"Найдено {len(categories)} категорий на zara.com")
            return categories
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге категорий zara.com: {e}")
            return []
    
    def parse_product_list(self, 
                          category_url: str, 
                          max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из категории."""
        products = []
        page = 0  # Zara обычно использует offset
        
        try:
            while page < max_pages:
                # Формируем URL с пагинацией (Zara может использовать разные схемы)
                if '?' in category_url:
                    page_url = f"{category_url}&ajax=true&page={page}"
                else:
                    page_url = f"{category_url}?ajax=true&page={page}"
                
                self.logger.info(f"Парсинг страницы {page}: {page_url}")
                
                html = self._make_request(page_url)
                if not html:
                    break
                
                # Проверяем, не пришел ли JSON ответ
                page_products = self._parse_zara_response(html, page_url)
                
                if not page_products:
                    # Пробуем обычный HTML парсинг
                    selector = self._parse_page(html, page_url)
                    page_products = self._parse_html_products(selector)
                
                if not page_products:
                    self.logger.warning(f"Не найдено товаров на странице {page}")
                    break
                
                # Обрабатываем найденные товары
                for item_data in page_products:
                    try:
                        product = self._process_zara_product(item_data, category_url)
                        if product and self.validate_product(product):
                            products.append(product)
                    except Exception as e:
                        self.logger.error(f"Ошибка обработки товара: {e}")
                
                self.logger.info(f"Найдено {len(page_products)} товаров на странице {page}")
                page += 1
                
                # Если товаров меньше ожидаемого, вероятно это последняя страница
                if len(page_products) < 20:  # Обычный размер страницы Zara
                    break
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге списка товаров: {e}")
        
        self.logger.info(f"Всего спарсено {len(products)} товаров из {category_url}")
        return products
    
    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит детальную страницу товара."""
        try:
            html = self._make_request(product_url)
            if not html:
                return None
            
            # Пробуем найти JSON данные в HTML
            product_data = self._extract_product_json(html)
            
            if not product_data:
                # Парсим HTML селекторами
                selector = self._parse_page(html, product_url)
                product_data = selector.extract_multiple(self.product_detail_selectors)
            
            # Дополнительно извлекаем атрибуты одежды
            fashion_attrs = self._extract_fashion_attributes(html, product_data)
            product_data.update(fashion_attrs)
            
            # Нормализуем данные
            product = self._normalize_zara_product(product_data, product_url)
            
            return product if self.validate_product(product) else None
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге товара {product_url}: {e}")
            return None
    
    def search_products(self, query: str, max_results: int = 50) -> List[ScrapedProduct]:
        """Поиск товаров по запросу."""
        try:
            search_url = f"/search?searchTerm={query}"
            return self.parse_product_list(search_url, max_pages=max_results // 20 + 1)
        except Exception as e:
            self.logger.error(f"Ошибка поиска товаров по запросу '{query}': {e}")
            return []
    
    def _parse_zara_response(self, content: str, url: str) -> List[Dict[str, Any]]:
        """Парсит ответ от Zara (может быть JSON)."""
        try:
            # Пробуем распарсить как JSON
            data = json.loads(content)
            
            # Ищем товары в разных структурах JSON
            products = []
            
            if isinstance(data, dict):
                # Ищем товары в разных ключах
                for key in ['products', 'productGroups', 'items', 'data']:
                    if key in data:
                        items = data[key]
                        if isinstance(items, list):
                            for item in items:
                                product_data = self._normalize_json_product(item)
                                if product_data:
                                    products.append(product_data)
            
            return products
            
        except json.JSONDecodeError:
            # Не JSON, возвращаем пустой список
            return []
    
    def _parse_html_products(self, selector: DataSelector) -> List[Dict[str, Any]]:
        """Парсит товары из HTML."""
        # Селекторы для товаров Zara
        product_selectors = [
            '.product-item',
            '.product-card',
            '.grid-card',
            'article',
            '.product-grid-item'
        ]
        
        for prod_selector in product_selectors:
            try:
                items = selector.extract_product_list(prod_selector, self.product_list_selectors)
                if items:
                    return items
            except:
                continue
        
        return []
    
    def _normalize_json_product(self, json_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Нормализует данные товара из JSON."""
        try:
            return {
                'name': json_data.get('name', ''),
                'price': json_data.get('price', {}).get('current'),
                'old_price': json_data.get('price', {}).get('old'),
                'url': json_data.get('url', ''),
                'image': json_data.get('image', {}).get('url', ''),
                'sku': json_data.get('id', ''),
                'colors': json_data.get('colors', []),
                'sizes': json_data.get('sizes', []),
            }
        except:
            return None
    
    def _extract_product_json(self, html: str) -> Optional[Dict[str, Any]]:
        """Извлекает JSON данные товара из HTML."""
        try:
            # Ищем JSON данные в script тегах
            json_patterns = [
                r'window\.zara\.viewPayload\s*=\s*({.+?});',
                r'window\.zara\.product\s*=\s*({.+?});',
                r'__ZARA_PRODUCT__\s*=\s*({.+?});',
                r'product:\s*({.+?})\s*[,}]'
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                for match in matches:
                    try:
                        data = json.loads(match)
                        if isinstance(data, dict) and data.get('name'):
                            return self._normalize_json_product(data)
                    except:
                        continue
            
        except Exception as e:
            self.logger.debug(f"Не удалось извлечь JSON данные: {e}")
        
        return None
    
    def _process_zara_product(self, item_data: Dict[str, Any], source_url: str) -> Optional[ScrapedProduct]:
        """Обрабатывает данные товара Zara."""
        try:
            # Нормализуем URL
            product_url = item_data.get('url', '')
            if product_url:
                if not product_url.startswith('http'):
                    product_url = urljoin(self.base_url, product_url)
            
            # Обрабатываем изображения
            images = []
            if item_data.get('image'):
                images.append(urljoin(self.base_url, item_data['image']))
            
            # Создаем объект товара
            product = ScrapedProduct(
                name=item_data.get('name', ''),
                price=item_data.get('price'),
                currency=extract_currency(str(item_data.get('price', ''))),
                url=product_url,
                images=images,
                external_id=item_data.get('sku') or self._extract_id_from_url(product_url),
                source=self.get_name(),
                category=self._extract_category_from_url(source_url),
                brand='Zara',
                attributes={
                    'colors': item_data.get('colors', []),
                    'sizes': item_data.get('sizes', []),
                    'old_price': item_data.get('old_price')
                }
            )
            
            return product
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки товара Zara: {e}")
            return None
    
    def _normalize_zara_product(self, data: Dict[str, Any], url: str) -> ScrapedProduct:
        """Нормализует данные товара с zara.com."""
        # Обработка наличия
        availability_text = str(data.get('availability', 'available')).lower()
        is_available = 'available' in availability_text or 'в наличии' in availability_text
        
        # Обработка изображений
        images = []
        if data.get('images'):
            for img_url in data['images']:
                if img_url and not img_url.startswith('data:'):
                    images.append(urljoin(self.base_url, img_url))
        
        # Создаем объект товара
        product = ScrapedProduct(
            name=data.get('name', ''),
            description=data.get('description', ''),
            price=data.get('price'),
            currency=extract_currency(str(data.get('price', ''))),
            url=url,
            images=images,
            category=data.get('category', ''),
            brand=data.get('brand', 'Zara'),
            external_id=data.get('sku') or self._extract_id_from_url(url),
            sku=data.get('sku', ''),
            is_available=is_available,
            attributes={
                'colors': data.get('colors', []),
                'sizes': data.get('sizes', []),
                'old_price': data.get('old_price'),
                **data.get('attributes', {})
            },
            source=self.get_name()
        )
        
        return product
    
    def _extract_fashion_attributes(self, html: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлекает атрибуты одежды."""
        attributes = {}
        
        # Извлекаем материалы и уход
        care_patterns = [
            r'(?:Care|Уход|Bakım):\s*(.+?)(?:\n|\r|<)',
            r'(?:Material|Материал|Malzeme):\s*(.+?)(?:\n|\r|<)',
            r'(?:Composition|Состав|Bileşim):\s*(.+?)(?:\n|\r|<)'
        ]
        
        for pattern in care_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                attributes['care_instructions'] = matches[0].strip()
                break
        
        # Размерная сетка
        if data.get('sizes'):
            attributes['available_sizes'] = data['sizes']
        
        # Цвета
        if data.get('colors'):
            attributes['available_colors'] = data['colors']
        
        return {'attributes': attributes}
    
    def _extract_id_from_url(self, url: str) -> str:
        """Извлекает ID товара из URL."""
        if not url:
            return ""
        
        # Паттерны для Zara URLs
        patterns = [
            r'/p/(\d+)',           # /p/12345
            r'/product/(\d+)',     # /product/12345
            r'\.html\?v=(\d+)',    # .html?v=12345
            r'/(\d+)\.html',       # /12345.html
            r'productId=(\d+)',    # ?productId=12345
            r'/([a-zA-Z0-9\-_]+)\.html'  # /product-name.html
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # Если ничего не найдено, используем хеш URL
        return str(abs(hash(url)))
    
    def _extract_category_from_url(self, url: str) -> str:
        """Извлекает категорию из URL."""
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p]
            
            # Ищем категорию в пути
            category_keywords = ['woman', 'man', 'kids', 'home', 'category']
            
            for i, part in enumerate(path_parts):
                if part.lower() in category_keywords:
                    if i + 1 < len(path_parts):
                        return clean_text(path_parts[i + 1].replace('-', ' ').title())
            
            # Если не найдено, берем вторую часть пути (после локали)
            if len(path_parts) >= 2:
                return clean_text(path_parts[1].replace('-', ' ').title())
                
        except:
            pass
        
        return ""
