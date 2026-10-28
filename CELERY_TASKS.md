# Celery: очереди и задачи по расписанию

Источник правды для расписания — `CELERY_BEAT_SCHEDULE` в `backend/config/settings.py`. Инициализация приложения находится в `backend/config/celery.py`; задачи обнаруживаются через `autodiscover_tasks()`.

Временная зона проекта — `Europe/Moscow`: `CELERY_TIMEZONE` не задан, поэтому Celery берёт `TIME_ZONE` из настроек Django (`enable_utc` остаётся включённым). Расписания `crontab` ниже указаны по МСК. Интервалы (`каждую минуту`, `10 минут`, `каждый час`) отсчитываются Celery Beat и не привязаны к конкретному часу суток.

Состояние beat (`/app/celerybeat-schedule`) живёт в слое контейнера и пропадает при каждом пересоздании `celerybeat`, то есть при деплое. Интервал после этого отсчитывается заново, поэтому задача с интервалом длиннее промежутка между деплоями может не сработать никогда (так было с `cleanup-scraper-sessions` раз в 7 дней). Всё, что реже нескольких раз в час, ставьте через `crontab`.

## Очереди и workers

| Шаблон задачи | Очередь | Worker в Compose |
|---|---|---|
| `apps.ai.tasks.*` | `ai` | `celery_ai` |
| `apps.recommendations.tasks.encode_search_image` | `recsys_search` | `celery_recsys` |
| `apps.recommendations.tasks.*` | `recsys` | `celery_recsys` |
| `apps.payments.tasks.*` | `celery` | `celeryworker` |
| `apps.monitoring.tasks.*` | `celery` | `celeryworker` |
| `currency.*` | `celery` | `celeryworker` |
| Остальные задачи без route | очередь Celery по умолчанию | `celeryworker` |

Beat только публикует задачи. Для исполнения должны одновременно работать Redis и worker нужной очереди. В одном окружении должен быть только один активный экземпляр `celerybeat`, иначе периодические задачи могут публиковаться несколько раз.

## Активное расписание

