# Turk-Export - MVP интернет-магазина

Мультикатегорийная онлайн-платформа для поиска, заказа и оплаты турецких медикаментов, БАДов, одежды и обуви с автоматическим обновлением данных.

## 🚀 Быстрый старт

### Предварительные требования

- Docker и Docker Compose
- Python 3.12+ (для локальной разработки)
- Poetry (для управления зависимостями)

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd PharmaTurk
```

## Новые функции: Поиск по фото (Визуальный поиск)
Добавлен полноценный функционал поиска товаров по фото:
- Загрузка изображений пользователем напрямую с устройства.
- Поиск по URL изображений.
- Автоматическая валидация размера (до 5 МБ) и формата файлов.
- Встроенная безопасность от спама (rate-limiting 10 запросов/минуту).
- Фоновая очистка временных файлов загрузок каждый час через Celery, чтобы сервер не переполнялся.
- Векторный поиск по загруженному фото с использованием моделей CLIP и БД Qdrant для обеспечения выдачи похожих визуально товаров.

## Основные компоненты системы

### 2. Настройка переменных окружения

Скопируйте пример файла с переменными окружения:

```bash
cp env.example .env
```

Отредактируйте файл `.env` и установите необходимые значения:

```bash
# Обязательные настройки
VAPI_API_KEY=your-vapi-api-key-here

# Опциональные настройки
DJANGO_SECRET_KEY=your-super-secret-key-change-in-production-12345
```

### 3. Запуск проекта

```bash
# Сборка и запуск всех сервисов
docker compose up -d --build

# Проверка статуса
docker compose ps

# Просмотр логов
docker compose logs -f backend
```

### 4. Проверка работоспособности

```bash
# Проверка health check
curl http://localhost:8000/api/health/

# Swagger документация
open http://localhost:8000/api/docs/
```

### 5. Мобильное приложение (Flutter)

См. [docs/MOBILE_INTEGRATION.md](docs/MOBILE_INTEGRATION.md) для настройки и запуска.

## 📋 Структура проекта

```
PharmaTurk/
├── backend/                 # Django backend
│   ├── apps/
│   │   ├── catalog/        # Каталог товаров
│   │   ├── orders/         # Заказы и корзина
│   │   ├── payments/       # Платежные провайдеры
│   │   ├── users/          # Пользователи
│   │   └── vapi/           # Интеграция с Vapi API
│   ├── config/             # Настройки Django
│   └── api/                # Основные API эндпоинты
├── frontend/               # Next.js веб-приложение
├── mobile/                 # Flutter мобильное приложение (iOS/Android)
├── docs/                   # Документация
│   └── MOBILE_INTEGRATION.md
├── docker-compose.yml      # Конфигурация Docker
├── env.example             # Пример переменных окружения
└── README.md               # Документация
```

## 🔧 Технологический стек

### Backend
- **Django 4.2+** - основной фреймворк
- **Django REST Framework** - API
- **PostgreSQL 15+** - основная база данных
- **Redis** - кэширование и очереди
- **Celery** - фоновые задачи
- **OpenSearch** - полнотекстовый поиск

### Интеграции
- **Vapi API (vapi.co)** - каталог лекарств и БАДов
- **ЮKassa/CloudPayments** - платежные провайдеры
- **СДЭК/Почта РФ/DPD** - доставка

### Мониторинг
- **Prometheus + Grafana** - метрики
- **Sentry** - отслеживание ошибок
- **ELK Stack** - логирование

## 📊 API Endpoints

### Каталог товаров
```
GET  /api/catalog/products/           # Список товаров
GET  /api/catalog/products/{slug}/    # Детали товара
GET  /api/catalog/products/search/    # Поиск товаров
GET  /api/catalog/categories/         # Категории
GET  /api/catalog/brands/             # Бренды
```

### Vapi интеграция
```
POST /api/vapi/pull/                  # Загрузка товаров
POST /api/vapi/search/                # Поиск в Vapi
POST /api/vapi/sync-categories/       # Синхронизация справочников
POST /api/vapi/full-sync/             # Полная синхронизация
```

### Платежи (заглушки)
```
POST /api/payments/init/              # Инициализация платежа
```

## 🔑 Настройка Vapi API

### 1. Регистрация на vapi.co

1. Перейдите на [vapi.co](https://vapi.co)
2. Зарегистрируйтесь и выберите тариф
3. Получите API ключ

### 2. Настройка переменных

```bash
# В файле .env
VAPI_BASE_URL=https://api.vapi.co
VAPI_API_KEY=your-actual-api-key-here
```

### 3. Тестирование интеграции

```bash
# Загрузка тестовых данных
curl -X POST 'http://localhost:8000/api/vapi/pull/?page=1&page_size=5'

