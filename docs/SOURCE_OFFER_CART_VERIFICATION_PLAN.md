# Проверка цены и наличия первоисточника в корзине

Статус: production rollout для IKEA, Ummaland и LCW завершён: recording, live
verification, bounded background refresh и cart/checkout enforcement включены и
подтверждены canary. Catalog projection намеренно выключен до стабильного окна;
FLO/Zara ожидают доверенного proxy CA/provider fix и повторного стабильного canary,
а Alertmanager, отдельный staging smoke и fake-stock cleanup остаются открыты.
Создан: 2026-08-27
Последняя проверка по коду: 2026-08-28
Ответственный контур: `scrapers` → `catalog` → `orders/cart` → `checkout/payments` → frontend

Этот документ — рабочий источник правды по внедрению проверки supplier offer при
добавлении товара в корзину и перед оформлением заказа. При расхождении плана с
исполняемым кодом приоритет имеет код; расхождение сначала фиксируется здесь, затем
план корректируется до следующей правки.

## Правила ведения статуса

- `[ ]` — не начато или не подтверждено проверками.
- `[x]` — завершено, связанная логика проанализирована, критерии приёмки выполнены.
- Пункт нельзя закрывать только на основании написанного кода.
- Для каждого закрытого пункта в журнале работ указываются изменённые файлы,
  связанные контуры, точные команды проверок и их результат.
- Если проверка не запускалась из-за окружения, пункт остаётся открытым.
- В один момент реализуется один небольшой логический шаг. Массовые смешанные
  рефакторинги корзины, каталога и парсеров не допускаются.

## Зафиксированные решения

- Полный импорт-парсер не запускается из HTTP-контроллера корзины.
- Для проверки одного предложения вводится лёгкий read-only контракт `check_offer`.
- Проверяется конкретный buyable offer: источник + SKU/вариант + размер, а не только
  общий `Product`.
- Точный остаток хранится только когда источник действительно его сообщает.
  Значения `1000` и `3` не считаются реальным количеством.
- `source_unreachable` не приравнивается к `out_of_stock`.
- GET корзины остаётся без внешних HTTP-вызовов и без новых side effects.
- Перед checkout выполняется обязательная внешняя проверка вне DB-транзакции.
- Повышение цены требует явного подтверждения пользователя; снижение можно применить
  автоматически с уведомлением.
- Недоступная строка не удаляется молча: она остаётся видимой с причиной и действиями.
- Проверка парсером не считается резервированием товара у поставщика.
- В заказе сохраняется неизменяемый snapshot источника, SKU, закупочной цены и проверки.

## Обязательный протокол перед каждой правкой

Перед изменением:

- [ ] определить владельца бизнес-правила: parser, source-offer service, catalog,
  cart, checkout, payment или frontend;
- [ ] найти все вызовы и потребителей изменяемых функций/полей через `rg`;
- [ ] проверить модели, миграции, admin, serializers, API schema, Celery tasks и сигналы;
- [ ] проверить влияние на shadow `Product`, доменные товары, варианты и размеры;
- [ ] проверить цену источника, конвертацию валют, маржу, промокод, доставку и итоги;
- [ ] проверить anonymous/user cart identity, merge корзин, TTL и throttling;
- [ ] для checkout проверить обычный заказ, crypto invoice, paid webhook, повторный
  webhook, конкурентный checkout и списание/резерв;
- [ ] определить обратную совместимость API и необходимость feature flag;
- [ ] определить rollback до внесения миграции или изменения данных.

После изменения:

- [ ] просмотреть полный `git diff` и убедиться, что нет несвязанных правок;
- [ ] выполнить `git diff --check`;
- [ ] запустить минимальные unit/contract tests изменённого слоя;
- [ ] запустить связанные integration tests соседних слоёв;
- [ ] при изменении cart/checkout/payments проверить пересчёт суммы и card/crypto flow;
- [ ] при изменении frontend выполнить lint, typecheck и затронутые тесты;
- [ ] проверить OpenAPI/serializer response и RU/EN локализацию новых сообщений;
- [ ] обновить чекбоксы и журнал работ только после фактических проверок.

## Связанная логика, которую нельзя потерять

| Контур | Что необходимо сохранить |
| --- | --- |
| Parser registry | безопасный выбор parser по сохранённому source URL/domain |
| Scraper import | дедупликация, category/brand mapping, media pipeline, AI guards |
| Catalog | generic `Product`, доменные модели, shadow products, variants/sizes |
| Pricing | исходная цена и валюта, конвертация, глобальная/товарная маржа, `Decimal` |
| Cart identity | anonymous session, user cart, merge, unique constraints, TTL cleanup |
| Cart calculations | promo, shipping options, free-shipping threshold, totals |
| Checkout | row locks, повторная отправка, cart fingerprint, отсутствие двойного заказа |
| Payments | crypto invoice, paid webhook, идемпотентность, повторное списание |
| API/frontend | обратная совместимость, локализация, состояния строки, GTM events |
| SEO/feed | одинаковые цена/наличие в карточке, JSON-LD, checkout и feed |

## Фаза 0. Анализ и фиксация плана

- [x] Изучен единый контракт `ScrapedProduct` и `BaseScraper`.
- [x] Проверен parser registry и выбор parser по URL/domain.
- [x] Проанализированы Zara/Inditex, FLO, LCW, IKEA, Ummaland, IlacFiyati,
  Ilacabak и Instagram.
- [x] Подтверждены условные остатки `1000/3` и отсутствие точного stock у части источников.
- [x] Проанализированы add/update cart, сериализация цены, checkout и crypto webhook.
- [x] Зафиксирована целевая двухфазная архитектура проверки.
- [x] Создан постоянный рабочий план и правила закрытия пунктов.

Критерий завершения фазы: документ добавлен в индекс документации, исходный код не
изменён. Фаза не означает начало реализации.

## Фаза 1. Контракт данных источника

- [x] Зафиксировать финальную схему `ProductSourceOffer` до миграции.
- [x] Определить гранулярность: одна запись на buyable SKU/вариант/размер.
- [x] Добавить статусы availability: `in_stock`, `out_of_stock`, `limited`,
  `discontinued`, `unknown`, `source_unreachable`, `unsupported`.
- [x] Добавить `stock_precision`: `exact`, `boolean`, `unknown`.
- [x] Хранить исходную цену только как `Decimal` и отдельно от публичной цены магазина.
- [x] Добавить parser/config, canonical URL, external SKU/ID, variant/size keys,
  priority, timestamps и диагностическое состояние.
- [x] Спроектировать уникальные ограничения и индексы без блокирующей data migration.
- [x] Сделать schema migration отдельно от backfill.
- [x] Добавить admin только для диагностики; критические source-поля не редактировать
  случайно массовыми действиями.
- [x] Добавить model tests и migration tests.

Критерий завершения фазы: новая схема обратно совместима, старые cart/catalog paths
работают без source verification, миграция проверена вперёд и rollback-план описан.

Rollback фазы 1: пока dual-write не включён, обратная миграция `0202 → 0201` удаляет
только пустую новую таблицу и не меняет `Product`, cart или order. После начала фазы 2
откатывать таблицу разрешено только после выключения writer feature flag и экспорта
offer-строк; штатный rollback следующих фаз — отключение readers/writers без удаления
накопленной диагностической истории.

## Фаза 2. Dual-write из обычного парсинга

- [x] При обычном импорте upsert `ProductSourceOffer` без изменения текущего поведения витрины.
- [x] Сохранять связь с generic `Product`, доменным товаром, вариантом и размером.
- [x] Не терять parser name при создании shadow `Product`.
- [x] Для merged product хранить несколько source offers, не выбирать поставщика неявно.
- [x] Добавить явный supplier priority/selection policy.
- [x] Реализовать dry-run аудит исторических `external_url` и `scraped_sources`.
- [x] Реализовать bounded/idempotent backfill отдельной management command.
- [x] Не удалять условные остатки до появления корректных readers новой схемы.
- [x] Добавить тесты повторного scrape, variant sync, dedup и нескольких источников.

Критерий завершения фазы: новые и повторно спарсенные товары получают стабильные offers;
повторный запуск не создаёт дубли; старый каталог и корзина дают прежние ответы.

## Фаза 3. Лёгкий parser contract `check_offer`

- [x] Добавить `OfferCheckResult` с `Decimal`, status, nullable quantity,
  stock precision, canonical URL, checked_at и typed error.
- [x] Добавить явное `UnsupportedOfferVerification`, а не ложный успешный результат.
- [x] Гарантировать read-only режим: без media download, AI, дедупликации и создания товара.
- [x] Реализовать Zara и общую Inditex-базу.
- [x] Реализовать Bershka, Pull&Bear и Massimo Dutti через общую базу.
- [x] Реализовать FLO для выбранного color/size SKU.
- [x] Реализовать LCW без обхода всех цветовых вариантов.
- [x] Реализовать IKEA с различием exact stock и unknown availability.
- [x] Реализовать Ummaland в пределах доступных данных.
- [x] Пометить Instagram и недостоверные медицинские источники как manual/unsupported,
  пока нет надёжного supplier API.
- [x] Добавить contract fixtures: in stock, out of stock, price change, missing size,
  404/410, 403/challenge, timeout, malformed payload.

Критерий завершения фазы: каждый поддержанный parser проверяет один offer; неизвестное
количество остаётся `None`; сетевой сбой не выдаётся за отсутствие товара.

## Фаза 4. SourceOfferVerificationService и устойчивость

- [x] Создать единый service layer для выбора parser и нормализации результата.
- [x] Принимать только сохранённый trusted source offer, не URL из клиентского payload.
- [x] Проверять supported domain и redirect target.
- [x] Добавить короткие connect/read timeouts и bounded retry.
- [x] Добавить Redis cache с отдельным TTL успешного и ошибочного результата.
- [x] Добавить single-flight для одновременной проверки одного offer.
- [x] Добавить circuit breaker и per-source concurrency/rate limits.
- [x] Добавить feature flag глобально и per source.
- [x] Добавить структурированные логи и метрики latency/success/error/change.
- [x] Добавить unit и resilience integration tests.

Критерий завершения фазы: деградация одного внешнего сайта не блокирует worker pool и
не вызывает шторм одинаковых запросов; выключение flag возвращает старое поведение.

## Фаза 5. Backend корзины

- [x] Расширить `CartItem`: source offer, verification status/time, observed quantity,
  price-change state и acknowledgement.
- [x] Миграцию CartItem сделать nullable и обратно совместимой.
- [x] Интегрировать проверку в add после serializer resolve, но до создания anonymous cart.
- [x] Проверять источник при увеличении quantity, если cache устарел.
- [x] Добавить явный `POST /cart/revalidate`; GET cart оставить side-effect free.
- [x] Добавить issue codes: `source_out_of_stock`, `source_quantity_changed`,
  `source_price_changed`, `source_unreachable`, `verification_unsupported`, `cart_changed`.
