# Source offer: эксплуатация и диагностика

Последняя проверка по коду: 2026-08-31
Владелец: catalog-commerce
Контур: parser adapters → `ProductSourceOffer` → открытие карточки/корзины → snapshot checkout

> Фоновый refresh удалён. Сетевые проверки допустимы только при открытии карточки
> товара и один раз при открытии корзины. Add/update/acknowledge/checkout не обращаются
> к поставщику и используют сохранённый snapshot.

Этот runbook относится только к лёгкой проверке одного сохранённого supplier offer.
Он не разрешает запуск полного импорта всех парсеров и не заменяет подтверждение
заказа у поставщика.

## Безопасный порядок включения

Все новые флаги по умолчанию выключены. Включайте их отдельными deploy/config шагами:

1. применить migrations `catalog 0202`, `orders 0010` и `orders 0011` на копии
   production data, затем в staging;
2. включить `SOURCE_OFFER_RECORDING_ENABLED=true`, выполнить dry-run backfill и
   проверить заполненность admin без изменения корзины;
3. включить `SOURCE_OFFER_VERIFICATION_ENABLED=true` и один источник в
   `SOURCE_OFFER_VERIFICATION_SOURCES`; оставить cart/background/catalog projection
   выключенными;
4. проверить latency, error outcomes, price/stock changes и circuit breaker;
5. включить cart enforcement, выполнить обычный и crypto staging smoke;
6. только после стабильного окна включить catalog/YML projection.
7. отдельно включить `PRODUCT_CARD_SOURCE_REFRESH_ENABLED=true` сначала для одного
   parser key. Этот reader/writer не зависит от background refresh и не должен
   включаться сразу для всего allowlist.

Не включайте пустой allowlist как первый rollout: при включённой verification пустое
значение означает все зарегистрированные adapters.

## Флаги и ограничения

| Переменная | Безопасное начальное значение | Назначение |
| --- | --- | --- |
| `SOURCE_OFFER_VERIFICATION_ENABLED` | `false` | главный выключатель сетевой проверки |
| `SOURCE_OFFER_VERIFICATION_SOURCES` | один parser key | allowlist источников; пусто = все |
| `SOURCE_OFFER_CART_ENFORCEMENT_ENABLED` | `false` | применение snapshot-проверки в cart/checkout |
| `SOURCE_OFFER_CATALOG_PROJECTION_ENABLED` | `false` | DB-only projection свежего status в detail/YML |
| `PRODUCT_CARD_SOURCE_REFRESH_ENABLED` | `false` | async обновление спарсенной карточки при открытии |
| `PRODUCT_CARD_SOURCE_REFRESH_SOURCES` | один parser key | обязательный allowlist; пусто означает, что ни один товар не eligible |
| `PRODUCT_CARD_SOURCE_REFRESH_STATE_TTL_SECONDS` | `300` | freshness/success TTL и защита от повторных запросов |
| `PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS` | `30` | короткий cooldown retryable source errors |
| `PRODUCT_CARD_SOURCE_REFRESH_LOCK_SECONDS` | `150` | singleflight одной карточки, дольше hard timeout task |

On-demand verifier сохраняет timeout/retry, per-source rate/concurrency, single-flight
и circuit breaker. Планового batch-прохода больше нет.

## Платный transport и бюджет

`SCRAPER_PROXY_URL` и Bright Data Web Unlocker являются тарифицируемыми внешними
transport. Их возможности, актуальная модель оплаты, лимит зоны, правила выбора и
чек-лист повторного использования описаны в
[`PAID_WEB_ACCESS_SERVICES.md`](PAID_WEB_ACCESS_SERVICES.md).

Для FLO Web Unlocker допустим только из product-card-open и cart-revalidate. Один
business event не должен превращаться в batch crawl или app-level retry. FLO
использует browser rendering без manual `expect`: product-only expectation делал
redirect снятого товара дорогим timeout. Карточка проверяет только один сохранённый
цвет; provider limit `Suspend zone and Alert` обязателен, а auto recharge не
включается без отдельного подтверждения владельца.

## Read-only rollout audit

До изменения feature flags выполните отчёт на копии production data, затем тем же
artifact — в staging:

```bash
docker compose exec backend poetry run python manage.py \
  audit_source_offer_rollout --format json --fail-on-blockers
```

Команда выполняет только aggregate SELECT и чтение `django_migrations`. Она не пишет
в catalog/cart/orders, не вызывает parser и не использует Redis. JSON содержит:

- применённость `catalog.0202`, `orders.0010` и `orders.0011`;
- число source-кандидатов, покрытие active offers и legacy fake stock `3/1000`;
- availability/stock precision, freshness, errors и разбивку по parser key;
- состояние CartItem/OrderItem source columns, если их миграции применены;
- текущие feature flags, `blockers`, `warnings` и `ready_for_source_rollout`.

`--fail-on-blockers` предназначен для release job. Не продолжайте rollout при missing
migration, нулевом покрытии кандидатов, cart/background без общего verification flag
или verification с пустым allowlist. Fake stock, never-checked и stale offers выводятся
как warnings: их нужно разобрать до enforcement, но они не меняются этой командой.

