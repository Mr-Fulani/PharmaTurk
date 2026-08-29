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
- [~] TD-001: исправить состояния и результат фонового обогащения медиа.
- [~] TD-002: автоматизировать полный pre-deploy backup и безопасную retention.
- [~] TD-003: отделить Akakçe discovery БАДов от справочной цены IlacFiyati.
- [ ] Прогнать полный backend/frontend/Compose CI для exact commit.
- [ ] Создать и проверить новый production backup, выполнить deploy и canary.
- [ ] После окна наблюдения применить retention, сохранив минимум семь последних
  валидных копий и явно защитив текущую rollback-копию.
- [ ] Подключить внешний канал ошибок/алертов после предоставления DSN или
  Alertmanager receiver.

## P1 — ближайшие работы

### TD-001 — Обогащение медиа товаров

- **Статус:** `[~]` исправление подготовлено.
- **Было:** ранний выход при трёх изображениях и cache-hit мог оставлять товар в
  `processing`; отсутствие результата возвращалось как общий `success`; админка
  сообщала об успехе выполнения сразу после publish и не показывала task ID;
  колонка статуса находилась в несвязанном cleanup mixin.
- **Сделано в текущем изменении:** терминальные статусы и причины для ранних
  выходов, отдельные `success`/`no_changes`/`partial`/`error`, счётчики
  `skipped`/`no_results`, task ID в сообщении админки, перенос метода статуса в
  `MediaEnrichmentMixin`, regression tests.
- **Осталось для закрытия:** CI, deploy, проверка Celery logs; затем безопасно
  вернуть в очередь накопившиеся `pending` и зависшие `processing` записи
  ограниченными партиями.

### TD-002 — Backup, retention и заполнение диска

- **Статус:** `[~]` automation подготовлена; production retention не запускалась.
- **Факт аудита:** корневой диск production заполнен на 94%, доступно около
  2.5 GiB; в каталоге находятся 13 pre-deploy копий примерно на 6.7 GiB.
- **Сделано в текущем изменении:** единая команда создаёт PostgreSQL custom dump,
  snapshot каждой живой коллекции Qdrant, защищённую копию `.env`, manifest и
  checksums; cleanup удаляет только созданные этой командой временные snapshots.
  Retention работает в dry-run по умолчанию, требует точного подтверждения для
  apply, принимает текущий и исторический layout и умеет защищать конкретные
  rollback-копии. Для safety logic добавлен shell regression test в CI.
- **Осталось для закрытия:** CI; новый проверенный backup; review точного dry-run;
  удаление только подтверждённых старых копий; повторная проверка диска.
- **Отдельный открытый риск:** копии на том же сервере защищают от неудачного
  релиза, но не от потери хоста. Нужен off-host encrypted backup и периодическая
  restore rehearsal в изолированную БД/Qdrant.

### TD-003 — Связанность IlacFiyati и Akakçe для БАДов

- **Статус:** `[~]` исправление подготовлено.
- **Было:** seller discovery Akakçe выполнялся только после успешного обновления
  справочной цены IlacFiyati. Ошибка цены блокировала второй независимый источник,
  а свежая цена могла повторно запускать price task только ради stock discovery.
- **Сделано в текущем изменении:** отдельная идемпотентная Celery-задача Akakçe,
  enqueue lock, повторные попытки только для временных ошибок, общий per-source
  rate/concurrency guard, независимый запуск до разрешения IlacFiyati. Результат
  постановки seller discovery добавлен только в API БАДов. Продажа БАДов по
  актуализированной коммерческой цене по-прежнему не блокируется отсутствием
  предложения Akakçe.
- **Осталось для закрытия:** CI, production canary для (1) успешных обоих
  источников и (2) отказа IlacFiyati при работающем Akakçe.

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