- [x] Не удалять существующую недоступную строку; исключать её из payable total.
- [x] При повышении цены требовать acknowledgement; снижение применять с уведомлением.
- [x] Пересчитать promo, shipping и free-shipping threshold после изменения активных строк.
- [x] Сохранить anonymous cart no-op/invalid mutation guarantees и throttles.
- [x] Проверить user/anonymous cart merge и source-offer identity.
- [x] Обновить OpenAPI и RU/EN тексты ошибок.
- [x] Добавить unit/integration/concurrency tests корзины.

Критерий завершения фазы: новая позиция не становится покупаемой без допустимой проверки;
существующая позиция показывает точную причину блокировки; старые клиенты получают
обратно совместимые базовые поля ответа.

## Фаза 6. Frontend корзины и checkout

- [x] Расширить cart types/store под verification fields и `issues`.
- [x] Показать `Нет в наличии`, `Доступно N`, `Количество неизвестно`,
  `Цена изменилась`, `Не удалось проверить`.
- [x] Добавить действия: подтвердить цену, повторить, уменьшить quantity, удалить,
  перейти к аналогам.
- [x] Блокировать checkout при blocking issues и объяснять каждую причину.
- [x] Не считать unavailable line в payable total; отдельно показать количество строк.
- [x] Добавить все строки в RU/EN locale files.
- [x] Сохранить add_to_cart/remove_from_cart analytics semantics.
- [x] Проверить cart SSR, hydration и mobile layout.
- [x] Выполнить lint, typecheck, tests и production build.

Критерий завершения фазы: пользователь всегда понимает, что изменилось и какое действие
нужно выполнить; UI не обещает точный остаток, если источник его не сообщает.

## Фаза 7. Checkout, заказ и платежи

- [x] Убрать внешнюю source-проверку из области DB row locks.
- [x] Реализовать preflight вне транзакции и fingerprint корзины.
- [x] В короткой транзакции повторно lock cart/items и сравнить fingerprint.
- [x] При изменении цены/наличия вернуть `409` с обновлённой корзиной до создания заказа.
- [x] Сохранить в `OrderItem` immutable source snapshot: supplier, URL, SKU, option,
  source price/currency, status и checked_at.
- [x] Разделить реальный source stock, локальную allocation и условную availability.
- [x] Не считать parser verification резервированием у поставщика.
- [x] Определить `supplier_confirmation_required` для источников без reservation API.
- [x] Для обычного checkout проверить создание заказа и атомарность allocation.
- [x] Для crypto проверить источник до invoice и политику при изменении до paid webhook.
- [x] Сохранить идемпотентность повторных/concurrent paid webhooks.
- [x] Добавить тесты concurrent checkout, invoice failure, duplicate webhook,
  stock/price drift и cart change во время preflight.
- [ ] Выполнить ручной staging smoke для обычного и crypto flow.

Критерий завершения фазы: заказ и платёж не создаются по устаревшей корзине; блокировки
не удерживаются во время supplier HTTP; source snapshot пригоден для fulfillment/audit.

## Фаза 8. Фоновые проверки, admin и SEO/feed

- [x] Добавить Celery refresh только для stale/popular offers с bounded batch.
- [x] Не запускать внешнюю проверку как side effect чтения каталога или корзины.
- [x] Добавить read-only admin dashboard состояния, freshness/errors и circuit breaker.
- [x] Добавить метрики и репозиторные alert rules по latency, error rate, stale offers,
  circuit и частым price changes; подключение внешнего Alertmanager остаётся rollout gate.
- [x] Синхронизировать `availability_status`, `is_available` и публичный Offer JSON-LD.
- [x] Проверить sitemap и product feed: единственный feed проекта YML использует тот же
  availability resolver; отдельной Merchant Center интеграции в проекте сейчас нет.
- [x] Для discontinued/out-of-stock сохранить страницу товара 200, убрать buy actions и
  оставить существующий блок рекомендаций/аналогов.
- [x] Документировать runbook диагностики и безопасного повторного запуска.

Критерий завершения фазы: фоновые задачи ограничены, наблюдаемы и не создают нагрузочный
шторм; storefront, checkout, JSON-LD и feed показывают согласованные данные.

## Фаза 9. Rollout и удаление временной совместимости

- [x] Добавить read-only rollout audit миграций, coverage, freshness, fake stock,
  cart/order readiness и опасных сочетаний feature flags.
- [x] Проверить `0202/0010/0011` на изолированной копии текущей локальной schema/data,
  сохранить существующие cart/order rows и удалить временную БД после проверки.
- [x] После успешной rehearsal и полного CI применить `orders.0010/0011` к рабочей
  локальной dev-БД, подтвердить пустой повторный plan и сохранность cart/order rows.
- [x] Выполнить dry-run и идемпотентный historical backfill локальной dev-БД без
  supplier HTTP; подтвердить offer-key uniqueness и структурное coverage.
- [x] Включить recording offers без cart enforcement.
- [x] Провести dry-run и сохранить отчёт по покрытию source offers на восстановленной
  копии production data.
- [ ] Повторить тот же audit artifact и cart/checkout smoke в отдельном staging.
- [x] Включить live verification первого источника через feature flag: rollout начат
  с `ikea`.
- [x] Поэтапно включить подтверждённые canary источники: `ikea`, `ummaland`, `lcw`.
- [ ] Включить Zara/Inditex и FLO только после настройки доверенного proxy CA/provider
  chain и стабильного повторного canary; direct-проверки блокируются anti-bot защитой,
  а текущий proxy canary корректно остановлен на TLS chain validation.
- [x] Проверить health, cart outcomes, background task и rollback после каждого уже
  включённого источника.
- [ ] Подключить `ops/prometheus/source_offer_alerts.yml` к production Prometheus/
  Alertmanager, заменить runbook URL и выполнить `promtool check rules`.
- [ ] Только после стабильного rollout удалить использование fake stock как реального лимита.
- [ ] Удалить временные dual-read paths отдельным PR после полного покрытия.
- [x] Обновить `SCRAPERS_GUIDE.md`, Cart API docs, runbook и этот документ.

Критерий завершения фазы: feature работает на production для включённых источников,
есть подтверждённый rollback, fake stock не влияет на покупаемое количество.

## Общие release gates

- [x] Все миграции применяются на копии production schema/data без ручного исправления;
  `CartItem=16` и `OrderItem=1` сохранены, повторный migration plan пуст.
- [x] Все три миграции применены на изолированной копии текущей локальной schema/data;
  existing `CartItem`/`OrderItem` counts сохранены, повторный plan пуст.
- [x] Нет N+1 запросов в cart serialization.
- [x] Внешний URL невозможно подменить клиентским запросом.
- [x] В коде расчёта денег нет новых `float`.
- [x] Timeout/403/404 имеют разные бизнес-результаты.
- [x] GET cart не создаёт внешних запросов, session или Cart для пустого anonymous client.
- [x] Promo/shipping/totals используют только payable lines и подтверждённую цену.
- [x] Concurrent checkout создаёт не более одного заказа.
- [x] Crypto paid webhook не списывает allocation повторно.
- [x] RU/EN UI и API ошибки согласованы.
- [x] Backend targeted suite, полный обязательный CI и frontend build зелёные.
- [x] Production-like Docker images собраны локально; release-image backend/frontend
  проверки и clean-schema runtime smoke завершены успешно.
- [x] Immutable 40-character release SHA отправлен в GitHub, remote CI завершён успешно,
  backend/frontend manifests опубликованы в GHCR и проверены анонимным pull.
- [x] Production canary для IKEA, Ummaland и LCW подтверждает trusted offer selection,
  актуальную цену/наличие, bounded background task и cart outcomes: verified/payable
  `200` и `source_out_of_stock` `409`; тестовые cart rows удалены.
- [ ] Staging smoke выполнен для cart, checkout, обычной оплаты и crypto.

## Журнал работ

### 2026-08-27 — анализ и фиксация

- Статус: завершена только фаза 0.
- Изменённые файлы: `docs/SOURCE_OFFER_CART_VERIFICATION_PLAN.md`,
  `docs/README.md`.
- Связанные контуры: только документация; исполняемые parser, catalog, cart,
  checkout и payment paths не менялись.
- Код приложения, модели и миграции не менялись.
- Выполненные проверки: просмотр архитектуры parser/catalog/cart/checkout/payment и
  статический анализ связанных тестов.
- Команды проверки документа: `git status --short`,
  `rg -n "SOURCE_OFFER_CART_VERIFICATION_PLAN" docs/README.md`,
  `git diff --check`; все завершились успешно.
- Не заявлялось: запуск backend test suite, Docker smoke или frontend build.
- Причина отсутствия test suite: изменение состоит только из Markdown-документации;
  закрытие следующих фаз без профильных тестов запрещено.
- Следующий безопасный шаг: финализировать схему `ProductSourceOffer` и сначала добавить
  только nullable schema migration без подключения к корзине.

### 2026-08-27 — фаза 1, контракт и schema migration

- Статус: фаза 1 завершена; фазы 2–9 не включены.
- Изменённые файлы: `backend/apps/catalog/models.py`,
  `backend/apps/catalog/admin.py`,
  `backend/apps/catalog/migrations/0202_productsourceoffer.py`,
  `backend/apps/catalog/tests/test_product_source_offer.py`,
  `backend/apps/catalog/tests/test_product_source_offer_migration.py`.
- Связанные контуры: единый `Product`, shadow/domain product resolver, cart identity,
  read-side корзины и политика повторного scrape; readers/writers offer пока отсутствуют.
- `ProductSourceOffer` привязан к единому `Product`; конкретный buyable offer задаётся
  внешними SKU/ID, variant/size keys, options и стабильным SHA-256 `offer_key`.
- DB constraints запрещают сохранять условное количество при boolean/unknown stock.
- Admin сделан диагностическим read-only: создание и удаление отключены.
- Команды и результаты:
  - `.venv-local/bin/python manage.py check` — успешно;
  - `docker compose exec backend poetry run python manage.py makemigrations --check --dry-run`
    — `No changes detected`;
  - `docker compose exec backend poetry run pytest apps/catalog/tests/test_product_source_offer.py apps/catalog/tests/test_product_source_offer_migration.py -q`
    — `5 passed`;
  - `docker compose exec backend poetry run pytest apps/catalog/tests/test_product_resolve.py apps/orders/tests/test_cart_identity_constraints.py apps/orders/tests/test_cart_mutation_security.py apps/orders/tests/test_cart_read_side_effects.py apps/scrapers/test_existing_product_update_policy.py -q`
    — `69 passed`;
  - `git diff --check` — успешно.
- Известное ограничение локального runtime: Python 3.11 окружение не содержит
  `curl_cffi`; полные проверки выполнены в штатном Python 3.12 Docker-контейнере.
