# База прода: сессии, логи парсеров, VACUUM

Снимок 2026-10-19 (только чтение): база 2,75 ГБ.

| Таблица | Размер | Строк | Что внутри |
|---|---|---|---|
| `scrapers_scrapedproductlog` | 773 МБ (таблица 31 МБ, TOAST 727 МБ) | 14 713, из них 13 720 старше 30 дней | логи парсеров; живые `scraped_data` в сжатом виде ≈ 19 МБ, остальное TOAST — мёртвое место от прошлых обновлений и удалений |
| `django_session` | 590 МБ (таблица 275 МБ, индексы 314 МБ) | 312 010, из них 286 036 просрочены (с 14.06) | почти пустые сессии (≈ 78 байт данных): анонимная корзина и избранное открывают сессию каждому посетителю без cookie, в том числе ботам. Всплеск 15–28.06 — ≈ 250 тыс. |

## Почему не чистилось

- Сессии Django: `clearsessions` не был в расписании.
- Логи парсеров: задача `cleanup-scraper-sessions` (ретенция 30 дней) стояла с
  интервалом «раз в 7 дней». Состояние beat (`/app/celerybeat-schedule`) живёт в
  слое контейнера и пропадает при каждом пересоздании `celerybeat` (деплой).
  Интервал отсчитывается от старта beat, а деплои чаще раза в неделю —
  задача не срабатывала ни разу. То же относится к любому интервалу длиннее,
  чем время между деплоями (см. `CELERY_TASKS.md`).

## Что сделано в коде

- `users-clear-expired-sessions` — `manage.py clearsessions` каждую ночь в
  04:00 МСК. У `Session` нет связей и сигналов: это один `DELETE` без загрузки
  строк в память. В обычный день — 2–3 тыс. строк.
- `cleanup-scraper-sessions` — каждую ночь в 04:20 МСК (crontab, не интервал),
  ретенция 30 дней, удаление пачками по 1000 строк, каждая пачка — своя
  транзакция: блокируются только удаляемые строки, память воркера не растёт.
  Индекс по `created_at` уже есть (`scrapers_sc_created_6ac29e_idx`), новый не нужен.

После деплоя первая же ночь удалит накопленное: ≈ 286 тыс. сессий и ≈ 13,7 тыс.
логов. Это и есть «первая чистка». Если нужно сделать её раньше и под контролем,
выполните шаги ниже до деплоя или сразу после него, днём при малой нагрузке.

## Первая чистка и VACUUM (по согласию владельца)

Сколько освободится:

| Действие | Диск | Блокировки |
|---|---|---|
| Удаление + обычный `VACUUM` | файлы почти не уменьшатся; ≈ 1,3 ГБ станут свободным местом **внутри** таблиц и будут переиспользованы, рост остановится | `VACUUM` не мешает чтению и записи (`SHARE UPDATE EXCLUSIVE`) |
| + `VACUUM FULL` двух таблиц | ≈ 1,3 ГБ вернутся ОС: логи 773 МБ → ≈ 20 МБ, сессии 590 МБ → ≈ 15 МБ; база ≈ 2,75 → ≈ 1,45 ГБ | `ACCESS EXCLUSIVE` на таблицу на время переписывания живых строк — единицы секунд при таком объёме |

`VACUUM FULL` переписывает таблицу заново: пока идёт, к ней нельзя ни читать, ни
писать. Для `django_session` это значит, что запросы с сессией (админка,
анонимная корзина) подождут несколько секунд; для логов — запись логов
парсером. Нужно свободного места на размер живых данных (десятки МБ).
`lock_timeout` ниже не даёт `VACUUM FULL` встать в очередь за долгой
транзакцией и заблокировать всех за собой: при неудаче просто повторить.

`pg_repack` (переписывание без долгой блокировки) в образе `postgres:15-alpine`
не установлен; ставить расширение ради двух таблиц по 20 МБ живых данных не
стоит.

### Шаги

Окно — тихий час, например 05:15 МСК (02:15 UTC на сервере), не во время
ночных задач 04:00–04:50.

```bash
# Короткая обёртка: SQL из stdin в базу прода
psql_prod() { docker exec -i mudaroba-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'; }

# 0. Место и бэкап двух таблиц (≈ 50 МБ в gzip)
df -h /
docker exec mudaroba-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t scrapers_scrapedproductlog -t django_session' \
  | gzip > ~/backups/pre-db-cleanup-$(date +%Y%m%d-%H%M).sql.gz
ls -lh ~/backups/pre-db-cleanup-*.sql.gz

# 1. Удаление (после деплоя этого PR — теми же задачами, что ночью)
docker exec mudaroba-backend-1 poetry run python manage.py clearsessions
docker exec mudaroba-backend-1 poetry run python manage.py shell -c \
  "from apps.scrapers.tasks import cleanup_old_sessions; print(cleanup_old_sessions.run(30))"

# 2. Обычный VACUUM (без блокировок)
psql_prod <<'SQL'
VACUUM (ANALYZE, VERBOSE) django_session;
VACUUM (ANALYZE, VERBOSE) scrapers_scrapedproductlog;
SQL

# 3. Только если нужно вернуть место ОС: VACUUM FULL, по одной таблице
psql_prod <<'SQL'
SET lock_timeout = '5s';
VACUUM (FULL, ANALYZE) scrapers_scrapedproductlog;
VACUUM (FULL, ANALYZE) django_session;
SQL

# 4. Проверка
psql_prod <<'SQL'
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables WHERE relname IN ('django_session', 'scrapers_scrapedproductlog');
SELECT pg_size_pretty(pg_database_size(current_database()));
SQL
df -h /
curl -s https://mudaroba.com/api/health/
```

До деплоя этого PR шаг 1 можно выполнить так же: `clearsessions` есть в Django,
а старая `cleanup_old_sessions(30)` удаляет те же логи одним запросом (13,7 тыс.
строк — допустимо).

Бэкап удалить после проверки работы сайта (через несколько дней), с согласия
владельца. Откат: `gunzip -c <файл> | psql_prod` — дамп создаёт таблицы заново, поэтому
сначала переименовать текущие (`ALTER TABLE … RENAME TO …_new`) и после
проверки удалить лишнее.

## Дальше

- Рост `django_session` (≈ 2–3 тыс. в сутки) создают `orders/views.py`
  (корзина) и `catalog/views.py` (избранное): `request.session.save()` для
  каждого анонима без cookie. Ночная чистка держит таблицу в пределах
  `SESSION_COOKIE_AGE` (2 недели). Убрать запись сессии для ботов — отдельная
  задача.
- Таблица логов теперь стабильна (≈ 30 дней логов), повторный `VACUUM FULL` не
  нужен: autovacuum переиспользует место.
