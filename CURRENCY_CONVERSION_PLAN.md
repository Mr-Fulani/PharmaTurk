# План реализации системы ценообразования с конвертацией валют

## Обзор
Система для автоматической конвертации цен из турецких лир в рубли, тенге и другие валюты с настраиваемой маржой.

## Архитектура

### 1. Модели данных

#### CurrencyRate (курсы валют)
```python
class CurrencyRate(models.Model):
    from_currency = models.CharField(max_length=3)  # TRY, USD, EUR
    to_currency = models.CharField(max_length=3)    # RUB, KZT, USD
    rate = models.DecimalField(max_digits=10, decimal_places=4)
    updated_at = models.DateTimeField(auto_now=True)
    source = models.CharField(max_length=50)  # 'centralbank', 'openexchangerates'
```

#### MarginSettings (настройки маржи)
```python
class MarginSettings(models.Model):
    currency_pair = models.CharField(max_length=10)  # 'TRY-RUB', 'USD-RUB'
    margin_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_now_add=True)
```

#### ProductPrice (цены товаров)
```python
class ProductPrice(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3)  # TRY, RUB, KZT, USD
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    converted_price = models.DecimalField(max_digits=10, decimal_places=2)
    price_with_margin = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)
```

### 2. Сервис конвертации валют

#### CurrencyConverter
- Получение актуальных курсов из API
- Кэширование курсов
- Применение маржи
- Конвертация между любыми валютами

### 3. Интеграция с парсерами

#### Парсеры TurkishMedicine
- Автоматическая конвертация при парсинге
- Сохранение оригинальной цены в TRY
- Расчет цен в RUB, KZT, USD

### 4. API для фронтенда

#### Endpoints
- `/api/prices/convert/` - конвертация цены
- `/api/prices/rates/` - текущие курсы
- `/api/products/{id}/prices/` - цены товара во всех валютах

## Поддерживаемые валюты
- **Базовые:** TRY (турецкие лиры)
- **Целевые:** RUB (рубли), KZT (тенге), USD (доллары), EUR (евро)

## Источники курсов валют
1. Центральный банк РФ (для RUB)
2. Национальный банк Казахстана (для KZT)
3. Центральный банк Турции (для TRY)
4. OpenExchangeRates API (запасной вариант)

## Алгоритм конвертации

```
original_price (TRY) 
→ apply_exchange_rate(TRY → RUB) 
→ apply_margin(RUB) 
→ final_price (RUB)
```

## Настройка маржи
- Глобальная маржа по умолчанию: 15%
- Индивидуальная маржа для пар валют
- Настройка через админ-панель

## Обновление курсов
- Автоматическое обновление каждые 4 часа
- Принудительное обновление через админ-панель
- Логирование обновлений

## Приоритеты реализации

### Высокий приоритет
1. Модели данных
2. Базовый сервис конвертации
3. Интеграция с парсерами

### Средний приоритет
4. Обновление моделей товаров
5. API эндпоинты
6. Админ-панель

### Низкий приоритет
7. Периодическое обновление
8. Расширенные настройки маржи

## Технические требования
- Python 3.8+
- Django 4.0+
- Redis для кэширования
- Celery для фоновых задач
- Requests для API запросов
