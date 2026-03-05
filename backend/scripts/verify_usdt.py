import os
import sys

# Добавляем путь к корню проекта, чтобы Django мог загрузить настройки
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from decimal import Decimal
from apps.catalog.services.currency_service import CurrencyRateService
from apps.catalog.utils.currency_converter import currency_converter
from apps.catalog.models import CurrencyRate

def verify_usdt_behavior():
    print("--- 1. Проверка загрузки и расчета кросс-курса USDT ---")
    
    # 1.1 Получаем активные курсы из базы
    usd_rate = CurrencyRate.objects.filter(from_currency='USD', to_currency='TRY', is_active=True).first()
    usdt_rate = CurrencyRate.objects.filter(from_currency='USDT', to_currency='TRY', is_active=True).first()
    usdt_rate_from_rub = CurrencyRate.objects.filter(from_currency='USDT', to_currency='RUB', is_active=True).first()
    
    if not (usd_rate and usdt_rate and usdt_rate_from_rub):
        print("Ошибка: Не найдены необходимые курсы в базе данных. Вы точно выполняли CurrencyRateService().update_rates()?")
        print("Текущие курсы в бд:", list(CurrencyRate.objects.filter(is_active=True).values_list('from_currency', 'to_currency')))
        return
        
    print(f"Курс USD -> TRY: {usd_rate.rate}")
    print(f"Курс USDT -> TRY: {usdt_rate.rate}")
    
    # Поскольку покупатель должен переплатить 3% в USDT, мы занизили курс USDT в базе.
    # Значит 1 USDT = USD / 1.03
    expected_usdt = (usd_rate.rate / Decimal('1.03')).quantize(Decimal('0.000001'))
    actual_usdt = usdt_rate.rate.quantize(Decimal('0.000001'))
    
    if expected_usdt == actual_usdt:
        print("✅ УСПЕХ: Курс USDT рассчитывается ровно как USD / 1.03 (что повысит цену товара)")
    else:
        print(f"❌ ОШИБКА: Ожидался курс {expected_usdt}, но в базе {actual_usdt}. Разница: {abs(expected_usdt - actual_usdt)}")
    
    print("\n--- 2. Проверка конвертации (CurrencyConverter) ---")
    
    amount = Decimal('100.00')
    from_currency = 'TRY'
    
    # 2.1 Конвертация в мульти-валюты
    print(f"Конвертируем {amount} {from_currency} во все поддерживаемые валюты:")
    results = currency_converter.convert_to_multiple_currencies(
        amount=amount,
        from_currency=from_currency,
        target_currencies=currency_converter.get_supported_currencies(),
        apply_margin=True
    )
    
    if 'USDT' in results and results['USDT']:
        usdt_pricing = results['USDT']
        print(f"✅ УСПЕХ: USDT присутствует в словаре конвертации:")
        print(f"   Базовая цена: {usdt_pricing['original_price']} TRY")
        print(f"   Конвертированная цена: {usdt_pricing['converted_price']} USDT")
        print(f"   Цена с маржой (по умолчанию 15%): {usdt_pricing['price_with_margin']} USDT")
        
        # Ручная проверка ожидаемой конвертированной цены
        # TRY -> USDT == TRY -> USD / 1.03
        rate_try_to_usdt = CurrencyRate.objects.get(from_currency='TRY', to_currency='USDT').rate
        expected_converted = (amount * rate_try_to_usdt).quantize(Decimal('0.01'))
        if expected_converted == usdt_pricing['converted_price']:
             print("✅ УСПЕХ: Математика конвертации точна.")
        else:
             print(f"❌ ПРЕДУПРЕЖДЕНИЕ: Ожидалось {expected_converted}, получили {usdt_pricing['converted_price']}")
             
    else:
        print("❌ ОШИБКА: Валюта USDT отсутствует в результатах конвертации!")

if __name__ == "__main__":
    verify_usdt_behavior()
    