# Поиск лекарств
curl -X POST 'http://localhost:8000/api/vapi/search/?query=парацетамол&limit=10'
```

## 📈 Мониторинг и логи

### Просмотр логов

```bash
# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f backend
docker compose logs -f celeryworker
```

### Метрики

```bash
# Prometheus метрики
curl http://localhost:8000/metrics/

# Grafana (если настроена)
open http://localhost:3000
```

## 🛠 Разработка

### Локальная разработка

```bash
# Установка зависимостей
cd backend
poetry install

# Применение миграций
poetry run python manage.py migrate

# Запуск сервера разработки
poetry run python manage.py runserver
```

### Создание миграций

```bash
docker compose exec backend poetry run python manage.py makemigrations
docker compose exec backend poetry run python manage.py migrate
```

### Создание суперпользователя

```bash
docker compose exec backend poetry run python manage.py createsuperuser
```

### Восстановление каталога (seed)

Команда `seed_catalog_data` создаёт полную структуру каталога: 18 корневых категорий (медицина, БАДы, медтехника, одежда, обувь, электроника, мебель, посуда, аксессуары, украшения, нижнее бельё, головные уборы, парфюмерия, книги, услуги, спорттовары, автозапчасти, исламская одежда, благовония), подкатегории с иерархией L2–L5, типы динамических атрибутов и бренды. **При первом запуске backend seed выполняется автоматически** (см. `docker-entrypoint.sh`).

```bash
# Полное восстановление (категории + атрибуты + бренды)
docker compose run --rm backend poetry run python manage.py seed_catalog_data

# Только категории (без брендов)
docker compose run --rm backend poetry run python manage.py seed_catalog_data --categories-only

# Только бренды
docker compose run --rm backend poetry run python manage.py seed_catalog_data --brands-only

# Только типы динамических атрибутов (GlobalAttributeKey)
docker compose run --rm backend poetry run python manage.py seed_catalog_data --attributes-only

# Исправить parent у подкатегорий (после миграций)
docker compose run --rm backend poetry run python manage.py seed_catalog_data --fix-hierarchy
```

### Статические страницы (privacy, delivery, returns)

Команда `load_initial_pages` создаёт страницы «Политика конфиденциальности», «Доставка и оплата», «Возврат товара» с контентом на ru/en. **Создаёт только отсутствующие страницы, не перезаписывает существующий контент.** Выполняется автоматически при старте backend (см. `docker-entrypoint.sh`).

```bash
# Ручной запуск (если нужно)
docker compose exec backend poetry run python manage.py load_initial_pages
```

Если backend уже запущен:

```bash
docker compose exec backend poetry run python manage.py seed_catalog_data --categories-only
```

## 🔒 Безопасность

### Продакшен настройки

1. Измените `DJANGO_SECRET_KEY` на уникальный
2. Установите `DJANGO_DEBUG=0`
3. Настройте `DJANGO_ALLOWED_HOSTS`
4. Добавьте SSL сертификаты
5. Настройте Sentry для мониторинга ошибок

### Переменные окружения

```bash
# Обязательные для продакшена
DJANGO_SECRET_KEY=your-production-secret-key
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-domain.com

# Мониторинг
SENTRY_DSN=your-sentry-dsn

# Платежи
YUKASSA_SHOP_ID=your-shop-id
YUKASSA_SECRET_KEY=your-secret-key
```

## � Instagram Parser

Парсер для автоматического сбора товаров из Instagram постов с медиа и описаниями.

### Быстрый старт

```bash
# Инициализация парсера
cd backend
poetry run python manage.py init_instagram_scraper

# Тестовый запуск
poetry run python manage.py run_instagram_scraper \
  --username bookstore_example \
  --max-posts 5 \
  --dry-run

# Реальный запуск
poetry run python manage.py run_instagram_scraper \
  --username bookstore_example \
  --max-posts 30 \
  --category books
```

### Возможности

- ✅ Парсинг постов из профилей Instagram
- ✅ Парсинг по хештегам
- ✅ Извлечение медиа (изображения/видео)
- ✅ Автоматическое создание товаров в каталоге
- ✅ Поддержка аутентификации

### Документация

- 📖 Полное руководство: [`INSTAGRAM_PARSER_GUIDE.md`](INSTAGRAM_PARSER_GUIDE.md)
- 🚀 Быстрый старт: [`backend/INSTAGRAM_PARSER_QUICKSTART.md`](backend/INSTAGRAM_PARSER_QUICKSTART.md)

**Важно**: Цены устанавливаются вручную через Django Admin после парсинга.

## �📝 Лицензия

Проект разработан для Turk-Export. Все права защищены.

## 🤝 Поддержка

Для получения поддержки обращайтесь к команде разработки.

---

**Примечание**: Это MVP версия. Для продакшена требуется дополнительная настройка безопасности, мониторинга и оптимизации производительности.
