# Диск прода и Redis: что занимает место и что ограничить

Снимок с прода 2026-10-18 (после инцидента: диск 100 % → Redis MISCONF → 503).
Сервер: 38 ГБ, занято 29 ГБ (80 %), свободно 7,2 ГБ; RAM 7,6 ГБ без swap.

## Что занимает диск

| Что | Размер | Рекомендация |
|---|---|---|
| Образы Docker (`overlay2` ≈ 12 ГБ вместе со слоями контейнеров) | ≈ 7,9 ГБ | Backend ≈ 1,9 ГБ и frontend ≈ 0,9 ГБ на релиз. Теперь `deploy.sh` после успешного релиза удаляет образы всех релизов, кроме текущего и предыдущего (`prune-images.sh`). Сейчас лишний backend `bb0a7ba…`, но его удерживают остановленные контейнеры `migrate-run-*` (см. ниже). `node:22.23.2-bookworm-slim` (227 МБ) не используется |
| `/var/log/journal` (журнал systemd) | 2,6 ГБ | Ограничить: `SystemMaxUse=300M` в `/etc/systemd/journald.conf` и однократно `journalctl --vacuum-size=300M`. Нужен sudo (делает владелец сервера) |
| Том `mudaroba_postgres_data` | 3,1 ГБ | Рабочие данные, не трогать |
| Том `mudaroba_redis_data` (`dump.rdb`) | 1,8 ГБ | Почти целиком кэш картинок; бэкенд больше их туда не пишет, старые ключи удалить вручную (см. раздел Redis) |
| Том `mudaroba_huggingface_cache` | 1,1 ГБ | Модели эмбеддингов, рабочий кэш, не трогать |
| Том `mudaroba_qdrant_data` | 0,7 ГБ | Рабочие данные, не трогать |
| Анонимные тома без контейнеров (≈ 150 шт.) | ≈ 0,22 ГБ | `docker volume prune` (удаляет только анонимные тома без контейнеров), только после согласия |
| `backups/pharmaturk`: 5 предрелизных бэкапов от 17–18.10 | 3,2 ГБ (≈ 640 МБ каждый) | `prune-backups.sh --keep 2` (сначала dry-run) освободит ≈ 1,9 ГБ. Только после согласия |
| `backups/*.sql.gz` (pre-brand-merge, pre-brands-media от 18.10) | 0,48 ГБ | Удалить после проверки результатов слияния брендов, только после согласия |
| Лог контейнера nginx (json-file без ротации) | 0,47 ГБ за 7 недель | Ротация `max-size: 50m`, `max-file: 3` добавлена в `docker-compose.prod.yml`. Действует после пересоздания контейнера (nginx пересоздаётся полным деплоем) |
| Кэш nginx `proxy_media` в слое контейнера | 1,0 ГБ | Лимит уже есть (`max_size=1g`). Теперь это единственный кэш готовых картинок. Пропадает при пересоздании контейнера nginx (тома нет), `docker restart` его сохраняет |
| Кэш nginx `next_image` (ответы оптимизатора `/_next/image`, с 2026-10-21) | до 0,5 ГБ | `max_size=512m`, 30 дней без обращений; как и `proxy_media`, живёт в слое контейнера nginx (см. `PROD_MEMORY.md`, «Картинки баннеров и next/image») |
| Брошенный полный снапшот Qdrant `full-snapshot-2026-09-07-22-46-14.snapshot` в слое контейнера qdrant | 0,38 ГБ | Удалить через API Qdrant (`DELETE /snapshots/<имя>`), только после согласия |
| Stage `mudaroba-stage-9122b27`: 4 остановленных контейнера (5 недель), тома и `~/pharmaturk-stage-9122b27` | ≈ 0,16 ГБ | `docker compose -p mudaroba-stage-9122b27 down -v` и удаление каталога, только после согласия |
| 6 остановленных `mudaroba-migrate-run-*` | 0 Б сами, но держат образы `820bcd7…` и `bb0a7ba…` (≈ 1,9 ГБ каждый) | Появлялись из-за `backend_release.py` (`compose run` без `--rm`), исправлено в PR #88. Существующие удалить `docker rm`, после чего `prune-images.sh` сможет убрать старый образ |

Выполнено 2026-10-18 с согласия владельца: удалены 6 `migrate-run-*`, образ
backend `bb0a7ba…`, брошенный снапшот Qdrant и stage `mudaroba-stage-9122b27`
(контейнеры, тома, сети, git worktree; архив тома PostgreSQL —
`backups/stage-9122b27-postgres-data-20261018.tar.gz`, 10 МБ). Свободно стало
9,5 ГБ (74 %). Бэкапы, journald и анонимные тома не трогали.

