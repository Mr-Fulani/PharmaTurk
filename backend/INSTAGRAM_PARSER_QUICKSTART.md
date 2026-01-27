# Instagram Parser - Быстрый старт

بسم الله الرحمن الرحيم

## Установка и первый запуск

### 1. Установите зависимости

```bash
cd backend
poetry install
```

### 2. Инициализируйте парсер

```bash
poetry run python manage.py init_instagram_scraper
```

### 3. Создайте категорию "books" (если еще не создана)

```bash
poetry run python manage.py shell
```

```python
from apps.catalog.models import Category, CategoryType

category_type, _ = CategoryType.objects.get_or_create(
    slug='books',
    defaults={'name': 'Книги', 'is_active': True}
)

category, _ = Category.objects.get_or_create(
    slug='books',
    defaults={
        'name': 'Книги',
        'category_type': category_type,
        'is_active': True
    }
)
print(f"Категория создана: {category.name}")
exit()
```

### 4. Тестовый запуск (dry-run)

```bash
poetry run python manage.py run_instagram_scraper \
  --username bookstore_example \
  --max-posts 5 \
  --dry-run
```

### 5. Реальный запуск с сохранением

```bash
poetry run python manage.py run_instagram_scraper \
  --username bookstore_example \
  --max-posts 30 \
  --category books
```

### 6. Установите цены через Django Admin

1. Откройте `http://localhost:8000/admin/`
2. Перейдите в **Catalog → Products**
3. Найдите спарсенные товары (is_available = False)
4. Установите цены и активируйте товары

## Примеры использования

### Парсинг по хештегу

```bash
poetry run python manage.py run_instagram_scraper \
  --hashtag turkishbooks \
  --max-posts 50
```

### Парсинг конкретного поста

```bash
poetry run python manage.py run_instagram_scraper \
  --post-url "https://www.instagram.com/p/ABC123xyz/"
```

### С аутентификацией (для приватных профилей)

```bash
poetry run python manage.py run_instagram_scraper \
  --username bookstore \
  --max-posts 30 \
  --login your_instagram_login \
  --password your_instagram_password
```

## Что дальше?

📖 Полная документация: `INSTAGRAM_PARSER_GUIDE.md`

🔧 Настройка автоматической синхронизации через Celery

🎨 Кастомизация извлечения названий и категорий

📦 Расширение для других категорий товаров (одежда, электроника и т.д.)
