"""Базовый класс для всех парсеров."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import httpx
from fake_useragent import UserAgent

from .selectors import DataSelector, SelectorConfig
from .utils import clean_text, normalize_price, extract_currency


@dataclass
class ScrapedProduct:
    """Структура данных спарсенного товара."""
    
    # Основная информация
    name: str
    description: str = ""
    price: Optional[float] = None
    currency: str = "RUB"
    
    # URLs и изображения
    url: str = ""
    images: List[str] = field(default_factory=list)
    
    # Категоризация
    category: str = ""
    brand: str = ""
    
    # Идентификаторы
    external_id: str = ""
    sku: str = ""
    barcode: str = ""
    
    # Наличие и характеристики
    is_available: bool = True
    stock_quantity: Optional[int] = None
    
    # Дополнительные атрибуты
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    # Метаданные
    source: str = ""
    scraped_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует объект в словарь."""
        return {
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'currency': self.currency,
            'url': self.url,
            'images': self.images,
            'category': self.category,
            'brand': self.brand,
            'external_id': self.external_id,
            'sku': self.sku,
            'barcode': self.barcode,
            'is_available': self.is_available,
            'stock_quantity': self.stock_quantity,
            'attributes': self.attributes,
            'source': self.source,
            'scraped_at': self.scraped_at,
        }


class BaseScraper(ABC):
    """Базовый абстрактный класс для всех парсеров."""
    
    def __init__(self, 
                 base_url: str,
                 delay_range: tuple = (1, 3),
                 timeout: int = 30,
                 max_retries: int = 3,
                 use_proxy: bool = False):
        """Инициализация парсера.
        
        Args:
            base_url: Базовый URL сайта
            delay_range: Диапазон задержек между запросами (мин, макс)
            timeout: Таймаут запросов в секундах
            max_retries: Максимальное количество повторных попыток
            use_proxy: Использовать ли прокси
        """
        self.base_url = base_url.rstrip('/')
        self.delay_range = delay_range
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_proxy = use_proxy
        
        # Настройка логгера
        self.logger = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")
        
        # Генерация User-Agent
        try:
            self.user_agent = UserAgent().random
        except:
            self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        # HTTP клиент
        self.client = None
        self._setup_client()
    
    def _setup_client(self):
        """Настройка HTTP клиента."""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        self.client = httpx.Client(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
        )
    
    def __enter__(self):
        """Контекстный менеджер - вход."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер - выход."""
        if self.client:
            self.client.close()
    
    def _make_request(self, url: str, **kwargs) -> Optional[str]:
        """Выполняет HTTP запрос с повторными попытками.
        
        Args:
            url: URL для запроса
            **kwargs: Дополнительные параметры для httpx
            
        Returns:
            HTML содержимое или None при ошибке
        """
        if not url.startswith(('http://', 'https://')):
            url = urljoin(self.base_url, url)
        
        for attempt in range(self.max_retries + 1):
            try:
                self.logger.info(f"Запрос к {url} (попытка {attempt + 1})")
                
                response = self.client.get(url, **kwargs)
                response.raise_for_status()
                
                # Задержка между запросами
                if attempt < self.max_retries:
                    delay = self.delay_range[0] + (self.delay_range[1] - self.delay_range[0]) * (attempt / self.max_retries)
                    time.sleep(delay)
                
                return response.text
                
            except httpx.HTTPStatusError as e:
                self.logger.warning(f"HTTP ошибка {e.response.status_code} для {url}")
                if e.response.status_code in [429, 503, 504]:  # Rate limiting, server errors
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                break
                
            except Exception as e:
                self.logger.error(f"Ошибка запроса к {url}: {e}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                break
        
        return None
    
    def _parse_page(self, html: str, url: str) -> DataSelector:
        """Создает селектор для парсинга страницы.
        
        Args:
            html: HTML содержимое
            url: URL страницы
            
        Returns:
            DataSelector для извлечения данных
        """
        return DataSelector(html, url)
    
    @abstractmethod
    def get_name(self) -> str:
        """Возвращает имя парсера."""
        pass
    
    @abstractmethod
    def get_supported_domains(self) -> List[str]:
        """Возвращает список поддерживаемых доменов."""
        pass
    
    @abstractmethod
    def parse_product_list(self, 
                          category_url: str, 
                          max_pages: int = 10) -> List[ScrapedProduct]:
        """Парсит список товаров из категории.
        
        Args:
            category_url: URL категории
            max_pages: Максимальное количество страниц
            
        Returns:
            Список спарсенных товаров
        """
        pass
    
    @abstractmethod
    def parse_product_detail(self, product_url: str) -> Optional[ScrapedProduct]:
        """Парсит детальную страницу товара.
        
        Args:
            product_url: URL товара
            
        Returns:
            Спарсенный товар или None
        """
        pass
    
    def parse_categories(self) -> List[Dict[str, Any]]:
        """Парсит список категорий сайта.
        
        Returns:
            Список категорий с метаданными
        """
        # Базовая реализация - может быть переопределена
        return []
    
    def parse_brands(self) -> List[Dict[str, Any]]:
        """Парсит список брендов сайта.
        
        Returns:
            Список брендов с метаданными
        """
        # Базовая реализация - может быть переопределена
        return []
    
    def search_products(self, query: str, max_results: int = 50) -> List[ScrapedProduct]:
        """Поиск товаров по запросу.
        
        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов
            
        Returns:
            Список найденных товаров
        """
        # Базовая реализация - может быть переопределена
        return []
    
    def validate_product(self, product: ScrapedProduct) -> bool:
        """Валидирует спарсенный товар.
        
        Args:
            product: Товар для валидации
            
        Returns:
            True если товар валиден
        """
        # Базовые проверки
        if not product.name or not product.name.strip():
            self.logger.warning("Товар без названия")
            return False
        
        if product.price is not None and product.price < 0:
            self.logger.warning(f"Отрицательная цена у товара {product.name}")
            return False
        
        return True
    
    def normalize_product_data(self, raw_data: Dict[str, Any]) -> ScrapedProduct:
        """Нормализует сырые данные товара.
        
        Args:
            raw_data: Сырые данные из парсера
            
        Returns:
            Нормализованный объект товара
        """
        from datetime import datetime
        
        return ScrapedProduct(
            name=clean_text(raw_data.get('name', '')),
            description=clean_text(raw_data.get('description', '')),
            price=normalize_price(raw_data.get('price', '')) if raw_data.get('price') else None,
            currency=extract_currency(raw_data.get('price', '')) if raw_data.get('price') else 'RUB',
            url=raw_data.get('url', ''),
            images=raw_data.get('images', []),
            category=clean_text(raw_data.get('category', '')),
            brand=clean_text(raw_data.get('brand', '')),
            external_id=raw_data.get('external_id', ''),
            sku=raw_data.get('sku', ''),
            barcode=raw_data.get('barcode', ''),
            is_available=raw_data.get('is_available', True),
            stock_quantity=raw_data.get('stock_quantity'),
            attributes=raw_data.get('attributes', {}),
            source=self.get_name(),
            scraped_at=datetime.now().isoformat(),
        )
