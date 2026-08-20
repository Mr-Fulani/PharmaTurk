# Система ценообразования с конвертацией валют

> **Архивное описание.** Часть импортов, команд и состава сервисов ниже
> устарела. Сверяйте фактическую реализацию в `backend/apps/catalog` и не
> используйте этот файл как production runbook.

## Обзор

Полностью реализованная система для автоматической конвертации цен из турецких лир в рубли, тенге и другие валюты с настраиваемой маржой.

## ✅ Реализованные компоненты

### 1. Модели данных
- **CurrencyRate** - хранение курсов валют из разных источников
- **MarginSettings** - настройки маржи для пар валют
- **ProductPrice** - цены товаров в разных валютах
- **CurrencyUpdateLog** - логи обновления курсов

### 2. Сервисы
- **CurrencyRateService** - получение курсов из API (ЦБ РФ, Нацбанк КЗ, ЦБ Турции, OpenExchangeRates)
- **CurrencyConverter** - конвертация с учетом маржи
- **Базовые парсеры** с поддержкой валют

### 3. Интеграция
- Методы в модели Product для работы с ценами
- Обновленные сериализаторы с полями цен
- Management команды для обновления
- Админ-панель управления

### 4. Автоматизация
- Периодические задачи Celery
- Обновление курсов каждые 4 часа
- Ежедневное обновление цен товаров

## 🚀 Быстрый старт

### 1. Применение миграций
```bash
python manage.py migrate catalog
```

### 2. Настройка начальных курсов
```bash
# Обновить курсы из API
python manage.py shell
>>> from catalog.services.currency_service import CurrencyRateService
>>> service = CurrencyRateService()
>>> service.update_rates()
```

### 3. Настройка маржи
```bash
# Через админ-панель /admin/catalog/marginsettings/
# Или через shell
>>> from catalog.currency_models import MarginSettings
>>> MarginSettings.objects.create(
...     currency_pair='TRY-RUB',
...     margin_percentage=15.00,
...     description='Маржа для турецких товаров в рублях'
... )
```

### 4. Обновление цен товаров
```bash
# Обновить все цены
python manage.py update_product_prices --force-update-rates

# Обновить только медицинские товары
python manage.py update_product_prices --product-type medicines

# Предпросмотр изменений
python manage.py update_product_prices --dry-run
```

## 💻 API использование

### Получение цен товара
```python
from catalog.models import Product

product = Product.objects.first()

# Цена в конкретной валюте
price_rub = product.get_price_in_currency('RUB')
price_kzt = product.get_price_in_currency('KZT')

# Все цены
all_prices = product.get_all_prices()

# Текущая цена с учетом предпочтений
current_price, currency = product.get_current_price('RUB')
```

### Конвертация цен
```python
from catalog.utils.currency_converter import currency_converter

# Конвертация с маржой
original, converted, with_margin = currency_converter.convert_price(
    Decimal('100.50'), 'TRY', 'RUB', apply_margin=True
)

# Конвертация в несколько валют
results = currency_converter.convert_to_multiple_currencies(
    Decimal('100.50'), 'TRY', ['RUB', 'USD', 'KZT']
)
```

### Использование в парсерах
```python
from catalog.parsers.base_currency_parser import TurkishMedicineParser

parser = TurkishMedicineParser()

product_data = {
    'name': 'Аспирин',
    'price': '45.50 ₺',
    'old_price': '50.00 ₺',
    'brand': 'Bayer',
    'category': 'medicines'
}

parsed = parser.parse_product(product_data)
# Результат содержит конвертированные цены
```

## 🔧 Админ-панель

### Разделы
- **Курсы валют** (/admin/catalog/currencyrate/)
- **Настройки маржи** (/admin/catalog/marginsettings/)
- **Цены товаров** (/admin/catalog/productprice/)
- **Логи обновлений** (/admin/catalog/currencyupdatelog/)

### Возможности
- Цветовая индикация статусов
- Массовые операции
- Фильтрация и поиск
- История изменений

## 📊 API эндпоинты

### Product API
```json
{
  "id": 1,
  "name": "Аспирин",
  "price": "45.50",
  "currency": "TRY",
  "prices_in_currencies": {
    "RUB": {
      "original_price": "45.50",
      "converted_price": "159.25",
      "price_with_margin": "183.14"
    },
    "USD": {
      "original_price": "45.50", 
      "converted_price": "2.65",
      "price_with_margin": "3.05"
    }
  },
  "current_price": {
    "amount": "183.14",
    "currency": "RUB",
    "formatted": "183.14 RUB"
  }
}
```

