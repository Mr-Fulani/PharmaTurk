"""Парсер для сайта zara.com - одежда и аксессуары."""

import logging
import re
import time
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import requests

from ..base.scraper import BaseScraper, ScrapedProduct
from ..base.selectors import SelectorConfig, SelectorType

logger = logging.getLogger(__name__)


class ZaraParser(BaseScraper):
    """Парсер для сайта zara.com."""

    def __init__(self, base_url="https://www.zara.com", **kwargs):
        """Инициализация парсера zara.com."""
        super().__init__(
            base_url=base_url,
            delay_range=(3, 5),  # Больше задержка для защиты от блокировки
            **kwargs
        )
        
        # Настройка заголовков для обхода Akamai Bot Manager
        self.default_headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
        })
        
        # URL категорий для Zara (прямые ссылки)
        self.category_urls = [
            'https://www.zara.com/tr/tr/kadin-l1000.html',
            'https://www.zara.com/tr/tr/erkek-l1000.html',
            'https://www.zara.com/tr/tr/cocuk-l1000.html',
            'https://www.zara.com/tr/tr/ev-l1000.html',
            'https://www.zara.com/tr/tr/kozmetik-l1000.html',
        ]

    def get_category_urls(self) -> List[str]:
        """Получает список URL категорий."""
        logger.info(f"Используем предустановленные URL категорий для {self.base_url}")
        return self.category_urls

    def parse_products_page(self, url: str) -> List[ScrapedProduct]:
        """Парсит страницу с товарами."""
        logger.info(f"Парсинг страницы товаров: {url}")
        
        try:
            # Добавляем задержку перед запросом
            self._random_delay()
            
            # Делаем запрос с правильными заголовками
            response = self._make_request(url)
            if not response:
                logger.warning(f"Не удалось получить страницу: {url}")
                return []
            
            soup = self._parse_html(response.text)
            if not soup:
                return []
            
            # Ищем товары на странице
            products = []
            
            # Пробуем разные селекторы для товаров
            product_selectors = [
                '[data-qa-action="product-card"]',
                '.product-card',
                '.product-item',
                '[data-productid]',
                '.product',
                'article[data-qa-action="product-card"]'
            ]
            
            for selector in product_selectors:
                product_elements = soup.select(selector)
                if product_elements:
                    logger.info(f"Найдено {len(product_elements)} товаров с селектором: {selector}")
                    break
            
            if not product_elements:
                # Если не нашли товары, попробуем найти любые ссылки на товары
                product_links = soup.find_all('a', href=re.compile(r'/tr/tr/.*\.html'))
                logger.info(f"Найдено {len(product_links)} ссылок на товары")
                
                for link in product_links[:10]:  # Ограничиваем для теста
                    href = link.get('href')
                    if href and '/tr/tr/' in href and '.html' in href:
                        product_url = urljoin(self.base_url, href)
                        product_name = link.get_text(strip=True) or "Товар Zara"
                        
                        products.append(ScrapedProduct(
                            name=product_name,
                            price=None,
                            image_url=None,
                            product_url=product_url,
                            category=None,
                            brand="Zara",
                            description=None,
                            external_id=None,
                            external_data={
                                'source': 'zara',
                                'url': product_url
                            }
                        ))
                
                return products
            
            # Парсим найденные товары
            for element in product_elements[:10]:  # Ограничиваем для теста
                try:
                    # Извлекаем данные товара
                    name_elem = element.select_one('[data-qa-action="product-card-name"]') or element.select_one('.product-name') or element.select_one('h3') or element.select_one('h4')
                    name = name_elem.get_text(strip=True) if name_elem else "Товар Zara"
                    
                    price_elem = element.select_one('[data-qa-action="product-card-price"]') or element.select_one('.price') or element.select_one('.product-price')
                    price = price_elem.get_text(strip=True) if price_elem else None
                    
                    image_elem = element.select_one('img[data-qa-action="product-card-image"]') or element.select_one('img')
                    image_url = image_elem.get('src') if image_elem else None
                    if image_url:
                        image_url = urljoin(self.base_url, image_url)
                    
                    link_elem = element.select_one('a[data-qa-action="product-card-link"]') or element.select_one('a')
                    product_url = link_elem.get('href') if link_elem else None
                    if product_url:
                        product_url = urljoin(self.base_url, product_url)
                    
                    # Определяем категорию из URL
                    category = None
                    if product_url:
                        path = urlparse(product_url).path
                        if '/kadin/' in path:
                            category = "Женская одежда"
                        elif '/erkek/' in path:
                            category = "Мужская одежда"
                        elif '/cocuk/' in path:
                            category = "Детская одежда"
                        elif '/ev/' in path:
                            category = "Дом"
                        elif '/kozmetik/' in path:
                            category = "Косметика"
                    
                    products.append(ScrapedProduct(
                        name=name,
                        price=price,
                        image_url=image_url,
                        product_url=product_url,
                        category=category,
                        brand="Zara",
                        description=None,
                        external_id=None,
                        external_data={
                            'source': 'zara',
                            'url': product_url,
                            'raw_element': str(element)[:500]  # Сохраняем часть HTML для отладки
                        }
                    ))
                    
                except Exception as e:
                    logger.error(f"Ошибка при парсинге товара: {e}")
                    continue
            
            logger.info(f"Успешно спарсено {len(products)} товаров с {url}")
            return products
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге страницы {url}: {e}")
            return []

    def _make_request(self, url: str, retries: int = None) -> Optional[requests.Response]:
        """Делает HTTP запрос с обходом защиты."""
        if retries is None:
            retries = self.max_retries
            
        for attempt in range(retries + 1):
            try:
                logger.info(f"Запрос к {url} (попытка {attempt + 1})")
                
                # Добавляем случайную задержку
                self._random_delay()
                
                response = requests.get(
                    url,
                    headers=self.default_headers,
                    timeout=self.timeout,
                    allow_redirects=True
                )
                
                # Проверяем на Akamai challenge
                if 'bm-verify' in response.text or 'Access Denied' in response.text:
                    logger.warning(f"Обнаружена защита Akamai на {url}")
                    if attempt < retries:
                        logger.info(f"Ждем перед повторной попыткой...")
                        time.sleep(5 + attempt * 2)  # Увеличиваем задержку
                        continue
                    else:
                        logger.error(f"Не удалось обойти защиту Akamai после {retries} попыток")
                        return None
                
                if response.status_code == 200:
                    return response
                else:
                    logger.warning(f"HTTP ошибка {response.status_code} для {url}")
                    
            except Exception as e:
                logger.error(f"Ошибка запроса к {url}: {e}")
                if attempt < retries:
                    time.sleep(2)
                    continue
                    
        return None
    
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
    
    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит детальную страницу товара."""
        try:
            response = self._make_request(product_url)
            if not response:
                return None
            
            soup = self._parse_html(response.text)
            if not soup:
                return None
            
            # Извлекаем данные товара
            name_elem = soup.select_one('h1') or soup.select_one('.product-name') or soup.select_one('[data-qa-action="product-name"]')
            name = name_elem.get_text(strip=True) if name_elem else "Товар Zara"
            
            price_elem = soup.select_one('.price') or soup.select_one('.product-price') or soup.select_one('[data-qa-action="product-price"]')
            price = price_elem.get_text(strip=True) if price_elem else None
            
            image_elem = soup.select_one('img') or soup.select_one('.product-image img')
            image_url = image_elem.get('src') if image_elem else None
            if image_url:
                image_url = urljoin(self.base_url, image_url)
            
            # Определяем категорию из URL
            category = None
            path = urlparse(product_url).path
            if '/kadin/' in path:
                category = "Женская одежда"
            elif '/erkek/' in path:
                category = "Мужская одежда"
            elif '/cocuk/' in path:
                category = "Детская одежда"
            elif '/ev/' in path:
                category = "Дом"
            elif '/kozmetik/' in path:
                category = "Косметика"
            
            return ScrapedProduct(
                name=name,
                price=price,
                image_url=image_url,
                product_url=product_url,
                category=category,
                brand="Zara",
                description=None,
                external_id=None,
                external_data={
                    'source': 'zara',
                    'url': product_url
                }
            )
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге товара {product_url}: {e}")
            return None
    
    def parse_product_list(self, category_url: str, max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из категории."""
        products = []
        
        try:
            # Парсим первую страницу
            page_products = self.parse_products_page(category_url)
            products.extend(page_products)
            
            # Если нужно больше страниц, можно добавить пагинацию
            if max_pages > 1 and len(page_products) > 0:
                logger.info(f"Найдено {len(page_products)} товаров на первой странице")
                # Здесь можно добавить логику пагинации для Zara
            
        except Exception as e:
            logger.error(f"Ошибка при парсинге списка товаров: {e}")
        
        logger.info(f"Всего спарсено {len(products)} товаров из {category_url}")
        return products
