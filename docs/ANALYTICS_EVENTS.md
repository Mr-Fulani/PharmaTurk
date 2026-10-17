# Аналитика: согласие, события и цели

## Согласие на cookie

- Статус хранится в cookie `pharma_cookie_consent` (`accepted` / `rejected`).
- `hooks/useCookieConsent.ts` — общее состояние для всех компонентов
  (`useSyncExternalStore`): после «Принять» `_app.tsx` сразу грузит Метрику и GA4,
  без перезагрузки.
- GTM грузится всегда, но в `_document.tsx` до него выставлен Consent Mode
  `default`: `denied` до ответа, `granted` при сохранённом согласии. При принятии —
  `consent update granted` + событие `cookie_consent_granted` (`lib/gtm.ts`).
- Метрика инициализируется без `defer`, поэтому первый просмотр учитывается при
  init; дальше — `ymPageHit` на `routeChangeComplete`.

## События dataLayer (GA4 e-commerce)

| Событие | Где | Данные |
|---|---|---|
| `view_item` | карточка товара (`product/[[...slug]].tsx`), один раз на товар | item_id (как в add_to_cart), название, тип, бренд, цена и валюта карточки |
| `add_to_cart` | `AddToCartButton`, `BuyNowButton` | item_id, slug, quantity (без цены) |
| `begin_checkout` | `checkout.tsx`, после загрузки непустой корзины | позиции, сумма, валюта корзины |
| `purchase` | `checkout.tsx`, после создания заказа (любой способ оплаты; при выключенной онлайн-оплате = отправленная заявка, `payment_method=manager`) | transaction_id = номер заказа, сумма и валюта заказа |
| `search` | `search.tsx` | search_term |
| `contact_click` | `ContactWidget` | contact_channel: telegram/whatsapp/vk/email/phone |
| `sourcing_request` | `SourcingRequestForm` (главная, пустая категория, поиск) | placement: home/category/search |

## Google Analytics 4

- Ресурс **Mudaroba** (до 17.10.2026 — turk-export; поток «Mudaroba», `G-C333XNVW4X`) в аккаунте Google Mr.Fulani;
  контейнер GTM `GTM-MR4C4W83` на 16.10.2026 пустой (тегов нет, не опубликован).
- GA4 подключён напрямую (`gtag`), а объектные `dataLayer.push` gtag не обрабатывает, поэтому
  `gtmEvent` (`lib/gtm.ts`) дублирует каждое событие в `gtag('event', …)` с ecommerce-полями на
  верхнем уровне (`ga4EventParams`). Если когда-нибудь настроить GA4-теги в GTM — убрать это
  дублирование, иначе события задвоятся.
- Ключевые события в GA4: `purchase` (по умолчанию), `sourcing_request`.

## Цели Яндекс.Метрики (`ymReachGoal`)

Создать в Метрике цели типа «JavaScript-событие» с идентификаторами:

`add_to_cart`, `buy_now`, `begin_checkout`, `purchase` (параметры
`order_price`, `currency`, `payment_method`), `search`, `click_telegram`,
`click_whatsapp`, `click_vk`, `click_email`, `click_phone`, `sourcing_request` (параметр `placement`).

Изменения событий проверять в Preview-режиме GTM и в отладке Метрики
(`?_ym_debug=1`), см. `DEVELOPMENT_RULES.md`.
