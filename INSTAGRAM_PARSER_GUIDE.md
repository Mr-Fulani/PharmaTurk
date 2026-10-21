# Instagram Parser - Руководство по использованию

بسم الله الرحمن الرحيم

## Описание

Instagram парсер для PharmaTurk позволяет автоматически собирать посты из Instagram с медиа (изображения/видео) и описаниями для дальнейшего отображения в карточках товаров на сайте.

Изначально разработан для парсинга книг, но может быть легко расширен для других категорий товаров.

## Возможности

- ✅ Парсинг постов из профиля Instagram по username
- ✅ Парсинг постов по хештегу
- ✅ Парсинг конкретного поста по URL
- ✅ Извлечение всех медиа (изображения и видео)
- ✅ Извлечение описаний (captions)
- ✅ Сбор метаданных (лайки, комментарии, дата публикации)
- ✅ Автоматическое создание товаров в каталоге
- ✅ Поддержка аутентификации (опционально)
- ✅ Dry-run режим для тестирования

## Установка

### 1. Установка зависимостей

```bash
cd backend
poetry install
```

Парсер использует библиотеку `instaloader`, которая уже добавлена в `pyproject.toml`.

### 2. Применение миграций

```bash
poetry run python manage.py migrate
```

## Использование

### Базовые команды

#### Парсинг профиля

```bash
poetry run python manage.py run_instagram_scraper --username bookstore_istanbul --max-posts 30
```

#### Парсинг по хештегу

```bash
poetry run python manage.py run_instagram_scraper --hashtag books --max-posts 50
```

#### Парсинг конкретного поста

```bash
poetry run python manage.py run_instagram_scraper --post-url "https://www.instagram.com/p/ABC123xyz/"
```

### Дополнительные опции

#### Dry-run режим (без сохранения в БД)

```bash
poetry run python manage.py run_instagram_scraper --username bookstore --max-posts 10 --dry-run
```

#### С аутентификацией

```bash
poetry run python manage.py run_instagram_scraper \
  --username bookstore \
  --max-posts 50 \
  --login your_instagram_login \
  --password your_instagram_password
```

#### Указание категории товара

```bash
poetry run python manage.py run_instagram_scraper \
  --username bookstore \
  --max-posts 30 \
  --category books
```

### Использование через Django Admin

#### 1. Создание конфигурации парсера

1. Зайдите в Django Admin: `http://localhost:8000/admin/`
2. Перейдите в раздел **Scrapers → Scraper configs**
3. Нажмите **Add scraper config**
4. Заполните поля:
   - **Name**: Instagram Books Parser
   - **Parser class**: `instagram`
   - **Base URL**: `https://www.instagram.com`
   - **Status**: Active
   - **Is enabled**: ✓
   - **Delay min**: 5.0
   - **Delay max**: 10.0
   - **Max pages per run**: 50
   - **Sync enabled**: ✓ (для автоматической синхронизации)
   - **Sync interval hours**: 24

5. Сохраните конфигурацию

#### 2. Запуск через конфигурацию

```bash
poetry run python manage.py run_instagram_scraper --config-id 1 --max-posts 50
```

## Структура данных

### Что парсится из Instagram поста:

- **Название товара**: Извлекается из первого предложения caption
- **Описание**: Полный текст caption
- **Изображения**: Все медиа из поста (включая карусели)
- **URL поста**: Ссылка на оригинальный пост
- **External ID**: Shortcode поста (уникальный идентификатор)
- **Метаданные**:
  - Количество лайков
  - Количество комментариев
  - Хештеги
  - Дата публикации
  - Username автора
  - URL видео (если есть)

### Маппинг на модель Product

```python
Product:
  - name: Извлечено из caption
  - slug: Автоматически из name
  - description: Полный caption
  - product_type: "books" (по умолчанию)
  - category: CategoryBooks
  - external_id: shortcode поста
  - external_url: URL поста
  - external_data: Все метаданные
  - is_available: False (пока не установлена цена)
  - main_image: Первое изображение
  - images: Все медиа через ProductImage
```

## Установка цен

**Важно**: Парсер создает товары **без цены** и в статусе **недоступен**.

Цены устанавливаются вручную через Django Admin:

1. Перейдите в **Catalog → Products**
2. Найдите спарсенный товар
3. Установите цену в поле **Price**
4. Выберите валюту в поле **Currency**
5. Установите **Is available** = ✓
6. Сохраните

## Настройка категорий

### Создание категории для книг

```bash
poetry run python manage.py shell
```

```python
from apps.catalog.models import Category, CategoryType

# Создаем тип категории
category_type, _ = CategoryType.objects.get_or_create(
    slug='books',
    defaults={'name': 'Книги', 'is_active': True}
)

# Создаем категорию
category, _ = Category.objects.get_or_create(
    slug='books',
    defaults={
        'name': 'Книги',
        'category_type': category_type,
        'is_active': True
    }
)
```

### Маппинг хештегов на категории

Через Django Admin можно настроить автоматическое определение категории по хештегам:

1. **Scrapers → Category mappings**
2. Создайте маппинг:
   - **Scraper config**: Instagram Books Parser
   - **External category name**: #books
   - **Internal category**: Книги