- Следующий безопасный шаг: отдельный idempotent writer, который создаёт offers при
  обычном scrape, без изменения текущих цен/остатков каталога и без cart enforcement.

### 2026-08-27 — фаза 2, dual-write и backfill

- Статус: фаза 2 завершена за выключенным по умолчанию feature flag;
  cart/checkout readers по-прежнему не используют source offers.
- Изменённые файлы: `backend/apps/scrapers/source_offers.py`,
  `backend/apps/scrapers/services.py`, `backend/config/settings.py`, `.env.example`,
  `backend/apps/catalog/management/commands/backfill_source_offers.py`,
  `backend/apps/scrapers/test_source_offer_writer.py`,
  `backend/apps/catalog/tests/test_backfill_source_offers.py`,
  `backend/apps/orders/serializers.py`,
  `backend/apps/orders/tests/test_cart_variant_navigation.py`.
- Связанные контуры: обычный parser import, repeat scrape, fashion/furniture variant
  sync, shadow Product navigation, catalog stock compatibility и scraper audit log.
- `SOURCE_OFFER_RECORDING_ENABLED=false` по умолчанию; writer вызывается после
  успешного импорта и не превращает свою ошибку в ошибку существующего scrape.
- Priority policy: меньшее число имеет приоритет; default и per-source значения
  настраиваются через env. Writer ничего не выбирает для продажи неявно.
- Zara/Inditex/FLO/LCW и остальные boolean-источники не записывают `1000/3` как
  exact quantity. IKEA записывает exact только когда normalized supplier API вернул
  число (включая явный zero для unsellable); отсутствие числа остаётся boolean
  availability без количества.
- Variant sync сохраняет `source_parser` и `source_offer_product_id`; эти ключи
  переносятся в cart-facing shadow Product вместе с source variant identity.
- Backfill по умолчанию работает в dry-run; `--apply`, `--limit`, `--batch-size`,
  `--start-id` и `--source` делают запись явной, ограниченной и возобновляемой.
- Команды и результаты:
  - `docker compose exec backend poetry run pytest apps/scrapers/test_source_offer_writer.py apps/catalog/tests/test_backfill_source_offers.py apps/catalog/tests/test_product_source_offer.py -q`
    — `11 passed`;
  - `docker compose exec backend poetry run pytest apps/scrapers/test_existing_product_update_policy.py apps/scrapers/test_zara_parser.py apps/scrapers/test_inditex_parsers.py apps/scrapers/test_flo_parser.py apps/scrapers/test_lcw_parser.py apps/catalog/tests/test_ikea_service.py apps/scrapers/test_rescrape_skip_counter.py apps/scrapers/test_accessory_parsed_media_resave.py -q`
    — `104 passed`;
  - `docker compose exec backend poetry run pytest apps/orders/tests/test_cart_variant_navigation.py apps/scrapers/test_accessory_parsed_media_resave.py apps/scrapers/test_source_offer_writer.py -q`
    — `16 passed`;
  - `.venv-local/bin/python manage.py check`, Black check новых файлов и
    `git diff --check` — успешно.
- Rollback: оставить migration 0202, выключить `SOURCE_OFFER_RECORDING_ENABLED`;
  существующий import/cart не читают новую таблицу. Созданные offers сохраняются для
  диагностики и не требуют удаления.
- Следующий безопасный шаг: добавить typed read-only `OfferCheckResult` и parser
  adapters без подключения к корзине.

### 2026-08-27 — фаза 3, typed `check_offer`

- Статус: фаза 3 завершена; live-check ещё не вызывается cart/checkout.
- Изменённые файлы: `backend/apps/scrapers/base/offers.py`,
  `backend/apps/scrapers/base/scraper.py`, parser adapters Zara/FLO/LCW/IKEA/Ummaland
  и `backend/apps/scrapers/test_offer_check_contract.py`.
- Связанные контуры: parser registry, full detail parsing, Inditex inheritance,
  HTTP error mapping и source stock precision; media/catalog writers не вызываются.
- Typed contract содержит `OfferCheckContext`, `OfferCheckResult`, `Decimal`,
  availability/stock enums, checked_at, typed error и проверку invariant quantity.
- Base parser по умолчанию бросает `UnsupportedOfferVerification`; Instagram,
  IlacFiyati и Ilacabak не выдают ложный live result.
- Zara/Inditex проверяют один server payload. FLO/LCW запрашивают только сохранённый
  variant URL. IKEA запрашивает один item code без обхода color siblings.
- Отдельный `_make_offer_request` не меняет legacy full-scrape retry path и различает
  404 `not_found`, 410 `gone`, 403 `access_blocked`, timeout и transport error.
- Команды и результаты:
  - `docker compose exec backend poetry run pytest apps/scrapers/test_offer_check_contract.py -q`
    — `19 passed`;
  - `docker compose exec backend poetry run pytest apps/scrapers/test_parser_registry.py apps/scrapers/test_zara_parser.py apps/scrapers/test_inditex_parsers.py apps/scrapers/test_flo_parser.py apps/scrapers/test_lcw_parser.py apps/catalog/tests/test_ikea_service.py apps/scrapers/test_ilacfiyati_parser.py apps/scrapers/test_instagram_parser.py -q`
    — `116 passed`;
  - `.venv-local/bin/python manage.py check`, py_compile, Black check новых файлов и
    `git diff --check` — успешно.
- Rollback: adapters не имеют readers; удаление/отключение будущего service flag
  возвращает систему к full scrape. Схема и recorded offers остаются совместимыми.
- Следующий безопасный шаг: единый `SourceOfferVerificationService`, принимающий только
  сохранённый offer и отвечающий за domain guard, cache, single-flight и circuit breaker.

### 2026-08-27 — фаза 4, resilient live verification service

- Статус: фаза 4 завершена за выключенным по умолчанию feature flag; корзина и
  checkout ещё не вызывают внешний источник.
- Изменённые файлы: `backend/apps/catalog/services/source_offer_verification.py`,
  `backend/apps/catalog/tests/test_source_offer_verification_service.py`,
  `backend/apps/scrapers/base/offers.py`, `backend/config/settings.py`, `.env.example`.
- Связанные контуры: parser registry/domain resolution, Redis cache, typed parser
  errors, offer diagnostics и Prometheus/logging; cart/checkout/payment paths не менялись.
- Service принимает только сохранённый активный `ProductSourceOffer`. HTTPS URL,
  сохранённый домен, parser key и parser registry проверяются до сетевого запроса;
  credentials в URL и редирект в неподдерживаемый домен отклоняются.
- Внутренние retries полного парсера отключены. Service централизованно ограничивает
  timeout, не более двух retry, backoff, source rate/concurrency, single-flight и
  circuit breaker. Cache degradation работает fail-open и не маскирует parser result.
- Успешные и ошибочные результаты имеют разные TTL. Production cache уже настроен на
  Django `RedisCache`; тесты используют изолированный LocMem backend согласно общей
  политике тестов, чтобы не очищать Redis работающего приложения.
- При допустимом supplier redirect атомарно обновляются canonical URL и source domain;
  отдельный тест доказывает, что следующая проверка не блокируется domain guard.
- Метрики фиксируют latency, outcome и изменения price/availability/stock; логи содержат
  source, outcome, duration и offer/change diagnostics без клиентского URL payload.
- Команды и результаты:
  - `docker compose exec backend poetry run pytest apps/catalog/tests/test_source_offer_verification_service.py apps/scrapers/test_offer_check_contract.py apps/scrapers/test_source_offer_writer.py apps/catalog/tests/test_product_source_offer.py apps/catalog/tests/test_product_source_offer_migration.py -q`
    — `40 passed`;
  - `docker compose exec backend poetry run pytest apps/scrapers/test_parser_registry.py apps/scrapers/test_zara_parser.py apps/scrapers/test_inditex_parsers.py apps/scrapers/test_flo_parser.py apps/scrapers/test_lcw_parser.py apps/catalog/tests/test_ikea_service.py apps/scrapers/test_ilacfiyati_parser.py apps/scrapers/test_instagram_parser.py -q`
    — `116 passed`;
  - `docker compose exec backend poetry run python manage.py check` — успешно;
  - `docker compose exec backend poetry run python manage.py makemigrations --check --dry-run`
    — `No changes detected`;
  - Black check новых файлов, `py_compile` и `git diff --check` — успешно.
- Rollback: оставить накопленные offer diagnostics, выключить
  `SOURCE_OFFER_VERIFICATION_ENABLED`; ни parser import, ни действующая корзина service
  не вызывают. Per-source rollout дополнительно ограничивается allowlist.
- Следующий безопасный шаг: nullable поля `CartItem` отдельной schema migration и
  backward-compatible serializer output до подключения live-check к add/update cart.

### 2026-08-27 — фаза 5, backend корзины

- Статус: фаза 5 завершена; cart enforcement остаётся выключенным по умолчанию,
  frontend-фаза 6 и checkout preflight/snapshot фазы 7 ещё не включены.
- Изменённые файлы: `backend/apps/orders/models.py`, `admin.py`, `serializers.py`,
  `views.py`, `cart_source_verification.py`, migration `0010`, cart tests,
  variant source-identity writer/serializer, settings/env и RU/EN API locale files.
- Связанные контуры: add/update/revalidate cart, anonymous/user merge, optimistic
  concurrency, totals, promo, shipping/free-shipping, checkout guard, throttles,
  variant identity, currency conversion и product markup.
- `CartSourceOfferPolicy` выбирает только сохранённый server-owned offer конкретного
  варианта/размера и вызывает лёгкий verifier. Клиент не может передать source URL,
  parser key или supplier SKU.
- Add проверяет источник до создания anonymous Cart. Повторный add блокирует уже
  сохранённую строку, если offer исчез. Update/revalidate сохраняют результат через
  optimistic compare по quantity/updated_at без сетевого запроса под DB lock.
- Повышенная публичная цена привязана к точной сумме и валюте acknowledgement;
  снижение применяется автоматически. Exact stock может уменьшить quantity; boolean
  stock не выдаёт пользователю выдуманное число.
- Заблокированная строка остаётся видимой, но не участвует в payable total, скидке,
  доставке или checkout. Удаление диагностического offer не разблокирует snapshot.
- Добавлены `POST /api/orders/cart/{id}/acknowledge-price` и
  `POST /api/orders/cart/revalidate`; явный revalidate обходит result TTL, сохраняя
  circuit breaker, rate/concurrency limits и max-items bound. GET cart не вызывает сеть.
