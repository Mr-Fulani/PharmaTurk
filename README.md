# Mudaroba

Mudaroba — двуязычная (ru/en) мультикатегорийная площадка турецких товаров и услуг. Репозиторий исторически называется `PharmaTurk`, но актуальное имя продукта, Docker-образов и API — **Mudaroba**.

Проект объединяет публичный каталог, корзину и заказы, JWT-аутентификацию, криптооплату через CoinRemitter, импорт данных, AI-инструменты для контента и визуальные рекомендации на Qdrant.

## Состояние проекта

На 9 августа 2026 года основной стек зафиксирован на следующих версиях:

| Компонент | Версия / роль |
| --- | --- |
| Python | 3.12.13 |
| Django | 5.2.17 |
| Django REST Framework | 3.18.0 |
| Node.js | 22.23.2 |
| Next.js | 15.5.21 (Pages Router) |
| PostgreSQL | 15.18 |
| Redis | 7.4.10 |
| Qdrant | 1.18.3 |
| Celery | фоновые задачи и отдельные очереди AI/RecSys |
| Nginx | входной reverse proxy в production |

OpenSearch удалён из актуальной архитектуры как неиспользуемый компонент. Обычные поисковые и фильтрующие запросы каталога обслуживает основная БД, а векторный поиск — Qdrant.

## Возможности

- 19 корневых доменов каталога: от медикаментов, одежды и электроники до книг, услуг и благовоний;
- отдельные доменные модели и API для разных типов товаров;
- корзина, оформление заказа, уведомления и PDF-чеки;
- криптоинвойсы CoinRemitter и сверка webhook с данными провайдера;
- поиск по изображению с CLIP/Qdrant, лимитом 5 МБ, проверкой формата и защитой загрузки по URL от SSRF;
- двуязычные SEO-страницы, sitemap и товарные фиды;
- импорт VAPI, парсеры и AI-обработка контента;
- Cloudflare R2 для медиа (опционально для каталога с локальным fallback, но
  обязательно, если включена генерация и отправка PDF-чеков);
- Prometheus-метрики и опциональная отправка ошибок в Sentry.

Административные API VAPI и AI доступны только staff-пользователям. Глобальный DRF-default требует аутентификацию; публичные catalog/settings/health/webhook endpoints открываются явно в коде.

## Архитектура

```text
Client
  -> Nginx
      -> Next.js frontend
      -> Django/DRF backend
           -> PostgreSQL
           -> Redis -> Celery workers / Celery Beat
           -> Qdrant
           -> CoinRemitter / VAPI / OpenAI / R2 (если настроены)
```

Основные каталоги:

```text
backend/          Django, DRF, Celery, миграции и тесты
frontend/         Next.js Pages Router, ru/en UI
docs/             актуальные правила, roadmap и тематические документы
nginx/            reverse proxy и production routing
.github/workflows CI-проверки
```

## Быстрый старт через Docker Compose

Требуются Docker Engine и Docker Compose v2.

```bash
cp .env.example .env
# Заполните переменные в .env по комментариям, прежде всего SECRET_KEY и URL сервисов.
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
docker compose ps
```

Локальные адреса development-профиля:

- frontend: <http://localhost:3001>;
- backend API: <http://localhost:8000>;
- Django Admin: <http://localhost:8000/admin/>;
- OpenAPI UI: <http://localhost:8000/api/docs/>;
- readiness: <http://localhost:8000/api/health/>;
- liveness: <http://localhost:8000/api/live/>;
- PostgreSQL: `localhost:5433`;
- Redis: `localhost:6379`;
- Qdrant HTTP/gRPC: `localhost:6333` / `localhost:6334`.

`/api/health/` проверяет PostgreSQL и Redis cache/throttle backend и возвращает
`503`, если сервис не готов. `/api/live/` не обращается к зависимостям и
показывает, что процесс Django жив.

### Seed каталога