| Имя schedule | Задача | Расписание | Очередь | Основной эффект |
|---|---|---|---|---|
| `catalog-brand-product-counts` | `catalog.refresh_brand_product_counts` | каждые 60 секунд (`expires` 60 с) | `celery` | Пересчитывает число публичных товаров по брендам (всего и по типу товара) в кэш, TTL 15 минут; при уже идущем пересчёте возвращает `already_running`. |
| `monitoring-production-watchdog` | `apps.monitoring.tasks.run_production_watchdog` | каждые 5 минут | `celery` | Проверяет homepage/liveness/readiness и доставляет дедуплицированные Telegram alert/recovery. |
| `monitoring-database-backup` | `apps.monitoring.tasks.run_database_backup` | ежедневно `01:15` | `celery` | `pg_dump` потоком во внешний бакет, ротация 7/4/3, Telegram при сбое; только при `DB_BACKUP_ENABLED=true`. |
| `monitoring-database-backup-check` | `apps.monitoring.tasks.check_database_backup` | воскресенье `01:45` | `celery` | Свежесть, SHA-256 и `pg_restore --list` последней копии; по флагу — пробное восстановление. |
| `coinremitter-outbox-dispatch` | `apps.payments.tasks.dispatch_pending_crypto_invoice_requests` | каждую минуту | `celery` | Подбирает durable pending invoice requests, пропущенные immediate publish. |
| `coinremitter-reconciliation` | `apps.payments.tasks.reconcile_coinremitter_state` | каждые 5 минут | `celery` | Карантинирует stale provider claims и пишет read-only drift summary. |
| `currency-update-rates` | `currency.update_rates` | каждые 4 часа: `00:05`, `04:05`, … `20:05` | `celery` | Обновляет курсы валют. |
| `currency-update-prices` | `currency.update_product_prices` | ежедневно `05:00` | `celery` | Вызывает `update_product_prices`, batch size 200. |
| `users-clear-expired-sessions` | `users.clear_expired_sessions` | ежедневно `04:00` | `celery` | `manage.py clearsessions`: удаляет просроченные сессии Django. |
| `cleanup-scraper-sessions` | `apps.scrapers.tasks.cleanup_old_sessions` | ежедневно `04:20` | `celery` | Пачками по 1000 удаляет логи товаров (`ScrapedProductLog`) и сессии скрапинга старше 30 дней. |
| `orders-cleanup-stale-anonymous-carts` | `orders.cleanup_stale_anonymous_carts` | ежедневно `04:10` | `celery` | Батчами удаляет неактивные анонимные корзины; user carts не затрагивает. |
| `orders-remind-abandoned-carts` | `orders.remind_abandoned_carts` | ежечасно `:20` | `celery` | Напоминания о неотправленном Списке заявки (email/Telegram) по настройкам в админке; по умолчанию выключены, без них задача ничего не делает. До 50 корзин за запуск; см. `docs/CART_REMINDERS.md`. |
| `scrapers-weekly-duplicate-candidates` | `apps.scrapers.tasks.find_and_merge_duplicates` | понедельник `04:30` | `celery` | Ищет и сохраняет кандидатов на ручную дедупликацию. |
| `cleanup-orphaned-media` | `catalog.cleanup_orphaned_media` | воскресенье `03:30` | `celery` | Удаляет безопасно определённые orphaned media; при превышении лимита — только отчёт в Telegram. |
| `catalog-expire-new-badges` | `catalog.expire_new_badges` | ежедневно `03:40` | `celery` | Снимает «Новинку» (`is_new`) с товаров, добавленных раньше `NEW_BADGE_DAYS` дней назад (по умолчанию 30). |
| `catalog-recompute-sort-ranks` | `catalog.recompute_sort_ranks` | ежедневно `04:50` | `celery` | Пересчитывает `sort_rank` медикаментов и БАДов — порядок «Популярные» (по умолчанию) на их страницах. |
| `catalog-generate-yml-feeds` | `catalog.generate_yml_feeds` | каждые 6 часов: `00:35`, `06:35`, `12:35`, `18:35` | `celery` | Собирает готовые YML-фиды (корневые категории, затем полный каталог) частями до 7,5 МБ / 15 000 офферов в файлы `feeds/yml/` хранилища; лекарства не выгружаются; эндпоинт фида отдаёт их как есть. `docs/VK_YML_FEED.md`. |
| `payments-expire-crypto-invoices` | `apps.payments.tasks.expire_pending_crypto_payments` | каждые 10 минут | `celery` | Помечает просроченные pending crypto invoices как `expired`. |
| `monitoring-server-resources` | `apps.monitoring.tasks.check_server_resources` | каждые 10 минут | `celery` | Свободное место на диске, память и снимки обоих Redis; алерт и «в норме» в Telegram, повтор не чаще раза в 6 ч (`docs/PROD_DISK_AND_REDIS.md`). |
| `ai-cleanup-old-logs` | `apps.ai.tasks.cleanup_old_ai_logs` | воскресенье `04:40` | `ai` | Удаляет `completed`/`approved` AI-логи старше 30 дней. |
| `recsys-sync-stale-nightly` | `apps.recommendations.tasks.sync_stale_products_to_qdrant` | ежедневно `02:15` | `recsys` | Ставит на индексацию до 200 новых/изменённых товаров батчами по 25. |
| `cleanup-temp-images` | `apps.recommendations.tasks.cleanup_temp_images` | каждый час | `recsys` | Удаляет файлы старше часа из storage-префикса `temp/`. |
| `monitoring-media-backup` | `apps.monitoring.tasks.run_media_backup` | ежедневно `02:00` | `celery` | Копия `marketing/`, `pages/`, `services/` бакета медиа в бакет бэкапов (`media/`): только новое и изменённое, пропавшие файлы хранятся 30 дней; при `MEDIA_BACKUP_ENABLED` (= `DB_BACKUP_ENABLED`). `docs/DB_BACKUP.md`, «Копия медиа». |
| `monitoring-media-backup-check` | `apps.monitoring.tasks.check_media_backup` | воскресенье `02:30` | `celery` | Копия медиа свежая (не старше 26 ч) и полная по манифесту; Telegram при сбое. |
| `catalog-nightly-stock-check` | `catalog.nightly_stock_check` | каждые 10 минут `01:00`–`04:50` и `06:00`–`06:20` (05:xx — пересчёт цен) | `celery` | Пачка ночной сверки наличия у бесплатных источников (LCW, IKEA, UmmaLand), ≤ 8 минут; только при `NIGHTLY_STOCK_CHECK_ENABLED=true`. `docs/NIGHTLY_STOCK_CHECK.md`. |
| `catalog-nightly-stock-check-report` | `catalog.nightly_stock_check_report` | ежедневно `06:45` | `celery` | Итог ночной сверки владельцу в Telegram: сколько проверено, закончилось, вернулось, пропало у продавца. |

