# Production-деплой Mudaroba

Этот документ описывает текущий Docker Compose-стек проекта. Команды ниже
предназначены для сервера; локальный Docker для проверки этой инструкции не
нужен.

## 1. Состав и требования

В production-профиле запускаются:

- PostgreSQL `15.18`, Redis `7.4.10` и Qdrant `1.18.2`;
- Django/Gunicorn и Celery на Python `3.12.13`;
- Next.js на Node.js `22.23.2` и npm `10.x`;
- Nginx `1.30.4`, который маршрутизирует `/api`, `/admin`, `/swagger`,
  `/static` и `/media` в Django, а остальные запросы — в Next.js.

OpenSearch в актуальном стеке отсутствует: поиск по каталогу выполняет
приложение, а векторные рекомендации хранит Qdrant.

Минимальные требования для базового стека — Linux, Docker Engine с Compose v2,
8 GB RAM и 30 GB свободного диска. Для одновременного запуска AI- и
recsys-worker'ов планируйте память по фактической модели и нагрузке; лимиты всех
контейнеров не означают, что сервер физически располагает этой памятью.

## 2. Получение проекта

```bash
git clone https://github.com/Mr-Fulani/PharmaTurk.git
cd PharmaTurk
cp .env.production.example .env
chmod 600 .env
```

Не коммитьте `.env`, дампы базы, Qdrant snapshots и ключи внешних сервисов.

## 3. Обязательная настройка `.env`

### Django fail-fast

При `DJANGO_DEBUG=0` приложение намеренно отказывается стартовать, если:

- `DJANGO_SECRET_KEY` короче 32 символов или совпадает с известным placeholder;
- `DJANGO_ALLOWED_HOSTS` пуст или содержит `*`;
- `DATABASE_URL` не PostgreSQL URL, не содержит host/database/user/password или
  использует пароль короче 16 символов либо известный dev/placeholder;
- `CRYPTO_DUMMY_MODE=1`;
- `TELEGRAM_BOT_TOKEN` задан без уникального `TELEGRAM_WEBHOOK_SECRET` длиной
  не менее 32 символов;
- Redis broker/cache/result URL не разделены по трём DB/targets.

Сгенерировать секрет можно так:

```bash
openssl rand -base64 48
```

Обязательно задайте реальные домены без протокола в
`DJANGO_ALLOWED_HOSTS`, а HTTPS origins — с протоколом в
`CSRF_TRUSTED_ORIGINS` и `CORS_ALLOWED_ORIGINS`.

### PostgreSQL: согласованные переменные

Compose читает `POSTGRES_DB`, `POSTGRES_USER` и `POSTGRES_PASSWORD` из `.env`.
Тем же пользователем, паролем и именем базы заполните `DATABASE_URL`:

```text
postgres://USER:PASSWORD@postgres:5432/DB_NAME
```

Если значения различаются, PostgreSQL может быть healthy, но backend не пройдёт
readiness. Не оставляйте dev-пароль `pharmaturk` на публичном сервере. Если
пароль содержит специальные URL-символы, оставьте его исходным в
`POSTGRES_PASSWORD`, но URL-encode в `DATABASE_URL`.

`DB_CONNECT_TIMEOUT_SECONDS`, `REDIS_CONNECT_TIMEOUT_SECONDS` и
`REDIS_SOCKET_TIMEOUT_SECONDS` ограничивают ожидание зависимостей, в том числе
readiness probe. Не задавайте нулевые/неограниченные timeout в production.

Redis также разделён логически: `REDIS_URL` — Celery broker (`/0`),
`REDIS_CACHE_URL` — Django cache/throttles (`/1`), а
`CELERY_RESULT_BACKEND_URL` — результаты задач (`/2`). Не направляйте их в одну
DB: очистка cache иначе может удалить очередь или результаты Celery. Logical DB
не изолируют общий лимит памяти и политику eviction; при существенной нагрузке
broker, cache и result backend следует вынести в отдельные Redis instances.