- Команды и результаты:
  - `docker compose exec backend poetry run pytest apps/orders/tests apps/payments/tests -q`
    — `131 passed`, `17 subtests passed`;
  - `docker compose exec backend poetry run pytest apps/catalog/tests apps/scrapers -q`
    — `562 passed`, `4 subtests passed`;
  - финальный cart policy/API/model набор — `27 passed`;
  - `docker compose exec backend poetry run python manage.py check` — успешно;
  - `docker compose exec backend poetry run python manage.py makemigrations --check --dry-run`
    — `No changes detected`;
  - `msgfmt --check` для RU/EN — успешно;
  - `manage.py spectacular --validate` — `0 errors`; оставшиеся предупреждения относятся
    к существующим неаннотированным serializer method fields проекта;
  - Black check новых файлов и `git diff --check` — успешно.
- Rollback: выключить `SOURCE_OFFER_CART_ENFORCEMENT_ENABLED`; legacy cart lines и
  ответы сохраняются, nullable snapshots остаются диагностическими. Migration 0010
  откатывать только после выключения reader и проверки отсутствия нужной истории.
- Следующий безопасный шаг: фаза 6 — frontend types/store/UI для issue codes и действий,
  затем отдельная фаза 7 с live preflight вне checkout transaction и immutable OrderItem
  source snapshot.

### 2026-08-27 — фаза 6, frontend корзины и checkout

- Статус: фаза 6 завершена; supplier-conflict UI включается только при backend feature
  flag, checkout preflight и immutable snapshot остаются открытой фазой 7.
- Изменённые файлы: общие cart types и verification helpers, Zustand cart store,
  `AddToCartButton`, `BuyNowButton`, страницы cart/checkout и RU/EN locale JSON.
- Связанные контуры: exact offer identity с выбранным размером, add/buy-now conflict
  retry, totals/payable count, promo/shipping read-side, SSR refresh и checkout submit.
- Add/buy-now обрабатывают совместные quantity/price conflicts одним подтверждённым
  повтором; 409 больше не повторяется автоматически из-за trailing-slash fallback.
- Заблокированная строка остаётся видимой, исключена из отображаемого payable total и
  имеет действия: подтвердить цену, уменьшить до точного остатка, перепроверить,
  удалить или перейти к товару/аналогам. Boolean stock не показывается как точное число.
- Cart и checkout используют один тип ответа и заменяют состояние ответом backend после
  каждой мутации/конфликта; кнопка оформления блокируется и на странице cart, и при
  submit checkout.
- Команды и результаты:
  - `npm exec tsc -- --noEmit --pretty false` — успешно;
  - `npm test` — `53 passed`;
  - `npm run lint` — `0 errors`, `43` существующих предупреждения `no-img-element`;
  - `npm run build` — production build успешно, `/cart` и `/checkout` собраны;
  - RU/EN locale JSON parse — успешно;
  - локальный browser smoke `http://localhost:3001/cart` — desktop и viewport
    `390x844`, SSR/hydration без падения, mobile empty-state визуально корректен.
- Не заявлялось: staging smoke supplier-conflict fixture с живым source flag; он остаётся
  в release/staging gates и не подменяется локальным empty-cart smoke.
- Следующий безопасный шаг: фаза 7 — вынести live-check до checkout transaction,
  сравнить fingerprint под коротким lock и сохранить immutable source snapshot заказа.

### 2026-08-27 — фаза 7, checkout preflight и source snapshot

- Статус: код, schema migration и автоматические проверки фазы 7 завершены; единственный
  открытый пункт фазы — ручной staging smoke обычного и реального crypto flow.
- Изменённые файлы: checkout в `backend/apps/orders/views.py`, `OrderItem` model/admin,
  migration `0011`, source-preflight/migration tests, reservation allowlist setting/env и
  явная webhook policy в `backend/apps/payments/views.py`.
- `CreateOrderSerializer` валидируется до дорогой проверки. Supplier preflight выполняет
  `force=True` вне `transaction.atomic`, сохраняет результат optimistic update и строит
  SHA-256 fingerprint cart/promo/items/source identity.
- Короткий checkout transaction повторно блокирует только cart/items, bulk-read загружает
  nullable source offers без недопустимого PostgreSQL outer-join lock и сравнивает
  fingerprint до promo, invoice, заказа или allocation.
- Price/stock drift возвращает обновлённую корзину и `409`; transient supplier failure
  остаётся `503`. Exact stock может зажать quantity, но checkout останавливается для
  явного просмотра изменения пользователем. Crypto invoice при drift не создаётся.
- `OrderItem` хранит plain immutable snapshot без FK к offer: parser/domain/URL,
  external product/SKU, variant/size/options, source price/currency, availability,
  stock precision/quantity и checked_at. Последующее изменение offer snapshot не меняет.
- Live verification не считается reservation. Для всех source parsers вне пустого по
  умолчанию `SOURCE_OFFER_RESERVATION_CAPABLE_SOURCES` ставится
  `supplier_confirmation_required=true`; local allocation остаётся отдельной логикой.
- Paid webhook намеренно не запускает supplier parser: он авторитетно и идемпотентно
  применяет provider payment один раз, списывает local allocation и оставляет supplier
  confirmation fulfillment-контуру.
- Команды и результаты:
  - новые preflight/fingerprint/snapshot/migration tests — `6 passed`;
  - связанный checkout/cart/webhook suite — `46 passed`, `17 subtests passed`;
  - полный `apps/orders/tests apps/payments/tests` — `139 passed`,
    `17 subtests passed`;
  - `manage.py check` — успешно; `makemigrations --check --dry-run` —
    `No changes detected`;
  - `manage.py spectacular --validate` — `0 errors`; 577 существующих warnings;
  - `manage.py spectacular --validate` — `0 errors`; 577 существующих schema warnings;
  - Black check трёх новых файлов и `git diff --check` — успешно;
  - frontend production build после финального cart action — успешно.
- Rollback: выключить cart enforcement, оставить snapshot columns nullable/blank.
  Migration `0011 → 0010` удаляет только новые audit columns, поэтому перед rollback
  требуется экспорт source snapshot уже созданных заказов.
- Следующий безопасный шаг: применить миграции на копии production data и выполнить
  staging smoke с включёнными Zara/Inditex source flags, затем обычный и crypto checkout.

### 2026-08-27 — фаза 8, background refresh, admin и storefront/feed consistency

- Статус: код и автоматические проверки фазы 8 завершены. Все новые readers/tasks
  выключены по умолчанию; production monitoring и source-by-source rollout не заявлялись.
- Изменённые контуры: bounded Celery task/service, Beat/settings/env, read-only offer
  admin, public detail serializer projection, YML availability, product JSON-LD/UX,
  Prometheus rules, Celery docs и отдельный operations runbook.
- Scheduled task каждые 5 минут является no-op до двух enable-флагов. Один проход берёт
  не более 100 stale offers, ставит recently changed cart offers первыми, имеет общий
  lock дольше hard timeout и не поглощает Celery soft timeout.
- Проверка остаётся в `SourceOfferVerificationService`: trusted saved URL, source
  allowlist, cache/single-flight, rate/concurrency и circuit breaker не дублируются.
  Ни GET catalog/cart, ни serializer не запускают supplier HTTP.
- Detail/YML projection имеет отдельный флаг. Один свежий sellable offer разрешает
  supplier availability, но не отменяет ручной `is_available=false` магазина;
  out-of-stock/discontinued выставляется только если все enabled active offers свежие
  и окончательно недоступны. Stale/unknown/unreachable сохраняют прежнее состояние
  каталога. Feed работает с prefetch и запрещает per-product fallback query.
- Sitemap по-прежнему включает `is_active` товары независимо от наличия. Resolve test
  подтверждает HTTP 200 для out-of-stock; frontend скрывает buy actions, сохраняет
  карточку и существующий `SimilarProducts`, а Offer JSON-LD использует тот же status.
- Admin не имеет add/delete действий и показывает freshness, consecutive failures,
  last error и circuit state; ручного массового запуска парсера из списка нет.
- Добавлены шесть alert rules. Compose проекта не содержит Prometheus/Alertmanager,
  поэтому rules являются проверяемым deployment artifact, а подключение вынесено в фазу 9.
- Команды и результаты:
  - phase-8 source/admin/projection target — `18 passed`, затем после review
    `13 passed`; два timeout/HTTP guard-теста отдельно — `2 passed`, merchandising
    guard — `1 passed`;
  - связанный source/product-resolve/serializer/SEO/YML/parser suite — `117 passed`;
  - `manage.py check` — успешно; `makemigrations --check --dry-run` —
    `No changes detected`;
  - task зарегистрирована как `catalog.refresh_source_offers`, Beat schedule — 300 секунд;
  - alert YAML прочитан Ruby YAML parser, найдено 6 rules; `git diff --check` — успешно;
  - `npm exec tsc -- --noEmit --pretty false` — успешно;
  - `npm test` — `57 passed`, включая 4 JSON-LD availability tests;
  - `npm run lint` — `0 errors`, 43 существующих `no-img-element` warnings;
  - `npm run build` — production build успешно, product/cart/checkout routes собраны.
- Rollback: последовательно выключить catalog projection, cart enforcement, background
  refresh и verification/allowlist. Offer diagnostics и order snapshots не удалять.
- Следующий безопасный шаг: production-copy migration gate и staging smoke фазы 7,
  затем source-by-source rollout фазы 9 по runbook.

### 2026-08-27 — фаза 9, rollout audit и локальная migration rehearsal

- Статус: закрыты rollout tooling/documentation, репетиция на копии текущей локальной
  БД и доступные локальные release gates. Production/staging flags не менялись,
  supplier HTTP не запускался.
- Добавлена read-only management command `audit_source_offer_rollout` и service layer.
  Отчёт агрегирует migration status, source-candidate coverage, fake stock, offer
  freshness/errors/per-source, CartItem/OrderItem readiness и feature flags. При
  частично применённой схеме команда не обращается к отсутствующим колонкам.
- `--format json` даёт release artifact; `--fail-on-blockers` возвращает ненулевой
  exit при missing migrations, unsafe allowlist/flag combination или наличии source
  candidates без active offers. Команда не пишет в БД, не вызывает parser и Redis.
- Тесты `apps/catalog/tests/test_source_offer_rollout_audit.py` проверяют aggregate
  coverage, отсутствие mutations, partial-schema guard и machine-readable JSON:
  `3 passed`.
- Read-only аудит текущей локальной БД: 209 products, 195 source candidates, 0 offers,
  coverage 0%; legacy stock `1000` у 168 кандидатов и `3` у 13. В рабочей dev-БД
  применена `catalog.0202`, а `orders.0010/0011` остаются pending; все source flags false.
- Для репетиции создан согласованный custom-format dump (размер исходной БД около
  57.6 MB) и отдельная БД `pharmaturk_source_offer_rehearsal_20260827`. Исходно в ней
  были 2 CartItem и 5 OrderItem, `0202` applied, `0010/0011` pending.
- `migrate --plan` показал только `orders.0010` и `0011`; обе применились без ручного
  исправления. Counts остались 2/5, Django check — `0 issues`, повторный migration plan
  — `No planned migration operations`, audit увидел все три migration как applied.