Текстовый формат удобен для ручного просмотра:

```bash
docker compose exec backend poetry run python manage.py audit_source_offer_rollout
```

Cart API, issue codes и конфликтные ответы описаны в
`docs/SOURCE_OFFER_CART_API.md`.

## Что смотреть

В Django admin откройте «Предложения источников». Таблица read-only показывает parser,
domain, status/stock/price, актуальность, число ошибок подряд, последний error code и
текущее состояние circuit breaker. Фильтры позволяют отделить never checked и stale.

Prometheus endpoint проекта — `/metrics`. Основные ряды:

- `source_offer_verification_total{source,outcome}` — результат каждой проверки;
- `source_offer_verification_seconds` — latency histogram;
- `source_offer_verification_changes_total{source,field}` — price/availability/stock drift;
- `source_offer_stale_backlog` — число stale active offers в allowlist;
- `source_offer_background_refresh_total{outcome}` — состояние scheduled runs.
- `product_card_source_refresh_total{source,outcome}` — результат полного card refresh;
- `product_card_source_refresh_seconds{source}` — latency полного card refresh;
- `product_card_source_refresh_changes_total{source,field}` — изменения raw price и
  созданные/обновлённые variants/sizes.

Репозиторные alert rules находятся в
`ops/prometheus/source_offer_alerts.yml`. В Compose проекта Prometheus/Alertmanager не
развёрнуты, поэтому production monitoring должен подключить этот файл, заменить
`runbook_url` на абсолютный URL и проверить правила штатным `promtool check rules`.
Наличие файла в репозитории само по себе не доставляет уведомления.

## Диагностика алертов

### Error rate или открытый circuit

1. Сгруппируйте `source_offer_verification_total` по `source,outcome`.
2. Отличайте `not_found/gone` от `timeout/access_blocked/source_unreachable`.
3. Проверьте один offer в admin: trusted HTTPS domain, parser key, SKU/variant/size,
   `last_error_code` и `consecutive_failures`.
4. Проверьте изменения supplier HTML/API на staging fixture, не на cart GET.
5. Не очищайте весь Redis. Circuit сам закрывается после recovery timeout. Если
   исправление подтверждено и требуется срочная проверка, дождитесь recovery и
   поставьте один bounded task.

### Burst изменения цен

1. Сверьте валюту supplier offer и курс; не сравнивайте TRY и публичный RUB напрямую.
2. Выберите несколько offers из одного source и подтвердите цену на первоисточнике.
3. Проверьте parser selector/API field на ошибочную old/list price.
4. При массовом неверном результате выключите конкретный source в allowlist. Не
   переписывайте цены каталога массовой командой до исправления adapter и dry-run.

## Безопасный ручной повтор

Сначала выполните task как синхронный bounded вызов в staging. Он уважает общий lock,
batch, allowlist, circuit и rate limits:

```bash
docker compose exec backend poetry run python manage.py shell -c \
  "from apps.catalog.services.source_offer_background_refresh import refresh_stale_source_offers as r; print(r())"
```

Ожидаемые статусы: `disabled`, `already_running` или `completed`. Поля `selected`,
`checked`, `successful`, `retryable_errors`, `permanent_errors`, `outcomes` и
`stale_total` нужны для решения, можно ли продолжать rollout. Повторный вызов не
создаёт offers и не запускает media/AI/dedup pipelines.

Для проверки регистрации без запуска supplier HTTP:

```bash
docker compose exec celeryworker poetry run celery -A config inspect registered
```

## Согласованность витрины и feed

Catalog projection читает только свежие строки БД и никогда не вызывает parser. Один
свежий sellable offer подтверждает supplier availability, но не отменяет ручной
`is_available=false` магазина. Чтобы выставить out-of-stock или discontinued, все
активные enabled offers должны иметь свежий окончательный статус.
Stale/unknown/unreachable/unsupported сохраняет старое catalog-состояние.

Detail API проецирует `availability_status` и `is_available`; frontend использует их
в публичном Offer JSON-LD и скрывает кнопки покупки при `is_available=false`. YML
использует тот же resolver. Sitemap продолжает включать активную страницу независимо
от наличия, поэтому out-of-stock/discontinued карточка остаётся HTTP 200 и показывает
блок рекомендаций/аналогов.

## Rollback

Откатывайте readers, не данные:

1. `SOURCE_OFFER_CATALOG_PROJECTION_ENABLED=false`;
2. `PRODUCT_CARD_SOURCE_REFRESH_ENABLED=false`;
3. `SOURCE_OFFER_CART_ENFORCEMENT_ENABLED=false`;
4. удалите проблемный parser key из allowlist или выключите verification полностью;
5. оставьте offer history и immutable order snapshots для аудита.

Paid webhook не запускает parser и не должен меняться при этом rollback. Откат таблиц
после production orders требует экспорта source snapshots и отдельного change plan.
