# Утилиты для разработки

## Скрипт перезапуска проекта

### `restart.sh` (Linux/macOS)

Скрипт для полного перезапуска проекта с опциями очистки и пересборки.

**Использование:**
```bash
./restart.sh [опции]
```

**Опции:**
- `--clean` - Удалить volumes (база данных будет очищена!)
- `--no-cache` - Пересобрать образы без кэша Docker
- `--rebuild` - Полная пересборка (--clean + --no-cache)
- `--logs` - Показать логи после запуска
- `--help` - Показать справку

**Примеры:**
```bash
# Обычный перезапуск
./restart.sh

# Пересборка без кэша
./restart.sh --no-cache

# С очисткой базы данных
./restart.sh --clean

# Полная пересборка с логами
./restart.sh --rebuild --logs
```

### `restart.bat` (Windows)

Аналогичный скрипт для Windows.

**Использование:**
```cmd
restart.bat [опции]
```

## Утилиты для разработки

### `dev-utils.sh` (Linux/macOS)

Набор полезных функций для ежедневной разработки.

**Загрузка утилит:**
```bash
source dev-utils.sh
# или
. dev-utils.sh
```

**Доступные команды:**

#### Основные команды
- `restart_backend` - Перезапустить backend
- `restart_frontend` - Перезапустить frontend
- `logs [service]` - Показать логи (всех или конкретного сервиса)
- `status` - Показать статус контейнеров

#### Django команды
- `manage <command>` - Выполнить manage.py команду
- `makemigrations [app]` - Создать миграции
- `migrate` - Применить миграции
- `createsuperuser` - Создать суперпользователя
- `shell` - Открыть Django shell
- `collectstatic` - Собрать статику

#### Очистка
- `clear_python_cache` - Очистить кэш Python
- `clear_next_cache` - Очистить кэш Next.js
- `clear_all_cache` - Очистить все кэши

#### Другое
- `backend_exec <command>` - Выполнить команду в backend контейнере
- `frontend_exec <command>` - Выполнить команду в frontend контейнере
- `disk_usage` - Показать использование дискового пространства

**Примеры использования:**
```bash
# Загрузить утилиты
. dev-utils.sh

# Показать логи backend
logs backend

# Создать миграции
makemigrations users

# Применить миграции
migrate

# Открыть Django shell
shell

# Очистить все кэши
clear_all_cache
```

## Быстрые команды Docker Compose

### Просмотр логов
```bash
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f backend
docker compose logs -f frontend
```

### Выполнение команд в контейнерах
```bash
# Backend
docker compose exec backend poetry run python manage.py <command>
docker compose exec backend poetry shell

# Frontend
docker compose exec frontend npm run <command>
docker compose exec frontend sh
```

### Перезапуск сервисов
```bash
# Все сервисы
docker compose restart

# Конкретный сервис
docker compose restart backend
docker compose restart frontend
```

### Остановка и запуск
```bash
# Остановить все
docker compose stop

# Запустить все
docker compose start

# Остановить и удалить контейнеры
docker compose down

# Остановить и удалить контейнеры + volumes
docker compose down -v
```

## Полезные команды для разработки

### Django

```bash
# Создать суперпользователя
docker compose exec backend poetry run python manage.py createsuperuser

# Применить миграции
docker compose exec backend poetry run python manage.py migrate

# Создать миграции
docker compose exec backend poetry run python manage.py makemigrations

# Django shell
docker compose exec backend poetry run python manage.py shell

# Собрать статику
docker compose exec backend poetry run python manage.py collectstatic

# Сбросить пароль пользователя
docker compose exec backend poetry run python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); user = User.objects.get(username='admin'); user.set_password('newpassword'); user.save()"
```

### Frontend

```bash
# Установить зависимости
docker compose exec frontend npm install

# Запустить линтер
docker compose exec frontend npm run lint

# Собрать проект
docker compose exec frontend npm run build
```

### Очистка

```bash
# Очистить кэш Python
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete

# Очистить кэш Next.js
rm -rf frontend/.next
rm -rf frontend/node_modules/.cache

# Очистить Docker кэш
docker system prune -f

# Очистить неиспользуемые образы
docker image prune -a -f
```

## SEO/медиа памятка