Автоматический seed выключен безопасным значением `RUN_SEED_CATALOG=0`. Запускайте его только осознанно:

```bash
docker compose exec backend poetry run python manage.py seed_catalog_data
```

Команда идемпотентно создаёт 19 корневых категорий, дерево подкатегорий, типы динамических атрибутов и бренды. Доступны флаги `--categories-only`, `--attributes-only`, `--brands-only`, `--fix-hierarchy` и `--category-seo-only`.

## Локальный запуск без Docker

Для полного backend нужны доступные PostgreSQL, Redis и Qdrant. Версии Python и Node должны совпадать с зафиксированными в Dockerfile и `.nvmrc`.

```bash
cd backend
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver
```

```bash
cd frontend
npm ci
npm run dev
```

Frontend по умолчанию слушает порт `3000` при прямом запуске; порт `3001` используется development Compose.

## Проверки

```bash
cd backend
poetry check --lock
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run pytest -q
```

```bash
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm test
npm run build
```

Эти же классы проверок выполняются в GitHub Actions. Во время аудита 9 августа 2026 года локальные Docker-контейнеры и Docker-сборки намеренно не запускались, поскольку Docker был занят другим приложением; контейнерный smoke-test остаётся обязательным перед production-деплоем.

## Production-безопасность

При `DJANGO_DEBUG=0` приложение аварийно останавливается, если:

- `DJANGO_SECRET_KEY` отсутствует, является заглушкой или короче 32 символов;
- `DJANGO_ALLOWED_HOSTS` пуст или содержит `*`;
- `DATABASE_URL` неполон или содержит известный dev/placeholder password;
- включён тестовый `CRYPTO_DUMMY_MODE`;
- задан Telegram bot token без отдельного webhook secret длиной не менее 32
  символов;
- Celery broker, Django cache и Celery result backend направлены в одну Redis
  DB вместо раздельных targets.

Frontend получает только явно перечисленные public/SSR variables и находится
в сети `edge`; PostgreSQL, Redis и Qdrant изолированы во внутренней `data` и не
доступны frontend-контейнеру напрямую.

TLS redirect и HSTS включаются только после проверки HTTPS-прокси через `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_HSTS_INCLUDE_SUBDOMAINS` и `SECURE_HSTS_PRELOAD`. Не копируйте development-секреты и пароли в production. Подробный чек-лист находится в [DEPLOY.md](DEPLOY.md).

## Ключевые API

```text
GET  /api/catalog/products/             публичный каталог
POST /api/auth/jwt/create/              JWT login с rate limiting
POST /api/payments/init/                фиксированный тест DummyProvider (staff)
POST /api/payments/crypto/webhook       CoinRemitter webhook
POST /api/recommendations/search_by_image поиск по изображению
POST /api/vapi/*                        VAPI, только staff
*    /api/ai/*                          AI-инструменты, только staff
```

Полный контракт доступен в Swagger/OpenAPI UI после запуска backend.

## Документация

- [README-DEV.md](README-DEV.md) — рабочий процесс разработчика и команды проверок;
- [docs/README.md](docs/README.md) — индекс актуальной и исторической документации;
- [docs/AUDIT_2026-08-09.md](docs/AUDIT_2026-08-09.md) — полный аудит, результаты проверок и release gates;
- [docs/ROADMAP.md](docs/ROADMAP.md) — текущие задачи и отделённый исторический snapshot;
- [DEPLOY.md](DEPLOY.md) — production deployment;
- [CRYPTO_PAYMENTS.md](CRYPTO_PAYMENTS.md) — CoinRemitter и криптоплатежи;
- [docs/notifications-and-receipts.md](docs/notifications-and-receipts.md) — уведомления и чеки;
- [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md) — соглашения проекта.

Мобильный Flutter-клиент находится в отдельном репозитории: [pharmaturk-mobile](https://github.com/Mr-Fulani/pharmaturk-mobile).

## Лицензия

Проект Mudaroba является проприетарным. Все права защищены.
