# Source offer: контракт Cart API

Последняя проверка по коду: 2026-08-27
Контур: `/api/orders/cart/` → source-offer policy → checkout preflight

Документ описывает добавленные поля и конфликтные ответы. Исполняемый OpenAPI schema,
serializers и views имеют приоритет при расхождении.

## Маршруты

| Метод и путь | Назначение | Внешняя проверка |
| --- | --- | --- |
| `GET /api/orders/cart/` | получить корзину | никогда |
| `POST /api/orders/cart/add/` | добавить товар/вариант | при включённом enforcement |
| `POST /api/orders/cart/{item_id}/update/` | изменить quantity | при увеличении или stale/unverified строке |
| `POST /api/orders/cart/{item_id}/acknowledge-price/` | подтвердить конкретную повышенную цену | да |
| `POST /api/orders/cart/revalidate/` | принудительно перепроверить bounded набор строк | да |

Supplier URL, parser key, external SKU и source price не принимаются из клиентского
payload. Сервер выбирает сохранённый `ProductSourceOffer` по product/variant/size.

## Поля строки корзины

Новые поля являются read-only:

- `source_offer` — внутренний ID выбранного сохранённого offer;
- `verification_status` — `not_checked`, `verified`, `blocked`,
  `retryable_error` или `unsupported`;
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
- `cart_changed`.

## Конфликты и повтор запроса

Окончательный supplier conflict возвращает `409`. В ответе add/acknowledge есть
`detail`, `code`, `issues[]` и `verification`; при конкурентном изменении корзины
возвращается актуальный `CartSerializer` с `operation_issues`. Временная недоступность
источника возвращает `503`, а не ложный out-of-stock.

Повышенную цену клиент подтверждает точной парой `acknowledged_price` и
`acknowledged_currency`. Не следует автоматически повторять любой `409`: сначала UI
должен показать причину и получить явное действие пользователя. Снижение цены можно
применить автоматически с уведомлением.

Checkout повторяет source preflight до короткой DB-транзакции. При изменении корзины,
цены или availability заказ/crypto invoice не создаются; клиент получает обновлённую
корзину для review. Проверка поставщика не означает резервирование товара.

## Совместимость

Все source-поля добавлены к существующему ответу и не удаляют legacy-поля. При
`SOURCE_OFFER_CART_ENFORCEMENT_ENABLED=false` старый add/update flow сохраняется, а
nullable/read-only поля остаются диагностическими. GET пустой anonymous cart не создаёт
session или строку Cart.
