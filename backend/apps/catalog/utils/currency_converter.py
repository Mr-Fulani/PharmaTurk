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


    def update_or_create_variant_price(self, variant_instance, base_price: Decimal, base_currency: str):
        """
        Обновить или создать цену для варианта товара
        
        Args:
            variant_instance: Экземпляр варианта (ClothingVariant, ShoeVariant и т.д.)
            base_price: Базовая цена варианта
            base_currency: Валюта базовой цены
        """
        from ..currency_models import ProductVariantPrice
        from django.contrib.contenttypes.models import ContentType
        
        try:
            # Получаем ContentType для модели варианта
            content_type = ContentType.objects.get_for_model(variant_instance)
            
            # Конвертируем в основные валюты
            results = self.convert_to_multiple_currencies(
                base_price, base_currency, ['RUB', 'USD', 'KZT', 'EUR', 'TRY'], apply_margin=True
            )
            
            # Создаем или обновляем запись
            price_obj, created = ProductVariantPrice.objects.update_or_create(
                content_type=content_type,
                object_id=variant_instance.id,
                defaults={
                    'base_currency': base_currency,
                    'base_price': base_price,
                    'rub_price': results['RUB']['converted_price'] if results['RUB'] else None,
                    'rub_price_with_margin': results['RUB']['price_with_margin'] if results['RUB'] else None,
                    'usd_price': results['USD']['converted_price'] if results['USD'] else None,
                    'usd_price_with_margin': results['USD']['price_with_margin'] if results['USD'] else None,
                    'kzt_price': results['KZT']['converted_price'] if results['KZT'] else None,
                    'kzt_price_with_margin': results['KZT']['price_with_margin'] if results['KZT'] else None,
                    'eur_price': results['EUR']['converted_price'] if results['EUR'] else None,
                    'eur_price_with_margin': results['EUR']['price_with_margin'] if results['EUR'] else None,
                    'try_price': results['TRY']['converted_price'] if results['TRY'] else None,
                    'try_price_with_margin': results['TRY']['price_with_margin'] if results['TRY'] else None,
                }
            )
            
            return price_obj, created
            
        except Exception as e:
            logger.error(f"Error updating variant price for {variant_instance}: {str(e)}")
            return None, False

    def update_variant_shipping_costs(self, variant_instance, air_cost=None, sea_cost=None, ground_cost=None):
        """
        Обновить стоимость доставки для варианта
        
        Args:
            variant_instance: Экземпляр варианта
            air_cost: Стоимость авиа доставки
            sea_cost: Стоимость морской доставки  
            ground_cost: Стоимость наземной доставки
        """
        from ..currency_models import ProductVariantPrice
        from django.contrib.contenttypes.models import ContentType
        
        try:
            content_type = ContentType.objects.get_for_model(variant_instance)
            
            price_obj, created = ProductVariantPrice.objects.update_or_create(
                content_type=content_type,
                object_id=variant_instance.id,
                defaults={
                    'air_shipping_cost': air_cost,
                    'sea_shipping_cost': sea_cost,
                    'ground_shipping_cost': ground_cost,
                }
            )
            
            return price_obj, created
            
        except Exception as e:
            logger.error(f"Error updating variant shipping costs for {variant_instance}: {str(e)}")
            return None, False

    def backfill_variant_prices(self):
        from apps.catalog.models import ClothingVariant, ShoeVariant, JewelryVariant, FurnitureVariant, BookVariant

        created_count = 0
        updated_count = 0
        skipped_count = 0
        models = [ClothingVariant, ShoeVariant, JewelryVariant, FurnitureVariant, BookVariant]

        for model in models:
            for variant in model.objects.all().iterator():
                price = getattr(variant, "price", None)
                if price is None or price <= 0:
                    skipped_count += 1
                    continue
                price_obj, created = self.update_or_create_variant_price(
                    variant_instance=variant,
                    base_price=price,
                    base_currency=getattr(variant, "currency", None) or "TRY",
                )
                if not price_obj:
                    skipped_count += 1
                    continue
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        return {
            "created": created_count,
            "updated": updated_count,
            "skipped": skipped_count,
        }


# Глобальный экземпляр для использования в приложении
currency_converter = CurrencyConverter()
