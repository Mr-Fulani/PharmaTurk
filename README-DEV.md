# Разработка Mudaroba

Практическое руководство для локальной разработки и проверки изменений. Обзор продукта и быстрый старт находятся в [README.md](README.md), production-процедуры — в [DEPLOY.md](DEPLOY.md).

## Зафиксированный toolchain

- Python `3.12.13`;
- Poetry `2.4.1`;
- Node.js `22.23.2` (см. `frontend/.nvmrc`);
- npm `10.x`, lockfile обязателен;
- Django `5.2.17`;
- Next.js `15.5.21`;
- PostgreSQL `15.18`, Redis `7.4.10`, Qdrant `1.18.2`.

Не используйте `npm install` вместо `npm ci` в CI или воспроизводимой сборке. Backend-зависимости задаются только `backend/pyproject.toml` и `backend/poetry.lock`; устаревший `requirements.txt` больше не является источником правды.

## Вариант 1: локальный запуск без Docker

Этот режим удобен для кода и быстрых unit-тестов. Интеграционные сценарии требуют доступных PostgreSQL, Redis и Qdrant.

### Backend

```bash
cd backend
poetry install
cp ../.env.example .env
# Скорректируйте DATABASE_URL, три Redis URL (broker/cache/results), QDRANT_HOST и секреты.
poetry run python manage.py migrate
poetry run python manage.py runserver 0.0.0.0:8000
```

При `DJANGO_DEBUG=0` обязательны секрет длиной не менее 32 символов и явный список hosts. Для обычной локальной разработки используйте `DJANGO_DEBUG=1`; не переносите этот режим в production.

Celery broker, Django cache/throttles и Celery result backend используют один
Redis-сервис, но разные logical DB: соответственно `/0`, `/1` и `/2`. Не
сводите их к одной DB — очистка cache не должна затрагивать очередь задач.
На production с ограниченным `maxmemory` предпочтительны отдельные instances,
поскольку logical DB всё равно делят память и eviction policy.

Для scraper proxy TLS всегда проверяется. Если провайдер инспектирует HTTPS,
укажите путь к его PEM bundle в `SCRAPER_PROXY_CA_BUNDLE`; `verify=False` в
парсерах запрещён.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Прямой `npm run dev` слушает `3000`, а development Compose публикует frontend на `3001`.

