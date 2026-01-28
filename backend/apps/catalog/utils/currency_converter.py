from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Optional, Tuple
import logging
from ..currency_models import CurrencyRate, MarginSettings

logger = logging.getLogger(__name__)


class CurrencyConverter:
    """Утилита для конвертации валют с учетом маржи"""
    
    def __init__(self):
        self._margin_cache = {}
    
    def convert_price(
        self, 
        amount: Decimal, 
        from_currency: str, 
        to_currency: str,
        apply_margin: bool = True
    ) -> Tuple[Decimal, Decimal, Decimal]:
        """
        Конвертация цены с учетом маржи
        
        Returns:
            Tuple[original_price, converted_price, price_with_margin]
        """
        
        if from_currency == to_currency:
            # Если валюты одинаковые, применяем только маржу если нужно
            if apply_margin:
                margin_rate = self._get_margin_rate(from_currency, to_currency)
                price_with_margin = amount * (1 + margin_rate / 100)
                return amount, amount, price_with_margin
            return amount, amount, amount
        
        # Получаем курс конвертации
        try:
            rate_obj = CurrencyRate.objects.get(
                from_currency=from_currency, 
                to_currency=to_currency, 
                is_active=True
            )
            rate = rate_obj.rate
        except CurrencyRate.DoesNotExist:
            logger.error(f"No rate found for {from_currency} → {to_currency}")
            raise ValueError(f"Currency rate not available: {from_currency} → {to_currency}")
        
        # Конвертируем цену
        converted_price = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        if apply_margin:
            # Применяем маржу
            margin_rate = self._get_margin_rate(from_currency, to_currency)
            price_with_margin = converted_price * (1 + margin_rate / 100)
            price_with_margin = price_with_margin.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            price_with_margin = converted_price
        
        return amount, converted_price, price_with_margin
    
    def convert_to_multiple_currencies(
        self, 
        amount: Decimal, 
        from_currency: str, 
        target_currencies: list,
        apply_margin: bool = True
    ) -> Dict[str, Dict[str, Decimal]]:
        """
        Конвертация цены в несколько валют
        
        Returns:
            Dict[target_currency] = {
                'original_price': amount,
                'converted_price': converted_price,
                'price_with_margin': price_with_margin
            }
        """
        results = {}
        
        for target_currency in target_currencies:
            try:
                original, converted, with_margin = self.convert_price(
                    amount, from_currency, target_currency, apply_margin
                )
                
                results[target_currency] = {
                    'original_price': original,
                    'converted_price': converted,
                    'price_with_margin': with_margin
                }
                
            except Exception as e:
                logger.error(f"Error converting {from_currency} → {target_currency}: {str(e)}")
                results[target_currency] = None
        
        return results
    
    def get_price_breakdown(
        self, 
        amount: Decimal, 
        from_currency: str, 
        to_currency: str
    ) -> Dict[str, Decimal]:
        """
        Получение детализации цены
        
        Returns:
            {
                'original_amount': amount,
                'exchange_rate': rate,
                'converted_amount': converted_price,
                'margin_percentage': margin_rate,
                'margin_amount': margin_amount,
                'final_price': price_with_margin
            }
        """
        
        if from_currency == to_currency:
            margin_rate = self._get_margin_rate(from_currency, to_currency)
            margin_amount = amount * (margin_rate / 100)
            final_price = amount + margin_amount
            
            return {
                'original_amount': amount,
                'exchange_rate': Decimal('1'),
                'converted_amount': amount,
                'margin_percentage': margin_rate,
                'margin_amount': margin_amount.quantize(Decimal('0.01')),
                'final_price': final_price.quantize(Decimal('0.01'))
            }
        
        try:
            rate_obj = CurrencyRate.objects.get(
                from_currency=from_currency, 
                to_currency=to_currency, 
                is_active=True
            )
            rate = rate_obj.rate
        except CurrencyRate.DoesNotExist:
            raise ValueError(f"Currency rate not available: {from_currency} → {to_currency}")
        
        converted_price = (amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        margin_rate = self._get_margin_rate(from_currency, to_currency)
        margin_amount = converted_price * (margin_rate / 100)
        
        return {
            'original_price': amount,
            'converted_price': converted_price,
            'margin_rate': margin_rate,
            'margin_amount': margin_amount.quantize(Decimal('0.01')),
            'final_price': (converted_price + margin_amount).quantize(Decimal('0.01'))
        }
    
    def _get_margin_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """Получение процента маржи для пары валют"""
        cache_key = f"margin_{from_currency}_{to_currency}"
        
        if cache_key in self._margin_cache:
            return self._margin_cache[cache_key]
        
        # Ищем конкретную настройку для пары валют
        currency_pair = f"{from_currency}-{to_currency}"
        
        try:
            margin_setting = MarginSettings.objects.get(
                currency_pair=currency_pair,
                is_active=True
            )
            margin_rate = margin_setting.margin_percentage
        except MarginSettings.DoesNotExist:
            # Если конкретной настройки нет, используем глобальную маржу по умолчанию
            margin_rate = Decimal('15.00')  # 15% по умолчанию
            logger.info(f"Using default margin for {currency_pair}: {margin_rate}%")
        
        self._margin_cache[cache_key] = margin_rate
        return margin_rate
    
    def clear_margin_cache(self):
        """Очистка кэша маржи"""
        self._margin_cache.clear()
    
    def get_supported_currencies(self) -> list:
        """Получение списка поддерживаемых валют"""
        return ['TRY', 'RUB', 'KZT', 'USD', 'EUR']
    
    def validate_currency_pair(self, from_currency: str, to_currency: str) -> bool:
        """Проверка поддержки пары валют"""
        supported = self.get_supported_currencies()
        return from_currency in supported and to_currency in supported
    
    def estimate_price_range(
        self, 
        amount: Decimal, 
        from_currency: str, 
        to_currency: str,
        margin_variation: Decimal = Decimal('5')  # +/- 5%
    ) -> Dict[str, Decimal]:
        """
        Оценка диапазона цен при изменении маржи
        
        Returns:
            {
                'min_price': price_with_lower_margin,
                'base_price': price_with_current_margin,
                'max_price': price_with_higher_margin
            }
        """
        
        original, converted, _ = self.convert_price(
            amount, from_currency, to_currency, apply_margin=False
        )
        
        current_margin = self._get_margin_rate(from_currency, to_currency)
        
        base_price = converted * (1 + current_margin / 100)
        min_price = converted * (1 + (current_margin - margin_variation) / 100)
        max_price = converted * (1 + (current_margin + margin_variation) / 100)
        
        return {
            'min_price': min_price.quantize(Decimal('0.01')),
            'base_price': base_price.quantize(Decimal('0.01')),
            'max_price': max_price.quantize(Decimal('0.01'))
        }


# Глобальный экземпляр для использования в приложении
currency_converter = CurrencyConverter()
