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
что dev-сервер Next прожорливее). Сумма — 6,84 ГиБ, системе остаётся
≈ 0,7 ГиБ плюс swap 4 ГиБ. Тест `scripts/release/test_compose_memory.py`
не даёт сумме превысить 7 ГиБ и требует лимит у каждого постоянного сервиса.

| Сервис | mem_limit | Почему столько |
|---|---|---|
| backend | 1,5 ГиБ | без изменений: 2 gunicorn-воркера, поиск по фото грузит CLIP (≈ 0,7 ГБ) |
| celery_recsys | 1,5 ГиБ | было 3g; CLIP + MiniLM в памяти ≈ 1,3 ГБ, concurrency 1 |
| qdrant | 768 МиБ | векторы в RAM, данные ≈ 0,7 ГБ на диске |
| postgres | 640 МиБ | shared_buffers 128 МБ + соединения; кэш страниц ОС освобождается сам |
| celeryworker | 640 МиБ | было 3g; concurrency 2, `--max-memory-per-child=400000` |
| frontend | 512 МиБ | Next.js production-сервер |
| celery_ai | 512 МиБ | было 3g; concurrency 2 (ждёт OpenAI), `--max-memory-per-child=400000` |
| redis (брокер) | 384 МиБ | `maxmemory 192mb`, вдвое больше — запас на fork при BGSAVE |
| redis-cache | 192 МиБ | `maxmemory 128mb`, без записи на диск и fork |
| celerybeat | 160 МиБ | один процесс планировщика |
| nginx | 128 МиБ | процессы nginx; кэш `proxy_media` на диске |

`--max-memory-per-child` (КиБ): дочерний процесс Celery, разросшийся после
задачи больше ≈ 390 МиБ, заменяется свежим (как `max-requests` у gunicorn).

Что будет при упоре в лимит: ядро убивает самый большой процесс внутри этого
контейнера (`docker inspect … State.OOMKilled`, в логах — `WorkerLostError` или
перезапуск), остальной сервер работает. При включённом swap контейнер сначала
может уйти в swap на объём своего лимита (Docker по умолчанию
`memswap = 2 × mem_limit`) — станет медленнее, но не повесит хост.

Цифры выбраны по составу процессов, без снимка `docker stats` с прода. Перед
применением снимите его (только чтение) и сравните с таблицей:

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
   — должно быть заметно меньше 192 МБ (после чистки 19.10 было ≈ 14 МБ).
2. Сразу, без перезапуска, ограничить текущий Redis (действует до пересоздания
   контейнера, дальше значения берутся из Compose):

   ```bash
   docker exec mudaroba-redis-1 redis-cli CONFIG SET maxmemory 192mb
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
   docker update --memory 384m --memory-swap 768m mudaroba-redis-1
   docker update --memory 768m --memory-swap 1536m mudaroba-qdrant-1
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
`.env`, то есть кэш вернётся в db1 брокера, где теперь `noeviction` и 192 МБ:
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
