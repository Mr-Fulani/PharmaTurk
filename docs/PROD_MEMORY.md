# Память прода: лимиты, Redis, swap

Сервер: Hetzner cx33, 4 vCPU, 7,7 ГБ RAM, 38 ГБ диска. Compose project `mudaroba`.

## Инцидент 2026-10-19

Около 03:25 МСК сервер завис по памяти, сайт лежал до ~11:20 (помогло только
выключение/включение в Hetzner). Одновременно:

- Redis без лимита (`maxmemory 0`, `noeviction`) раздулся до 2,95 ГБ кэшем
  байтов картинок в db1 (бэкенд их больше не пишет, см. `PROD_DISK_AND_REDIS.md`);
- с 03:00 `catalog.cleanup_orphaned_media` 56 минут обходила весь R2 и БД;
- swap не было, а `mem_limit` (backend 1,5g + три воркера по 3g) в сумме
  превышали физическую память; postgres, redis, qdrant, frontend, beat и nginx
  были вообще без лимитов.

Без swap и при сумме лимитов больше RAM ядро не может никого быстро убить:
оно выталкивает из памяти код процессов и начинает бесконечно читать его с
диска — сервер «живой», но не отвечает даже по SSH.

## Бюджет памяти

Лимиты в `docker-compose.yml` (frontend — в `docker-compose.prod.yml`, потому
что dev-сервер Next прожорливее). Сумма — 7 ГиБ, системе остаётся
≈ 0,7 ГиБ плюс swap 4 ГиБ. Тест `scripts/release/test_compose_memory.py`
не даёт сумме превысить 7 ГиБ и требует лимит у каждого постоянного сервиса.

Пересчитано по факту после деплоя 2026-10-19 (`docker stats` через ≈ 40 минут
работы): запас не меньше 30 % над наблюдаемым. Первая версия давала celerybeat
160 МиБ при реальных ≈ 195 МБ — его 46 раз убил OOM, пока лимит не подняли
вручную.

| Сервис | mem_limit | Факт 19.10 | Почему столько |
|---|---|---|---|
| backend | 2 ГиБ | 426 МБ → 1,1 ГБ после #101 | 2 gunicorn-воркера по ≈ 560 МБ, см. «Веб-воркер» ниже |
| celery_recsys | 1,5 ГиБ | — | CLIP + MiniLM в памяти ≈ 1,3 ГБ, concurrency 1; CLIP (≈ 0,75 ГБ) — с момента старта, для поиска по фото |
| postgres | 640 МиБ | 400 МБ | shared_buffers 128 МБ + соединения; кэш страниц ОС освобождается сам |
| celeryworker | 640 МиБ | 381 МБ | concurrency 2, `--max-memory-per-child=400000` |
| celery_ai | 640 МиБ | 328 МБ | было 512: AI-задачи с длинными инструкциями лекарств; concurrency 2 |
| qdrant | 512 МиБ | 283 МБ | было 768: векторы в RAM, данные ≈ 0,7 ГБ на диске |
| frontend | 320 МиБ | 147 МБ | было 512: Next.js production-сервер, запас на оптимизатор картинок |
| celerybeat | 256 МиБ | ≈ 195 МБ | было 160 (OOM): процесс Django + планировщик |
| redis (брокер) | 256 МиБ | ≈ 14 МБ вместе с кэшем | `maxmemory 128mb`, вдвое больше — запас на fork при BGSAVE |
| redis-cache | 192 МиБ | — | `maxmemory 128mb`, без записи на диск и fork |
| nginx | 128 МиБ | — | процессы nginx; кэш `proxy_media` на диске |

Ночной бэкап базы (`docs/DB_BACKUP.md`) отдельного контейнера не требует:
`pg_dump` работает внутри `celeryworker` и добавляет к нему несколько десятков
МБ плюс буфер загрузки 16 МиБ.

### Веб-воркер gunicorn

После #101 (перезапуск воркера раз в 2000±500 запросов вместо 200±40) каждый
воркер на проде держит ≈ 560 МБ, backend целиком — 1,1 ГБ, поэтому лимит 2 ГиБ
(сумма осталась 7 ГиБ за счёт celerybeat 256m, брокера 256m/128mb и frontend 320m).

Замер 2026-10-19 (локально, тот же образ, gunicorn gthread 2×8, `DJANGO_DEBUG=0`):

- воркер после старта — 200–235 МБ (Django, DRF, numpy, Pillow, boto3,
  qdrant-client, openai); torch, transformers и sentence-transformers не
  импортируются;