- Временная rehearsal-БД и dump после проверки удалены; read-only проверка имени БД
  вернула `0`. На момент rehearsal рабочая `pharmaturk` ещё не мигрировалась.
- Обновлены `SCRAPERS_GUIDE.md`, `docs/SOURCE_OFFER_CART_API.md`, operations runbook и
  docs index: typed `check_offer`, stock precision, API issue/409/503 semantics,
  audit command и stop conditions rollout теперь зафиксированы.
- Закрыт cart serialization performance gate. `_get_cart_with_prefetch` теперь единым
  prefetch-планом загружает `product`, `source_offer`, category/brand/price info, изображения,
  доменные галереи и переводы. Serializer использует prefetch cache изображений вместо
  `filter()/first()` на каждую позицию. Регрессионный тест подтверждает строго одинаковое
  число SQL-запросов для корзин с 1 и 5 позициями: `1 passed`.
- Финальные локальные проверки на итоговом diff: `git diff --check` — успешно;
  `manage.py check` — `0 issues`; `makemigrations --check --dry-run` —
  `No changes detected`; полный backend suite — `1185 passed`, `30 subtests passed`,
  4 существующих warnings за 520.62 s. OpenAPI regression gate — `2 passed`;
  frontend: `npm test` — `57 passed`, TypeScript — успешно, lint — `0 errors`
  (43 существующих warnings), production build — успешно.
- После успешных rehearsal и CI к рабочей локальной dev-БД точечно применены только
  `orders.0010` и `orders.0011`: обе `OK`, повторный migration plan пуст, counts
  сохранены (`CartItem=2`, `OrderItem=5`). Повторный read-only audit подтверждает все
  три migration applied; migration blockers отсутствуют. До backfill единственным
  blocker был `source_candidates_without_active_offers`: 195 source candidates,
  0 offers, coverage 0%.
- Historical backfill сначала выполнен в dry-run: 195 products/sources, 631 offers,
  0 invalid sources и 0 products without source. Затем тот же bounded command запущен
  с `--apply`: записано 631 active offers с 631 уникальными `offer_key` — IKEA 56 offers
  для 27 products, LCW 465/58, ilacfiyati 110/110. Внешних HTTP-запросов не было;
  ilacfiyati остаётся вне live-verification allowlist.
- Итоговый локальный audit: schema applied, coverage 195/195 (100%), blockers отсутствуют,
  `ready_for_source_rollout=true`; JSON gate с `--fail-on-blockers` завершился с exit 0.
  Это структурная готовность, а не подтверждение текущих supplier price/stock: backfill
  восстановлен из сохранённой истории. Все source feature flags оставлены `false`;
  warning о legacy fake stock сохранён до controlled rollout.
- Изменённые файлы этого шага:
  `backend/apps/catalog/services/source_offer_rollout_audit.py`,
  `backend/apps/catalog/management/commands/audit_source_offer_rollout.py`,
  `backend/apps/catalog/tests/test_source_offer_rollout_audit.py`,
  `backend/apps/orders/views.py`, `backend/apps/orders/serializers.py`,
  `backend/apps/orders/tests/test_cart_read_side_effects.py`, документация выше.
- Не заявлялось: проверка на копии production data, staging smoke, включение recording/
  verification/cart/background/catalog flags или подключение Alertmanager.
- Следующий безопасный шаг требует production dump/staging access: повторить
  audit/migrations/smoke по runbook до включения первого source flag.

### 2026-08-27 — локальный production-like release gate

- В `.env.production.example` добавлен полный безопасный набор source-offer настроек:
  recording, verification, cart enforcement, background refresh и catalog projection
  по умолчанию выключены; первый allowlist ограничен IKEA. `DEPLOY.md` направляет rollout
  к source-offer runbook и запрещает одновременное включение всех readers/writers.
- Release predeploy собрал production backend/frontend images и выполнил проверки из
  этих images. Итог: Django check и migration drift — успешно; backend —
  `1185 passed`, `30 subtests passed`; frontend — `57 passed`, TypeScript и production
  build успешны, lint — `0 errors` при 43 существующих warnings.
- Выявлен upstream-дефект arm64-варианта `qdrant/qdrant:v1.18.3`
  (`entrypoint.sh: exec format error`). Только локальные test/smoke overlays используют
  рабочий `linux/amd64`; production Compose не изменён.
- Первый повторный smoke пересёкся с ещё завершавшимся запуском: оба получили одинаковое
  Compose project name из-за `$PPID`, и cleanup первого остановил PostgreSQL второго.
  `local-smoke.sh` и `predeploy.sh` переведены на PID самого скрипта (`$$`), а smoke
  теперь до cleanup собирает service diagnostics при ошибке.
- Финальный независимый runtime smoke завершён успешно: чистая PostgreSQL schema получила
  все миграции, включая `catalog.0202` и `orders.0010/0011`; backend readiness, frontend,
  nginx, liveness, HSTS и canonical-host redirect прошли; изолированные containers,
  networks и volumes удалены.
- Два теста, ранее зависевшие от внешней currency network/устаревшей patch target,
  сделаны детерминированными без изменения production-кода. Их target-прогон и полный
  release suite зелёные.
- Это локальный gate для текущего exact diff. Открыты: чистый immutable SHA, remote CI,
  production-copy migration rehearsal, backup manifests, staging smoke и поэтапное
  включение source flags.

### 2026-08-27 — production deploy, backfill и IKEA canary

- Remote CI attempt 2 для `369cc9d2b7067b47681eba97cd467ba7a57fabee` завершён
  успешно: secret scan, frontend, backend, Compose и immutable image publication зелёные.
- На production создан online PostgreSQL custom-format dump и Qdrant full snapshot;
  оба artifact проверены, зафиксированы SHA-256 и release manifest для предыдущего
  `78da4de4013130d17f4fd1e027dfede23f6b1c2f`.
- Dump восстановлен во временный изолированный PostgreSQL. Миграции `catalog.0202`,
  `orders.0010/0011` применились без ручного исправления; counts `16/1` не изменились,
  повторный plan пуст, временные container/network/volume удалены.
- Exact images прошли изолированный runtime smoke на production host, затем release
  развёрнут controlled maintenance workflow. Все application containers работают на
  одном SHA; public readiness, liveness и security-header smoke прошли.
- Production backfill выполнен двумя bounded batch без supplier HTTP. Итоговый audit:
  15 386/15 386 source-кандидатов покрыты, 27 509 active offers, flag blockers отсутствуют,
  DB uniqueness `(product, parser, offer_key)` не нарушена.
- `SOURCE_OFFER_RECORDING_ENABLED=true`; verification allowlist ограничен `ikea`,
  background refresh, cart enforcement и catalog projection оставлены выключенными.
- Контролируемый IKEA canary подтвердил успешный API response/price/availability для
  базового артикула, но выявил ложный `option_not_found` для exact furniture variants:
  adapter повторно применял generic variant selector после загрузки уже выбранного
  артикула. Rollout остановлен до cart enforcement; пользовательский flow не затронут.
- Исправление нормализует одиночный IKEA response по уже выбранному article code и имеет
  отдельный regression test. Parser contract — `20 passed`, связанный suite —
  `52 passed`, полный backend gate — `1186 passed`, `30 subtests passed`.
- Predeploy canary нового image был намеренно запущен вне production service stack и
  сначала получил DNS failure из-за подключения только к internal `data` network. Это
  выявило отдельную ошибку контракта: best-effort `IkeaService.fetch_item_details`
  возвращал `None` при transport/5xx, а live adapter ошибочно превращал это в
  `not_found/out_of_stock`.
- Для обычного bulk import сохранено прежнее best-effort поведение. Только live
  `check_offer` включает strict error propagation: DNS/transport и 5xx проходят через
  общий translator как retryable `source_unreachable`, а 404/410 остаются конечными
  supplier outcomes. Добавлены regressions для DNS и HTTP 503.
- После второго review связанный IKEA/access/verification suite — `63 passed`; финальный
  полный backend gate — `1188 passed`, `30 subtests passed`. Background/cart/catalog
  flags остаются выключены до успешного canary через production egress networks.

### 2026-08-28 — production IKEA verification, background и cart enforcement

- Hotfix временной недоступности поставщика зафиксирован отдельным commit
  `75bc4a44a06dfe2b91db6572740b9a8388dc6be4`. Повторный target gate — `38 passed`,
  полный backend gate — `1188 passed`; GitHub CI `33117989983` завершил Compose,
  secret scan, frontend, backend и exact-revision image jobs успешно.
- Опубликованы и сверены immutable images: backend
  `sha256:cded06ae300f0a10bc62b7bb40ff67dde59bbf499c598328128d74a0f986f1d3`, frontend
  `sha256:5d3067be79994d2c3e37ffd5eafb3ed52f877c6467502319e205fbca277f22d9`;
  OCI revision обоих образов совпадает с release SHA.
- Predeploy exact-image canary подключался одновременно к production `data` и `edge`
  networks. Offers `114/115/116` дали success: цены `29999/12999/12999 TRY`, варианты
  `00581918/00623862` вернули exact stock `29/127`; ложных `option_not_found` и
  `source_unreachable` нет. Отдельный isolated full-stack smoke применил все миграции с
  нуля и проверил readiness, HSTS и canonical redirect, затем удалил свой project.
- Controlled deploy `369cc9d2b7067b47681eba97cd467ba7a57fabee` → `75bc4a4...`
  использовал валидированный backup manifest; migration plan был пуст. Stateful
  PostgreSQL/Redis/Qdrant не пересоздавались, все application containers работают на
  одном SHA, public postdeploy smoke прошёл.
- Postdeploy canary через штатный backend повторил `3/3 success`. Bounded background
  включён только для `ikea` с batch `5`: синхронный прогон, реальная задача через broker
  и первый автоматический celerybeat-cycle дали суммарно `15/15 success`, retryable и
  permanent errors — `0`. IKEA stale backlog уменьшился `4302 → 4287`, error rows — `0`.
- Cart enforcement включён отдельным config step при выключенном catalog projection.
  Public anonymous canary подтвердил: product `127` выбрал trusted offer `114`, вернул
  `200`, `verified`, `in_stock`, payable; product `131` выбрал live-проверенный
  out-of-stock offer `125` и вернул `409 source_out_of_stock`, не создавая корзину.
  Созданная positive test cart и связанная строка удалены; обе test session identities
  отсутствуют после cleanup.
- Финальный read-only audit: blockers `0`, coverage `15386/15386` (`100%`), active offers
  `27509`, IKEA errors `0`, required migrations применены. Флаги production:
  recording/verification/background/cart — `true`, allowlist — `ikea`, batch — `5`,
  catalog projection — `false`. Public health после rollout: DB/cache healthy.
