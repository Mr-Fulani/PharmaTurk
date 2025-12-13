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

# Применяем миграции автоматически
echo "Применяем миграции..."
poetry run python manage.py migrate --noinput

# Запускаем сервер в зависимости от режима
if [ "$USE_RUNSERVER" != "1" ]; then
    echo "Запускаем gunicorn..."
    exec poetry run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --reload
else
    echo "Запускаем Django runserver (hot-reload включен)..."
    exec poetry run python manage.py runserver 0.0.0.0:8000
fi

