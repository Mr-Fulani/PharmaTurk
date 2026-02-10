# Деплой PharmaTurk на удалённый сервер

## Требования к серверу

- **ОС:** Linux (Ubuntu 22.04 / Debian 12 рекомендуется)
- **Docker** и **Docker Compose** v2+
- **Память:** минимум 4 GB RAM (рекомендуется 8 GB при OpenSearch + Qdrant)
- **Диск:** 20+ GB для образов, данных и логов

## 1. Подготовка сервера

```bash
# Установка Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Выйдите и зайдите снова, чтобы применить группу docker

# Установка Docker Compose plugin
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
```

## 2. Клонирование и настройка окружения

```bash
git clone https://github.com/Mr-Fulani/PharmaTurk.git
cd PharmaTurk
```

Создайте файл `.env` на основе продакшен-примера:

```bash
cp .env.production.example .env
nano .env   # или vim / другой редактор
```

**Обязательно задайте:**

| Переменная | Описание |
|------------|----------|
| `DJANGO_SECRET_KEY` | Уникальный длинный ключ (например: `openssl rand -base64 48`) |
| `DJANGO_ALLOWED_HOSTS` | Домены через запятую: `pharmaturk.ru,www.pharmaturk.ru` |
| `CSRF_TRUSTED_ORIGINS` | То же с протоколом: `https://pharmaturk.ru,https://www.pharmaturk.ru` |
| `CORS_ALLOWED_ORIGINS` | Те же URL для CORS |
| `DATABASE_URL` | Строка подключения к PostgreSQL (внутри Docker: `postgres://pharmaturk:ПАРОЛЬ@postgres:5432/pharmaturk`) |
| `NEXT_PUBLIC_API_BASE` | Публичный URL API для фронта, например `https://api.pharmaturk.ru/api` или `https://pharmaturk.ru/api` |

Пароль PostgreSQL задаётся в `docker-compose.yml` (переменные `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) или через `DATABASE_URL` в `.env`.

## 3. Запуск в режиме продакшена

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Проверка логов:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend frontend
```

Миграции и `collectstatic` выполняются при старте backend (см. `docker-entrypoint.sh`).

## 4. Первый запуск: индексация рекомендаций

После первого деплоя проиндексируйте векторы товаров в Qdrant (для блока «Похожие товары»):

```bash
# Один батч (100 товаров) в foreground
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend poetry run python manage.py sync_product_vectors

# Или полная синхронизация в фоне через Celery
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend poetry run python manage.py sync_product_vectors --full
```

## 5. Reverse proxy и SSL (Nginx)

На сервере перед контейнерами обычно ставят Nginx (или Caddy) для HTTPS и проксирования на backend (порт 8000) и frontend (порт 3001 в dev; в prod frontend слушает 3000 внутри контейнера).

Пример фрагмента конфига Nginx:

```nginx
# Frontend (Next.js)
server {
    listen 443 ssl http2;
    server_name pharmaturk.ru www.pharmaturk.ru;
    ssl_certificate /etc/letsencrypt/live/pharmaturk.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pharmaturk.ru/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Backend API
server {
    listen 443 ssl http2;
    server_name api.pharmaturk.ru;
    ssl_certificate /etc/letsencrypt/live/pharmaturk.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pharmaturk.ru/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

В `docker-compose.prod.yml` порты backend и frontend можно пробросить на localhost (например `8000:8000` и `3001:3000`), чтобы Nginx проксировал на них.

## 6. Обновление деплоя

```bash
cd PharmaTurk
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml build backend frontend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend frontend celeryworker celery_ai celerybeat
```

Миграции применяются при старте backend автоматически.

## 7. Полезные команды

| Действие | Команда |
|----------|---------|
| Логи всех сервисов | `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f` |
| Логи backend | `docker compose ... logs -f backend` |
| Статистика рекомендаций | `docker compose ... exec backend poetry run python manage.py recsys_stats` |
| Синхронизация векторов | `docker compose ... exec backend poetry run python manage.py sync_product_vectors [--full]` |
| Django shell | `docker compose ... exec backend poetry run python manage.py shell` |
| Остановка | `docker compose -f docker-compose.yml -f docker-compose.prod.yml down` |

## 8. Чек-лист перед продакшеном

- [ ] В `.env`: `DJANGO_DEBUG=0`, уникальный `DJANGO_SECRET_KEY`
- [ ] Заданы `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`
- [ ] `DATABASE_URL` и `REDIS_URL` указывают на сервисы в Docker (или внешние)
- [ ] `NEXT_PUBLIC_API_BASE` — публичный URL API (для запросов с браузера)
- [ ] R2 (или другое хранилище медиа) настроено при необходимости
- [ ] Nginx (или иной reverse proxy) настроен, SSL включён
- [ ] После первого запуска выполнен `sync_product_vectors` при необходимости