- GET по всем 153 маршрутам без параметров torch тоже не подгружает;
- POST `search_by_image` раньше грузил CLIP (torch ≈ 190 МБ + transformers +
  веса ≈ 600 МБ) в обслуживший запрос воркер до его перезапуска. Теперь картинку
  кодирует `celery_recsys` (задача `encode_search_image`, очередь
  `recsys_search`), а веб ждёт вектор до 15 секунд и иначе отвечает 503
  `search_unavailable`. Тест `test_web_search_queues_clip_and_never_imports_torch`
  проверяет, что после поиска torch и transformers нет в `sys.modules`.
  MiniLM (`TextEncoder`) в вебе тоже не используется.

Значит, остальные ≈ 330 МБ на воркер — данные запросов (кэши каталога,
ответы с большими списками, арены Pillow после proxy-media), которые теперь
живут в 10 раз дольше между перезапусками. Проверка на проде (только чтение):
`RssAnon` — куча Python, `RssFile` — отображённые библиотеки и файлы,
`torch` > 0 — в воркер загружена модель.

```bash
docker exec mudaroba-backend-1 sh -c 'for p in /proc/[0-9]*; do c=$(tr "\0" " " < $p/cmdline); case "$c" in *gunicorn*) echo "$(basename $p) $(grep -E "VmRSS|RssAnon|RssFile" $p/status | tr -s " " | tr "\n" " ") torch=$(grep -c libtorch $p/maps)";; esac; done'
```

Раньше поиск по фото, попавший в оба воркера, раздувал каждый до ≈ 1,3 ГБ и
упирал backend в 2 ГиБ. Теперь веб-воркер от поиска не растёт; `torch=0` в
проверке выше — норма для любого воркера. Потолок `celery_recsys` тот же:
поиск использует тот же экземпляр CLIP, что и индексация, без второго процесса
(`--concurrency=1`). Разница лишь в том, что CLIP (≈ 0,75 ГБ вместе с torch)
грузится при старте воркера, а не в 02:15 на ночной индексации. Через брокер
идёт PNG-копия ≤ 512 px (обычно 0,1–0,2 МБ, не больше ≈ 1 МБ), а не исходник до
5 МБ — Redis с `maxmemory 128mb` и `noeviction` их не накопит: веб ждёт 15 с, и
задачу с тем же `expires` воркер выбрасывает, не кодируя.
Как индексация уступает очередь поиску — `CELERY_TASKS.md`, «Поиск по фото в
`celery_recsys`».

`--max-memory-per-child` (КиБ): дочерний процесс Celery, разросшийся после
задачи больше ≈ 390 МиБ, заменяется свежим (как `max-requests` у gunicorn).

Что будет при упоре в лимит: ядро убивает самый большой процесс внутри этого
контейнера (`docker inspect … State.OOMKilled`, в логах — `WorkerLostError` или
перезапуск), остальной сервер работает. При включённом swap контейнер сначала
может уйти в swap на объём своего лимита (Docker по умолчанию
`memswap = 2 × mem_limit`) — станет медленнее, но не повесит хост.

Перед изменением лимитов снимите свежий снимок (только чтение) и сравните с
таблицей:

```bash
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'
free -m
```

Если какой-то контейнер уже близок к новому лимиту (> 80 %), поднимите его
лимит за счёт других до деплоя, сохранив сумму ≤ 7 ГиБ.

## Redis: брокер отдельно от кэша

- `redis` — брокер (db0) и результаты Celery (db2). `noeviction`: ключи очередей
  без TTL, вытеснять их нельзя. При упоре в `maxmemory` Redis отвечает ошибкой
  на запись (задача не поставится) — это видно в логах, а память сервера цела.
  RDB-снимки по умолчанию (`save 3600 1 300 100 60 10000`) остаются: очереди
  переживают пересоздание контейнера.
- `redis-cache` — кэш Django, троттлинг, служебные блокировки. `allkeys-lru`,
  `--save ""`, без тома: старые ключи вытесняются сами, рестарт просто
  очищает кэш. Блокировки (`recsys:sync-stale:scheduled`, watchdog, single-flight
  источников) в теории тоже вытесняемы; при текущем объёме кэша (единицы МБ)
  до 128 МБ далеко, а потеря блокировки означает лишь повторную постановку
  идемпотентной задачи.
- `REDIS_CACHE_URL=redis://redis-cache:6379/0` задаёт сервисам сам
  `docker-compose.yml` (перекрывает `.env`), поэтому деплой новой версии
  переводит кэш без правки `.env`. `validate_redis_separation` по-прежнему
  требует три разных цели.

## Применение на проде

Только с явного согласия владельца. Изменены описания redis/postgres/qdrant/
frontend/nginx — релиз только полный (`deploy.sh`), `backend_release.py`
откажется.

