# Celery: очереди и задачи по расписанию

Источник правды для расписания — `CELERY_BEAT_SCHEDULE` в `backend/config/settings.py`. Инициализация приложения находится в `backend/config/celery.py`; задачи обнаруживаются через `autodiscover_tasks()`.

Временная зона проекта — `Europe/Moscow`. Расписания `crontab` ниже указаны в этой зоне. Интервалы (`10 минут`, `4 часа`, `7 дней`) отсчитываются Celery Beat и не привязаны к конкретному часу суток.

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
| `monitoring-production-watchdog` | `apps.monitoring.tasks.run_production_watchdog` | каждые 5 минут | `celery` | Проверяет homepage/liveness/readiness и доставляет дедуплицированные Telegram alert/recovery. |
| `monitoring-database-backup` | `apps.monitoring.tasks.run_database_backup` | ежедневно `01:15` UTC | `celery` | `pg_dump` потоком во внешний бакет, ротация 7/4/3, Telegram при сбое; только при `DB_BACKUP_ENABLED=true`. |
| `monitoring-database-backup-check` | `apps.monitoring.tasks.check_database_backup` | воскресенье `01:45` UTC | `celery` | Свежесть, SHA-256 и `pg_restore --list` последней копии; по флагу — пробное восстановление. |
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
| `catalog-recompute-sort-ranks` | `catalog.recompute_sort_ranks` | ежедневно `04:50` | `celery` | Пересчитывает `sort_rank` медикаментов и БАДов — порядок «Популярные» (по умолчанию) на их страницах. |
| `payments-expire-crypto-invoices` | `apps.payments.tasks.expire_pending_crypto_payments` | каждые 10 минут | `celery` | Помечает просроченные pending crypto invoices как `expired`. |
| `monitoring-server-resources` | `apps.monitoring.tasks.check_server_resources` | каждые 10 минут | `celery` | Свободное место на диске, память и снимки обоих Redis; алерт и «в норме» в Telegram, повтор не чаще раза в 6 ч (`docs/PROD_DISK_AND_REDIS.md`). |
| `ai-cleanup-old-logs` | `apps.ai.tasks.cleanup_old_ai_logs` | воскресенье `04:40` | `ai` | Удаляет `completed`/`approved` AI-логи старше 30 дней. |
| `recsys-sync-stale-nightly` | `apps.recommendations.tasks.sync_stale_products_to_qdrant` | ежедневно `02:15` | `recsys` | Ставит на индексацию до 200 новых/изменённых товаров батчами по 25. |
| `cleanup-temp-images` | `apps.recommendations.tasks.cleanup_temp_images` | каждый час | `recsys` | Удаляет файлы старше часа из storage-префикса `temp/`. |
| `monitoring-media-backup` | `apps.monitoring.tasks.run_media_backup` | ежедневно `02:00` | `celery` | Копия `marketing/`, `pages/`, `services/` бакета медиа в бакет бэкапов (`media/`): только новое и изменённое, пропавшие файлы хранятся 30 дней; при `MEDIA_BACKUP_ENABLED` (= `DB_BACKUP_ENABLED`). `docs/DB_BACKUP.md`, «Копия медиа». |
| `monitoring-media-backup-check` | `apps.monitoring.tasks.check_media_backup` | воскресенье `02:30` | `celery` | Копия медиа свежая (не старше 26 ч) и полная по манифесту; Telegram при сбое. |

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
- `run_ai_maintenance(run_id, dry_run)` — предпросмотр и выполнение «Перегенерировать отклонённые названия» / «Закрыть решённые записи модерации».

Обе идут в очередь `ai`; если `celery_ai` остановлен, прогон через 5 минут покажется зависшим, а партия — остановится через 30 минут.

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
