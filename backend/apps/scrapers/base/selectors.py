"""Система селекторов для извлечения данных из HTML."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from bs4 import BeautifulSoup, Tag
import re


@dataclass
class SelectorConfig:
    """Конфигурация селектора для извлечения данных."""
    
    # CSS селектор или XPath
    selector: str
    
    # Атрибут для извлечения (text, href, src, data-*, и т.д.)
    attribute: str = "text"
    
    # Регулярное выражение для обработки результата
    regex: Optional[str] = None
    
    # Индекс элемента (если найдено несколько)
    index: int = 0
    
    # Извлечь все элементы (игнорирует index)
    all_elements: bool = False
    
    # Обязательное поле (если не найдено - ошибка)
    required: bool = False
    
    # Значение по умолчанию
    default: Any = None
    
    # Дополнительные преобразования
    transformations: List[str] = field(default_factory=list)


class DataSelector:
    """Класс для извлечения данных из HTML с помощью селекторов."""
    
    def __init__(self, html: str, base_url: str = ""):
        """Инициализация селектора.
        
        Args:
            html: HTML код страницы
            base_url: Базовый URL для относительных ссылок
        """
        self.soup = BeautifulSoup(html, 'lxml')
        self.base_url = base_url
        
    def extract(self, config: SelectorConfig) -> Any:
        """Извлекает данные по конфигурации селектора.
        
        Args:
            config: Конфигурация селектора
            
        Returns:
            Извлеченные данные
        """
        try:
            # Находим элементы по селектору
            elements = self.soup.select(config.selector)
            
            if not elements:
                if config.required:
                    raise ValueError(f"Обязательный селектор не найден: {config.selector}")
                return config.default
            
            # Выбираем элементы
            if config.all_elements:
                selected_elements = elements
            else:
                if config.index >= len(elements):
                    return config.default
                selected_elements = [elements[config.index]]
            
            # Извлекаем данные
            results = []
            for element in selected_elements:
                value = self._extract_from_element(element, config.attribute)
                
                # Применяем регулярное выражение
                if config.regex and value:
                    match = re.search(config.regex, str(value))
                    value = match.group(1) if match else config.default
                
                # Применяем преобразования
                value = self._apply_transformations(value, config.transformations)
                
                results.append(value)
            
            # Возвращаем результат
            if config.all_elements:
                return results
            else:
                return results[0] if results else config.default
                
        except Exception as e:
            if config.required:
                raise ValueError(f"Ошибка извлечения данных по селектору {config.selector}: {e}")
            return config.default
    
    def _extract_from_element(self, element: Tag, attribute: str) -> Any:
        """Извлекает значение атрибута из элемента.
        
        Args:
            element: HTML элемент
            attribute: Имя атрибута
            
        Returns:
            Значение атрибута
        """
        if attribute == "text":
            return element.get_text(strip=True)
        elif attribute == "html":
            return str(element)
        elif attribute == "href":
            href = element.get('href', '')
            return self._normalize_url(href) if href else ''
        elif attribute == "src":
            src = element.get('src', '')
            return self._normalize_url(src) if src else ''
        else:
            return element.get(attribute, '')
    
    def _normalize_url(self, url: str) -> str:
        """Нормализует URL относительно базового."""
        if not url or url.startswith(('http://', 'https://', 'data:')):
            return url
        
        from urllib.parse import urljoin
        return urljoin(self.base_url, url)
    
    def _apply_transformations(self, value: Any, transformations: List[str]) -> Any:
        """Применяет преобразования к значению.
        
        Args:
            value: Исходное значение
            transformations: Список преобразований
            
        Returns:
            Преобразованное значение
        """
        if not value or not transformations:
            return value
            
        result = value
        
        for transformation in transformations:
            if transformation == "strip":
                result = str(result).strip()
            elif transformation == "upper":
                result = str(result).upper()
            elif transformation == "lower":
                result = str(result).lower()
            elif transformation == "title":
                result = str(result).title()
            elif transformation == "int":
                try:
                    result = int(float(str(result).replace(',', '.')))
                except:
                    result = 0
            elif transformation == "float":
                try:
                    result = float(str(result).replace(',', '.'))
                except:
                    result = 0.0
            elif transformation == "price":
                from .utils import normalize_price
                result = normalize_price(str(result))
            elif transformation == "currency":
                from .utils import extract_currency
                result = extract_currency(str(result))
            elif transformation == "clean":
                from .utils import clean_text
                result = clean_text(str(result))
        
        return result
    
    def extract_multiple(self, configs: Dict[str, SelectorConfig]) -> Dict[str, Any]:
        """Извлекает данные по нескольким конфигурациям.
        
        Args:
            configs: Словарь конфигураций {имя_поля: SelectorConfig}
            
        Returns:
            Словарь извлеченных данных
        """
        results = {}
        
        for field_name, config in configs.items():
            results[field_name] = self.extract(config)
            
        return results
    
    def extract_product_list(self, 
                           item_selector: str,
                           field_configs: Dict[str, SelectorConfig]) -> List[Dict[str, Any]]:
        """Извлекает список товаров со страницы.
        
        Args:
            item_selector: Селектор для элементов товаров
            field_configs: Конфигурации полей для каждого товара
            
        Returns:
            Список словарей с данными товаров
        """
        products = []
        
        # Находим все элементы товаров
        product_elements = self.soup.select(item_selector)
        
        for element in product_elements:
            # Создаем временный селектор для текущего элемента
            element_html = str(element)
            element_selector = DataSelector(element_html, self.base_url)
            
            # Извлекаем данные товара
            product_data = element_selector.extract_multiple(field_configs)
            products.append(product_data)
        
        return products
