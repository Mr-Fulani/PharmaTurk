# Технический долг Mudaroba

Актуализировано: **29 августа 2026 года**.

Этот файл — рабочий реестр, а не список пожеланий. Закрытым считается только
пункт, который прошёл тесты, production deploy и короткое наблюдение после
релиза.

- `[x]` — закрыто и проверено;
- `[~]` — код подготовлен, но release gate ещё не завершён;
- `[ ]` — открыто.

Приоритеты: **P0** — блокирует production; **P1** — следующий безопасный релиз;
**P2** — системный долг; **P3** — улучшение.

## Текущий план

- [x] Зафиксировать production baseline, состояние источников, очередей, диска,
  медиа и CI перед изменениями.
- [x] TD-001: исправить состояния и результат фонового обогащения медиа.
- [x] TD-002: автоматизировать полный pre-deploy backup и безопасную retention.
- [x] TD-003: отделить Akakçe discovery БАДов от справочной цены IlacFiyati.
- [x] Прогнать полный backend/frontend/Compose CI для exact commit.
- [x] Создать и проверить новый production backup, выполнить deploy и canary.
- [x] Применить retention, сохранив минимум семь последних
  валидных копий и явно защитив текущую rollback-копию.
- [x] TD-004: перевести обогащение изображений в строго ручной режим с
  карантином кандидатов и обязательной модерацией перед публикацией.
- [ ] Подключить внешний канал ошибок/алертов после предоставления DSN или
  Alertmanager receiver.

## P1 — ближайшие работы

### TD-001 — Обогащение медиа товаров

- **Статус:** `[x]` закрыто в production 29 августа 2026 года.
- **Было:** ранний выход при трёх изображениях и cache-hit мог оставлять товар в
  `processing`; отсутствие результата возвращалось как общий `success`; админка
  сообщала об успехе выполнения сразу после publish и не показывала task ID;
  колонка статуса находилась в несвязанном cleanup mixin.
- **Сделано в текущем изменении:** терминальные статусы и причины для ранних
  выходов, отдельные `success`/`no_changes`/`partial`/`error`, счётчики
  `skipped`/`no_results`, task ID в сообщении админки, перенос метода статуса в
  `MediaEnrichmentMixin`, regression tests.
- **Проверка:** одна canary и bounded cleanup оставшихся 44 записей с уже тремя
  изображениями завершились как `no_changes`, `errors=0`, `skipped=45`; зависших
  `processing` с полным набором изображений больше нет. Новая причина сохранена в
  БД, Celery зарегистрировал и выполнил обе задачи без сетевого поиска.
- Автоматическая обработка `pending` backlog впоследствии отключена в TD-004:
  поиск выполняется только для явно выбранных администратором товаров.

### TD-004 — Ручное обогащение изображений с модерацией

- **Статус:** `[x]` закрыто в production 29 августа 2026 года.
- **Решение:** ночное расписание удалено; задача является no-op без явного списка
  товаров и ID активного сотрудника. Найденные файлы сохраняются отдельно от
  галереи как кандидаты вместе с инициатором, источником и поисковым запросом.
- **Публикация:** только отдельные действия «Одобрить»/«Отклонить» в центральной
  очереди модерации. До одобрения ни карточка товара, ни основное изображение,
  ни галерея не меняются.
- **Проверка:** локально прошли 35 targeted tests и migration drift check; GitHub
  Actions run `33263030248` полностью зелёный и опубликовал exact-SHA образы.
  Release `75b7d6cf56cc09fa6b3654335bb4bc4066dc02bd` развёрнут с backup
  `/home/deploy/backups/pharmaturk/20260829T164012Z_pre_e4469b0`; миграция
  `0205` применена. Production canary подтвердил отсутствие beat-расписания,
  регистрацию admin-модерации и безопасный `manual_selection_required` без
  созданных кандидатов или изменений товарных галерей.

### TD-002 — Backup, retention и заполнение диска

- **Статус:** `[x]` закрыто в production 29 августа 2026 года.
- **Факт аудита:** корневой диск production заполнен на 94%, доступно около
  2.5 GiB; в каталоге находятся 13 pre-deploy копий примерно на 6.7 GiB.
- **Сделано в текущем изменении:** единая команда создаёт PostgreSQL custom dump,
  snapshot каждой живой коллекции Qdrant, защищённую копию `.env`, manifest и
  checksums; cleanup удаляет только созданные этой командой временные snapshots.
  Retention работает в dry-run по умолчанию, требует точного подтверждения для
  apply, принимает текущий и исторический layout и умеет защищать конкретные
  rollback-копии. Для safety logic добавлен shell regression test в CI.
- **Проверка:** backup
  `/home/deploy/backups/pharmaturk/20260829T135402Z_pre_babfac5` содержит
  PostgreSQL dump SHA-256 `c94a4b680ba03ee3de56226ba71c68fad496414beaaf1c112fadb42fdf29cf1c`
  и Qdrant full snapshot SHA-256
  `4ffb3cab0b35ad508f749d1202c648a1f5562e7f99f40fc04099d1784c891dd5`;
  manifest, `pg_restore --list` и tar validation прошли дважды. После review
  dry-run удалены ровно пять старейших валидных копий; семь последних и две
  неполные legacy-копии сохранены. Неиспользуемый Docker build cache также
  удалён; диск перешёл с 94–100% к 78%, свободно 7.9 GiB.
- **Отдельный открытый риск:** копии на том же сервере защищают от неудачного
  релиза, но не от потери хоста. Нужен off-host encrypted backup и периодическая
  restore rehearsal в изолированную БД/Qdrant.

