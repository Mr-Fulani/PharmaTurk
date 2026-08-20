# 🚀 Чеклист развертывания системы ценообразования

> **Архивный документ. Не исполнять как checklist.** Он описывает устаревшие
> Python/Django/Celery зависимости и пути. Актуальные release gates находятся
> в [DEPLOY.md](DEPLOY.md) и [docs/ROADMAP.md](docs/ROADMAP.md).

## ✅ Предварительные требования

### Системные зависимости
- [ ] Python 3.8+
- [ ] Redis сервер
- [ ] PostgreSQL (рекомендуется)
- [ ] Celery worker + beat

### Python пакеты
- [ ] Django 4.0+
- [ ] celery
- [ ] redis
- [ ] django-celery-beat
- [ ] requests
- [ ] decimal (встроенный)

## 🗂️ Файлы системы

### Модели и миграции
- [ ] `backend/apps/catalog/currency_models.py` - модели валют
- [ ] `backend/apps/catalog/migrations/0070_currency_models.py` - миграция
- [ ] Интеграция в `backend/apps/catalog/models.py`

### Сервисы и утилиты
- [ ] `backend/apps/catalog/services/currency_service.py` - сервис курсов
- [ ] `backend/apps/catalog/utils/currency_converter.py` - конвертер
- [ ] `backend/apps/catalog/parsers/base_currency_parser.py` - парсеры

### Админ-панель
- [ ] `backend/apps/catalog/admin_currency.py` - админка валют

### Сериализаторы
- [ ] Обновлен `backend/apps/catalog/serializers.py` с полями цен

### Management команды
- [ ] `backend/apps/catalog/management/commands/update_product_prices.py`

### Задачи Celery
- [ ] Обновлен `backend/apps/catalog/tasks.py`
- [ ] `backend/celery_beat_schedule.py` - расписание

### Документация
- [ ] `CURRENCY_CONVERSION_PLAN.md` - план архитектуры
- [ ] `CURRENCY_SYSTEM_GUIDE.md` - руководство пользователя
- [ ] `CURRENCY_DEPLOYMENT_GUIDE.md` - инструкция деплоя

## 🔧 Конфигурация

