# Source offer: контракт Cart API

Последняя проверка по коду: 2026-10-21
Контур: открытие корзины → source-offer policy → сохранённый checkout snapshot

Документ описывает добавленные поля и конфликтные ответы. Исполняемый OpenAPI schema,
serializers и views имеют приоритет при расхождении.

## Маршруты

| Метод и путь | Назначение | Внешняя проверка |
| --- | --- | --- |
| `GET /api/orders/cart/` | получить корзину | никогда |
| `POST /api/orders/cart/add/` | добавить товар/вариант и сбросить его snapshot | никогда |
| `POST /api/orders/cart/{item_id}/update/` | изменить quantity по последнему snapshot | никогда |
| `POST /api/orders/cart/{item_id}/acknowledge-price/` | подтвердить сохранённую повышенную цену | никогда |
| `POST /api/orders/cart/revalidate/` | проверить все строки при открытии страницы корзины | да, один раз на открытие |
| `POST /api/orders/orders/create-from-cart/` | оформить по сохранённому snapshot | никогда |

`create-from-cart` открыт и гостю (`AllowAny`, с 27.10.2026): заявка менеджеру без регистрации,
как «Найдём товар». Гость оформляет только свою корзину — по `X-Cart-Session` / cookie
`cart_session`; `Order.user` пустой, имя и телефон обязательны. Криптооплата гостю — 401 (счёт
привязан к аккаунту). Лимит — 5 в минуту и 30 в сутки на аккаунт или, для гостя, на доверенный IP.
Страница `checkout-success` гостю показывает «Заявка №… отправлена» без деталей заказа (они по входу).

Supplier URL, parser key, external SKU и source price не принимаются из клиентского
payload. Сервер выбирает сохранённый `ProductSourceOffer` по product/variant/size.

## Поля строки корзины

Новые поля являются read-only:

- `source_offer` — внутренний ID выбранного сохранённого offer;
- `verification_status` — `not_checked`, `pending_confirmation`, `verified`,
  `blocked`, `retryable_error` или `unsupported`;
- `source_checked_at`, `source_availability_status`;
- `observed_source_price`, `observed_source_currency`;
- `observed_public_price`, `observed_public_currency`;
- `observed_stock_precision` — `exact`, `boolean` или `unknown`;
- `observed_stock_quantity` — число только для `exact`, иначе `null`;
- `verified_quantity`, `price_change_state` и price acknowledgement fields;
- `verification_issues` — стабильные machine-readable codes;
- `issues[]` — `{code, message, blocking}` для UI;
- `is_payable` — участвует ли строка в checkout/totals.

На уровне корзины возвращаются `payable_items_count`, объединённые `issues[]` и
`has_blocking_issues`. Заблокированные строки остаются видимыми, но не входят в payable
total, promo, shipping и free-shipping threshold.

## Коды проблем

- `source_out_of_stock`;
- `source_quantity_changed`;
- `source_price_changed`;
- `source_unreachable`;
- `verification_unsupported`;
- `cart_changed`;
- `manager_price_confirmation` — «Цена будет уточнена менеджером». Не блокирует:
  платный доступ к источнику (лимит зоны Web Unlocker FLO) исчерпан или
  приостановлен. Строка входит в заявку по последней сохранённой цене каталога,
  менеджер уточняет цену и наличие.

## Событийная модель

Карточка товара обновляет только свой источник при открытии. Страница корзины
автоматически вызывает `revalidate` один раз и не даёт перейти к оформлению до
ответа. Endpoint обрабатывает все строки без лимита. Ручной кнопки повторной
проверки нет: следующий запрос возможен только при новом открытии корзины.

Платный источник (FLO) проверяется не чаще раза в окно свежести
`PRODUCT_CARD_SOURCE_REFRESH_FRESHNESS_SECONDS` (24 ч), общее с карточкой: строка,
предложение которой успешно проверено за это время, берёт сохранённый результат без
запроса (`source_checked_at` — время той проверки). Если последняя проверка была
ошибкой, строка проверяется заново. Бесплатные источники проверяются при каждом
открытии.

Добавление товара, изменение количества, подтверждение цены и checkout не вызывают
поставщика. Checkout отклоняет непроверенный или заблокированный snapshot.

## Конфликты

Окончательный supplier conflict возвращает `409`. В ответе add/acknowledge есть
`detail`, `code`, `issues[]` и `verification`; при конкурентном изменении корзины
возвращается актуальный `CartSerializer` с `operation_issues`. Временная недоступность
источника возвращает `503`, а не ложный out-of-stock.

Повышенную цену клиент подтверждает точной парой `acknowledged_price` и
`acknowledged_currency`. Не следует автоматически повторять любой `409`: сначала UI
должен показать причину и получить явное действие пользователя. Снижение цены можно
применить автоматически с уведомлением.

Checkout сверяет сохранённый snapshot до короткой DB-транзакции. При блокирующем
состоянии или конкурентном изменении заказ/crypto invoice не создаются. Проверка
поставщика не означает резервирование товара.

Исключение бизнес-политики: для `supplements` availability является информационной.
Отсутствующий adapter, `out_of_stock` или недоступность источника не исключают строку
из payable total и не блокируют checkout. Используется последняя сохранённая цена с
текущей конвертацией и наценками; повышение цены всё равно требует явного подтверждения.
Заказ помечается `supplier_confirmation_required` для ручного исполнения администратором.

## Совместимость

Все source-поля добавлены к существующему ответу и не удаляют legacy-поля. При
`SOURCE_OFFER_CART_ENFORCEMENT_ENABLED=false` старый add/update flow сохраняется, а
nullable/read-only поля остаются диагностическими. GET пустой anonymous cart не создаёт
session или строку Cart.
