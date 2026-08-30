# Обновление спарсенной карточки при открытии

Последняя проверка по коду: 2026-08-30

Ветка реализации: `codex/product-card-source-refresh-lcw-hotfix`

Точный развёрнутый SHA всегда проверяется по Git label работающих production-контейнеров;
документ не хранит самоссылочный номер будущего release.
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
- Открытие корзины остаётся финальной live-проверкой конкретного выбранного варианта;
  checkout использует только сохранённый результат и не обращается к источнику. Для БАДов наличие является
  информационным и не блокирует заказ; повышение актуальной цены по-прежнему требует
  подтверждения пользователя.
- Будущий богатый источник проектируется как общий adapter для всех продаваемых
  категорий, кроме медикаментов. Лекарства навсегда остаются в отдельном справочном
  контуре без продажи.

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
  adapter цены/наличия; справочный источник `ilacfiyati` обновляет цену. Отсутствие
  stock offer или отрицательное наличие не блокируют checkout и передаются администратору
  как задача ручного исполнения заказа.
- [x] Безопасная политика partial response: отсутствующие опции не удаляются.
- [x] Frontend автоматически запускает POST, опрашивает GET и повторно читает detail
  в выбранной пользователем валюте. На карточке БАДов процесс работает без отдельного
  справочного/status-блока; покупатель видит обычную цену и стандартные кнопки продажи.
- [x] Недоступные варианты отображаются неактивными; существующая выбранная опция не
  сбрасывается после обновления.
- [x] Добавлены regression-тесты для manual no-op, content preservation, новой и
  вернувшейся матрицы вариантов, raw price + markup, identity error, singleflight и
  смены/потери supplier SKU без дублирования source offer.
- [x] Полный backend gate в изолированной серверной среде: `1265 passed`, `30 subtests
  passed`, Django system check без ошибок, migration drift отсутствует.
- [x] Frontend gates: `npm audit` — 0 vulnerabilities, TypeScript, 62 unit tests,
  ESLint без ошибок и успешный Next.js production build.
- [x] Immutable backend/frontend/test images собраны с точным revision label;
  параллельная Poetry-установка отключена для воспроизводимой сборки.
- [x] Initial production backup, deploy `4b4ecd2` с выключенным флагом и публичный
  HTTPS smoke выполнены; rollback image и backup manifest сохранены.
- [x] IKEA canary выявил скрытый `Product.post_save` side effect на shadow metadata;
  flag сразу выключен, запись переведена на атомарный `QuerySet.update`, добавлен
  regression-тест отсутствия content signals, полный hotfix predeploy пройден.
- [x] Свежий backup и deploy hotfix `a10326d` с выключенным флагом.
- [x] Повторный IKEA canary: цена/наличие обновлены, content-only и media hash не
  изменились, `post_save` content pipeline не запускался.
- [x] FLO canary: исходная цена обновлена `3599 → 3699 TRY`, матрица сохранена
  (`7` цветов, `59` размеров), явно недоступные опции выключены, контентный hash
  не изменился.
- [x] Публичный валютный canary после FLO: raw price остался в TRY; detail в RUB/USD
  отдал цену с текущим курсом, валютной маржой и товарной наценкой без записи
  наценки в базовую цену.
- [x] Zara canary: `7 → 9` цветов, `35 → 45` размеров, `1490 → 1590 TRY`;
  hash ранее существовавшего контента и `53` media rows совпал с verified backup.
- [x] LCW negative canary: нестабильный supplier group id дал `identity_mismatch`;
  цена, `84` размера, offers и protected hash остались без изменений.
- [x] Узкий LCW group-id hotfix допускает drift supplier group id только при точном
  совпадении сохранённых variant key + canonical URL; negative regression не разрешает
  похожий, но другой товар.
- [x] Частичный LCW-ответ без размеров не создаёт summary-offers с пустым `size_key`,
  если для цвета уже существуют сохранённые размерные offers; regression добавлен.
- [x] Deploy `60dfefa`, очистка четырёх canary summary-offers и повторный LCW canary:
  `12` цветов, `84` размера, `84` активных offer, `0` пустых размеров; protected hash
  до/после совпал.
- [x] Ummaland canary: raw/base цена `1216 → 1520 RUB`, публичная цена с действующей
  наценкой — `1748 RUB`; protected hash совпал.
- [x] Akakçe canary для БАДа: raw/base цена `360 TRY`, наличие восстановлено,
  публичная цена в выбранной валюте — `849.66 RUB`; protected hash совпал.
- [x] Полный allowlist включён поэтапно без массового запуска. Bershka, Pull&Bear и
  Massimo Dutti пока не имеют активных production offers и не создают нагрузку.
- [x] Финальный HTTPS liveness/readiness/security smoke пройден; все application
  containers работают на `60dfefa`, критических refresh/traceback строк после canary — `0`.

## Ошибки и поведение карточки

| Сценарий | Результат |
| --- | --- |
| ручной товар / флаг выключен / источник не разрешён | `not_eligible`, сеть не вызывается |
| React Strict Mode в рамках одного открытия | frontend переиспользует один POST/promise; backend возвращает тот же `pending/running` job |
| карточку открыли заново после `succeeded`/`failed` | ставится новый refresh job |
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
