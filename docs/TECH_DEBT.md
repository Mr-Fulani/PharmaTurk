# Технический долг Mudaroba

Актуализировано: **5 сентября 2026 года**.

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
- [x] TD-005: исправить source-specific разрешение вариантов LCW/Zara и
  безопасно переклассифицировать накопленные терминальные ошибки offers.
- [x] TD-007: сделать flake8 и backend coverage измеренными блокирующими
  quality gates без остановки релизов из-за старого baseline.
- [x] Исправить диагностику ручного поиска: ошибки Serper не маскируются под
  корректный пустой результат, placeholder-штрихкоды не отправляются во внешние
  API, а поисковое имя очищается от локализованного описательного хвоста.
- [x] Упорядочить главную страницу Django Admin и собрать модерацию, товарные
  изображения и медиа маркетинговых баннеров в единый блок без изменения
  моделей, прав, URL и бизнес-логики.
- [ ] Восстановить доступ Serper (проверить ключ/credits в кабинете) либо
  подключить второй image-search provider, затем вручную повторить RINVOQ.
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

#### Инцидент RINVOQ — пустая очередь модерации

- **Причина:** ручная задача действительно завершилась без кандидатов. Значение
  штрихкода `not specified` ошибочно уходило в OpenFoodFacts, а Serper отвечал
  `HTTP 400` на каждый image-запрос. Старый обработчик превращал отказ provider в
  обычный пустой список, записывал `completed / Изображений не найдено` и создавал
  отрицательный cache на семь дней.
- **Исправление:** `MediaSearchProviderError` сохраняет безопасную причину отказа
  без headers/credentials; после первой ошибки повторные Serper-запросы в том же
  запуске прекращаются; provider failure получает статус `failed` и не кэшируется.
  GTIN теперь принимается только как 8/12/13/14 цифр, а для RINVOQ основной запрос
  сокращается до `RINVOQ 15 MG` с действующим веществом в уточняющем варианте.
  Корректный пустой результат показывается отдельно как «Нет новых изображений».
- **Проверка:** 40 targeted tests, system check и migration drift прошли локально;
  GitHub Actions run `33265728310` полностью зелёный. Exact release
  `5b8ff8f8342fe413d0ed288ed78a7a480e7efedd` развёрнут в production с backup
  `/home/deploy/backups/pharmaturk/20260829T174011Z_pre_75b7d6c`. Read-only canary
  подтвердил пропуск placeholder barcode, compact query, новый admin-status и
  отсутствие кандидатов без повторного внешнего запуска. Public health зелёный.
- **Остаётся внешняя зависимость:** существующий ключ настроен, но provider должен
  снова принимать запросы. Автоматический retry намеренно не добавлен: после
  восстановления Serper администратор повторяет поиск вручную.

### Навигация Django Admin

- **Статус:** `[x]` закрыто в production 29 августа 2026 года.
- **Причина:** проект содержал подготовленный `MudarobaAdminSite`, но стандартный
  `django.contrib.admin` не активировал его. Заголовки менялись из нескольких
  доменных admin-модулей, а связанные с изображениями модели находились в разных
  местах длинного стандартного списка.
- **Сделано:** custom site подключён через `AdminConfig.default_site`; заголовки
  определены централизованно. Главная страница сгруппирована по рабочим областям,
  а блок «Изображения и медиа» содержит «Модерация изображений», «Изображения
  товаров» и «Маркетинг — Медиа баннеров». Страницы отдельных приложений оставлены
  стандартными; регистрации `ModelAdmin`, формы, permissions, model URLs и данные
  не менялись. Миграций нет.
- **Проверка:** regression tests покрывают активацию custom site, состав и порядок
  media-блока, сохранение URL/permissions и стандартный app index. GitHub Actions
  run `33268850385` полностью зелёный. Exact release
  `7c846a2487a4d96ceed6532981b9e6bdcbaad456` развёрнут с проверенным backup
  `/home/deploy/backups/pharmaturk/20260829T185203Z_pre_5b8ff8f`. Browser-canary и
  backend-canary подтвердили новый заголовок, все три ссылки, public health, БД и
  cache. По правилу keep-7 удалена старая валидная копия
  `/home/deploy/backups/pharmaturk/20260828T173952Z_pre_f411d42_to_6299680`;
  сохранены семь более новых и текущая rollback-копия. Неиспользуемые образы
  релиза `75b7d6c` удалены, текущий `7c846a2` и rollback `5b8ff8f` сохранены;
  заполнение диска снижено с 88% до 81%.

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

- **Статус:** `[x]` базовая доставка закрыта 2026-09-04 через существующий
  административный Telegram receiver.
- Периодический production watchdog проверяет homepage, liveness и readiness,
  требует два последовательных сбоя, дедуплицирует инцидент, напоминает не чаще
  раза в час и отправляет recovery. Конфигурация валидируется Django system check;
  токен не попадает в логи. Runbook: `docs/PRODUCTION_MONITORING_RUNBOOK.md`.
- `/metrics`, JSON logging и source-offer rules остаются в коде. Внешний монитор
  полного отказа Docker host/Internet/Redis broker и Prometheus/Grafana dashboards
  остаются расширением P1.5, а не частью базовой доставки.

### TD-005 — Качество source identity и накопленные ошибки offers

- **Статус:** `[x]` закрыто в production 5 сентября 2026 года.
- **Baseline:** текущий `option_not_found` был подтверждён у 1453 активных LCW
  offers и 41 Zara offers. У LCW страницы явно показывали распроданный родительский
  вариант без прежнего списка размеров; у Zara товар сохранялся, но исторический
  color/variant ID больше не присутствовал в payload. Ошибки оставались fail-safe:
  ложное наличие и оплата не разрешались.