Логи остальных контейнеров маленькие (Redis 32 МБ, PostgreSQL 17 МБ, Qdrant 14 МБ).
Ротация для PostgreSQL, Redis и Qdrant начнёт действовать только при плановом
пересоздании этих сервисов: `deploy.sh` их не пересоздаёт (`--no-recreate`).
Изменение их описаний в Compose означает, что следующий релиз должен быть полным:
`backend_release.py` откажется работать с изменённой конфигурацией frontend/nginx/
postgres/redis/qdrant.

## Защита при деплое

- `pull-images.sh` до скачивания проверяет свободное место в каталоге данных
  Docker: нужно не меньше 4 ГиБ (`MUDAROBA_MIN_FREE_GIB`), иначе понятная ошибка.
- `deploy.sh` после успешного релиза и смоук-проверки запускает
  `prune-images.sh --apply` с текущими и предыдущими SHA backend/frontend.
  Образы, используемые любым контейнером (в том числе остановленным), не удаляются.
  Ошибка очистки не делает успешный деплой неуспешным.
- Ручной просмотр без удаления: `./scripts/release/prune-images.sh --keep CURRENT_SHA --keep PREVIOUS_SHA`.
- С 22.10.2026 `deploy.sh` после успешного релиза запускает и `prune-backups.sh --keep 3
  --apply` с защитой текущей копии (из `--backup-manifest`): в `~/backups/pharmaturk`
  остаются три новейшие валидные копии перед деплоем (≈ 690 МБ каждая, ≈ 2,1 ГБ).
  Удаляются только каталоги с манифестом, дампом, снапшотом Qdrant и копией `.env`;
  `backend-release-*`, `banners-*` и прочее не трогаются. Ошибка очистки не делает
  деплой неуспешным. Копия базы вне сервера — ежедневная, [DB_BACKUP.md](DB_BACKUP.md).

## Оповещения о диске и Redis

С 22.10.2026 задача `apps.monitoring.tasks.check_server_resources` (каждые 10 минут,
очередь `celery`) пишет в тот же Telegram, что watchdog, если:

| Что | Порог (настройка в `.env`) |
|---|---|
| свободно на диске хоста меньше | 4 ГиБ (`SERVER_DISK_MIN_FREE_GB`; столько требует `pull-images.sh`) |
| брокер `redis`: `used_memory` от `maxmemory` | 70 % (`REDIS_BROKER_MAX_MEMORY_PERCENT`; при 100 % `noeviction` отказывает в записи, Celery не ставит задачи) |
| кэш `redis-cache`: `used_memory` от `maxmemory` | 110 % (`REDIS_CACHE_MAX_MEMORY_PERCENT`; с `allkeys-lru` кэш держится у 100 % — это норма) |
| у любого Redis не задан `maxmemory`, последний снимок на диск не удался (`rdb_last_bgsave_status`, дальше MISCONF) или Redis недоступен | всегда |

Новая проблема — сразу, та же — не чаще раза в 6 часов (`SERVER_RESOURCES_REPEAT_SECONDS`),
после исправления всех — сообщение «снова в норме». Включается вместе с watchdog
(`SERVER_RESOURCES_MONITOR_ENABLED`, по умолчанию = `PRODUCTION_WATCHDOG_ENABLED`; на
проде включён, отдельный chat_id не нужен).

Свободное место берётся с корня контейнера воркера — это overlay на диске хоста. Размер
`~/backups` задача не считает: каталоги копий закрыты правами 700 (дампы БД и копии
`.env`), и воркеру (пользователь `app`) их читать незачем. Их рост виден по свободному
месту, а старые копии удаляет `deploy.sh`.

Если пришёл алерт о диске: `df -h /`, `docker system df`, `du -sh ~/backups/*` — что
занимает место, см. «Что занимает диск» выше; удалять бэкапы, тома и образы — по
`prune-*.sh` в режиме dry-run и после согласия владельца.

## Redis

Состояние на 2026-10-18 (с 2026-10-19 кэш Django вынесен в отдельный контейнер
`redis-cache`, у брокера и кэша по `maxmemory 128mb` — см. «Рекомендуемый
вариант» ниже и [PROD_MEMORY.md](PROD_MEMORY.md)). Тогда был один
`redis:7-alpine` для всего: db0 — брокер Celery (9 ключей),
db1 — кэш Django (≈ 100 тыс. ключей, ≈ 1,8 ГБ), db2 — результаты Celery
(≈ 5,4 тыс. ключей, TTL ≈ 15 ч). `maxmemory` не задан, политика `noeviction`,
RDB-снимки `save 3600 1 300 100 60 10000`, `stop-writes-on-bgsave-error yes`.

Почти весь кэш состоял из байтов картинок: ключи `r2webp_*` и `r2mw_q_*`
из `proxy_media` (`backend/apps/catalog/views.py`, TTL 30 дней, до 2,6 МБ
на ключ). Из-за них `dump.rdb` весил 1,8 ГБ: каждый BGSAVE пишет на диск ещё
столько же (временный файл) и делает fork процесса на 1,8 ГБ при 2,2 ГБ
свободной памяти. Когда места не хватило, BGSAVE упал, Redis запретил запись
(MISCONF) — и брокер, и кэш. С PR #89 бэкенд байты картинок в Redis не
пишет (см. «Устранение причины»).