### Django settings
```python
# Проверить наличие в settings.py
INSTALLED_APPS = [
    ...
    'django_celery_beat',
    'django_celery_results',
]

# Celery конфигурация
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'Europe/Moscow'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

### URL конфигурация
```python
# Проверить наличие в urls.py
urlpatterns = [
    ...
    path('admin/', admin.site.urls),
]
```

## 🗄️ База данных

### Миграции
- [ ] Применены миграции Django: `python manage.py migrate`
- [ ] Применены миграции Celery: `python manage.py migrate django_celery_beat`

### Начальные данные
- [ ] Созданы настройки маржи по умолчанию
- [ ] Обновлены курсы валют из API
- [ ] Обновлены цены существующих товаров

## 🚀 Запуск и проверка

### Сервисы
- [ ] Redis сервер запущен: `redis-server`
- [ ] Django сервер запущен: `python manage.py runserver`
- [ ] Celery worker запущен: `celery -A backend worker -l info -Q currency`
- [ ] Celery beat запущен: `celery -A backend beat -l info`

### Тестирование функциональности

#### 1. Курсы валют
```python
# shell
from catalog.services.currency_service import CurrencyRateService
service = CurrencyRateService()
success, message = service.update_rates()
# Ожидаемый результат: success=True
```

#### 2. Конвертация цен
```python
# shell
from catalog.utils.currency_converter import currency_converter
from decimal import Decimal
original, converted, with_margin = currency_converter.convert_price(
    Decimal('100'), 'TRY', 'RUB', apply_margin=True
)
# Ожидаемый результат: converted > 0, with_margin > converted
```

#### 3. API товаров
```bash
# curl
curl -H "X-Currency: KZT" http://localhost:8000/api/catalog/products/1/
# Ожидаемый результат: JSON с полями current_price, prices_in_currencies
```

#### 4. Админ-панель
- [ ] Доступ по URL: `/admin/`
- [ ] Раздел "Курсы валют" показывает данные
- [ ] Раздел "Настройки маржи" доступен
- [ ] Раздел "Цены товаров" работает
- [ ] Раздел "Логи обновлений" показывает историю

#### 5. Периодические задачи
```python
# shell
from catalog.tasks import update_currency_rates
result = update_currency_rates.delay()
# Ожидаемый результат: {'status': 'success', 'message': '...'}
```

## 📊 Мониторинг

### Логи
- [ ] Логи Django работают: `tail -f django.log`
- [ ] Логи Celery работают: `tail -f celery.log`
- [ ] Лги обновления курсов в базе данных

### Метрики
- [ ] Время конвертации цены < 10ms
- [ ] Время обновления курсов < 30 сек
- [ ] API ответ < 100ms
- [ ] Память worker'а < 200MB

### Алерты
- [ ] Настроены алерты для недоступности API курсов
- [ ] Настроены алерты для долгого выполнения задач
- [ ] Настроены алерты для отсутствия активных курсов

## 🔒 Безопасность

### Доступы
- [ ] Админ-панель защищена паролем
- [ ] Redis сервер защищен (если в проде)
- [ ] API эндпоинты защищены (если нужно)

### Валидация
- [ ] Цены валидируются на положительные значения
- [ ] Курсы валидируются на > 0
- [ ] Маржа валидируется 0-100%

## 🚀 Продакшен готовность

### Производительность
- [ ] Настроены индексы в базе данных
- [ ] Настроено кэширование Redis
- [ ] Оптимизированы запросы к базе
- [ ] Настроены очереди Celery

### Отказоустойчивость
- [ ] Graceful fallback при недоступности API
- [ ] Retry механизмы для сетевых запросов
- [ ] Логирование ошибок
- [ ] Резервные копирование данных

### Масштабирование
- [ ] Горизонтальное масштабирование worker'ов
- [ ] Балансировка нагрузки
- [ ] Разделение очередей по приоритетам

## 📝 Документация

### Техническая документация
- [ ] API документация обновлена
- [ ] Схемы баз данных задокументированы
- [ ] Архитектурные решения описаны

### Пользовательская документация
- [ ] Инструкция для администратора
- [ ] Гайд для разработчиков
- [ ] FAQ и troubleshooting

## 🎯 Финальная проверка

### Smoke tests
```bash
# 1. Проверка миграций
python manage.py showmigrations catalog
# Ожидаемый результат: все миграции применены

# 2. Проверка админки
python manage.py check
# Ожидаемый результат: no errors

# 3. Проверка Celery
celery -A backend inspect ping
# Ожидаемый результат: pong от worker'ов

# 4. Проверка Redis
redis-cli ping
# Ожидаемый результат: PONG
```

### Функциональные тесты
- [ ] Создание товара с ценой в TRY
- [ ] Автоматическая конвертация в RUB/KZT/USD
- [ ] Применение маржи
- [ ] Отображение в API
- [ ] Обновление через админ-панель

## 🚀 Go/No-Go Checklist

### Go условия ✅
- Все миграции применены
- Курсы валют обновляются автоматически
- Конвертация цен работает корректно
- Админ-панель функциональна
- API возвращает правильные данные
- Периодические задачи выполняются
- Логи работают
- Документация completa

### No-Go условия ❌
- Ошибки в миграциях
- Курсы не обновляются
- Конвертация неверная
- Админ-панель недоступна
- API возвращает ошибки
- Задачи Celery не выполняются
- Критические ошибки в логах

---

## 🎉 Готовность к продакшен!

Если все пункты отмечены галочками ✅, система ценообразования готова к использованию в продакшен среде!

### Следующие шаги:
1. Деплой на продакшен сервер
2. Настройка мониторинга
3. Обучение команды
4. Запуск в работу

**Система полностью готова!** 🚀🇹🇷→🇷🇺🇰🇿
