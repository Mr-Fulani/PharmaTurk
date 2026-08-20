# Деплой системы ценообразования

> **Архивный документ.** Команды и зависимости ниже относятся к прежнему
> стеку и не являются исполняемым production runbook. Для текущего окружения
> используйте [DEPLOY.md](DEPLOY.md), [README-DEV.md](README-DEV.md) и
> [CELERY_TASKS.md](CELERY_TASKS.md); валютный workflow нужно перепроверить по
> коду перед выполнением любых операций с данными.

## 🚀 Инструкция по развертыванию

### 1. Применение миграций
```bash
cd backend
python manage.py migrate catalog
```

### 2. Создание суперпользователя для админ-панели
```bash
python manage.py createsuperuser
```

### 3. Первоначальная настройка

#### 3.1 Обновление курсов валют
```bash
python manage.py shell
```
```python
from catalog.services.currency_service import CurrencyRateService
service = CurrencyRateService()
success, message = service.update_rates()
print(f"Обновление курсов: {success}, {message}")
```

#### 3.2 Настройка маржи
```python
from catalog.currency_models import MarginSettings
from decimal import Decimal

# Основные пары валют
margin_settings = [
    ('TRY-RUB', Decimal('15.00'), 'Маржа для турецких товаров в рублях'),
    ('TRY-KZT', Decimal('12.00'), 'Маржа для турецких товаров в тенге'),
    ('TRY-USD', Decimal('20.00'), 'Маржа для турецких товаров в долларах'),
    ('USD-RUB', Decimal('10.00'), 'Маржа для долларов в рублях'),
    ('EUR-RUB', Decimal('12.00'), 'Маржа для евро в рублях'),
]

for pair, margin, desc in margin_settings:
    MarginSettings.objects.get_or_create(
        currency_pair=pair,
        defaults={
            'margin_percentage': margin,
            'description': desc,
            'is_active': True
        }
    )
print("Настройки маржи созданы")
```

#### 3.3 Обновление цен существующих товаров
```bash
python manage.py update_product_prices --force-update-rates --batch-size 50
```

### 4. Настройка Celery

#### 4.1 Установка зависимостей
```bash
pip install celery redis django-celery-beat
```

#### 4.2 Настройка Redis
```bash
# Запуск Redis
redis-server
```

#### 4.3 Настройка Celery в settings.py
```python
# Добавить в settings.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Moscow'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

#### 4.4 Применение миграций Celery
```bash
python manage.py migrate django_celery_beat
python manage.py migrate django_celery_results
```

#### 4.5 Запуск воркеров
```bash
# Worker для валютных задач
celery -A backend worker -l info -Q currency -n currency@%h

# Beat scheduler
celery -A backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### 5. Проверка работы системы

#### 5.1 Проверка курсов валют
```python
from catalog.currency_models import CurrencyRate
rates = CurrencyRate.objects.filter(is_active=True)
print(f"Активных курсов: {rates.count()}")
for rate in rates[:5]:
    print(f"{rate.from_currency} → {rate.to_currency}: {rate.rate}")
```

#### 5.2 Проверка конвертации
```python
from catalog.utils.currency_converter import currency_converter
from decimal import Decimal

# Тестовая конвертация
original, converted, with_margin = currency_converter.convert_price(
    Decimal('100'), 'TRY', 'RUB', apply_margin=True
)
print(f"100 TRY → {converted} RUB → {with_margin} RUB (с маржой)")
```

#### 5.3 Проверка API
```bash
# Запуск сервера
python manage.py runserver

# Проверка API товара
curl -H "X-Currency: KZT" http://localhost:8000/api/catalog/products/1/
```

### 6. Админ-панель

#### Доступ
- URL: `http://localhost:8000/admin/`
- Разделы:
  - Курсы валют (`/admin/catalog/currencyrate/`)
  - Настройки маржи (`/admin/catalog/marginsettings/`)
  - Цены товаров (`/admin/catalog/productprice/`)
  - Логи обновлений (`/admin/catalog/currencyupdatelog/`)

#### Возможности
- ✅ Цветовая индикация статусов
- ✅ Массовые операции
- ✅ Фильтрация и поиск
- ✅ История изменений