- **Исправление:** LCW считает отсутствующий сохранённый размер терминальным только
  когда сам родительский вариант явно недоступен; неоднозначный доступный вариант
  по-прежнему возвращает typed `option_not_found`. Zara требует совпадение product
  identity, переопределяет изменившийся variant ID только по единственному
  совпадению сохранённого цвета и помечает исчезнувший цвет как `discontinued`.
  Общий verification service разрешает отсутствие цены только для блокирующих
  `out_of_stock`/`discontinued`, сохраняя последнюю известную цену; доступный товар
  без цены остаётся `malformed_response`.
- **Backfill:** dry-run отобрал ровно 1494 записи и 0 неоднозначных. После двух
  live canary транзакционно переклассифицированы оставшиеся 1452 LCW и 40 Zara
  offers без source traffic. Повторный dry-run вернул `eligible=0`; текущих
  `option_not_found` у LCW/Zara не осталось. LCW canary `13280` сохранился как
  `out_of_stock/boolean` с `parent_variant_out_of_stock`; Zara canary `9553` — как
  `discontinued/boolean` с `variant_no_longer_listed` и прежней ценой `1490 TRY`.
- **Проверка и release:** source-specific изменение прошло PR `#21` и main CI
  runs `33911642579`/`33912547329`; terminal-price guard — PR `#22` и runs
  `33915060515`/`33915905114`. Exact release
  `841c107a82f9282906a0f9c037995df18ed3ce4b` развёрнут с валидированным backup
  `/home/deploy/backups/pharmaturk/20260904T204418Z_pre_0c85ca3` (manifest
  SHA-256 `4ca7bdc91f0cd2204a3a687cc1253ed63f223c0b31e9558f055fcdafd4e343a7`).
  Public liveness/readiness, Django check и production watchdog зелёные; строгих
  application errors после релиза не обнаружено. Активная stub-refresh задача
  `#97` восстановлена тем же Celery ID без дубля и продолжила работу с 0 ошибок.
- **Оставшийся риск:** upstream payload может измениться снова. Неоднозначные
  варианты намеренно остаются typed errors; массовый обход без нового
  source-specific canary по-прежнему запрещён.

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

- **Статус:** `[x]` закрыто 5 сентября 2026 года.
- В PR #24 flake8 переведён из informational в incremental blocking gate:
  измеренный общий baseline ограничен 3030 замечаниями, в каждом изменённом
  Python-файле число замечаний не может расти, а новые и скопированные файлы
  должны начинаться с нуля. Unit-тесты фиксируют контракты add/modify/delete,
  rename/copy, нормализации путей и сравнения baseline.
- Первый полный CI run `33923532879` подтвердил baseline: flake8 `3030/3030`,
  `1407 passed`, `30 subtests passed`, coverage `64.73%` по 47 846 строкам.
  Блокирующий coverage floor установлен на 64%, чтобы небольшой запас на
  различия окружения не создавал ложных падений.
- Финальный PR CI `33924569064` и main CI `33925629643` для merge
  `bcdb8dec371d450a0125067f93b60e763a1ef20b` полностью зелёные. Main подтвердил
  flake8 `3030/3030`, coverage `64.73%`, обязательный floor 64%, `1407 passed` и
  `30 subtests passed`; exact-revision production images собраны и опубликованы.
- Перед rollout создан и проверен backup
  `/home/deploy/backups/pharmaturk/20260904T224222Z_pre_841c107`: PostgreSQL
  `146083464` байта, Qdrant `402036736` байт, `.env` `8879` байт, все файлы mode
  `600`; SHA-256 manifest
  `9ab1bd0ecd21a3eeecbf7b3c4c4480881046ccb71443beb621918af181080ab3`.
  PostgreSQL/Qdrant SHA-256:
  `72d5431acc60c1cad01b5e278fc5a9b8cfcba5de12a1209209d8d67fdcf3e156` /
  `d330e389cb5e4b084c4217f266617c92a77f6378cf6a22ae14c7083d8d1df86e`.
- Merge SHA развёрнут в production с rollback
  `841c107a82f9282906a0f9c037995df18ed3ce4b`; migration plan пуст. Public
  liveness/readiness вернули `status=ok`, DB/cache healthy, Django check чистый,
  watchdog имеет `active=false, failures=0`, а строгий поиск свежих
  `ERROR/CRITICAL/Traceback` дал 0. OCI revision labels совпадают с merge SHA,
  runtime users — `app` и `node`.
- Stub-refresh задача `#97` восстановлена не новым запуском, а атомарным Kombu
  `restore_by_tag` той же unacked delivery: Celery ID
  `4011070d-06b8-4be0-a696-a2c5c7a70fa3`, kwargs `offset=757, after_id=2861`,
  `redelivered=true`. После deploy прогресс вырос `759 → 761`, cursor
  `2863 → 2867`, ошибок 0.
- **Оставшийся риск:** baseline 3030 и floor 64% защищают от регрессии, но не
  заменяют постепенную выплату старого долга. Budget следует только снижать,
  coverage повышать, а 44 существующих frontend `no-img-element` warning
  устранять отдельными небольшими PR. После загрузки нового релиза на production
  осталось около 1.4 GiB (97% использования); дальнейшая очистка требует
  отдельного списка точных targets и подтверждения.

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