### TD-003 — Связанность IlacFiyati и Akakçe для БАДов

- **Статус:** `[x]` закрыто в production 29 августа 2026 года.
- **Было:** seller discovery Akakçe выполнялся только после успешного обновления
  справочной цены IlacFiyati. Ошибка цены блокировала второй независимый источник,
  а свежая цена могла повторно запускать price task только ради stock discovery.
- **Сделано в текущем изменении:** отдельная идемпотентная Celery-задача Akakçe,
  enqueue lock, повторные попытки только для временных ошибок, общий per-source
  rate/concurrency guard, независимый запуск до разрешения IlacFiyati. Результат
  постановки seller discovery добавлен только в API БАДов. Продажа БАДов по
  актуализированной коммерческой цене по-прежнему не блокируется отсутствием
  предложения Akakçe.
- **Проверка:** public POST для SOLGAR одновременно вернул две отдельные очереди;
  справочная цена завершилась `525.90 TRY` и корректно отобразилась как
  `1235.66 RUB`, Akakçe-задача отдельно завершилась строгим `no_match`. Для
  Betamega проверена конвертация `450.00 TRY → 11.23 USD`. Отказной canary с
  IlacFiyati identity, удалённой только из in-memory объекта, вернул
  `invalid_source`, при этом Akakçe task была поставлена раньше и успешно
  завершилась; сохранённая source identity в БД не менялась.

### Evidence последнего release

- exact commit: `e4469b0953c403aa7eb061a6862fd3b8b4a09ccd`;
- GitHub Actions run: `33255735944`, все jobs успешны;
- migrations: новых операций нет, `migrate --check` успешен;
- backend/frontend/Celery/beat используют exact OCI revision, restarts `0`,
  `OOMKilled=false`;
- public liveness/readiness/security smoke успешен;
- после canary: strict application errors `0`, nginx HTTP 5xx `0`.

### TD-004 — Доставка production-алертов

- **Статус:** `[ ]` открыто; требуется внешняя конфигурация.
- `/metrics`, JSON logging, Sentry integration и правила
  `ops/prometheus/source_offer_alerts.yml` есть в коде, но production Compose не
  поднимает Prometheus/Alertmanager, а `SENTRY_DSN` не задан.
- Нужен один согласованный receiver: Sentry DSN либо Alertmanager webhook с
  Telegram/email/PagerDuty. Секреты и адрес получателя нельзя придумывать или
  коммитить в репозиторий.

### TD-005 — Качество source identity и накопленные ошибки offers

- **Статус:** `[ ]` открыто.
- На baseline есть большие группы `option_not_found` у LCW и единичные ошибки
  Zara/FLO/UMMALAND. Это не P0: typed errors не превращаются в ложное наличие,
  а cart/checkout сохраняют fail-safe семантику.
- Нужны выборочные fixtures из production diagnostics, исправление mapping по
  источникам и backfill только затронутых offers. Массовый обход каталогов без
  source-specific исправления запрещён.

## P2 — системный долг

### TD-006 — Монолитные модули

- `backend/apps/catalog/serializers.py` — около 8 тыс. строк;
- `backend/apps/catalog/models.py` — около 7 тыс. строк;
- `backend/apps/catalog/views.py` — около 5.4 тыс. строк;
- `frontend/src/pages/product/[[...slug]].tsx` — около 3 тыс. строк;
- `backend/apps/orders/views.py` — более 2 тыс. строк.

Разделять нужно по вертикальным контрактам и только под regression tests:
product resolution, pricing, availability/source refresh, cart/checkout,
medicine reference flow и supplement flow. Механическое разбиение одним большим
PR слишком рискованно.

### TD-007 — Неполные quality gates

- **Статус:** `[ ]` открыто.
- Полный pytest, frontend tests/types/build, dependency audit, Django checks и
  migration drift обязательны. Flake8 пока informational из-за большого старого
  baseline; coverage threshold не зафиксирован.
- Следующий шаг: создать измеренный baseline, сделать ошибки только в изменённых
  файлах блокирующими и постепенно снижать общий budget предупреждений. Нельзя
  включать глобальный fail gate до очистки baseline: это остановит все релизы и
  не повысит качество текущих правок.

### TD-008 — Мёртвые/дублирующие Celery декларации

- **Статус:** `[ ]` открыто.
- В `apps/catalog/tasks.py` остаются неиспользуемые заглушки `refresh_stock` и
  `refresh_prices`; `backend/celery_beat_schedule.py` содержит старое отдельное
  расписание и неверный settings module, тогда как runtime использует
  `config/celery.py` и `config/settings.py`.
- Удалять после проверки внешних runbooks/cron и импорта задач. До этого они не
  включены в активный beat schedule и production не влияют.

### TD-009 — Временное исключение security advisory

- **Статус:** `[ ]` контролируемое исключение.
- CI временно игнорирует `PYSEC-2026-3412` для WeasyPrint; внешний контент при
  формировании receipt запрещён. Проверять наличие исправленного upstream release
  при каждом обновлении dependency lock и удалить исключение сразу после
  безопасного upgrade.

## Правила закрытия

Каждый пункт закрывается только после:

1. тестов связанной логики и полного CI;
2. backup и проверки rollback artifact;
3. exact-SHA deploy без миграционного drift;
4. публичного smoke/canary и проверки worker/backend logs;
5. фиксации результата и оставшихся рисков в этом файле.
