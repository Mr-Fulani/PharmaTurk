import os
import sys

# Настройка Django окружения
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from decimal import Decimal
from apps.catalog.currency_models import MarginSettings, GlobalCurrencySettings
from apps.catalog.utils.currency_converter import currency_converter

print("\n--- Проверка логики маржи ---")

# 1. Устанавливаем глобальную маржу 15%
global_settings, _ = GlobalCurrencySettings.objects.get_or_create(id=1)
global_settings.default_margin_percentage = Decimal('15.00')
global_settings.save()
print(f"Глобальная маржа (fallback) установлена: {global_settings.default_margin_percentage}%")

# 2. Убираем индивидуальную маржу USD-USDT и тестируем fallback
MarginSettings.objects.filter(currency_pair='USD-USDT').delete()
currency_converter.clear_margin_cache()

print("\n[Тест 1: Fallback — индивидуальная маржа для USD-USDT не задана, ожидаем 15%]")
base_price, converted, with_margin = currency_converter.convert_price(
    Decimal('100.00'), 'USD', 'USDT', apply_margin=True
)
print(f"  Базовая цена:        {base_price} USD")
print(f"  Чистая конвертация:  {converted} USDT")
print(f"  С маржой:            {with_margin} USDT")
if converted > 0:
    pct = ((with_margin / converted) - 1) * 100
    status = "✅ УСПЕХ" if abs(pct - 15) < 0.5 else "❌ ОШИБКА"
    print(f"  Фактическая маржа:   {pct:.2f}%  {status}")

# 3. Задаём индивидуальную маржу 25% и тестируем приоритет
print("\n[Тест 2: Индивидуальная маржа 25% для пары USD-USDT]")
setting, _ = MarginSettings.objects.get_or_create(
    currency_pair='USD-USDT',
    defaults={'margin_percentage': Decimal('25.00'), 'is_active': True}
)
setting.margin_percentage = Decimal('25.00')
setting.is_active = True
setting.save()
currency_converter.clear_margin_cache()

base_price, converted, with_margin = currency_converter.convert_price(
    Decimal('100.00'), 'USD', 'USDT', apply_margin=True
)
print(f"  Базовая цена:        {base_price} USD")
print(f"  Чистая конвертация:  {converted} USDT")
print(f"  С маржой:            {with_margin} USDT")
if converted > 0:
    pct = ((with_margin / converted) - 1) * 100
    status = "✅ УСПЕХ" if abs(pct - 25) < 0.5 else "❌ ОШИБКА"
    print(f"  Фактическая маржа:   {pct:.2f}%  {status}")

# 4. Конвертация доставки — БЕЗ маржи (apply_margin=False)
print("\n[Тест 3: Доставка USD -> USDT без маржи]")
base_price, converted_ship, _ = currency_converter.convert_price(
    Decimal('100.00'), 'USD', 'USDT', apply_margin=False
)
print(f"  Стоимость в базе:    {base_price} USD")
print(f"  Цена доставки:       {converted_ship} USDT (маржа не применяется)")

# 5. Тест с отключённой индивидуальной маржой (is_active=False) -> должен снова быть fallback 15%
print("\n[Тест 4: Индивидуальная маржа отключена (is_active=False) -> снова fallback 15%]")
setting.is_active = False
setting.save()
currency_converter.clear_margin_cache()

base_price, converted, with_margin = currency_converter.convert_price(
    Decimal('100.00'), 'USD', 'USDT', apply_margin=True
)
if converted > 0:
    pct = ((with_margin / converted) - 1) * 100
    status = "✅ УСПЕХ" if abs(pct - 15) < 0.5 else "❌ ОШИБКА"
    print(f"  Фактическая маржа:   {pct:.2f}%  {status}")

# Очищаем тестовые данные
MarginSettings.objects.filter(currency_pair='USD-USDT').delete()
currency_converter.clear_margin_cache()

print("\n--- Тесты завершены ---")