## Вариант 2: Docker Compose

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
docker compose ps
docker compose logs -f backend frontend
```

Development override монтирует исходники и включает Django/Next hot reload. Production-профиль задаётся отдельным файлом:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

Эта команда только валидирует объединённую конфигурацию. Реальный production-запуск и работа с секретами описаны в [DEPLOY.md](DEPLOY.md).

Backend-образ работает от непривилегированного UID/GID `10001`; вложенный
anonymous volume `/app/.venv` сохраняет собранное окружение при dev bind-mount и
не создаёт root-owned virtualenv в рабочей копии.

На первом этапе аудита 9 августа 2026 года Docker был занят другим приложением.
20 августа проверки завершены в отдельном `mudaroba_audit` project без host
ports: оба production image, миграции, Gunicorn health, Celery worker/Beat и
PostgreSQL/Redis/Qdrant persistence прошли. Перед выпуском gate всё равно нужно
повторить на CI/staging с production ingress и secret injection.

## Сервисы и очереди

| Сервис | Назначение |
| --- | --- |
| `backend` | Django/DRF и admin |
| `frontend` | Next.js Pages Router |
| `postgres` | транзакционные данные |
| `redis` | cache, Celery broker/result backend |
| `qdrant` | векторы товаров и визуальный поиск |
| `celeryworker` | общая очередь `celery` |
| `celery_ai` | очередь `ai` |
| `celery_recsys` | очередь `recsys` |
| `celerybeat` | расписание фоновых задач |
| `nginx` | production reverse proxy |

Production Compose изолирует stateful services во внутренней сети `data`:
frontend не имеет прямого маршрута к PostgreSQL, Redis или Qdrant. Dev override
публикует их порты на host только для локальной диагностики.

OpenSearch не входит в актуальный Compose: в проекте не было исполняемого потребителя этого сервиса.

## Seed и миграции

### Миграции

Создание миграции — явное действие разработчика:

```bash
cd backend
poetry run python manage.py makemigrations <app>
poetry run python manage.py migrate
poetry run python manage.py makemigrations --check --dry-run
```

В контейнере:

```bash
docker compose exec backend poetry run python manage.py showmigrations
docker compose exec backend poetry run python manage.py migrate
```

Entry point выполняет только `migrate`, но не `makemigrations`.

### Каталог

`RUN_SEED_CATALOG` имеет безопасный default `0`: seed выполняется только по явному запросу.

```bash
docker compose exec backend poetry run python manage.py seed_catalog_data
docker compose exec backend poetry run python manage.py seed_catalog_data --categories-only
docker compose exec backend poetry run python manage.py seed_catalog_data --attributes-only
docker compose exec backend poetry run python manage.py seed_catalog_data --brands-only
docker compose exec backend poetry run python manage.py seed_catalog_data --fix-hierarchy
```

Полный seed создаёт 19 корневых доменов и вложенные категории. Он идемпотентен, но всё равно меняет данные — перед запуском на production сделайте backup и dry-run доступных обслуживающих команд.

`load_initial_pages` создаёт только отсутствующие privacy/delivery/returns страницы и не перезаписывает существующий контент.

## Ежедневные проверки

### Backend

```bash
cd backend
poetry check --lock
poetry run python -m pip check
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run pytest -q
```

### Секреты

CI сканирует текущее дерево и всю доступную Git history через Gitleaks. Перед
push ту же blocking-проверку можно выполнить установленным локально бинарём:

```bash
gitleaks git --redact --verbose .
```

`--redact` обязателен при сохранении вывода в CI artifact или при передаче
лога другому человеку. Найденный реальный ключ сначала ротируется у провайдера,
и только затем удаляется из истории согласованной процедурой.
Подтверждённые placeholders допускается исключать только по точному fingerprint
в `.gitleaksignore`; не добавляйте allowlist для всего commit или каталога.

Production settings дополнительно проверяются с реальными безопасными env:

```bash
DJANGO_DEBUG=0 \
DJANGO_SECRET_KEY='<unique-random-secret-at-least-50-characters>' \
DJANGO_ALLOWED_HOSTS='example.com' \
DATABASE_URL='postgresql://app:<unique-password-at-least-16-characters>@localhost:5432/app' \
REDIS_URL='redis://localhost:6379/0' \
REDIS_CACHE_URL='redis://localhost:6379/1' \
CELERY_RESULT_BACKEND_URL='redis://localhost:6379/2' \
CRYPTO_DUMMY_MODE=0 \
TELEGRAM_BOT_TOKEN='' \
SECURE_SSL_REDIRECT=1 \
SECURE_HSTS_SECONDS=31536000 \
SECURE_HSTS_INCLUDE_SUBDOMAINS=1 \
poetry run python manage.py check --deploy --tag security --fail-level ERROR
```

Некоторые миграции используют PostgreSQL-specific SQL, поэтому полную DB-серию нельзя считать проверенной на SQLite.

### Frontend

```bash
cd frontend
npm ci
npm audit --omit=dev --audit-level=high
npm run lint
npx tsc --noEmit
npm test
npm run build
```

### Изменения API и схемы

После изменения serializer/view/route проверьте:

```bash
cd backend
poetry run python manage.py spectacular --validate --file /tmp/mudaroba-schema.yml
```

Предупреждения генератора нельзя маскировать коммитом заведомо устаревшей схемы. Swagger UI должен отражать реальные permissions, обязательные поля и ответы `4xx/5xx`.

## Модель доступа

- глобальный DRF default: `IsAuthenticated`;
- публичные read-only catalog/settings, auth, health и webhook endpoints помечаются `AllowAny` явно;
- VAPI и все AI API требуют `IsAdminUser`;
- `POST /api/payments/init/` требует staff;
- CoinRemitter webhook публичен по транспортной природе, но финальный статус, invoice identity, сумма и привязка заказа сверяются через авторизованный provider API;
- registration, login, email verification, JWT refresh/verify, social/Telegram
  login и загрузка изображений имеют отдельные IP/user throttles.

При добавлении endpoint нельзя полагаться на неявный default. Выберите permission осознанно и добавьте regression test.

## Визуальный поиск и загрузка файлов

Допустимы JPEG, PNG и WebP размером до 5 МБ. Backend проверяет фактический формат изображения, MIME, размеры/число пикселей и потоковый лимит.

Загрузка по URL проходит через общий safe fetcher:

- только HTTP/HTTPS и разрешённые порты;
- запрет credentials в URL;
- проверка всех DNS-адресов на global-routability;
- DNS pinning, ограниченные redirect и download size;
- generic error messages без утечки внутренних адресов.

Новые места загрузки внешнего изображения должны переиспользовать этот fetcher, а не вызывать `requests.get()` напрямую.

## Каталог и ручное наполнение

Общая модель `Product` сосуществует с доменными моделями. Одежду и обувь создавайте как `ClothingProduct` / `ShoeProduct`; их цветовые варианты и размеры живут в отдельных variant/size моделях. Обычный `Product` не заменяет доменную карточку в соответствующем разделе.

Для медиа категории/бренда используется `card_media_url`. Для оптимальной карточки предпочтительны WebP/AVIF до 300–400 КБ и пропорции 4:3 или 1:1. Подробности избранного, доменных id и proxy-media: [docs/CATALOG_FAVORITES_PROXY_MEDIA.md](docs/CATALOG_FAVORITES_PROXY_MEDIA.md).

Backfill характеристик мебели:

```bash
docker compose exec backend poetry run python manage.py backfill_furniture_attributes
docker compose exec backend poetry run python manage.py backfill_furniture_attributes --apply --batch-size 200
```

Все флаги и безопасное продолжение: [docs/FURNITURE_ATTRIBUTES_BACKFILL.md](docs/FURNITURE_ATTRIBUTES_BACKFILL.md).

## Скрипт `restart.sh`

Для повседневного контейнерного цикла доступны:

```bash
./restart.sh --quick --logs
./restart.sh --fast-rebuild
./restart.sh --with-seed
./restart.sh --help
```

`--with-seed` — явное разрешение на seed. `--clean` и `--rebuild` могут удалить volumes и данные; перед подтверждением проверьте target Compose project и наличие backup. Не используйте очистку как стандартный способ исправить проблему зависимостей или кэша.

## Рабочий процесс

1. Создайте отдельную ветку.
2. Для bugfix сначала добавьте тест, воспроизводящий дефект.
3. Выполните релевантные backend/frontend проверки.
4. Для checkout/payments вручную пройдите staging-сценарий и проверьте повтор webhook.
5. Для SEO проверьте ru/en canonical, hreflang, robots и sitemap.
6. В PR перечислите команды проверки и отдельно укажите, запускались ли Docker/staging tests.

CI проверяет lock-файлы, зависимости, Django settings и миграции, pytest, frontend lint/types/tests/build, dependency audit и Compose configuration. Flake8 пока информационный из-за накопленного legacy-baseline; новые ошибки добавлять нельзя.

## Документация

- [docs/README.md](docs/README.md) — единый индекс и статус документов;
- [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md) — правила кода, SEO и e-commerce;
- [docs/ROADMAP.md](docs/ROADMAP.md) — текущие приоритеты;
- [docs/HYDRATION_ERRORS_GUIDE.md](docs/HYDRATION_ERRORS_GUIDE.md) — диагностика hydration;
- [docs/PERSONALIZED_RECOMMENDATIONS.md](docs/PERSONALIZED_RECOMMENDATIONS.md) — ограничения персонализации;
- [CELERY_TASKS.md](CELERY_TASKS.md), [AI_GUIDE.md](AI_GUIDE.md), [SCRAPERS_GUIDE.md](SCRAPERS_GUIDE.md) — тематические руководства.
