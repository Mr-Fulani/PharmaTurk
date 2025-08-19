"""Парсер для сайта ilacabak.com - турецкие медикаменты и БАДы."""

import re
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.selectors import DataSelector, SelectorConfig
from ..base.utils import clean_text, normalize_price, extract_currency


class IlacabakParser(BaseScraper):
    """Парсер для сайта ilacabak.com."""
    
    def __init__(self, base_url="https://ilacabak.com", **kwargs):
        """Инициализация парсера ilacabak.com."""
        super().__init__(
            base_url=base_url,
            delay_range=(2, 4),  # Больше задержка для медицинского сайта
            **kwargs
        )
        
        # Селекторы для парсинга
        self.product_list_selectors = {
            'name': SelectorConfig(
                selector='h3 a, .product-name a, .ilaç-adı a',
                attribute='text',
                transformations=['clean', 'strip'],
                required=True
            ),
            'price': SelectorConfig(
                selector='.price, .fiyat, .price-current',
                attribute='text',
                transformations=['clean', 'price'],
                default=None
            ),
            'url': SelectorConfig(
                selector='h3 a, .product-name a, .ilaç-adı a',
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
                selector='h1, .product-title, .ilaç-başlık',
                attribute='text',
                transformations=['clean', 'strip'],
                required=True
            ),
            'description': SelectorConfig(
                selector='.product-description, .açıklama, .detay',
                attribute='text',
                transformations=['clean'],
                default=''
            ),
            'price': SelectorConfig(
                selector='.price, .fiyat, .price-current, .current-price',
                attribute='text',
                transformations=['clean', 'price'],
                default=None
            ),
            'old_price': SelectorConfig(
                selector='.old-price, .eski-fiyat, .price-old',
                attribute='text',
                transformations=['clean', 'price'],
                default=None
            ),
            'images': SelectorConfig(
                selector='.product-images img, .galeri img, .product-gallery img',
                attribute='src',
                all_elements=True,
                default=[]
            ),
            'brand': SelectorConfig(
                selector='.brand, .marka, .manufacturer, .üretici',
                attribute='text',
                transformations=['clean', 'strip'],
                default=''
            ),
            'category': SelectorConfig(
                selector='.breadcrumb a:last-of-type, .kategori, .category',
                attribute='text',
                transformations=['clean', 'strip'],
                default=''
            ),
            'sku': SelectorConfig(
                selector='[data-sku], .sku, .product-code, .ürün-kodu',
                attribute='text',
                transformations=['clean', 'strip'],
                default=''
            ),
            'barcode': SelectorConfig(
                selector='.barcode, .barkod',
                attribute='text',
                transformations=['clean', 'strip'],
                default=''
            ),
            'availability': SelectorConfig(
                selector='.stock-status, .stok-durumu, .availability',
                attribute='text',
                transformations=['clean', 'lower'],
                default='mevcut'
            ),
        }
    
    def get_name(self) -> str:
        """Возвращает имя парсера."""
        return "ilacabak"
    
    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        return ["ilacabak.com", "www.ilacabak.com"]
    
    def parse_categories(self) -> List[Dict[str, Any]]:
        """Парсит категории лекарств."""
        try:
            html = self._make_request("/")
            if not html:
                return []
            
            selector = self._parse_page(html, self.base_url)
            
            # Ищем навигационное меню или список категорий
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
            
            # Пробуем разные селекторы для категорий
            category_selectors = [
                '.menu a',
                '.category-list a',
                '.nav-categories a',
                '.kategori-listesi a',
                '.ana-menu a'
            ]
            
            categories = []
            for cat_selector in category_selectors:
                try:
                    items = selector.extract_product_list(cat_selector, category_configs)
                    if items:
                        for item in items:
                            if item.get('name') and item.get('url'):
                                categories.append({
                                    'name': item['name'],
                                    'url': urljoin(self.base_url, item['url']),
                                    'external_id': self._extract_id_from_url(item['url']),
                                    'source': self.get_name()
                                })
                        break
                except:
                    continue
            
            self.logger.info(f"Найдено {len(categories)} категорий на ilacabak.com")
            return categories
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге категорий ilacabak.com: {e}")
            return []
    
    def parse_product_list(self, 
                          category_url: str, 
                          max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из категории."""
        products = []
        page = 1
        
        try:
            while page <= max_pages:
                # Формируем URL страницы
                if '?' in category_url:
                    page_url = f"{category_url}&page={page}"
                else:
                    page_url = f"{category_url}?page={page}"
                
                self.logger.info(f"Парсинг страницы {page}: {page_url}")
                
                html = self._make_request(page_url)
                if not html:
                    break
                
                selector = self._parse_page(html, page_url)
                
                # Пробуем разные селекторы для товаров
                product_selectors = [
                    '.product-item',
                    '.ilaç-item',
                    '.product-card',
                    '.medicine-item',
                    '.drug-item',
                    'article',
                    '.list-item'
                ]
                
                page_products = []
                for prod_selector in product_selectors:
                    try:
                        items = selector.extract_product_list(prod_selector, self.product_list_selectors)
                        if items:
                            page_products = items
                            break
                    except:
                        continue
                
                if not page_products:
                    self.logger.warning(f"Не найдено товаров на странице {page}")
                    break
                
                # Обрабатываем найденные товары
                for item_data in page_products:
                    try:
                        product = self._process_product_item(item_data, category_url)
                        if product and self.validate_product(product):
                            products.append(product)
                    except Exception as e:
                        self.logger.error(f"Ошибка обработки товара: {e}")
                
                self.logger.info(f"Найдено {len(page_products)} товаров на странице {page}")
                page += 1
                
                # Проверяем, есть ли следующая страница
                if not self._has_next_page(selector):
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
            
            selector = self._parse_page(html, product_url)
            
            # Извлекаем основные данные товара
            product_data = selector.extract_multiple(self.product_detail_selectors)
            
            # Дополнительно извлекаем медицинские атрибуты
            medical_attrs = self._extract_medical_attributes(selector)
            product_data.update(medical_attrs)
            
            # Нормализуем данные
            product = self._normalize_ilacabak_product(product_data, product_url)
            
            return product if self.validate_product(product) else None
            
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге товара {product_url}: {e}")
            return None
    
    def search_products(self, query: str, max_results: int = 50) -> List[ScrapedProduct]:
        """Поиск товаров по запросу."""
        try:
            search_url = f"/arama?q={query}"
            return self.parse_product_list(search_url, max_pages=max_results // 20 + 1)
        except Exception as e:
            self.logger.error(f"Ошибка поиска товаров по запросу '{query}': {e}")
            return []
    
    def _process_product_item(self, item_data: Dict[str, Any], source_url: str) -> Optional[ScrapedProduct]:
        """Обрабатывает данные товара из списка."""
        try:
            # Нормализуем URL
            product_url = item_data.get('url', '')
            if product_url:
                product_url = urljoin(self.base_url, product_url)
            
            # Создаем базовый объект товара
            product = ScrapedProduct(
                name=item_data.get('name', ''),
                price=item_data.get('price'),
                currency=extract_currency(str(item_data.get('price', ''))),
                url=product_url,
                images=[urljoin(self.base_url, item_data.get('image', ''))] if item_data.get('image') else [],
                external_id=self._extract_id_from_url(product_url),
                source=self.get_name(),
                category=self._extract_category_from_url(source_url)
            )
            
            return product
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки товара: {e}")
            return None
    
    def _normalize_ilacabak_product(self, data: Dict[str, Any], url: str) -> ScrapedProduct:
        """Нормализует данные товара с ilacabak.com."""
        # Обработка наличия
        availability_text = str(data.get('availability', 'mevcut')).lower()
        is_available = 'mevcut' in availability_text or 'stokta' in availability_text
        
        # Обработка изображений
        images = []
        if data.get('images'):
            for img_url in data['images']:
                if img_url:
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
            brand=data.get('brand', ''),
            external_id=self._extract_id_from_url(url),
            sku=data.get('sku', ''),
            barcode=data.get('barcode', ''),
            is_available=is_available,
            attributes=data.get('attributes', {}),
            source=self.get_name()
        )
        
        return product
    
    def _extract_medical_attributes(self, selector: DataSelector) -> Dict[str, Any]:
        """Извлекает медицинские атрибуты товара."""
        attributes = {}
        
        # Селекторы для медицинских атрибутов
        medical_selectors = {
            'active_ingredient': ['.etken-madde', '.active-ingredient', '.composition'],
            'dosage_form': ['.form', '.şekil', '.dosage-form'],
            'strength': ['.güç', '.strength', '.doz'],
            'manufacturer': ['.üretici', '.manufacturer', '.firma'],
            'atc_code': ['.atc', '.atc-code'],
            'prescription_required': ['.reçete', '.prescription'],
            'indications': ['.endikasyon', '.indications', '.kullanım'],
            'contraindications': ['.kontrendikasyon', '.contraindications'],
            'side_effects': ['.yan-etki', '.side-effects'],
            'storage': ['.saklama', '.storage'],
            'expiry': ['.son-kullanma', '.expiry']
        }
        
        for attr_name, selectors in medical_selectors.items():
            for sel in selectors:
                try:
                    config = SelectorConfig(
                        selector=sel,
                        attribute='text',
                        transformations=['clean', 'strip'],
                        default=''
                    )
                    value = selector.extract(config)
                    if value:
                        attributes[attr_name] = value
                        break
                except:
                    continue
        
        return {'attributes': attributes}
    
    def _extract_id_from_url(self, url: str) -> str:
        """Извлекает ID товара из URL."""
        if not url:
            return ""
        
        # Пробуем разные паттерны ID
        patterns = [
            r'/(\d+)/?$',  # ID в конце URL
            r'/p/(\d+)',   # /p/12345
            r'/product/(\d+)',  # /product/12345
            r'id=(\d+)',   # ?id=12345
            r'/([a-zA-Z0-9\-_]+)/?$'  # Slug в конце
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
            category_keywords = ['kategori', 'category', 'ilac', 'medicine', 'drug']
            
            for i, part in enumerate(path_parts):
                if any(keyword in part.lower() for keyword in category_keywords):
                    if i + 1 < len(path_parts):
                        return clean_text(path_parts[i + 1].replace('-', ' ').title())
            
            # Если не найдено, берем последнюю часть пути
            if path_parts:
                return clean_text(path_parts[-1].replace('-', ' ').title())
                
        except:
            pass
        
        return ""
    
    def _has_next_page(self, selector: DataSelector) -> bool:
        """Проверяет, есть ли следующая страница."""
        next_selectors = [
            '.next-page',
            '.sonraki',
            '.pagination .next',
            'a[rel="next"]',
            '.page-next'
        ]
        
        for sel in next_selectors:
            try:
                config = SelectorConfig(selector=sel, default=None)
                if selector.extract(config):
                    return True
            except:
                continue
        
        return False