### Обогащение медиа лекарств

Автоматическое расписание отключено. `catalog.enrich_medicine_media` запускается только
ручным действием администратора для явно выбранных `MedicineProduct` или
`SupplementProduct`. Вызов без `product_ids` и ID активного сотрудника ничего
не обрабатывает. Инициатор сохраняется у каждого найденного кандидата.

Найденные файлы сохраняются как `MediaEnrichmentCandidate` и не добавляются в
товарную галерею. Перенос в `MedicineProductImage`/`SupplementProductImage`
выполняется только после явного одобрения в разделе «Модерация изображений».

### Валюты

`currency.update_rates` вызывает `CurrencyRateService.update_rates()`. `currency.update_product_prices` запускает management-команду пересчёта и не обновляет курс повторно внутри того же запуска.

Обе задачи стоят на `crontab`, а не на интервалах: состояние beat пропадает при каждом деплое, и интервал отсчитывался заново — курсы обновлялись с разрывами 9–12 ч, а пересчёт раз в 24 ч при нескольких деплоях в сутки не срабатывал. Пересчёт в `05:00` идёт после ночного окна `02:15`–`04:50` и на курсах `04:05`; `catalog.recompute_sort_ranks` (`04:50`) от сконвертированных цен не зависит — смотрит только на наличие базовой цены.

Обе задачи перехватывают исключения и возвращают `{"status": "error"}` вместо обязательного Celery failure. Поэтому мониторинг должен проверять не только state задачи, но и её result/log message.

### Production watchdog

Watchdog включается только явным `PRODUCTION_WATCHDOG_ENABLED=true`. Он делает
три публичных HTTPS-запроса, не следует redirect и проверяет точные JSON-контракты
liveness/readiness. Состояние инцидента хранится в cache: два последовательных
сбоя открывают alert, повторное сообщение возможно не чаще раза в час, успешное
восстановление закрывает инцидент отдельным сообщением. При недоступном cache
readiness-alert не подавляется. Полная процедура описана в
`docs/PRODUCTION_MONITORING_RUNBOOK.md`.

### Бэкап базы

Ежедневная копия PostgreSQL во внешний S3-совместимый бакет (Cloudflare R2) и
еженедельная проверка. Выключены, пока не задан `DB_BACKUP_ENABLED=true` с
ключами отдельного бакета. Устройство, включение и восстановление —
`docs/DB_BACKUP.md`. Ручной запуск: `manage.py db_backup [--check]`.

### CoinRemitter outbox

`create_coinremitter_invoice_request` выполняет внешний `invoice/create` только
после DB commit. Локальная идемпотентность обеспечивается единственной durable
строкой `CryptoInvoiceRequest` и atomic claim. Так как CoinRemitter не принимает
provider idempotency key, любой неоднозначный результат получает статус
`uncertain` и не ставится на автоматический retry. Подробности и процедура
ручной сверки описаны в `CRYPTO_PAYMENTS.md`. Dispatcher соблюдает интервал
`COINREMITTER_OUTBOX_REPUBLISH_SECONDS`, чтобы не накапливать копии сообщений
каждую минуту во время остановки worker.

### Проверка supplier offers

Фоновая Celery-задача supplier offers удалена из реестра и расписания. Внешние
проверки выполняются только по пользовательскому событию: при открытии карточки
товара и один раз при открытии корзины. Добавление/изменение строки и checkout
используют сохранённый snapshot без сетевого обращения к поставщику.

### Ночная сверка наличия

`catalog.nightly_stock_check` (с 28.10.2026) — единственная плановая проверка у
продавцов: товары «в наличии» бесплатных источников открываются тем же путём, что
и карточка при открытии (цена, наличие, цвета и размеры). Платные источники (FLO,
Zara/Inditex, Akakçe) не сверяются. Пачка занимает один слот `celeryworker` до
8 минут из каждых 10, вторая пачка не стартует, пока идёт первая (блокировка в
кэше). Пропавший у продавца товар становится кандидатом «Неактуальные товары», а
не удаляется. Устройство, предохранители и включение — `docs/NIGHTLY_STOCK_CHECK.md`.

### Очистка скраперных данных

