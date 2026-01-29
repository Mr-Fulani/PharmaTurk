"""Базовые классы для парсеров с поддержкой конвертации валют."""

from abc import ABC, abstractmethod
from decimal import Decimal
import logging
from typing import Dict, Optional, Any
from ..utils.currency_converter import currency_converter

logger = logging.getLogger(__name__)


class BaseCurrencyParser(ABC):
    """Базовый класс для парсеров с поддержкой конвертации валют."""
    
    def __init__(self, source_currency: str = 'TRY'):
        self.source_currency = source_currency
        self.target_currencies = ['RUB', 'USD', 'KZT', 'EUR']
    
    def parse_and_convert_price(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Парсит цену и конвертирует в разные валюты.
        
        Args:
            price_data: {
                'price': Decimal или str,
                'currency': str (опционально, defaults to source_currency),
                'old_price': Decimal или str (опционально)
            }
        
        Returns:
            Dict с конвертированными ценами
        """
        try:
            # Извлекаем базовую цену
            base_price = self._extract_price(price_data.get('price'))
            base_currency = price_data.get('currency', self.source_currency)
            old_price = self._extract_price(price_data.get('old_price'))
            
            if not base_price:
                return {}
            
            # Конвертируем базовую цену
            converted_prices = currency_converter.convert_to_multiple_currencies(
                base_price, base_currency, self.target_currencies, apply_margin=True
            )
            
            result = {
                'original_price': base_price,
                'original_currency': base_currency,
                'converted_prices': {}
            }
            
            # Добавляем конвертированные цены
            for currency, price_data in converted_prices.items():
                if price_data:
                    result['converted_prices'][currency] = {
                        'original_price': price_data['original_price'],
                        'converted_price': price_data['converted_price'],
                        'price_with_margin': price_data['price_with_margin']
                    }
            
            # Конвертируем старую цену если есть
            if old_price:
                old_converted = currency_converter.convert_to_multiple_currencies(
                    old_price, base_currency, self.target_currencies, apply_margin=True
                )
                result['old_original_price'] = old_price
                result['old_converted_prices'] = {}
                
                for currency, price_data in old_converted.items():
                    if price_data:
                        result['old_converted_prices'][currency] = {
                            'original_price': price_data['original_price'],
                            'converted_price': price_data['converted_price'],
                            'price_with_margin': price_data['price_with_margin']
                        }
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing and converting price: {str(e)}")
            return {}
    
    def _extract_price(self, price_value) -> Optional[Decimal]:
        """Извлекает цену из различных форматов."""
        if price_value is None:
            return None
        
        try:
            if isinstance(price_value, str):
                # Удаляем символы валют и пробелы
                cleaned = price_value.replace('₺', '').replace('$', '').replace('€', '').replace('₽', '').replace(' ', '')
                cleaned = cleaned.replace(',', '.')  # Заменяем запятые на точки
                return Decimal(cleaned)
            elif isinstance(price_value, (int, float)):
                return Decimal(str(price_value))
            elif isinstance(price_value, Decimal):
                return price_value
        except (ValueError, TypeError) as e:
            logger.error(f"Error extracting price from {price_value}: {str(e)}")
        
        return None
    
    def get_price_for_product_creation(self, price_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Подготавливает данные о ценах для создания товара.
        
        Returns:
            Dict с полями для модели Product
        """
        converted = self.parse_and_convert_price(price_data)
        
        if not converted:
            return {}
        
        result = {
            'price': converted['original_price'],
            'currency': converted['original_currency']
        }
        
        # Добавляем конвертированные цены
        rub_prices = converted['converted_prices'].get('RUB', {})
        if rub_prices:
            result.update({
                'converted_price_rub': rub_prices['converted_price'],
                'final_price_rub': rub_prices['price_with_margin']
            })
        
        usd_prices = converted['converted_prices'].get('USD', {})
        if usd_prices:
            result.update({
                'converted_price_usd': usd_prices['converted_price'],
                'final_price_usd': usd_prices['price_with_margin']
            })
        
        # Добавляем старую цену если есть
        if 'old_original_price' in converted:
            result['old_price'] = converted['old_original_price']
        
        return result
    
    @abstractmethod
    def parse_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Абстрактный метод для парсинга товара."""
        pass


class TurkishMedicineParser(BaseCurrencyParser):
    """Парсер для турецких медицинских товаров."""
    
    def __init__(self):
        super().__init__(source_currency='TRY')
    
    def parse_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Парсит данные товара с турецкого сайта."""
        try:
            # Базовые поля товара
            result = {
                'name': product_data.get('name', ''),
                'description': product_data.get('description', ''),
                'external_id': product_data.get('id'),
                'external_url': product_data.get('url'),
                'sku': product_data.get('sku'),
                'barcode': product_data.get('barcode'),
                'brand': product_data.get('brand'),
                'category': product_data.get('category'),
                'manufacturer': product_data.get('manufacturer'),
                'country_of_origin': product_data.get('country', 'TR'),
                'is_available': product_data.get('in_stock', True),
                'stock_quantity': product_data.get('stock'),
                'images': product_data.get('images', []),
                'attributes': product_data.get('attributes', {})
            }
            
            # Обрабатываем цены
            price_data = {
                'price': product_data.get('price'),
                'currency': 'TRY',  # Турецкие товары всегда в лирах
                'old_price': product_data.get('old_price')
            }
            
            price_result = self.get_price_for_product_creation(price_data)
            result.update(price_result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing Turkish medicine product: {str(e)}")
            return {}


class GeneralProductParser(BaseCurrencyParser):
    """Универсальный парсер для товаров из разных источников."""
    
    def __init__(self, source_currency: str = 'USD'):
        super().__init__(source_currency=source_currency)
    
    def parse_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """Универсальный парсинг товара."""
        try:
            result = {
                'name': product_data.get('name', ''),
                'description': product_data.get('description', ''),
                'external_id': product_data.get('id'),
                'external_url': product_data.get('url'),
                'sku': product_data.get('sku'),
                'brand': product_data.get('brand'),
                'category': product_data.get('category'),
                'is_available': product_data.get('in_stock', True),
                'stock_quantity': product_data.get('stock'),
                'images': product_data.get('images', []),
                'attributes': product_data.get('attributes', {})
            }
            
            # Определяем валюту из данных или используем базовую
            currency = product_data.get('currency', self.source_currency)
            
            price_data = {
                'price': product_data.get('price'),
                'currency': currency,
                'old_price': product_data.get('old_price')
            }
            
            price_result = self.get_price_for_product_creation(price_data)
            result.update(price_result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing general product: {str(e)}")
            return {}


# Фабрика парсеров
class ParserFactory:
    """Фабрика для создания парсеров."""
    
    @staticmethod
    def create_parser(parser_type: str, **kwargs) -> BaseCurrencyParser:
        """Создает парсер указанного типа."""
        parsers = {
            'turkish_medicine': TurkishMedicineParser,
            'general': GeneralProductParser,
        }
        
        if parser_type not in parsers:
            raise ValueError(f"Unknown parser type: {parser_type}")
        
        return parsers[parser_type](**kwargs)
