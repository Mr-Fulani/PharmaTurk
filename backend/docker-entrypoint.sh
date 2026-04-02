#!/bin/bash
set -e

# КАПИТАЛЬНАЯ ОЧИСТКА КЭША ПЕРЕД ЗАПУСКОМ
echo "🧹 Очищаем весь кэш Python..."
find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find /app -type f -name "*.pyc" -delete 2>/dev/null || true
find /app -type f -name "*.pyo" -delete 2>/dev/null || true
find /app -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
echo "✅ Кэш Python очищен"

# Смонтированный ./backend может содержать обновлённый pyproject.toml / poetry.lock без пересборки образа
echo "📦 Синхронизация зависимостей Poetry..."
poetry install --no-interaction --no-ansi --no-root

# Устанавливаем weasyprint если не установлен (требует системных библиотек Pango/Cairo из Dockerfile)
echo "📦 Проверяем weasyprint..."
poetry run python -c "import weasyprint" 2>/dev/null || {
    echo "⬇️  weasyprint не найден, устанавливаем..."
    poetry run pip install weasyprint -q && echo "✅ weasyprint установлен" || echo "⚠️  weasyprint не удалось установить (PDF-чеки будут недоступны)"
}

# Очистка кэша Django
echo "🧹 Очищаем кэш Django..."
poetry run python manage.py clear_cache 2>/dev/null || true
echo "✅ Кэш Django очищен"

# Применяем миграции (makemigrations должен выполняться ВРУЧНУЮ разработчиком, а не при старте!)
echo "Применяем миграции..."
poetry run python manage.py migrate --noinput

echo "Сборка статических файлов (collectstatic)..."
poetry run python manage.py collectstatic --noinput

# Восстанавливаем категории и бренды после пересоздания БД (идемпотентно)
echo "Восстанавливаем категории и бренды (seed_catalog_data)..."
poetry run python manage.py seed_catalog_data 2>/dev/null || true

# Статические страницы (privacy, delivery, returns) — создаём только если ещё нет
echo "Загружаем статические страницы (load_initial_pages)..."
poetry run python manage.py load_initial_pages 2>/dev/null || true

# Регистрируем Telegram webhook (если заданы TELEGRAM_BOT_TOKEN и SITE_URL)
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$SITE_URL" ]; then
  echo "Регистрируем Telegram webhook..."
  poetry run python manage.py set_telegram_webhook 2>/dev/null || true
fi

# Если передана команда — выполняем её (например: python manage.py seed_perfumery_brands)
if [ $# -gt 0 ]; then
    exec poetry run "$@"
fi

# Запускаем сервер в зависимости от режима
if [ "$USE_RUNSERVER" = "1" ]; then
    echo "Запускаем Django runserver (hot-reload включен)..."
    exec poetry run python manage.py runserver 0.0.0.0:8000
else
    echo "Запускаем gunicorn..."
    WORKERS="${GUNICORN_WORKERS:-4}"
    if [ "$DJANGO_DEBUG" = "1" ] || [ "$DJANGO_DEBUG" = "True" ]; then
        exec poetry run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "$WORKERS" --reload
    else
        exec poetry run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "$WORKERS"
    fi
fi

