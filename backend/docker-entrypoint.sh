#!/bin/bash
set -e

# КАПИТАЛЬНАЯ ОЧИСТКА КЭША ПЕРЕД ЗАПУСКОМ
echo "🧹 Очищаем весь кэш Python..."
find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find /app -type f -name "*.pyc" -delete 2>/dev/null || true
find /app -type f -name "*.pyo" -delete 2>/dev/null || true
find /app -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
echo "✅ Кэш Python очищен"

# Синхронизация зависимостей — только в dev (USE_RUNSERVER=1), где ./backend
# смонтирован поверх /app и pyproject/lock могут быть новее образа.
# В проде зависимости ставятся при сборке образа; install на буте — лишняя
# зависимость от сети при каждом рестарте.
if [ "${USE_RUNSERVER:-0}" = "1" ]; then
    echo "📦 Синхронизация зависимостей Poetry (dev)..."
    poetry install --no-interaction --no-ansi --no-root

    # weasyprint требует системных библиотек Pango/Cairo из Dockerfile
    echo "📦 Проверяем weasyprint..."
    poetry run python -c "import weasyprint" 2>/dev/null || {
        echo "⬇️  weasyprint не найден, устанавливаем..."
        poetry run pip install weasyprint -q && echo "✅ weasyprint установлен" || echo "⚠️  weasyprint не удалось установить (PDF-чеки будут недоступны)"
    }
fi

# Кэш Django при старте НЕ чистим: в Redis живут 30-дневные ресайзы картинок
# (proxy_media) — их вайп давал всплеск латентности после каждого деплоя.
# При несовместимых изменениях формата кэша версионировать ключи (v1 → v2).

# В release-процессе миграции выполняет отдельный одноразовый compose service.
# Значение 1 сохраняет удобное прежнее поведение для локальной разработки.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Применяем миграции..."
  poetry run python manage.py migrate --noinput
else
  echo "Пропускаем миграции (RUN_MIGRATIONS=${RUN_MIGRATIONS:-0})"
fi

echo "Сборка статических файлов (collectstatic)..."
poetry run python manage.py collectstatic --noinput

# Восстанавливаем категории и бренды после пересоздания БД (идемпотентно)
if [ "${RUN_SEED_CATALOG:-0}" = "1" ]; then
  echo "Восстанавливаем категории и бренды (seed_catalog_data)..."
  poetry run python manage.py seed_catalog_data 2>/dev/null || true
else
  echo "Пропускаем seed_catalog_data (RUN_SEED_CATALOG=${RUN_SEED_CATALOG:-0})"
fi

# Статические страницы (privacy, delivery, returns) — создаём только если ещё нет
echo "Загружаем статические страницы (load_initial_pages)..."
poetry run python manage.py load_initial_pages 2>/dev/null || true

# Если передана команда — выполняем её (например: pytest, manage.py ...).
# Webhook и прочие side-effects сервера для command-запусков не выполняем.
if [ $# -gt 0 ]; then
    exec poetry run "$@"
fi

# Registration mutates provider-side state. Keep it explicit so a staging
# container can never redirect a shared production bot during an ordinary boot.
if [ "${REGISTER_TELEGRAM_WEBHOOK_ON_START:-0}" = "1" ] && \
   [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && \
   [ -n "${SITE_URL:-}" ] && \
   [ -n "${TELEGRAM_WEBHOOK_SECRET:-}" ]; then
  echo "Регистрируем Telegram webhook..."
  poetry run python manage.py set_telegram_webhook || \
    echo "⚠️  Telegram webhook не зарегистрирован; проверьте настройки и доступ к API"
elif [ "${REGISTER_TELEGRAM_WEBHOOK_ON_START:-0}" = "1" ]; then
  echo "⚠️  Telegram webhook пропущен: нужны TELEGRAM_BOT_TOKEN, SITE_URL и TELEGRAM_WEBHOOK_SECRET"
fi

# Запускаем сервер в зависимости от режима
if [ "${USE_RUNSERVER:-0}" = "1" ]; then
    echo "Запускаем Django runserver (hot-reload включен)..."
    exec poetry run python manage.py runserver 0.0.0.0:8000
else
    echo "Запускаем gunicorn..."
    # The production backend container is capped at 1.5 GiB. Django workers retain
    # native/Pillow/http parser arenas after large media and supplier responses, so
    # four long-lived processes can hit the cgroup limit even when the host still
    # has free memory. Two gthread workers keep 16 concurrent request threads while
    # leaving enough headroom for a large response in each process.
    WORKERS="${GUNICORN_WORKERS:-2}"
    THREADS="${GUNICORN_THREADS:-8}"
    # Periodic rolling recycle returns retained native allocator arenas to the OS.
    # Jitter prevents both workers from restarting on the same request boundary.
    MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-200}"
    MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-40}"
    # gthread: длинные ответы (proxy_media: стриминг видео, ресайз) не занимают
    # целый sync-воркер; concurrency обеспечивается потоками, а не числом тяжёлых
    # Django-процессов.
    GUNICORN_ARGS="--bind 0.0.0.0:8000 --workers $WORKERS --worker-class gthread --threads $THREADS --timeout 60 --max-requests $MAX_REQUESTS --max-requests-jitter $MAX_REQUESTS_JITTER"
    if [ "${DJANGO_DEBUG:-0}" = "1" ] || [ "${DJANGO_DEBUG:-0}" = "True" ]; then
        exec poetry run gunicorn config.wsgi:application $GUNICORN_ARGS --reload
    else
        exec poetry run gunicorn config.wsgi:application $GUNICORN_ARGS
    fi
fi
