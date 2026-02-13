#!/bin/bash
set -e

# КАПИТАЛЬНАЯ ОЧИСТКА КЭША ПЕРЕД ЗАПУСКОМ
echo "🧹 Очищаем весь кэш Python..."
find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find /app -type f -name "*.pyc" -delete 2>/dev/null || true
find /app -type f -name "*.pyo" -delete 2>/dev/null || true
find /app -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
echo "✅ Кэш Python очищен"

# Очистка кэша Django
echo "🧹 Очищаем кэш Django..."
poetry run python manage.py clear_cache 2>/dev/null || true
echo "✅ Кэш Django очищен"

# Создаем и применяем миграции автоматически
echo "Создаем миграции..."
poetry run python manage.py makemigrations || true
echo "Применяем миграции..."
poetry run python manage.py migrate --noinput

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

