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

## Таблицы товаров: autovacuum после массовых правок

20 и 21.10.2026 после массовых правок лекарств (чистка `old_price`,
перескрейпы, применение AI) `/api/catalog/medicines/products` отвечал 8–13 с,
пока не прогнали `VACUUM (ANALYZE)` вручную. У `catalog_medicineproduct`
autovacuum не запускался ни разу (`last_autovacuum` пустой), autoanalyze —
запускался.

### Почему

1. `COUNT(*)` списка читается index-only сканом частичных индексов
   0194/0208/0212 и не трогает `external_data`. Index-only скан дешёв, только
   пока страницы таблицы отмечены в visibility map «все строки видимы».
   UPDATE снимает отметку со своей страницы, вернуть её может только VACUUM.
2. Пороги по умолчанию: autoanalyze — 50 + 10 % изменённых строк (у лекарств
   1353), autovacuum — 50 + 20 % мёртвых (2657). После правки ≈ 2000 строк
   ANALYZE запустился и записал в `pg_class.relallvisible` новую, низкую долю
   видимых страниц, а VACUUM — нет. Без новых правок таблица так и оставалась.
3. Планировщик счёл index-only скан дорогим (почти каждую строку проверять по
   таблице) и выбрал seq scan. Условие `external_data ? 'is_stub'` он считает
   почти бесплатным, а на деле оно детоастит jsonb каждой строки: 394 МБ TOAST
   (тексты инструкций), ≈ 48 тыс. буферов с диска, 12,8 с.

У `catalog_product` то же самое (условия `source_variant_*` и `is_stub`, TOAST
403 МБ), но там порог VACUUM достигался чаще. Остальные доменные таблицы не
страдают: их TOAST мал (БАДы 2,4 МБ), seq scan по ним — миллисекунды.

### Замеры

| Где | Видимых страниц | План `COUNT` | Буферов | Время |
|---|---|---|---|---|
| прод 20–21.10, до ручного VACUUM | — | Seq Scan | ≈ 48 тыс. с диска | 12,8 с |
| прод 21.10 после ручного VACUUM | 100 % | Index Only Scan | 166 | 3,6 мс |
| копия, правка 2000 строк, пороги по умолчанию | 44 % | Seq Scan | 99,7 тыс. | 1,3 с (всё в памяти) |
| копия, правка 2000 строк, пороги 0218 | 100 % | Index Only Scan | 49 | 10 мс |

Копия — синтетическая таблица той же формы, что на проде: 13 035 строк,
heap 25 МБ, TOAST 407 МБ, те же частичные индексы, тот же SQL `COUNT`, правка
`UPDATE … SET old_price = NULL` пачками по 500, как в
`clear_heuristic_old_prices`. В логе копии с порогами по умолчанию — только
`automatic analyze`, с 0218 — `automatic vacuum` (0,25 с) через минуту после
правки, затем analyze. План переключается на seq scan, когда видимыми остаются
меньше ≈ 75 % страниц: хватает ≈ 550 изменённых строк (4 % таблицы), если после
них прошёл ANALYZE, а VACUUM — нет. На проде seq scan оценивается всего в
4,5 раза дороже index-only (3718 против 820), хотя на деле медленнее в тысячи раз.

### Что сделано

Миграция `catalog.0218` для `catalog_product` и `catalog_medicineproduct`:
`autovacuum_vacuum_scale_factor = 0.01` и
`autovacuum_vacuum_insert_scale_factor = 0.01`. Теперь VACUUM приходит раньше
ANALYZE: у лекарств после 180 мёртвых строк (ANALYZE — после 1353 изменений),
у Product — после 311 (ANALYZE — 2660); после вставок — 1130 и 1261.
TOAST-таблицы берут те же значения. Повторный VACUUM дешёвый: уже видимые
страницы он пропускает. Это работает для любой правки — команд, Celery,
админки, AI — без VACUUM в коде каждой команды. Тест —
`apps/catalog/tests/test_product_tables_autovacuum.py`.

После деплоя ничего делать не нужно: `migrate` ставит настройки за доли
секунды (блокировка `SHARE UPDATE EXCLUSIVE`, чтение и запись не ждут).

### Если список всё же тормозит

Только чтение:

```sql
SELECT relname, n_dead_tup, n_mod_since_analyze, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables WHERE relname IN ('catalog_product', 'catalog_medicineproduct');
SELECT relname, reloptions, round(relallvisible::numeric / greatest(relpages, 1), 2) AS visible
FROM pg_class WHERE relname IN ('catalog_product', 'catalog_medicineproduct');
```

`visible` ниже 0,75 при пустом `reloptions` — миграция не применена; при
заполненном — autovacuum ещё не догнал правку или ему мешает долгая транзакция
(VACUUM не отмечает видимыми строки моложе самой старой открытой транзакции):

```sql
SELECT pid, now() - xact_start AS age, state, left(query, 80)
FROM pg_stat_activity WHERE xact_start < now() - interval '10 minutes';
```

Лечение — обычный VACUUM, без блокировок, ≈ 2,5 мин на обе таблицы:

```sql
VACUUM (ANALYZE) catalog_medicineproduct;
VACUUM (ANALYZE) catalog_product;
```

### Что решили не делать

- **Булев столбец `is_stub` вместо условия на jsonb.** Seq scan тогда не
  детоастил бы, и план не зависел бы от VACUUM. Но в `catalog_product` то же
  делают ключи `source_variant_id`/`source_variant_slug` — нужно 2–3 столбца,
  пересоздать 12 частичных индексов (0194/0195/0208/0212/0217), поменять
  фильтры в `views.py` и `querysets.py` и поддерживать флаги при каждой записи
  `external_data`. `GeneratedField` перезаписал бы таблицы с 400 МБ TOAST под
  исключительной блокировкой, а заполнение обычного столбца — само массовая
  правка всех строк. Вернуться к этому при следующей переделке выборок.
- **VACUUM в конце массовых команд.** Его пришлось бы добавлять в каждую
  команду и задачу (и не забывать в новых), а внутри транзакции он не
  работает. Пониженный порог закрывает все пути записи сразу.

## Дальше

- Рост `django_session` (≈ 2–3 тыс. в сутки) создают `orders/views.py`
  (корзина) и `catalog/views.py` (избранное): `request.session.save()` для
  каждого анонима без cookie. Ночная чистка держит таблицу в пределах
  `SESSION_COOKIE_AGE` (2 недели). Убрать запись сессии для ботов — отдельная
  задача.
- Таблица логов теперь стабильна (≈ 30 дней логов), повторный `VACUUM FULL` не
  нужен: autovacuum переиспользует место.