`cleanup_old_sessions(30)` удаляет `ScrapedProductLog`, затем `ScrapingSession` старше cutoff пачками (`batch_size`, по умолчанию 1000, допустимо 1..10000), каждая пачка — отдельная транзакция. Это реальное удаление данных, поэтому изменение retention требует отдельного решения по аудиту и резервному копированию. Первая чистка накопленного и `VACUUM` — `docs/PROD_DB_MAINTENANCE.md`.

### Сессии Django

`users.clear_expired_sessions` вызывает `manage.py clearsessions`. У `Session` нет связей и сигналов, удаление — один `DELETE` без загрузки строк в память. Сессии создают анонимная корзина и избранное, ≈ 2–3 тыс. в сутки.

### Очистка анонимных корзин

`orders.cleanup_stale_anonymous_carts` удаляет только `Cart` с `user IS NULL`, у которых
не было записей ни в саму корзину, ни в её `CartItem` после cutoff. Корзины
авторизованных пользователей не удаляются. Retention и batch задаются через
`ANONYMOUS_CART_TTL_DAYS` (по умолчанию 30) и `ANONYMOUS_CART_CLEANUP_BATCH_SIZE` (по умолчанию 500,
допустимо 1..10000).

Перед сменой retention проверьте объём без удаления:

```bash
docker compose exec backend poetry run python manage.py shell -c \
  "from apps.orders.tasks import cleanup_stale_anonymous_carts as t; print(t.run(days=30, dry_run=True))"
```

Результат содержит `matched`, `deleted`, `dry_run`, `retention_days`. В production сначала
выполните dry-run и оцените `matched`; сам scheduled cleanup не является backup-механизмом.

### Кандидаты в дубликаты

Несмотря на историческое имя `find_and_merge_duplicates`, scheduled task **не объединяет товары автоматически**. Она:

1. сканирует каталог;
2. создаёт или обновляет `ProductDuplicateCandidate`;
3. оставляет кандидатов в `pending_moderation`;
4. отправляет Telegram-сводку, если поиск нашёл кандидатов и уведомления настроены.

Модерация находится в `/admin/scrapers/productduplicatecandidate/`. То же сканирование доступно из admin action; выбор отдельных товаров не ограничивает область — проверяется весь каталог.

### Очистка orphaned media

`catalog.cleanup_orphaned_media`:

- раз в неделю, воскресенье `03:30`: тихий час и не вместе с `recsys-sync-stale-nightly` (02:15);
- в `DEBUG=True` пропускает выполнение;
- память: пути из БД читаются `values_list(...).iterator()` и хранятся только как
  8-байтовые отпечатки (blake2b) в отсортированном массиве; R2 читается потоково
  (постраничный листинг бакета), полный список ключей не строится. Совпадение
  отпечатков может только сохранить файл, но не удалить его;