Если residential proxy для парсеров выполняет TLS inspection, смонтируйте PEM
bundle его CA read-only и задайте `SCRAPER_PROXY_CA_BUNDLE=/run/secrets/...`.
Отключение проверки сертификатов не поддерживается: без доверенного CA запрос
должен завершиться ошибкой, а не переходить на `verify=False`.

### Публичные URL

Текущий Nginx обслуживает frontend и API на одном origin. Для стандартной схемы
задайте:

```dotenv
NEXT_PUBLIC_SITE_URL=https://mudaroba.com
SITE_URL=https://mudaroba.com
FRONTEND_SITE_URL=https://mudaroba.com
```

`INTERNAL_API_BASE=http://backend:8000` уже задаётся в Compose и не должен
указывать на публичный домен. Переменные `NEXT_PUBLIC_*` встраиваются во
frontend при сборке, поэтому после их изменения требуется пересобрать образ
frontend, а не только перезапустить контейнер.

## 4. TLS, Cloudflare и доверенная proxy-цепочка

Проверенный в репозитории production Compose публикует только Nginx-порт `80`.
Сам контейнерный Nginx сертификат не обслуживает: TLS должен завершаться во
внешнем ingress с origin-сертификатом либо трафик должен поступать через
Cloudflare Tunnel.

Текущий Nginx сохраняет входящий `X-Forwarded-Proto=https`, иначе использует
собственный `$scheme`. Django доверяет этому заголовку. Это корректно только
когда прямой доступ к origin закрыт firewall'ом/security group и заголовок может
поставить исключительно доверенный proxy. Публичный origin:80 позволил бы
клиенту подделать заголовок и обойти HTTPS redirect.

Предпочтительная схема — Cloudflare **Full (strict)** с валидным origin TLS либо
Cloudflare Tunnel. Режим Flexible не используйте: участок Cloudflare → origin в
нём остаётся незашифрованным, а при неправильной обработке
`X-Forwarded-Proto` типичный результат — бесконечный redirect.

`SECURE_SSL_REDIRECT=1` включайте только после проверки всей цепочки:

1. HTTP-запрос к публичному домену получает один redirect на HTTPS;
2. HTTPS-запрос достигает Django с `X-Forwarded-Proto=https` и возвращает
   конечный ответ, а не новый redirect на тот же URL;
3. origin недоступен напрямую: `nginx/cloudflare-realip.inc` принимает public
   Host только от официальных диапазонов Cloudflare, а private/loopback ranges
   оставлены для локальных smoke checks; диапазоны сверяются с официальными
   endpoints при каждом уведомлении Cloudflare об изменении;
4. `/api/live/` и `/api/health/` проходят через тот же production hostname.

Та же граница доверия относится к IP throttles и CoinRemitter allowlist.
Проектный Nginx принимает public Host только от перечисленных Cloudflare source
ranges, доверяет `CF-Connecting-IP` исключительно для такого TCP peer и затем
перезаписывает `X-Real-IP` для Django. Не удаляйте source-range gate и не
доверяйте произвольному `X-Forwarded-For`. Provider IP allowlist оставьте пустым
до отдельной проверки CoinRemitter ingress.

До выполнения этих условий оставьте Django redirect/HSTS выключенными и
принудительно используйте HTTPS на внешнем ingress. HSTS preload включайте
только когда HTTPS гарантирован для основного домена и всех поддоменов: его
откат занимает время.

Backend, Gunicorn, Celery и Beat запускаются внутри образа от непривилегированного
UID/GID `10001`. Новый пустой `staticfiles` volume наследует корректного владельца
из образа. При обновлении старой инсталляции сначала проверьте права уже
существующего volume на staging: если он был создан прежним root-образом,
однократно смените владельца `/app/staticfiles` на `10001:10001` либо пересоздайте
только этот воспроизводимый volume и снова выполните `collectstatic`. Не меняйте
владельца PostgreSQL/Qdrant volumes этой процедурой.