- Два ранних ручных config-stage запуска безопасно остановились до feature rollout:
  сначала из-за неверного имени Compose override, затем из-за исторического `.env`
  `IMAGE_TAG`. Rollback вернул флаги в `false`, работающий release и public health не
  менялись. Финальные команды использовали `docker-compose.prod.yml`, явный immutable
  `IMAGE_TAG` и закрытый stdin для `docker compose exec`; резервные `.env` сохранены.

### 2026-08-28 — расширение production allowlist и trusted proxy release candidate

- Production inventory содержит active offers из `flo`, `ikea`, `ilacfiyati`,
  `instagram`, `lcw`, `ummaland` и `zara`. Instagram и медицинские источники оставлены
  manual/unsupported: без надёжного supplier API они не должны давать ложный live
  результат.
- Ummaland canary `3/3` подтвердил актуальные RUB-цены. После отдельного config step
  bounded worker дал `5/5 success`, public cart подтвердил trusted offer и обязательное
  acknowledgement изменившейся цены; тестовая корзина удалена.
- LCW canary подтвердил две доступные позиции с текущими TRY-ценами и корректный
  конечный `option_not_found/out_of_stock` для исчезнувшего размера. После отдельного
  config step bounded worker дал `5/5 success`; public cart вернул `200` для доступного
  размера и `409 source_out_of_stock` для недоступного; тестовые корзины удалены.
- Текущий production allowlist — `ikea,ummaland,lcw`; recording, verification,
  background batch `5` и cart enforcement включены, catalog projection выключен.
  Read-only сверка подтвердила checkout/runtime SHA
  `75bc4a44a06dfe2b91db6572740b9a8388dc6be4` и отсутствие config drift.
- FLO direct canary получил supplier challenge для всех трёх проверок. Zara дал
  перемежающиеся `403/access_blocked`, хотя часть запросов вернула корректный terminal
  out-of-stock результат. Оба источника оставлены вне allowlist.
- Анализ связанного пути выявил, что full scrape передавал `ScraperConfig.use_proxy`,
  а лёгкий `SourceOfferVerificationService` создавал parser без этой server-side policy.
  Release candidate добавляет proxy только при непустом server-owned proxy URL и точном
  совпадении active/enabled `ScraperConfig` с сохранённым parser key. Ни proxy URL, ни
  config identity не принимаются из cart request; mismatch никогда не включает proxy
  из чужой конфигурации и сохраняет штатный direct parser mode.
- Локальные gates release candidate: связанный parser/proxy/verification suite —
  `69 passed`; полный backend suite — `1191 passed`, `30 subtests passed`;
  Django check — `0 issues`, migration drift — `No changes detected`, Black и
  `git diff --check` — успешно.
- Release commit `26b4fe9aa3bd5002fff4b6965e2ad4251b9d9eef` прошёл GitHub CI
  `33125644807`: secret scan, Compose, frontend, backend и exact-revision images зелёные.
  Опубликованные digest: backend
  `sha256:d4e473cd3ca5ab65404b9082e0ce81dd71e924996d151114ca8e28cc5a87a75f`,
  frontend
  `sha256:b910788568d569c691d3e88bfa9aa52a54d7a9aaa1aa266b2eb498aec96ff031`.
- Exact-image proxy canary подтвердил `proxy_policy=true` для всех выбранных FLO/Zara
  offers, но внешний proxy не прошёл TLS chain validation: `CERTIFICATE_VERIFY_FAILED`,
  итог — корректный retryable `source_unreachable`. URL использует `http`, доверенный
  CA bundle не настроен. TLS verification не отключалась, извлечённый сертификат не
  добавлялся в trust store; FLO/Zara остались вне production allowlist.
- Первый запуск canary остановился до parser на `collectstatic` из-за заполненного
  диска. После read-only inventory удалены только неиспользуемые старые image revisions
  `78da/859/369/f40`; rollback `75bc...`, release `26b4...`, state volumes и running
  containers сохранены. Финально доступно около `9.4 GB`.
- Exact SHA прошёл isolated full-stack smoke на чистых PostgreSQL/Redis/Qdrant volumes:
  все миграции, readiness, liveness, HSTS и canonical redirect зелёные; временный
  Compose project удалён.
- Создан свежий backup
  `/home/deploy/backups/pharmaturk/20260827T233612Z_pre_75bc4a4_to_26b4fe9`:
  PostgreSQL custom dump `123 MB`, Qdrant full snapshot `402 MB`; manifest повторно
  проверен по checksum и previous release `75bc4a4...`.
- Controlled deploy `75bc4a4... → 26b4fe9...` завершён с пустым migration plan.
  PostgreSQL/Redis/Qdrant не пересоздавались; backend, frontend, все workers и beat
  имеют exact revision `26b4fe9...`; public readiness/security smoke зелёный.
- Postdeploy live canary включённых источников — `3/3 success`: IKEA offer `114`
  `29999 TRY`, Ummaland offer `1` `1520 RUB`, LCW offer `424` `399.99 TRY`.
  Ручной bounded background batch дал `5/5 success`; первый автоматический Beat cycle
  также дал `5/5 success`, retryable/permanent errors — `0`.
- Public cart подтвердил оба пользовательских исхода после deploy: product `127` —
  `200`, trusted offer `114`, `verified/in_stock/payable`; product `131` —
  `409 source_out_of_stock` с exact quantity `0`. Единственная созданная тестовая
  корзина и строка удалены; обе test session identities отсутствуют.
- Финальный read-only audit: blockers `0`, coverage `15386/15386` (`100%`), active
  offers `27509`, все требуемые миграции применены. Production allowlist остаётся
  `ikea,lcw,ummaland`, catalog projection — `false`. Открыты: доверенный CA/provider
  fix для FLO/Zara, отдельный staging обычного/crypto checkout, Alertmanager,
  catalog projection observation gate и последующее удаление влияния fake stock.

## Отдельный поток: лекарство по пользовательскому запросу

### Зафиксированное решение 2026-08-28

- [x] Отказались от ежедневного обхода большого каталога медикаментов. Медицинские
  источники не включаются в cart/background allowlist и не влияют на продажи,
  checkout или `payable`.
- [x] Триггером является выраженный интерес к конкретной карточке. Ссылка «Как
  заказать из Турции» передаёт стабильный `medicine_slug` на страницу инструкции.
  Обычное открытие общей FAQ-страницы без препарата ничего не запускает.
- [x] Нельзя запускать сетевую мутацию из SSR/обычного `GET`: Next.js prefetch,
  поисковый робот или повторная загрузка страницы не должны становиться запросом к
  источнику. После фактического открытия страницы с `medicine_slug` клиент отправляет
  отдельный идемпотентный `POST` на создание/получение проверки.
- [x] Проверяется только выбранная карточка: актуальная reference price в TRY и
  источник/время наблюдения. Для IlacFiyati этот же точечный разбор может обновить
  явные связи из вкладок `Eşdeğeri` и `SGK Eşdeğeri`; полный каталог не обходится.
- [x] Существующие `MedicineAnalog`, barcode, ATC и SGK equivalent code и API
  `medicines/products/{slug}/analogs` переиспользуются. Аналоги показываются как
  информационные эквиваленты, а не как медицинская рекомендация или гарантированное
  наличие; замена требует подтверждения врача/фармацевта.
- [x] Legacy `IlacFiyatiParser.stock_quantity=3` и `is_available=True` не являются
  реальным аптечным остатком. On-demand поток не записывает эти значения и не меняет
  `is_available`/`stock_quantity`; он обновляет только рыночную цену, метаданные
  наблюдения и связи аналогов.

### Контракт и защита источника

- [x] Добавить отдельную сущность проверки/наблюдения со статусами
  `pending/running/succeeded/source_unavailable/failed`, сохранённой ценой, валютой,
  source URL, безопасным кодом ошибки и timestamps. Не переиспользовать продажный
  `ProductSourceOffer`.
- [x] `POST /api/catalog/medicines/products/{slug}/market-check`: `202` для новой
  Celery-задачи, `200` для свежего результата или уже выполняющейся проверки. Вход
  содержит только slug из каталога; parser key, source URL и proxy policy разрешаются
  сервером из сохранённого товара и active/enabled `ScraperConfig`.
- [x] `GET /api/catalog/medicines/products/{slug}/market-check`: только чтение
  статуса/результата без внешнего HTTP-запроса. Клиент делает bounded polling и
  прекращает его на terminal status или по таймауту.
- [x] Дедупликация: одна выполняющаяся задача на препарат. Freshness TTL по умолчанию
  12 часов: повторный интерес возвращает уже проверенный результат; явный force
  публичному клиенту не предоставляется. TTL должен настраиваться server-side.
- [x] Rate limit по trusted client IP и глобальный лимит запуска задач; Redis-lock до
  постановки в очередь и DB uniqueness/transaction как защита от гонки. Ошибка Redis
  не должна открывать неограниченный доступ к источнику.
- [x] В Celery использовать короткие hard/soft timeouts и отдельный task name/метрики.
  `source_unavailable` не затирает последнюю успешную цену: UI показывает последнюю
  проверенную цену с датой и сообщение, что свежую проверку выполнить не удалось.
- [x] Price update выполнять атомарно с `PriceHistory(source="ilacfiyati_on_demand")`
  и shadow-sync. При отсутствующей/некорректной цене карточка не обновляется.
- [x] Обновление аналогов вынести в безопасный market-observation service: не
  создавать продаваемый/доступный товар из parser defaults, не удалять старые связи
  при частичной ошибке вкладки и не показывать stub-карточки в публичной выдаче.

### Пользовательский сценарий

- [x] Запускать проверку только явной кнопкой «Узнать актуальную цену» непосредственно
  в карточке препарата; browser передаёт только server-owned catalog slug и не может
  выбирать parser, source URL или принудительно обходить freshness TTL.
- [x] В той же карточке показывать bounded состояния queue/running, terminal error,
  последнюю подтверждённую цену и дату. После success сразу обновлять видимую цену
  карточки значением и валютой первоисточника; таймаут/read error снова разрешают retry.
- [x] Ссылка «Как заказать из Турции» ведёт на обычную FAQ без query intent. Старый
  `?medicine=...` остаётся обратно совместимым URL, но больше не запускает POST,
  polling, analog lookup или отдельный блок проверки.
- [x] Ответ FAQ «Как узнать актуальную цену?» объясняет новый сценарий внутри карточки;
  кнопка, process/retry/error и быстрый ответ локализованы для RU/EN.
- [x] Наблюдение эквивалентов остаётся безопасной серверной частью успешной проверки,
  но не перегружает FAQ и не обещает замену/наличие. Продажа лекарств и medicine cart
  flow по-прежнему выключены.

### Проверка и rollout

- [x] Unit: source resolution, price validation, отсутствие stock mutations,
  дедупликация/TTL/lock, terminal errors, частичная ошибка analog tabs.