### Заголовки для выбора валюты
```
X-Currency: KZT
# или параметр запроса
?currency=USD
```

## ⚙️ Настройки

### Источники курсов валют
1. **Центробанк РФ** - основной для RUB
2. **Нацбанк Казахстана** - для KZT
3. **Центробанк Турции** - для TRY
4. **OpenExchangeRates** - запасной

### Маржа по умолчанию
- Глобальная: 15%
- Индивидуальная для пар валют
- Настраивается через админ-панель

### Периодичность обновлений
- Курсы валют: каждые 4 часа
- Цены товаров: ежедневно в 2:00
- Очистка логов: еженедельно
- Резервное копирование: ежедневно

## 🔄 Автоматические задачи

### Celery задачи
- `currency.update_rates` - обновление курсов
- `currency.update_product_prices` - обновление цен
- `currency.cleanup_old_logs` - очистка логов
- `currency.health_check` - проверка здоровья
- `currency.backup_rates` - резервное копирование

### Запуск
```bash
# Worker
celery -A backend worker -l info -Q currency

# Beat scheduler
celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## 📈 Мониторинг

### Проверка здоровья
```python
from catalog.tasks import currency_system_health_check

health = currency_system_health_check()
# {
#   'active_rates': 12,
#   'products_without_prices': 0,
#   'products_without_converted': 5,
#   'status': 'healthy'
# }
```

### Логи обновлений
Все обновления курсов логируются в `CurrencyUpdateLog` с:
- Источником данных
- Временем выполнения
- Количеством обновленных курсов
- Ошибками при наличии

## 🔒 Безопасность

### Кэширование
- Курсы кэшируются на 4 часа
- Конвертированные цены кэшируются на 5 минут
- Redis для распределенного кэша

### Обработка ошибок
- Graceful fallback при недоступности API
- Логирование всех ошибок
- Сохранение последних успешных курсов

## 🚀 Производительность

### Оптимизации
- Batch обработка товаров
- Выборочная конвертация
- Асинхронные задачи
- Индексы в базе данных

### Рекомендации
- Обновлять цены пачками по 100-200 товаров
- Использовать отдельную очередь для валютных задач
- Настраивать приоритеты задач

## 🛠️ Расширение

### Добавление новой валюты
1. Добавить в `CURRENCY_CHOICES`
2. Обновить источники API
3. Перезапустить worker'ы

### Новый источник курсов
1. Добавить в `API_ENDPOINTS`
2. Реализовать парсер ответа
3. Добавить в `SOURCE_CHOICES`

### Кастомная логика маржи
```python
# Наследовать CurrencyConverter
class CustomCurrencyConverter(CurrencyConverter):
    def _get_margin_rate(self, from_currency, to_currency):
        # Кастомная логика
        return super()._get_margin_rate(from_currency, to_currency)
```

## 📝 Примеры использования

### Парсинг турецкого сайта
```python
from catalog.parsers.base_currency_parser import TurkishMedicineParser

parser = TurkishMedicineParser()

# Данные с турецкого сайта
raw_data = {
    'id': '12345',
    'name': 'İbuprofen 400mg',
    'price': '28,90 ₺',
    'old_price': '35,50 ₺',
    'brand': 'Bayer',
    'category': 'Ağrı Kesiciler',
    'in_stock': True,
    'images': ['https://example.com/image.jpg']
}

# Автоматическая конвертация цен
product_data = parser.parse_product(raw_data)

# Создание товара
product = Product.objects.create(**product_data)
```

### Массовое обновление
```python
from catalog.models import Product
from catalog.tasks import update_product_prices_batch

# Обновить все медицинские товары
update_product_prices_batch.delay(product_type='medicines')

# Обновить конкретный товар
product = Product.objects.get(id=123)
product.update_currency_prices(['RUB', 'KZT', 'USD'])
```

## 📋 Планируется

### USDT (Tether)
- **Статус:** Пока не внедрён. Курс USDT → RUB сейчас не обновляется (ЦБ РФ не предоставляет криптовалюты).
- **План:** Добавить USDT как отдельную валюту на сайте. Курс будет обновляться через **отдельное API** (биржевые данные, крипто-агрегаторы и т.п.).
- **При внедрении:** создать новый источник курсов в `CurrencyRateService`, добавить в расписание Celery.

Система полностью готова к использованию и масштабированию! 🎉