Compose разделяет сети: Nginx/frontend находятся в `edge`, stateful PostgreSQL,
Redis и Qdrant — во внутренней `data`; только backend соединяет web и data
контуры. Celery workers получают `data` и отдельную outbound-only для состава
проекта `egress`, чтобы обращаться к внешним API. Не подключайте frontend или
Nginx к `data` и не публикуйте stateful ports в production override.

## 5. Предстартовая проверка и запуск

Проверьте итоговую конфигурацию без вывода значений `.env` в публичный лог:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
./scripts/release/predeploy.sh \
  --environment staging \
  --release-id "$(git rev-parse HEAD)"
```

Release-образы backend/frontend получают неизменяемый тег полного Git SHA и OCI
label `org.opencontainers.image.revision` с тем же значением. Backend и все
Celery workers обязаны использовать один SHA. Скрипт откажется от staging или
production проверки при незакоммиченном diff либо несовпадении SHA с `HEAD`.

В локальной разработке backend entrypoint по умолчанию:

1. применяет существующие миграции;
2. выполняет `collectstatic`;
3. создаёт отсутствующие статические страницы;
4. запускает Gunicorn.

`makemigrations` при старте не выполняется. `seed_catalog_data` также выключен
по умолчанию и запускается только при `RUN_SEED_CATALOG=1`. Включайте seed для
новой/восстановленной пустой базы осознанно, затем снова возвращайте `0`.
В release-профиле `RUN_MIGRATIONS=0`: миграции выполняются ровно один раз через
one-shot service `migrate` из профиля `ops`, до перезапуска web/workers.
Проектный `./restart.sh` тоже пропускает seed по умолчанию; единственный явный
shortcut для его включения — `./restart.sh --with-seed`.

`REGISTER_TELEGRAM_WEBHOOK_ON_START` также должен оставаться `0`. Обычный
restart не должен менять provider-side URL бота. После проверки `SITE_URL`,
bot token и отдельного webhook secret выполните один раз именно в целевом
окружении:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backend poetry run python manage.py set_telegram_webhook
```

`deploy.sh` открывает короткое maintenance-окно: останавливает Nginx, web и все
Celery-процессы перед применением schema migrations, затем запускает весь набор
на одном SHA. Это намеренный выбор целостности данных вместо конкурентных
записей старого кода во время добавления constraints. До остановки он проверяет
наличие как новых, так и предыдущих SHA-образов; при отсутствии rollback artifact
деплой не начинается.

Проверить состояние:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=200 backend nginx frontend
```

## 6. Liveness и readiness

Эндпоинты имеют разную семантику:

- `GET /api/live/` — liveness процесса; не обращается к внешним зависимостям и
  возвращает 200, пока Django способен обработать запрос;
- `GET /api/health/` — readiness; проверяет PostgreSQL и Redis cache/throttle
  backend и возвращает 503, если хотя бы одна зависимость недоступна.

Docker healthcheck backend использует `/api/health/`, поэтому frontend не
стартует до готовности БД и Redis. Внешний балансировщик должен использовать readiness
для выдачи трафика, а liveness — только для решения о перезапуске процесса.

```bash
curl --fail https://mudaroba.com/api/live/
curl --fail https://mudaroba.com/api/health/
```

## 7. Первый запуск

Создайте администратора:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py createsuperuser
```

Индекс рекомендаций заполняется отдельно:

```bash
# Небольшая синхронизация в foreground
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py sync_product_vectors

# Полная синхронизация ставится в очередь Celery
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py sync_product_vectors --full
```

Проверьте, что `celery_recsys` запущен до постановки полной синхронизации.

## 8. CoinRemitter

Для реальных криптоплатежей задайте API key/password кошелька CoinRemitter и
публичный HTTPS `SITE_URL`. Создаваемый backend URL уведомлений:

```text
https://mudaroba.com/api/payments/crypto/webhook/
```