- Карточка категории/бренда: в админке `Catalog -> Category/Brand` заполнить поле `card_media_url` (можно загрузить файл в медиа и вставить URL). Рекомендации: формат webp/avif, до 300–400 КБ, пропорции 4:3 или 1:1; для видео — короткие mp4/webm.
- Кэш: в разработке (DEBUG=True) кэш заголовков для robots/sitemap отключён. В проде ставится `Cache-Control: public, max-age=3600` только для SEO эндпоинтов, чтобы не мешать разработке.
- Sitemap/robots: отдаются бэкендом (`/sitemap.xml`, `/robots.txt`) и включают категории, бренды и товары (до 5000 товаров); обновление происходит на каждый запрос.

## Доступные сервисы

После запуска проекта доступны:

- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:3001
- **Admin Panel**: http://localhost:8000/admin/
- **Swagger Docs**: http://localhost:8000/api/docs/
- **PostgreSQL**: localhost:5433
- **Redis**: localhost:6379
- **OpenSearch**: http://localhost:9200

## Работа с товарами вручную

В админке (`/admin/catalog/product/`) появился расширенный интерфейс ручного добавления товаров:

- тип товара, бренд и категория можно выбрать или создать "на лету" благодаря `autocomplete_fields`.
- SEO-поля (meta/og) для русского и английского языков, а также локализованные названия и описания помогают настроить карточку под поисковые системы.
- Для логистики доступны вес/габариты, GTIN/MPN, MOQ, упаковка и страна происхождения, чтобы правильно отображать карточку в каталогах.
- Раздел "Медиа" поддерживает до 5 изображений, требуя одного главного, а в списке и инлайнах показываются превью.
- Swagger-документация автоматически отражает новые поля `product_type`, `availability_status` и `country_of_origin` для фильтрации.
- Валюта выбирается из фиксированного списка (`RUB`, `USD`, `EUR`, `TRY`, `GBP`, `USDT`), поэтому оператору видно, какие расчётные единицы доступны для товара.
 - SEO- и OpenGraph-поля заполняются только на английском, их надо использовать для отображения карточки в англоязычном интерфейсе.
 - Обувь и одежда на сайте тянутся из моделей `ShoeProduct`/`ClothingProduct`, а не из общей `Product`. Если нужно, чтобы товар появился в каталоге одежды/обуви, создавайте его в соответствующей модели (они тоже располагаются в админке `Catalog`), иначе обычный `Product` будет попадать только в общие разделы.
- Для обуви добавлена галерея изображений (инлайн в админке) и выпадающий список размеров (EU-формат). Если нужной категории нет — создайте её в `ShoeCategory`; главное изображение задаётся в поле `main_image`, дополнительные — через галерею.

### Варианты одежды и обуви

- Родительские карточки: `ShoeProduct`/`ClothingProduct` (slug, SEO, бренд, категория, описание).
- Вариант = цвет: создавайте в инлайне `ShoeVariant`/`ClothingVariant` у родителя. Заполняйте цвет, цену/валюту, остаток по цвету, `is_active`, при необходимости загрузите главное изображение и до 5 фото (флаг `is_main` обязателен, если нет `main_image` у варианта).
- Размеры внутри варианта: в инлайне `ShoeVariantSize`/`ClothingVariantSize` указывайте размер, доступность и остаток. У одного цвета может быть до 5 фото, но размеры не имеют своих фото.
- Если у родителя нет ни одного варианта, можно добавлять в корзину саму карточку по её slug — бэкенд создаст связанный базовый `Product` автоматически.
- Добавление в корзину:
  - Базовые товары: `product_id`.
  - Вариант цвета одежды/обуви: `product_type` (`clothing`/`shoes`) + `product_slug` (slug варианта-цвета) + `size`.
- Фронт: на странице товара переключение цвета выбирает slug варианта-цвета; сетка размеров берется из `sizes` выбранного варианта. AddToCart отправляет slug варианта, `product_type` и выбранный `size`. Галерея показывает фото выбранного варианта, при его отсутствии — фото родителя.

## Решение проблем

### Проблемы с портами

Если порты заняты, измените их в `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Вместо 8000:8000
```

### Проблемы с кэшем

Используйте полную пересборку:
```bash
./restart.sh --rebuild
```

### Проблемы с базой данных

Очистите volumes (⚠️ удалит все данные):
```bash
./restart.sh --clean
```

### Проблемы с зависимостями

Пересоберите образы без кэша:
```bash
./restart.sh --no-cache
```