- [x] API: anonymous rate limit, `POST` idempotency, read-only `GET`, неизвестный slug,
  отсутствие client-controlled URL/parser/proxy, polling contract.
- [x] Frontend: URL с slug, отсутствие запроса на общей FAQ, один `POST` при intent,
  terminal UI states и безопасное отображение аналогов.
- [x] Canary на нескольких реальных IlacFiyati-карточках; Ilacabak включать только
  после отдельной проверки селекторов и качества цены. Затем feature flag, небольшой
  global concurrency limit, мониторинг success/latency/source errors и rollback без
  изменения cart flow.

### Граница для БАДов из того же источника

- [x] `ProductMarketCheck` привязан к generic `Product`, поэтому справочную цену БАДов
  можно наблюдать тем же типом записи без второй параллельной таблицы.
- [x] `IlacFiyatiParser.parse_market_snapshot()` различает `/ilaclar/` и
  `/takviye-edici-gida/`: для БАДов получает одну цену и не запрашивает медицинские
  вкладки эквивалентов.
- [x] Продажное наличие БАДов отделено от справочного наблюдения. Legacy
  `is_available=True/stock_quantity=3` не считается подтверждением поставщика и не
  может автоматически включить БАД в cart enforcement.
- [x] Перед включением продаж БАДов реализован отдельный supplement capability gate:
  reference-price может переиспользовать `ProductMarketCheck`, но buyable availability
  должен подтверждаться реальным `ProductSourceOffer.check_offer` (boolean/exact),
  выбранным SKU/вариантом и checkout preflight. Если источник не сообщает stock,
  заказ остаётся через консультанта, а не становится автоматически payable.
- [ ] Подключить конкретного поставщика БАДов: получить server-owned API/URL и SKU,
  создать `ProductSourceOffer`, добавить parser с явным `check_offer` и только после
  canary внести его key в `SUPPLEMENT_STOCK_ADAPTER_SOURCES`. До этого allowlist пуст,
  а прямые продажи БАДов намеренно закрыты.

### Журнал реализации 2026-08-28

- Добавлена migration `catalog.0203`: generic `ProductMarketCheck` и справочные поля
  `MedicineAnalog`; admin наблюдений read-only, схема не меняет cart/order таблицы.
- `MedicineMarketCheckService` принимает только server-owned IlacFiyati URL активного
  `ScraperConfig`, канонизирует HTTPS host/path, ограничивает client/global rate,
  Redis enqueue lock и source concurrency, дедуплицирует DB/Celery и сохраняет
  последнюю успешную цену при временной ошибке.
- Celery task имеет soft/hard timeout `100/120s`. Успех атомарно обновляет только цену,
  shadow product, `PriceHistory(source="ilacfiyati_on_demand")` и reference-аналоги;
  parser defaults `is_available=True/stock_quantity=3` не проецируются.
- `parse_market_snapshot` не загружает вкладки инструкции; частичный сбой optional
  analog tab не мешает сохранить цену и не удаляет прошлые связи. Для БАДов medicine
  analog tabs вообще не запрашиваются.
- Добавлены read-only `GET` и intent `POST` market-check API. Клиентский URL/parser
  игнорируются, неизвестный slug даёт `404`, anonymous burst фактически ограничен
  `3/min`, polling не запускает источник.
- Карточка препарата передаёт только encoded slug на страницу инструкции без Next
  prefetch. Страница делает single-flight POST, bounded polling, показывает свежую или
  последнюю успешную цену, справочные эквиваленты и локализованный WhatsApp intent.
  Общая FAQ без `medicine` source-запрос не выполняет.
- Проверки:
  - финальный medicine/parser/legacy analog contract — `36 passed`; отдельно
    medicine-файл с фактическим anonymous throttle case — `15 passed`;
  - полный backend suite — `1209 passed`, `30 subtests passed`, 5 существующих warnings;
  - `manage.py check` — 0 issues; migration drift — `No changes detected`;
  - OpenAPI validation — exit `0`, ошибок `0`; `573` warnings (`570` unique)
    относятся к существующим serializer type hints, а не к новому endpoint;
  - frontend — `63 passed`, TypeScript без ошибок, lint `0 errors` и 43 существующих
    `no-img-element` warnings;
  - production `NODE_ENV` build — успешно, включая `/how-to-order-medicines` и
    `/product/[[...slug]]`; `git diff --check` и Python compile — успешно.
- Rollback до canary: `MEDICINE_MARKET_CHECK_ENABLED=false` (default) полностью
  отключает новые POST-запуски; накопленные observation rows безопасно оставить.
  Migration `0203 → 0202` допустима только до появления нужной истории наблюдений или
  после её экспорта. Cart/checkout feature flags и allowlist не меняются.

### Упрощение medicine UX 2026-08-28

- Отдельный intent-экран на `/how-to-order-medicines?medicine=...` удалён. FAQ теперь
  всегда остаётся инструкцией и не выполняет market-check как side effect навигации.
- Новый `MedicinePriceCheck` встроен в карточку: один ручной POST, single-flight,
  bounded GET polling, отмена stale timer при смене slug/unmount, повтор после terminal
  error и локализованные состояния. Success обновляет верхнюю цену карточки точным
  source amount/currency; reference disclaimer и medicine non-sale policy сохранены.
- Удалены устаревшие query-link и medicine consultation-message helpers. Кнопка больше
  не обещает консультацию; отдельная ссылка на инструкцию не содержит slug/query.
- Проверки до release:
  - frontend unit suite — `61 passed`;
  - TypeScript `--noEmit` — успешно;
  - lint — `0 errors`, 43 существующих `no-img-element` warnings;
  - production Next.js build — успешно;
  - локальный browser smoke RU/EN на карточке RAPAMUNE подтвердил
    `idle → pending(disabled) → succeeded → retry`, показ `12225.03 TRY`, обновление
    верхней цены и отсутствие автопроверки на FAQ даже со старым query URL;
  - locale JSON и `git diff --check` — успешно.
- Rollback ограничен frontend release: backend API, Celery, price history, analog
  observation, medicine availability/stock и контуры БАДов/корзины не менялись.

### Production rollout 2026-08-28

- Release commit `234315cb0ff7407194a87ed0d98a7d445edc069c` прошёл GitHub CI
  `33160806225`, attempt 5: secret scan, Compose/release contracts, frontend,
  backend и exact-revision image publication зелёные. Опубликованные digests:
  backend `sha256:621f6db98af1cde86067af04ef2405e9ea9a9e587fc0fd7a8185c09ba44034ae`,
  frontend `sha256:4cb2b24f018abf108d0a1d39d050f13b488f02d5f42141e105032c764b85d3ac`.
- Exact x86_64 images прошли isolated full-stack smoke на production host: чистая
  база получила все миграции, включая `catalog.0203`; readiness, canonical host и
  security headers зелёные; временный Compose project удалён.
- Перед deploy создан и проверен backup
  `/home/deploy/backups/pharmaturk/20260828T122727Z_pre_26b4fe9_to_234315c`:
  PostgreSQL custom dump `128509534` bytes, Qdrant full snapshot `420881408` bytes,
  checksums совпали с источниками и сформирован restore manifest. Временная внутренняя
  копия нового Qdrant snapshot удалена только после успешного внешнего копирования.
- Controlled deploy `26b4fe9... → 234315c...` применил только `catalog.0203`.
  PostgreSQL, Redis и Qdrant не пересоздавались; backend, frontend и workers работают
  на одном exact revision; публичный postdeploy smoke зелёный.
- До включения feature flag синхронный live canary завершился `3/3 success`:
  LASIRIN `118.59 TRY` и 4 аналога, ASIVIRAL `218.89 TRY` и 13 аналогов,
  GLIVANTA `864.55 TRY` и 9 аналогов. Во всех случаях medicine/shadow
  `is_available` и `stock_quantity` остались без изменений.
- После `MEDICINE_MARKET_CHECK_ENABLED=true` публичный anonymous flow подтвердил
  `POST 202 queued → running → succeeded` через штатный Celery worker; RINVOQ получил
  справочную цену `17719.34 TRY`. Страница инструкции и read-only GET отвечают `200`.
  В runtime-логах backend/worker нет traceback/critical ошибок.
- Продажный контур не расширялся: source verification allowlist остаётся
  `ikea,ummaland,lcw`, cart enforcement/background refresh включены по прежним
  правилам, catalog projection выключен; IlacFiyati используется только отдельным
  medicine intent flow и не становится автоматически payable.

### Контур БАДов 2026-08-28 — развёрнут в production

- Live-аудит IlacFiyati подтвердил, что `/takviye-edici-gida/` публикует справочную
  цену и каталожный статус, но не продаёт товар и не сообщает складской остаток.
  Найденные в production значения `is_available=true/stock_quantity=3` и IlacFiyati
  offer `in_stock/boolean` признаны legacy synthetic defaults, а не stock evidence.
- `IlacFiyatiParser` и writer offer-наблюдений теперь всегда дают для этого источника
  `is_available=false`, `stock_quantity=null`, `availability=unknown`,
  `stock_precision=unknown`. Migration `catalog.0204` однократно карантинирует старые
  БАДы/shadow products и IlacFiyati offers, сохраняя их цены и response metadata.
- Добавлен отдельный `SupplementAvailabilityService`: карточка может включить прямую
  продажу только при одновременно включённых cart enforcement/source verification,
  активном offer из явного `SUPPLEMENT_STOCK_ADAPTER_SOURCES` и зарегистрированном
  parser, который переопределяет `BaseScraper.check_offer`. `ilacfiyati` жёстко
  исключён из stock allowlist даже при ошибочной конфигурации.
- При пустом/неподдерживаемом supplier adapter любой старый БАД fail-closed блокируется
  при add-to-cart и повторно при checkout (`409 verification_unsupported`), не создаёт
  payable cart line и не использует legacy stock. Проверенный adapter по-прежнему
  обязан подтвердить цену, boolean/exact availability и запрошенное количество.
- Добавлены intent `POST` и read-only `GET`
  `/catalog/supplements/products/{slug}/market-check`: trusted IlacFiyati URL берётся
  только с сервера, запрос дедуплицируется DB/Redis, ограничен burst/global rate,
  source concurrency и Celery timeout `100/120s`. Успех атомарно обновляет только
  справочную цену и `PriceHistory(source="ilacfiyati_supplement_on_demand")`; stock и
  availability проверяются на неизменность.
- Карточка БАДов без supplier adapter показывает справочную цену с disclaimer,
  запускает проверку только после явного клика, делает bounded polling и предлагает
  консультацию через WhatsApp/Telegram. Количество, cart/buy-now и schema.org `Offer`
  скрыты; SEO не обещает продажу или наличие.