## Запуск из админки и расписание

### Задачи Instagram

Пост или весь профиль парсится задачей **Scrapers → Задачи парсинга Instagram**
(`InstagramScraperTask`): «Ссылка на пост» — один пост; username без ссылки и
«Максимум постов» не меньше числа постов (до 5000) — весь профиль. Кнопка
«Запустить» ставит Celery-задачу `run_instagram_scraper_task(instagram_task_id,
resume=False)` (`backend/apps/scrapers/tasks.py`) с прогрессом, паузой и
остановкой. Режимы всех парсеров — [docs/PARSER_MODES.md](docs/PARSER_MODES.md).

### Расписание

Периодического запуска Instagram нет. Если он понадобится:

- запись добавляется в словарь `CELERY_BEAT_SCHEDULE` в
  `backend/config/settings.py` (только `crontab`: состояние beat теряется при
  каждом деплое). Присваивать `app.conf.beat_schedule = {...}` в
  `config/celery.py` нельзя — это затрёт всё расписание проекта;
- вызывать из beat `run_instagram_scraper_task` с id задачи напрямую не
  получится: после первого прогона в задаче остаётся старый `task_id`, и
  следующий запуск завершится как `superseded`. Нужна обёртка, которая, как
  `InstagramScraperTaskAdmin._enqueue_instagram_task`, сбрасывает `task_id` и
  выдаёт новый `run_token`, — это правка кода.

## Troubleshooting

### Ошибка аутентификации

**Проблема**: профиль отдаёт 401, или задача падает с «Instagram требует
подтвердить вход… (Checkpoint required)».

**Решение**: без входа профиль не парсится, а вход по паролю с сервера
Instagram отправляет на проверку. Нужна сессия из браузера:
- войдите в бот-аккаунт в браузере или приложении и подтвердите вход;
- в конфигурации парсера Instagram (**Scrapers → Конфигурации парсеров**)
  положите в «Cookies» `{"sessionid": "<значение cookie>"}` и заполните
  «Логин парсера» и «Пароль парсера»: без них парсер вход не пытается
  (`InstagramParser._ensure_authenticated`), а с `sessionid` загружает сессию
  без входа по паролю (`InstagramParser._authenticate`).

### Rate limiting (429 ошибка)

**Проблема**: `Too many requests`

**Решение**:
- Увеличьте задержки между запросами (delay_min, delay_max)
- Уменьшите количество постов за раз (max-posts)
- Используйте аутентификацию для увеличения лимитов

### Пост без медиа

**Проблема**: Пост пропускается из-за отсутствия изображений

**Решение**:
- Парсер автоматически пропускает посты без медиа
- Это нормальное поведение для товарного каталога

### Дубликаты товаров

**Проблема**: Создаются дубликаты при повторном парсинге

**Решение**:
- Парсер использует `external_id` (shortcode) для предотвращения дубликатов
- При повторном парсинге товар обновляется, а не создается заново

## Best Practices

### 1. Используйте dry-run для тестирования

Перед первым запуском проверьте результаты:

```bash
poetry run python manage.py run_instagram_scraper --username test_account --max-posts 5 --dry-run
```

### 2. Начинайте с малого количества постов

Первый запуск делайте с `--max-posts 10`, затем увеличивайте.

### 3. Регулярная синхронизация

Настройте автоматическую синхронизацию раз в день для обновления данных.

### 4. Модерация контента

Рекомендуется проверять спарсенные товары перед публикацией:
- Проверьте корректность названий
- Установите цены
- Добавьте дополнительные описания при необходимости

### 5. Резервное копирование медиа

Instagram может удалить посты. Рекомендуется:
- Скачивать медиа на собственный сервер
- Использовать CDN для хранения изображений

## Расширение функционала

### Парсинг других категорий товаров

Для парсинга не только книг, но и других товаров:

```bash
poetry run python manage.py run_instagram_scraper \
  --username fashion_store \
  --max-posts 30 \
  --category clothing
```

### Кастомизация извлечения названия

Отредактируйте метод `_extract_product_name` в `instagram.py`:

```python
def _extract_product_name(self, caption: str, max_length: int = 100) -> str:
    # Ваша логика извлечения названия
    # Например, по паттерну или ключевым словам
    pass
```

### Фильтрация по хештегам

Добавьте фильтрацию в `_parse_post`:

```python
hashtags = self._extract_hashtags(caption)
if 'books' not in hashtags:
    return None  # Пропускаем посты без нужного хештега
```

## API Reference

### InstagramParser

**Методы:**

- `parse_product_list(category_url, max_pages)` - Парсинг списка постов
- `parse_product_detail(product_url)` - Парсинг одного поста
- `_parse_profile(username, max_posts)` - Парсинг профиля
- `_parse_hashtag(hashtag, max_posts)` - Парсинг по хештегу
- `_parse_post(post)` - Преобразование поста в ScrapedProduct

## Поддержка

При возникновении проблем:

1. Проверьте логи: `backend/logs/`
2. Используйте `--dry-run` для отладки
3. Проверьте статус парсера в Django Admin

## Лицензия

Этот парсер является частью проекта PharmaTurk.

---

**Разработано с именем Аллаха** ﷻ