Маршрут принимает вариант с завершающим `/` и без него. Он должен быть доступен
из интернета без browser challenge, авторизации и промежуточного HTML redirect.
Не используйте localhost или бесплатную interstitial-страницу ngrok.

Тело webhook не считается доверенным: backend использует идентификатор как
подсказку и запрашивает актуальный статус и суммы через аутентифицированный
CoinRemitter `invoice/get`. Поэтому работоспособность webhook зависит и от
исходящего HTTPS-доступа backend к CoinRemitter. После настройки проведите
отдельную оплату минимального тестового заказа и убедитесь, что повторная
доставка webhook не списывает остаток второй раз.

До и после deploy выполните read-only сверку (команда не меняет статусы):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py reconcile_coinremitter \
  --all-statuses --fail-on-drift
```

При drift сохраните вывод и provider audit trail. Для оплаченного у провайдера,
но не подтверждённого локально платежа повторно доставьте подлинный webhook;
не исправляйте статус напрямую в PostgreSQL, обходя атомарное списание остатков.

Legacy PDF сначала инвентаризируются без удаления:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py cleanup_legacy_receipts
```

Mutation-режим требует `--apply --confirm-bucket <точное-имя>` и отдельный
`--quarantine-prefix <непредсказуемый-префикс>`. Команда сначала копирует все
найденные объекты в quarantine и лишь затем удаляет предсказуемые ключи; при
ошибке копирования источники не удаляются. Запускайте её только после retention
решения. Если доступен отдельный private/non-CDN bucket, явно задайте его через
`--quarantine-bucket`; same-bucket fallback защищён только непредсказуемостью
ключа. Флаг `--show-keys` нельзя использовать в общих CI/deploy logs.

## 9. Резервное копирование и обновление Qdrant

Перед каждым обновлением сохраняйте PostgreSQL dump и выносите резервную копию
за пределы Docker volumes. Для Qdrant изменение тега образа — миграция данных, а
не обычный restart.

Безопасная последовательность обновления Qdrant:

1. зафиксировать текущий тег образа и список collections/число points;
2. остановить `celery_recsys` и любые ручные команды записи в Qdrant;
3. создать snapshot через Qdrant Snapshot API и скопировать его за пределы
   volume `qdrant_data`;
4. проверить, что snapshot скачивается и имеет ненулевой размер;
5. прочитать release notes всех пропускаемых версий и проверить поддерживаемую
   последовательность обновления;
6. обновить только Qdrant, проверить collections, counts и тестовый поиск;
7. после проверки снова запустить writers.

Если существующий volume когда-либо запускался на Qdrant `1.15.x` или старше,
не переходите прямо на `1.18.2`: сначала поднимите последний `1.15.x`, затем
`1.16.x`, проверьте данные и только после этого переходите на `1.18.2`. На
каждом шаге нужен отдельный проверенный snapshot; точную цепочку дополнительно
сверяйте с release notes фактически установленной исходной версии.

Не удаляйте `qdrant_data` ради обновления и не рассчитывайте, что downgrade
образа прочитает данные, уже изменённые новой версией. Для rollback используйте
проверенный snapshot и прежний тег.

## 10. Обновление приложения

Полная исполняемая процедура находится в
[`scripts/release/README.md`](scripts/release/README.md). Сначала прогоните
изолированный локальный контур: он использует уникальное имя Compose project,
loopback-порт и удаляет только собственные контейнеры/volumes.

```bash
./scripts/release/predeploy.sh \
  --environment local \
  --release-id "audit-$(git rev-parse --short HEAD)" \
  --allow-dirty
./scripts/release/local-smoke.sh \
  --release-id "audit-$(git rev-parse --short HEAD)"
```

Dirty tag предназначен только для проверки и не допускается к deploy. После
review и коммита дождитесь зелёного CI, повторите predeploy с полным SHA и без
`--allow-dirty`, затем применяйте один и тот же уже собранный artifact сначала
на staging и только после observation window — на production.

