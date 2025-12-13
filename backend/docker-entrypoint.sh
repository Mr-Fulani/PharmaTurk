#!/bin/bash
set -e

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

