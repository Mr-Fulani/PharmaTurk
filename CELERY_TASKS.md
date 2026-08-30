# Celery: очереди и задачи по расписанию

Источник правды для расписания — `CELERY_BEAT_SCHEDULE` в `backend/config/settings.py`. Инициализация приложения находится в `backend/config/celery.py`; задачи обнаруживаются через `autodiscover_tasks()`.

Временная зона проекта — `Europe/Moscow`. Расписания `crontab` ниже указаны в этой зоне. Интервалы (`10 минут`, `4 часа`, `7 дней`) отсчитываются Celery Beat и не привязаны к конкретному часу суток.

## Очереди и workers

| Шаблон задачи | Очередь | Worker в Compose |
|---|---|---|
| `apps.ai.tasks.*` | `ai` | `celery_ai` |
| `apps.recommendations.tasks.*` | `recsys` | `celery_recsys` |
| `apps.payments.tasks.*` | `celery` | `celeryworker` |
| `currency.*` | `celery` | `celeryworker` |
| Остальные задачи без route | очередь Celery по умолчанию | `celeryworker` |

Beat только публикует задачи. Для исполнения должны одновременно работать Redis и worker нужной очереди. В одном окружении должен быть только один активный экземпляр `celerybeat`, иначе периодические задачи могут публиковаться несколько раз.

## Активное расписание

| Имя schedule | Задача | Расписание | Очередь | Основной эффект |
|---|---|---|---|---|
| `currency-update-rates` | `currency.update_rates` | каждые 4 часа | `celery` | Обновляет курсы валют. |
| `currency-update-prices` | `currency.update_product_prices` | каждые 24 часа | `celery` | Вызывает `update_product_prices`, batch size 200. |
| `cleanup-scraper-sessions` | `apps.scrapers.tasks.cleanup_old_sessions` | каждые 7 дней | `celery` | Удаляет сессии и логи скрапинга старше 30 дней. |
| `orders-cleanup-stale-anonymous-carts` | `orders.cleanup_stale_anonymous_carts` | ежедневно `04:10` | `celery` | Батчами удаляет неактивные анонимные корзины; user carts не затрагивает. |
| `scrapers-weekly-duplicate-candidates` | `apps.scrapers.tasks.find_and_merge_duplicates` | понедельник `04:30` | `celery` | Ищет и сохраняет кандидатов на ручную дедупликацию. |
| `cleanup-orphaned-media` | `catalog.cleanup_orphaned_media` | ежедневно `03:00` | `celery` | Удаляет безопасно определённые orphaned media. |
| `payments-expire-crypto-invoices` | `apps.payments.tasks.expire_pending_crypto_payments` | каждые 10 минут | `celery` | Помечает просроченные pending crypto invoices как `expired`. |
| `ai-cleanup-old-logs` | `apps.ai.tasks.cleanup_old_ai_logs` | каждые 7 дней | `ai` | Удаляет `completed`/`approved` AI-логи старше 30 дней. |
| `recsys-sync-stale-nightly` | `apps.recommendations.tasks.sync_stale_products_to_qdrant` | ежедневно `02:15` | `recsys` | Ставит на индексацию до 200 новых/изменённых товаров батчами по 25. |
| `cleanup-temp-images` | `apps.recommendations.tasks.cleanup_temp_images` | каждый час | `recsys` | Удаляет файлы старше часа из storage-префикса `temp/`. |

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

Обе задачи перехватывают исключения и возвращают `{"status": "error"}` вместо обязательного Celery failure. Поэтому мониторинг должен проверять не только state задачи, но и её result/log message.

### Проверка supplier offers

Фоновая Celery-задача supplier offers удалена из реестра и расписания. Внешние
проверки выполняются только по пользовательскому событию: при открытии карточки
товара и один раз при открытии корзины. Добавление/изменение строки и checkout
используют сохранённый snapshot без сетевого обращения к поставщику.

### Очистка скраперных данных

`cleanup_old_sessions(30)` удаляет `ScrapingSession` и `ScrapedProductLog` старше cutoff. Это реальное удаление данных, поэтому изменение retention требует отдельного решения по аудиту и резервному копированию.

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

- в `DEBUG=True` пропускает выполнение;
- исключает защищённые AI/temp/avatar и чужие environment prefixes;
- прекращает удаление, если в БД найдено меньше 100 media paths;
- прекращает удаление, если кандидаты составляют более половины storage;
- возвращает `skipped`/`aborted`/`error` как результат, поэтому эти состояния нужно мониторить отдельно.

Это защитные ограничения, а не гарантия резервного копирования. Перед сменой `R2_PREFIX`, storage backend или структуры media paths необходим отдельный dry audit.

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

### Временные изображения visual search

Каждый час `cleanup_temp_images` проверяет файлы непосредственно в `temp/` через `default_storage` и удаляет те, чьё время изменения старше одного часа. Задача работает и с локальным, и с S3-совместимым storage, но результат зависит от поддержки `listdir()` и `get_modified_time()` конкретным backend.

## AI-задачи, исключённые из Beat

Следующие задачи существуют, но запускаются вручную через `/admin/ai/manual-tasks/`, потому что могут расходовать OpenAI-токены:

- `process_uncategorized` — категоризация товаров без категории;
- `process_without_description` — генерация отсутствующих описаний;
- `retry_failed_processing` — повтор AI-ошибок за последние 7 дней.

Они публикуются в очередь `ai` и по умолчанию используют `auto_apply=False`.

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