- исключает защищённые AI/temp/avatar и чужие environment prefixes;
- ничего не удаляет и шлёт отчёт админу в Telegram (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`), если:
  какое-то поле с медиа в БД не прочиталось; в БД меньше 100 путей; к удалению больше
  `ORPHANED_MEDIA_MAX_DELETE` файлов (по умолчанию 3000) или больше
  `ORPHANED_MEDIA_MAX_DELETE_PERCENT` процентов хранилища (по умолчанию 10);
- ошибка листинга или БД тоже приходит в Telegram, удаление не начинается;
- возвращает `skipped`/`aborted`/`dry_run`/`error`/`success` и счётчики `db_paths`, `storage`,
  `orphaned`, `protected_excluded`, `deleted`.

Отчёт без удаления и ручной запуск с другим лимитом после проверки отчёта:

```bash
docker compose exec celeryworker poetry run python manage.py shell -c \
  "from apps.catalog.tasks import cleanup_orphaned_media as t; print(t.run(dry_run=True))"
docker compose exec celeryworker poetry run python manage.py shell -c \
  "from apps.catalog.tasks import cleanup_orphaned_media as t; print(t.run(max_delete=6000))"
```

Это защитные ограничения, а не гарантия резервного копирования. Перед сменой `R2_PREFIX`, storage backend или структуры media paths необходим отдельный dry audit.

### Чистка products/parsed/ после парсинга

Не задача Beat: `_sweep_parsed_orphans` (`apps/scrapers/tasks.py`) вызывается, когда
цепочка задачи парсера завершилась, и удаляет из `products/parsed/<парсер>/` файлы,
на которые не ссылается ни одно поле БД. Это копии, уже перенесённые сигналами в
читаемые пути, и медиа пропущенных дублей. Резервной копии медиа товаров нет, поэтому
(с 22.10.2026):

- ссылки ищутся пакетно (`apps/catalog/utils/media_references.py`): по одному запросу
  `LIKE` на каждое поле с медиа во всех моделях (FileField, URLField и текстовые поля
  с медийным именем — 272 поля на проде), а не по запросу на файл; путь находится в имени
  файла, в URL CDN и в `?path=` proxy-media. Ошибка любого запроса — ничего не удаляется;
- файлы моложе `PARSED_MEDIA_SWEEP_MIN_AGE_HOURS` (6 ч) не трогаются: их могла только что
  скачать другая задача, ещё не записав строку товара; они удалятся следующим проходом;
- пока у парсера есть задача `pending`/`running`, чистка пропускается (зависшая в
  `running` задача её откладывает — тогда отменить задачу в админке);
- в БД меньше 100 товаров (пустая или чужая база, как стек 14.06.2026) — ничего не удаляется;
- кандидатов больше `PARSED_MEDIA_SWEEP_MAX_DELETE` (20 000) — ничего не удаляется, админу
  приходит отчёт в Telegram. Доля от числа файлов не проверяется, как у
  `cleanup_orphaned_media`: после переноса ничейными становятся почти все файлы прохода
  (21.10.2026 у ilacfiyati — 2540 из 2885, из них 2518 моложе 6 ч);
- ключи листинга считаются относительно `R2_PREFIX`: на dev чистится `dev/products/parsed/…`.

Отчёт без удаления и ручной запуск с другим лимитом после проверки:

```bash
docker compose exec celeryworker poetry run python manage.py shell -c \
  "from apps.scrapers.tasks import _sweep_parsed_orphans as s; print(s('ilacfiyati', dry_run=True))"
docker compose exec celeryworker poetry run python manage.py shell -c \
  "from apps.scrapers.tasks import _sweep_parsed_orphans as s; print(s('ilacfiyati', max_delete=40000))"
```

Та же пакетная проверка, тоже закрытая при сбое, защищает старое главное фото, которое
парсер удаляет после переключения `main_image_file` на файл галереи
(`ScraperIntegrationService._media_key_referenced`).

### YML-фиды для ВК Маркета и Яндекса

`catalog.generate_yml_feeds` собирает фид каждой активной корневой категории и
полного каталога потоком во временные файлы частями до 7,5 МБ / 15 000 офферов
(лимиты ВК), кладёт в хранилище (`feeds/yml/`, на проде — R2) и переключает записи
`YMLFeedSnapshot` (раздел + часть); прежний файл удаляется после переключения,
лишние части прежней сборки и фиды выключенных или заблокированных разделов
(лекарства) — тоже. Ошибка одного раздела не останавливает остальные, прежний
файл раздела остаётся в силе. Повторный запуск во время сборки возвращает
`already_running`. Без готового файла эндпоинт отвечает 503 и сам ставит сборку.
`catalog.sync_vk_photos` (без расписания) — фото в ВК по кнопке в админке, итог
в Telegram. Подробности — `docs/VK_YML_FEED.md`.

### Ранг медикаментов и БАДов

`catalog.recompute_sort_ranks` (`services/catalog_sort_rank.py`) для
`MedicineProduct` и `SupplementProduct` пишет в
`sort_rank` число из разрядов: цена и наличие → ручной `is_featured` → спрос
(заявки, корзины, избранное, запросы проверки цены; с потолком) → качество
карточки (фото, русское описание). Товары без цены всегда ниже товаров с ценой.
Список читает готовое поле по частичным индексам 0212 и 0214, без агрегатов в запросе.
`bulk_update` не трогает `updated_at` и shadow-sync. После первого деплоя запустить
один раз вручную, иначе до 04:50 у всех ранг 0 и порядок — по `id`.

### Истечение крипто-инвойсов

Каждые 10 минут задача одним DB update переводит записи `CryptoPayment` со статусом `pending` и прошедшим `expires_at` в `expired`. Остатки она не изменяет и уведомление об истечении не отправляет. Если таблица ещё не создана во время rollout, известная ошибка `does not exist` обрабатывается как временный no-op.

### Очистка AI-логов

Единственная AI-задача в Beat не вызывает OpenAI. Она удаляет только старые логи со статусами `completed` и `approved`; `failed`, `moderation`, `pending`, `processing` и `rejected` этим фильтром не удаляются.

Она маршрутизируется в `ai`, поэтому остановленный `celery_ai` задержит и эту сервисную очистку, даже если стандартный worker работает.

### Инкрементальная RecSys-индексация

Ночной scheduler выбирает доступные товары без актуального `vector_data.last_synced`, не более 200 за запуск, и публикует батчи по 25. Redis lock на 6 часов защищает от повторной постановки того же scheduled прохода.

Эта задача использует локальные SentenceTransformer/CLIP и Qdrant, не OpenAI. Она не строит пользовательские профили. Полная переиндексация остаётся ручной операцией:

```bash
docker compose exec celery_recsys poetry run python manage.py sync_product_vectors --full
docker compose exec celery_recsys poetry run python manage.py sync_product_vectors --until-done
docker compose exec celery_recsys poetry run python manage.py sync_product_vectors --force --until-done
docker compose exec backend poetry run python manage.py clear_similar_cache
```

`--force` сбрасывает marker синхронизации и создаёт существенно более тяжёлую нагрузку; применять его следует только при подтверждённом рассинхроне.

### Поиск по фото в `celery_recsys`

POST `/api/recommendations/search_by_image/` не грузит CLIP в веб-процесс: веб проверяет картинку, кладёт её уменьшенную копию (PNG ≤ 512 px) в задачу `encode_search_image` (очередь `recsys_search`) и ждёт вектор 15 секунд (`expires` у задачи такой же — опоздавшую задачу воркер выбросит). Таймаут, ошибка задачи или недоступный брокер — ответ 503 `search_unavailable`.

Тот же однопоточный `celery_recsys` ведёт индексацию, поэтому:

- воркер слушает `-Q recsys_search,recsys` с `--disable-prefetch` — следующую задачу он берёт из Redis только при свободном слоте и не держит в памяти заранее взятый батч индексации;
- задача индексации, запущенная воркером, перед каждым следующим товаром смотрит длину списка `recsys_search` в брокере и, если поиск ждёт, ставит оставшиеся товары новой задачей (`priority=3`) и завершается. Поиск ждёт не больше одного товара (картинка + CLIP, обычно 1–2 с). Прямой вызов из `sync_product_vectors` батч не прерывает.

При старте воркер, слушающий `recsys_search`, сам ставит туда задачу на картинке 32×32 (сигнал `worker_ready`): импорт torch и загрузка CLIP (≈ 15–17 с) проходят сразу, а не на первом поиске, который иначе не уложился бы в 15 секунд.

Проверка очереди на проде (только чтение): `docker exec mudaroba-redis-1 redis-cli LLEN recsys_search` — в норме 0.

### Временные изображения visual search

Каждый час `cleanup_temp_images` проверяет файлы непосредственно в `temp/` через `default_storage` и удаляет те, чьё время изменения старше одного часа. Задача работает и с локальным, и с S3-совместимым storage, но результат зависит от поддержки `listdir()` и `get_modified_time()` конкретным backend.

## AI-задачи, исключённые из Beat

Следующие задачи существуют, но запускаются вручную через `/admin/ai/manual-tasks/`, потому что могут расходовать OpenAI-токены:

- `process_uncategorized` — категоризация товаров без категории;
- `process_without_description` — генерация отсутствующих описаний;
- `retry_failed_processing` — повтор AI-ошибок за последние 7 дней.

Они публикуются в очередь `ai` и по умолчанию используют `auto_apply=False`.

Массовые AI-прогоны из раздела админки «AI → AI-прогоны» (см. [docs/AI_RUNS_ADMIN_GUIDE.md](docs/AI_RUNS_ADMIN_GUIDE.md)) тоже не входят в Beat:

- `advance_ai_run(run_id, token)` — короткий шаг прогона: проверяет партию, ставит следующую и перепланирует себя через 15 с (`priority=0`, `acks_late`);
- `run_ai_maintenance(run_id, dry_run)` — предпросмотр и выполнение «Перегенерировать отклонённые названия» / «Закрыть решённые записи модерации»;
- `preview_medicine_paragraph_run(run_id)` — «Посчитать» для перевода абзацев инструкций лекарств: абзацы, которых нет в памяти, части, запросы и оценка цены (`priority=0`);
- `advance_medicine_paragraph_run(run_id, token)` — шаг перевода абзацев через OpenAI Batch API: проверяет часть, забирает готовую, отправляет следующую и перепланирует себя через 5 минут (`priority=0`, `acks_late`).

Все идут в очередь `ai`; если `celery_ai` остановлен, прогон товаров через 5 минут покажется зависшим, а партия — остановится через 30 минут; прогон абзацев считается зависшим через 20 минут без шага.

## Другие отключённые scheduled entries

В `CELERY_BEAT_SCHEDULE` закомментированы:

- `refresh-stock` — текущая реализация является заглушкой;
- `run-all-scrapers` — автоматический запуск всех активных скраперов;
- `vapi-sync-products`, `vapi-sync-categories`, `vapi-full-sync` — VAPI-интеграция.

Для включения недостаточно только раскомментировать строку: нужно проверить credentials, идемпотентность, время выполнения, queue capacity и наблюдаемость. VAPI HTTP API проекта отдельно защищён staff-only permissions; это не заменяет проверку фоновых credentials.

## Задачи без Beat

Существуют, но не планируются автоматически:

- `currency.cleanup_old_logs`;
- `currency.health_check`;
- `currency.refresh_margin_snapshots`;
- `currency.refresh_usdt_price_snapshots`;
- `catalog.sync_ikea_products`;
- `catalog.refresh_product_card_source` — обновляет цену и наличие одной спарсенной карточки из первоисточника, без импорта контента; ставит `POST catalog/products/<slug>/source-refresh`, который фронтенд шлёт при открытии карточки;
- `catalog.refresh_medicine_market_check` — проверяет справочную цену лекарства и его аналогов; ставит `POST catalog/medicines/products/<slug>/market-check` по кнопке проверки цены на карточке;
- `catalog.refresh_supplement_market_check` — то же для справочной цены БАДа; ставит `POST catalog/supplements/products/<slug>/market-check`, который карточка БАДа шлёт сама при открытии;
- `catalog.discover_supplement_stock_offer` — ищет продавца (offer) БАДа независимо от справочной цены; ставит тот же `market-check` БАДа, если активного offer ещё нет;
- `apps.scrapers.tasks.run_scraper_task` — запуск парсера чанками, каждый чанк ставит следующий; ставят админка (запуск `ScraperConfig`, задача парсинга сайта) и `manage.py run_scraper --async`;
- `apps.scrapers.tasks.run_stub_refresh_task` — обновление заглушек лекарств короткими чанками с ID-курсором; ставит запуск задачи парсинга сайта с типом «Обновление заглушек» в админке, дальше — сама себя;
- `apps.scrapers.tasks.run_instagram_scraper_task` — парсинг Instagram; ставит запуск «Задачи парсинга Instagram» в админке;
- `apps.feedback.tasks.notify_admin_product_review` — Telegram админу о новом или изменённом отзыве на модерации; ставит API отзывов;
- `apps.feedback.tasks.notify_admin_product_question` — Telegram админу о новом вопросе о товаре; ставит API вопросов;
- `apps.feedback.tasks.notify_review_author_reply` — автору отзыва об ответе магазина (Telegram, если включён, и email); ставит сохранение ответа в админке отзывов;
- точечная и полная индексация рекомендаций;
- AI batch/variant tasks;
- задачи уведомлений заказов и криптоплатежей.

## Операционная проверка

Статус процессов и последние логи:

```bash
docker compose ps celeryworker celery_ai celery_recsys celerybeat redis
docker compose logs --tail=200 celerybeat
docker compose logs --tail=200 celeryworker
docker compose logs --tail=200 celery_ai
docker compose logs --tail=200 celery_recsys
```

Зарегистрированные задачи и текущая загрузка workers:

```bash
docker compose exec celeryworker poetry run celery -A config inspect registered
docker compose exec celeryworker poetry run celery -A config inspect active
docker compose exec celeryworker poetry run celery -A config inspect reserved
```

`inspect scheduled` показывает ETA/countdown задачи, уже переданные workers, но не является полным представлением будущего расписания Beat. Для проверки конфигурации сравнивайте `CELERY_BEAT_SCHEDULE` и startup logs `celerybeat`.

После изменения schedule или task routes необходимо перезапустить Beat и затронутые workers. Не удаляйте файл состояния Beat во время работающего процесса; сначала корректно остановите единственный экземпляр.