1. Проверки: `df -h /` (≥ 4 ГиБ свободно), снимок `docker stats` (см. выше),
   `docker exec mudaroba-redis-1 redis-cli INFO memory | grep used_memory_human`
   — должно быть заметно меньше 128 МБ (после чистки 19.10 было ≈ 14 МБ).
2. Сразу, без перезапуска, ограничить текущий Redis (действует до пересоздания
   контейнера, дальше значения берутся из Compose):

   ```bash
   docker exec mudaroba-redis-1 redis-cli CONFIG SET maxmemory 128mb
   docker exec mudaroba-redis-1 redis-cli CONFIG SET maxmemory-policy noeviction
   ```

3. Полный деплой релиза. `deploy.sh` создаёт `redis-cache`
   (`up -d --no-recreate postgres redis redis-cache qdrant`) и пересоздаёт
   backend, воркеры, beat, frontend и nginx уже с новыми лимитами и кэшем в
   `redis-cache`. Postgres, redis и qdrant он не пересоздаёт. После деплоя —
   `docker restart mudaroba-nginx-1` и смоук `/api` через сайт.
4. Лимиты postgres/redis/qdrant применить без перезапуска:

   ```bash
   docker update --memory 640m --memory-swap 1280m mudaroba-postgres-1
   docker update --memory 256m --memory-swap 512m mudaroba-redis-1
   docker update --memory 512m --memory-swap 1024m mudaroba-qdrant-1
   ```

5. Проверка: `curl -s https://mudaroba.com/api/health/` → `"cache":true`;
   `docker exec mudaroba-redis-cache-1 redis-cli INFO keyspace` — ключи
   появляются; `docker exec mudaroba-redis-1 redis-cli CONFIG GET maxmemory*`.
6. Старый кэш в db1 брокера больше никто не читает. Ключи с TTL истекут сами;
   чтобы освободить память сразу (только db1, очереди в db0/db2 не трогает):
   `docker exec mudaroba-redis-1 redis-cli -n 1 FLUSHDB` — с согласия владельца.

Пересоздание брокера без потери очередей (когда нужно, например при смене
версии образа Redis): в окно обслуживания остановить `celerybeat`, записать
`redis-cli LLEN celery`, `LLEN ai`, `LLEN recsys` и `DBSIZE` для db0/db2,
выполнить `redis-cli SAVE`, затем
`docker compose -p mudaroba -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps redis`
(при остановке Redis ещё раз сохраняет RDB, новый контейнер читает тот же том),
сверить счётчики и запустить beat.

Откат: деплой предыдущего тега. Старый Compose берёт `REDIS_CACHE_URL` из
`.env`, то есть кэш вернётся в db1 брокера, где теперь `noeviction` и 128 МБ:
заполнившийся кэш начнёт блокировать постановку задач. Поэтому при откате
сначала вернуть брокеру прежний режим
(`redis-cli CONFIG SET maxmemory 0`) либо прописать в `.env`
`REDIS_CACHE_URL=redis://redis-cache:6379/0` (контейнер `redis-cache` остаётся в
сети `data` и после отката).

## Swap (делает владелец под root)

У `deploy` нет sudo, поэтому swap включается через root: по SSH, если у root
есть ключ, или через консоль Hetzner Cloud (сервер → иконка `>_` «Console»;
пароль root, если его нет, задаётся во вкладке Rescue → «Reset root password»).

Простыми словами: swap — запасная «память» на диске. Когда оперативной памяти
не хватает, ядро переносит туда то, что давно не трогали (например, модели,
которые нужны раз в сутки), вместо того чтобы зависнуть. На диске это медленно,
поэтому `vm.swappiness=10` говорит ядру пользоваться swap только при реальной
нехватке. 4 ГБ — запас на всплеск, а не постоянная добавка памяти.

Перед началом: `df -h /` — нужно ≥ 9 ГБ свободного (4 ГБ swap и 4 ГБ под
образы следующего релиза). Если меньше, сначала сократите журнал systemd
(≈ 2,6 ГБ, см. `PROD_DISK_AND_REDIS.md`).

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
sysctl -p /etc/sysctl.d/99-swappiness.conf
swapon --show
free -h
```

`swapon --show` должен показать `/swapfile 4G`, `free -h` — строку `Swap: 4.0Gi`.
Строка в `/etc/fstab` включает swap после перезагрузки. Убрать:
`swapoff /swapfile`, удалить строку из `/etc/fstab` и файл.

Необязательно, раз уж вы под root — ограничить журнал systemd (освободит
≈ 2,3 ГБ): в `/etc/systemd/journald.conf` задать `SystemMaxUse=300M`, затем
`systemctl restart systemd-journald` и `journalctl --vacuum-size=300M`.