До deploy нужны внешний PostgreSQL dump и Qdrant snapshot. Команда
`prepare-backup-manifest.sh` проверяет читаемость dump через `pg_restore`,
размеры файлов и записывает контрольные суммы. `deploy.sh` повторно проверяет
эти суммы, предыдущий release SHA, точную строку подтверждения и явное имя
Compose project; затем показывает migration plan, применяет миграции один раз,
запускает tagged images с `RUN_MIGRATIONS=0` и выполняет HTTPS smoke.

Проект пока не интегрирован с registry. Поэтому SHA-образы должны быть безопасно
доставлены на target host без пересборки между staging и production, а их OCI
labels — проверены. Если меняется только код, volumes PostgreSQL/Qdrant не
пересоздаются. Обновление самого Qdrant выполняйте только по разделу 9.

### Rollback приложения

До deploy сохраните предыдущие SHA-образы. При проблеме без несовместимого
изменения схемы используйте `scripts/release/rollback.sh`: он требует точное
подтверждение, проверяет OCI labels, переключает только приложение без запуска
миграций и повторяет readiness/smoke-проверки.

Если новая миграция уже изменила или удалила данные, обычный откат кода
недостаточен: остановите writers, восстановите согласованный PostgreSQL backup и
Qdrant snapshot, затем поднимайте прежнюю версию. Не запускайте reverse
migration в production, пока её обратимость не проверена на копии данных.

## 11. Операционные команды

```bash
# Логи сервиса
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend

# Состояние миграций
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py showmigrations

# Django system check
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  poetry run python manage.py check --deploy

# Остановка контейнеров с сохранением named volumes
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

Не добавляйте `-v` к `docker compose down`, если не намерены удалить данные
PostgreSQL, Redis и Qdrant.

## 12. Финальный чек-лист

- [ ] `DJANGO_DEBUG=0`, уникальный `DJANGO_SECRET_KEY` длиной не менее 32 символов.
- [ ] Рабочее дерево чистое, CI зелёный, `IMAGE_TAG` равен полному Git SHA;
      backend/frontend/workers используют один artifact revision.
- [ ] `DJANGO_ALLOWED_HOSTS` перечисляет реальные hosts и не содержит `*`.
- [ ] `POSTGRES_*` и `DATABASE_URL` согласованы; dev-пароль заменён.
- [ ] CSRF/CORS origins содержат только нужные HTTPS origins.
- [ ] Выбран корректный TLS-профиль; Full (strict)/Tunnel, закрытый origin и
      `X-Forwarded-Proto` проверены до включения Django redirect/HSTS.
- [ ] HTTP apex и `www` дают один redirect на canonical HTTPS host; HTTPS-ответ
      содержит согласованные security headers и не раскрывает лишние server
      headers.
- [ ] `/api/live/` возвращает 200, `/api/health/` возвращает 200 только при
      доступных PostgreSQL и Redis cache.
- [ ] `RUN_SEED_CATALOG=0` после первоначального заполнения.
- [ ] Backup PostgreSQL и snapshot Qdrant хранятся вне Docker volumes.
- [ ] Backup manifest проверен, предыдущие SHA-образы доступны для rollback.
- [ ] CoinRemitter webhook доступен по публичному HTTPS и проверен тестовой
      оплатой, если криптоплатежи включены.
- [ ] Read-only CoinRemitter reconciliation завершилась без drift и ошибок API.
- [ ] Legacy receipt inventory выполнена; решение об удалении/retention
      зафиксировано, HMAC-namespaced PDF не затронуты.
- [ ] Blocking Gitleaks CI по полной Git history прошёл; каждый новый finding
      классифицирован, а подтверждённые credentials ротированы до очистки
      history. Известные localhost JWT placeholders исключены только точными
      fingerprints в `.gitleaksignore`.
- [ ] R2, email, Telegram, OAuth, VAPI, OpenAI и Sentry включены только при
      наличии отдельных production-ключей. R2 обязателен, если включена
      генерация и отправка PDF-чеков.