### 7. Мониторинг

#### 7.1 Проверка здоровья системы
```python
from catalog.tasks import currency_system_health_check
health = currency_system_health_check()
print(health)
```

#### 7.2 Логи
```bash
# Просмотр логов Celery
tail -f celery.log

# Просмотр логов Django
tail -f django.log
```

### 8. Продакшен настройка

#### 8.1 Environment variables
```bash
export CELERY_BROKER_URL=redis://your-redis-host:6379/0
export DJANGO_SETTINGS_MODULE=backend.settings.production
```

#### 8.2 Systemd сервисы
```ini
# /etc/systemd/system/celery-worker.service
[Unit]
Description=Celery Worker
After=network.target

[Service]
Type=forking
User=www-data
Group=www-data
EnvironmentFile=/etc/default/celery
WorkingDirectory=/path/to/your/project
ExecStart=/bin/sh -c '${CELERY_BIN} -A ${CELERY_APP} worker \
    --loglevel=${CELERYD_LOG_LEVEL} \
    --queues=${CELERYD_QUEUES}'
Restart=always

[Install]
WantedBy=multi-user.target
```

#### 8.3 Nginx конфигурация
```nginx
location /admin/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 9. Тестирование

#### 9.1 Unit тесты
```bash
python manage.py test catalog.tests.test_currency
```

#### 9.2 Load тестирование
```bash
python manage.py shell
from catalog.utils.currency_converter import currency_converter
import time

start = time.time()
for i in range(1000):
    currency_converter.convert_price(Decimal('100'), 'TRY', 'RUB')
print(f"1000 конвертаций за {time.time() - start:.2f} сек")
```

### 10. Обслуживание

#### 10.1 Резервное копирование
```bash
# Курсы валют
python -c "
from catalog.tasks import backup_currency_rates
backup_currency_rates()
"

# База данных
pg_dump dbname > backup.sql
```

#### 10.2 Очистка
```bash
# Старые логи (старше 30 дней)
python manage.py shell -c "
from catalog.tasks import cleanup_old_currency_logs
cleanup_old_currency_logs.delay()
"
```

## 🔧 Troubleshooting

### Проблема: Курсы не обновляются
**Решение:**
```python
# Проверить доступность API
import requests
response = requests.get('https://www.cbr-xml-daily.ru/daily_json.js')
print(response.status_code)

# Проверить логи
from catalog.currency_models import CurrencyUpdateLog
logs = CurrencyUpdateLog.objects.filter(success=False).order_by('-created_at')[:5]
for log in logs:
    print(f"{log.source}: {log.error_message}")
```

### Проблема: Цены не конвертируются
**Решение:**
```python
# Проверить наличие курсов
from catalog.currency_models import CurrencyRate
rate = CurrencyRate.objects.filter(from_currency='TRY', to_currency='RUB', is_active=True).first()
if not rate:
    print("Нет курса TRY-RUB")
else:
    print(f"Курс: {rate.rate}")

# Проверить настройки маржи
from catalog.currency_models import MarginSettings
margin = MarginSettings.objects.filter(currency_pair='TRY-RUB', is_active=True).first()
if not margin:
    print("Нет настройки маржи TRY-RUB")
else:
    print(f"Маржа: {margin.margin_percentage}%")
```

### Проблема: Celery задачи не выполняются
**Решение:**
```bash
# Проверить статус воркеров
celery -A backend inspect active

# Проверить очереди
celery -A backend inspect reserved

# Перезапустить воркеры
sudo systemctl restart celery-worker
```

## 📊 Метрики производительности

### Ожидаемые показатели
- **Конвертация цены**: < 10ms
- **Обновление курсов**: < 30 сек
- **Обновление 1000 цен**: < 2 мин
- **API ответ**: < 100ms

### Мониторинг
```python
# Добавить в middleware
import time
class CurrencyTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration = time.time() - start
        if duration > 0.1:  # > 100ms
            logger.warning(f"Slow request: {request.path} took {duration:.3f}s")
        return response
```

Система готова к продакшен использованию! 🚀
