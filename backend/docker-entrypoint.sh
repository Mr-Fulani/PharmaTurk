#!/bin/bash
set -e

# Запускаем сервер в зависимости от режима
if [ "$USE_RUNSERVER" != "1" ]; then
    echo "Запускаем gunicorn (миграции должны быть применены заранее)..."
    exec poetry run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --reload
else
    echo "Запускаем Django runserver (hot-reload включен)..."
    exec poetry run python manage.py runserver 0.0.0.0:8000
fi