- Rollout-конфигурация для reference-only режима:
  `SOURCE_OFFER_CART_REQUIRED_PRODUCT_TYPES=supplements`,
  `SUPPLEMENT_STOCK_ADAPTER_SOURCES=` (пусто),
  `SUPPLEMENT_MARKET_CHECK_ENABLED=true`,
  `SUPPLEMENT_MARKET_CHECK_SOURCES=ilacfiyati`. `ilacfiyati` нельзя добавлять в
  `SOURCE_OFFER_VERIFICATION_SOURCES` как поставщика; текущие IKEA/LCW/Ummaland
  правила не меняются.
- Проверки release candidate: связанный backend suite — `70 passed`; data migration
  — `1 passed`; финальный полный backend — `1224 passed`, `30 subtests passed`,
  5 существующих warnings; OpenAPI — `2 passed`; Django check — 0 issues, migration
  drift — `No changes detected`; frontend — TypeScript без ошибок, `63 passed`, lint
  0 errors/43 существующих warnings и production build успешно; `git diff --check` и
  Python compile успешно.
- Rollback до canary: выключить `SUPPLEMENT_MARKET_CHECK_ENABLED`, оставить
  `SUPPLEMENT_STOCK_ADAPTER_SOURCES` пустым и при code rollback остановить полный
  IlacFiyati scrape, чтобы старый parser не вернул synthetic stock. Migration `0204`
  намеренно не восстанавливает ложные значения при reverse; `false/null/unknown`
  безопасно оставить в БД.
- Commit `289b978b14fd60d2f62df1a0caa8e0941463216c` прошёл GitHub Actions
  `33178197990`: secret scan, backend, frontend, Compose и публикация exact-revision
  images успешны. Проверены digest backend
  `sha256:d963bf8fe0ed8b54dcf4dff34681b98bb15aa320fc61db54ead2fa4ea0c690bf`
  и frontend
  `sha256:a769c95b15298411ecc4690923c811275e58af565e28de58d0d117d5467e78cb`.
- Перед deploy создан и проверен backup
  `/home/deploy/backups/pharmaturk/20260828T141004Z_pre_234315c_to_289b978`:
  PostgreSQL custom dump проходит `pg_restore --list`, Qdrant snapshot и оба SHA-256
  совпадают с release manifest. Exact images прошли isolated full-stack smoke на
  чистых state volumes; временный Compose project удалён.
- Controlled deploy `234315cb0ff7407194a87ed0d98a7d445edc069c` → `289b978...`
  применил только `catalog.0204`, не пересоздавая PostgreSQL/Redis/Qdrant. Backend,
  frontend и все Celery services работают на одном exact revision; public readiness,
  liveness и security-header smoke успешны.
- Postdeploy data check: все `2946` IlacFiyati-БАДов имеют `is_available=false` и
  `stock_quantity=null`; все `11262` IlacFiyati offers имеют
  `availability=unknown`, `stock_precision=unknown`, `stock_quantity=null`. Цена
  контрольного товара сохранилась.
- Public canary подтвердил карточку `consultation/supplier_not_configured`, затем
  `POST 202 pending → GET 200 succeeded` с ценой `49.70 TRY`. Stock/availability не
  изменились. Add-to-cart вернул `409 verification_unsupported`; canary Cart/CartItem
  не созданы. Повторный live canary прежних adapters — `3/3 success`: Ummaland
  `1520 RUB`, IKEA `29999 TRY`, LCW `399.99 TRY`.
- Финальный read-only audit: blockers `0`, schema применена, source-candidate coverage
  `15386/15386` (`100%`). Allowlist остаётся `ikea,lcw,ummaland`; IlacFiyati не влияет
  на payable, catalog projection выключен. В postdeploy backend/worker логах нет
  `ERROR`, `CRITICAL` или traceback.
- После observation checks диск был заполнен на `91%`. Удалены только внутренние
  Qdrant-дубликаты, чьи внешние backup-копии повторно совпали с manifest SHA-256, и
  два старых неиспользуемых image revision `26b4fe9...`/`75bc4a4...`. Текущий
  `289b978...`, немедленный rollback `234315c...` и все внешние backups сохранены;
  свободное место увеличилось до `9.5 GB` (`74%` занято), public health остался зелёным.

### FLO/Zara 2026-08-28 — trusted proxy CA release candidate

- Корневая причина прежнего `CERTIFICATE_VERIFY_FAILED` подтверждена: production
  использовал Bright Data `brd.superproxy.io:33335`, но
  `SCRAPER_PROXY_CA_BUNDLE` был пуст. TLS нельзя отключать или доверять сертификату,
  извлечённому из отдельного соединения.
- По актуальной официальной документации Bright Data новый native proxy использует
  port `44445` и `brightdata_root_ca_44445.crt`; старые CA/ports `22225` и `33335`
  прекращают работу 2026-09-25. Источники:
  `https://docs.brightdata.com/general/account/ssl-certificate` и
  `https://brightdata.com/static/brightdata_proxy_ca.zip`.
- Официальный root CA добавлен в immutable backend image. Зафиксированы archive
  SHA-256 `af8092570205eec5986f374f2e9b1ea9697f597e19ef6d1be11034f94cb903bc`
  и certificate fingerprint
  `DB:85:48:F8:A5:B1:16:65:36:92:0C:CD:04:73:84:0F:7F:DB:AF:16:5D:ED:F9:07:B7:B5:23:61:AB:C8:7B:60`;
  certificate действует до 2046-07-18 UTC.
- `BaseScraper` fail-closed отклоняет нечитаемый CA bundle, Bright Data без CA и
  устаревший port. Один CA path одинаково передаётся в httpx warmup и requests AJAX
  Zara; `verify=False` не добавлялся. Proxy URL/credentials остаются только в
  server-owned env.
- Изолированные gates: proxy/source suite — `21 passed`; расширенный
  FLO/Zara/parser/source suite — `91 passed`; Django check — 0 issues, migration
  drift — `No changes detected`, certificate fingerprint и `git diff --check`
  подтверждены.
- До изменения production env выполнен in-memory canary с теми же server-owned
  credentials, port `44445` и официальным CA. Первый FLO/Zara проход — `2/2 success`;
  повторный — `6/6 success`. FLO вернул `3699 TRY/in_stock`, Zara — корректный
  terminal `420 TRY/out_of_stock`; `403`, challenge, TLS и transport errors — `0`.
- Rollout остаётся staged: deploy exact image и config `44445+CA`, повторить canary,
  затем отдельно добавить `flo`, проверить background/cart и только после этого
  отдельно добавить `zara`. До завершения этих gates оба источника остаются вне
  production verification allowlist и не влияют на payable.

### Medicine UX `65b29cf` — развёрнут в production 2026-08-28

- [x] Release commit `65b29cf13553826ce661ed0fbe257e86b2ef52a4` собран на
  production host без расходования GitHub Actions. Exact x86_64 images имеют
  revision label полного Git SHA: backend
  `sha256:a393126831f42070dfebc3c9b34c4392c2f4427c98f2f05d1d5f698eea9b4ab8`,
  frontend
  `sha256:36fdd3ef00d401f6807ccc66b9dab1610d5e3205a2438863b2cfd8e4fec96957`.
- [x] Оба exact image прошли Django check, migration drift check, production Next
  build и повторный isolated full-stack smoke на чистых state volumes: вся история
  миграций применена, readiness/liveness, canonical host и security headers зелёные;
  временный Compose project и volumes удалены.
- [x] Перед переключением создан backup
  `/home/deploy/backups/pharmaturk/20260828T161647Z_pre_289b978_to_65b29cf`:
  PostgreSQL custom dump `128418700` bytes проходит `pg_restore --list`, Qdrant full
  snapshot `420881408` bytes имеет SHA-256
  `92f603aeed159683065201c10566dc0229b8b9ba4ad25322be514072254f072a`,
  PostgreSQL SHA-256
  `5a413939c855cbe3661369b9ed5c8deea5e39a393ead02cb1198a0e2de76dfb9`;
  restore manifest и backup-файлы закрыты правами `600`.
- [x] Controlled deploy `289b978b14fd60d2f62df1a0caa8e0941463216c` →
  `65b29cf13553826ce661ed0fbe257e86b2ef52a4` не потребовал миграций и не
  пересоздавал PostgreSQL/Redis/Qdrant. Backend, frontend и все Celery services
  работают на exact release; встроенный public postdeploy smoke успешен.
- [x] Browser canary на RAPAMUNE подтвердил production-сценарий
  `Узнать актуальную цену → Проверка поставлена в очередь… → Цена проверена →
  Обновить цену ещё раз`. Верхняя цена карточки обновилась с `36 067 RUB` до
  `12 225 TRY`, рядом показана точная справочная цена `12225.03 TRY`; read-only API
  вернул `succeeded`, `source=ilacfiyati`, `analog_count=3`, без stale/error.
- [x] Medicine non-sale invariant сохранён: после проверки ORM-цена равна
  `12225.03 TRY`, существующие medicine/shadow availability и stock остались без
  изменений (`true/3` для контрольной legacy-карточки), но в production UI нет
  `Добавить в корзину`/`Купить сейчас` и отображается «Наш сайт не продает
  лекарства». Market-check не меняет эти поля и не создаёт payable flow.
- [x] Старый URL `/how-to-order-medicines?medicine=...` совместим, но больше не
  запускает проверку и не показывает отдельную панель. RU/EN FAQ содержит новые
  ответы; RU/EN карточки показывают `Узнать актуальную цену` / `Check current price`,
  текст консультации удалён, ссылка на инструкцию локализована.
- [x] Runtime safety audit: source verification allowlist остаётся
  `ikea,ummaland,lcw`; `SUPPLEMENT_STOCK_ADAPTER_SOURCES=[]`, catalog projection
  выключен, поэтому БАДы остаются reference-only, а FLO/ZARA не влияют на payable.
  В backend/worker/frontend журналах после canary нет traceback, `ERROR` или
  `CRITICAL`; public health отвечает `status=ok`, DB/cache доступны.
- [x] После повторной сверки внешнего Qdrant backup с manifest удалён только точный
  внутренний snapshot-дубликат `full-snapshot-2026-08-28-16-17-37.snapshot`;
  восстановление сохранено во внешнем backup. Текущий `65b29cf` и rollback images
  `289b978`/`234315c` сохранены; на диске свободно `3.8 GB`.
- [ ] Следующий отдельный rollout — FLO, затем ZARA: доверенный proxy CA, canary и
  последовательное расширение allowlist. Текущий medicine UX от него не зависит.

## Оценка

- Фазы 1–4: 8–12 рабочих дней.
- Фазы 5–7: 8–11 рабочих дней.
- Фазы 8–9 и staging rollout: 4–7 рабочих дней.
- Ориентир MVP: 3–4 недели для одного backend/full-stack разработчика при доступном
  тестовом окружении и стабильных ответах внешних источников.
