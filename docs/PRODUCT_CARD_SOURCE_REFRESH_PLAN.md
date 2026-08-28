# Обновление спарсенной карточки при открытии

Последняя проверка по коду: 2026-08-29  
Ветка реализации: `codex/product-card-source-refresh`  
Контур: product detail → async source refresh → inventory-only reconcile → detail refetch

## Цель и неизменяемые правила

При открытии спарсенной карточки один асинхронный запрос к её первоисточнику
обновляет исходную цену, наличие, цвета и размеры. Публичная конвертация, валютная
маржа и наценка бренд → категория → global применяются существующими сериализаторами
после повторного чтения карточки.

- Ручной товар без активного доверенного `ProductSourceOffer` не запускает parser.
- Лекарства `ilacfiyati` остаются в отдельном справочном price-check flow.
- Название, описание, переводы, SEO, категория, бренд и существующие медиа не
  обновляются этим контуром.
- `old_price`/акционная цена также не перезаписывается последней наблюдаемой ценой;
  динамика пишется в `PriceHistory`.
- URL, parser key и source identity берутся только из БД; клиент не передаёт источник.
- Сетевой/структурный сбой не меняет карточку. Все изменения применяются одной
  транзакцией только после полной валидации ответа.
- Один неполный ответ не деактивирует отсутствующий в нём цвет/размер. Явно
  вернувшиеся варианты реактивируются; новые создаются без скачивания медиа.
- Cart/checkout live verification остаётся финальной проверкой конкретного выбранного
  варианта и не заменяется проверкой при просмотре.

## Зафиксированный план

- [x] Аудит parser registry, full-detail запросов, source-offer identity, моделей
  вариантов и публичного расчёта цены.
- [x] Отдельные feature flag и allowlist; ручные товары и лекарства исключены.
- [x] Product-level singleflight, rate/concurrency guard, circuit breaker и Celery task.
- [x] Валидация HTTPS/parser/domain, external product identity, валюты, цены и
  аномального скачка до записи в БД.
- [x] Inventory-only reconcile для одежды/обуви/головных уборов/белья/исламской
  одежды, мебели и простых товаров; `ProductSourceOffer` обновляется для всех
  наблюдаемых опций.
- [x] Для БАДов с уже найденным коммерческим Akakçe offer переиспользуется точечный
  stock-adapter; справочный источник `ilacfiyati` не участвует в продаже.
- [x] Безопасная политика partial response: отсутствующие опции не удаляются.
- [x] Frontend автоматически запускает POST, опрашивает GET, показывает локализованный
  RU/EN статус и повторно читает detail в выбранной пользователем валюте.
- [x] Недоступные варианты отображаются неактивными; существующая выбранная опция не
  сбрасывается после обновления.
- [x] Добавлены regression-тесты для manual no-op, content preservation, новой и
  вернувшейся матрицы вариантов, raw price + markup, identity error и singleflight.
- [x] Frontend gates: TypeScript, 62 unit tests и ESLint без ошибок.
- [ ] Полный Django regression gate в контейнере (локальный Docker daemon 2026-08-29
  не отвечал даже на `docker info`; тесты нельзя отмечать пройденными).
- [ ] Production backup, deploy с выключенным флагом и smoke endpoint.
- [ ] Canary одного товара IKEA, одного FLO/LCW и одного Zara; сравнение с источником.
- [ ] Поочерёдное включение allowlist и окно наблюдения без массового включения.

## Ошибки и поведение карточки

| Сценарий | Результат |
| --- | --- |
| ручной товар / флаг выключен / источник не разрешён | `not_eligible`, сеть не вызывается |
| повторное открытие или React Strict Mode | возвращается тот же `pending/running` job |
| успешный результат ещё свежий | source повторно не вызывается, detail перечитывается |
| timeout, 403/challenge, 429, 5xx, proxy failure | старые данные сохраняются, короткий error cooldown |
| redirect на чужой домен или другая source identity | terminal failure, транзакции нет |
| пустая матрица fashion-вариантов, неверная цена/валюта | terminal failure, транзакции нет |
| цена отличается более чем в `0.05x..20x` | anomaly guard, транзакции нет |
| источник не прислал ранее известный вариант | вариант сохраняется как был |
| источник явно вернул option out-of-stock | размер/цвет становится неактивным |
| новая опция | создаётся минимальный variant/size без контентного и media pipeline |
| Celery/Redis временно недоступны | non-blocking сообщение; исходная карточка доступна |

## Production-параметры

Все значения по умолчанию выключены/ограничены:

```dotenv
PRODUCT_CARD_SOURCE_REFRESH_ENABLED=false
PRODUCT_CARD_SOURCE_REFRESH_SOURCES=zara,bershka,pullandbear,massimodutti,flo,lcw,ikea,ummaland,akakce
PRODUCT_CARD_SOURCE_REFRESH_TIMEOUT_SECONDS=12
PRODUCT_CARD_SOURCE_REFRESH_MAX_RETRIES=1
PRODUCT_CARD_SOURCE_REFRESH_STATE_TTL_SECONDS=300
PRODUCT_CARD_SOURCE_REFRESH_ERROR_TTL_SECONDS=30
PRODUCT_CARD_SOURCE_REFRESH_LOCK_SECONDS=150
PRODUCT_CARD_SOURCE_REFRESH_MIN_PRICE_RATIO=0.05
PRODUCT_CARD_SOURCE_REFRESH_MAX_PRICE_RATIO=20
```

Rollback не требует обратной записи данных: сначала установить
`PRODUCT_CARD_SOURCE_REFRESH_ENABLED=false`, затем при необходимости удалить только
проблемный parser key из allowlist. Source offers и `PriceHistory` сохраняются для
аудита.