Очереди Celery вытеснять нельзя: ключи брокера (списки очередей, `unacked`,
`_kombu.binding.*`) без TTL, их потеря = потерянные задачи.

### Рекомендуемый вариант: отдельный Redis для кэша

Сделано после инцидента 2026-10-19 с другими лимитами (брокер `maxmemory
128mb`, кэш `128mb`) и без правки `.env`: актуальная схема, лимиты контейнеров
и порядок применения — [PROD_MEMORY.md](PROD_MEMORY.md). Ниже — исходное
предложение.

```yaml
# docker-compose.yml
  redis-cache:
    image: redis:7.4.10-alpine3.21
    command: >-
      redis-server --save "" --appendonly no
      --maxmemory 768mb --maxmemory-policy allkeys-lru
    networks: [data]
```

и в прод `.env`: `REDIS_CACHE_URL=redis://redis-cache:6379/0`.

- Кэш живёт только в памяти, на диск не пишет, вытесняет старое сам (LRU),
  при рестарте просто пустеет.
- Основной Redis (брокер + результаты):
  `--maxmemory 512mb --maxmemory-policy noeviction`. Его RDB станет размером
  в мегабайты, BGSAVE мгновенный. При достижении лимита Redis отклоняет новые
  записи (ошибка постановки задачи) вместо того, чтобы съесть память сервера и
  получить OOM-kill — это сигнал, а не тихая потеря очередей.
- Алерт: `used_memory / maxmemory` и `rdb_last_bgsave_status != ok` — сделано
  22.10.2026, см. «Оповещения о диске и Redis».
- `stop-writes-on-bgsave-error` для брокера оставить `yes`: при маленьком RDB он
  сработает только при совсем полном диске, а алерт сообщит об этом раньше.

Применение — плановое окно обслуживания (пересоздание redis, добавление сервиса,
правка `.env`), не через `deploy.sh`. Полный релиз после изменения Compose.

### Быстрый вариант без нового сервиса

На текущем экземпляре: `maxmemory 1gb` и `maxmemory-policy volatile-lru`.
Вытесняются только ключи с TTL (кэш и результаты Celery), ключи брокера без TTL
не трогаются. Можно применить без рестарта (`CONFIG SET`) и закрепить в Compose
(`command:`). Минусы: RDB всё равно около 1 ГБ, могут вытесняться свежие
результаты задач.

### Устранение причины

`proxy_media` больше не кладёт байты картинок в Django-кэш: ни ресайзы
(`?max_width=`/`?w=`, бывшие `r2mw_q_*`), ни полноразмерный webp (бывшие
`r2webp_*`). Готовые ответы кэширует nginx (`proxy_cache proxy_media` в
`nginx/default.conf`: 1 ГБ, 30 дней без обращений, ключ учитывает webp в
`Accept`), браузер и CDN — по `Cache-Control: public, max-age=2592000, immutable`.
Повторный запрос картинки до Django не доходит, поэтому скорость отдачи не
меняется. Разница только на промахе nginx: картинку, которую раньше отдавал
Redis, Django заново прочитает из R2 и пережмёт (одна генерация на ключ, дальше
снова из кэша nginx). Тест: `test_proxy_media_*_does_not_store_image_bytes_in_cache`
в `backend/apps/catalog/tests/test_proxy_media_max_width.py`.

Кэш картинок Instagram в Redis (`insta_img_*` в `proxy_image`, до
1 МБ, сутки) остался: он маленький и защищает от лимитов Instagram.

После деплоя старые ключи сами истекут за 30 дней, но до этого держат ≈ 1,8 ГБ
памяти и `dump.rdb`. Удалить их сразу (только с согласия владельца; брокер и
результаты Celery в других БД не затрагиваются):

```bash
docker exec mudaroba-redis-1 sh -c \
  'for p in ":1:r2webp_*" ":1:r2mw_q_*"; do
     redis-cli -n 1 --scan --pattern "$p" --count 1000 | xargs -r -n 500 redis-cli -n 1 UNLINK >/dev/null
   done; redis-cli -n 1 DBSIZE; redis-cli INFO memory | grep used_memory_human; redis-cli BGSAVE'
```

Если после этого доля `MISS` в `X-Cache-Status` у `/api/catalog/proxy-media`
заметно вырастет (кэш nginx упирается в 1 ГБ: `du -sh /var/cache/nginx/proxy_media`
в контейнере nginx), можно поднять `max_size` до 2g: на диске освобождаются
1,8 ГБ `dump.rdb` и столько же под временный файл BGSAVE.
