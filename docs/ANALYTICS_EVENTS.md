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
| `add_to_cart` | `AddToCartButton`, `BuyNowButton` | item_id, slug, quantity (без цены) |
| `begin_checkout` | `checkout.tsx`, после загрузки непустой корзины | позиции, сумма, валюта корзины |
| `purchase` | `checkout.tsx`, после создания заказа (любой способ оплаты; при выключенной онлайн-оплате = отправленная заявка, `payment_method=manager`) | transaction_id = номер заказа, сумма и валюта заказа |
| `search` | `search.tsx` | search_term |
| `contact_click` | `ContactWidget` | contact_channel: telegram/whatsapp/vk/email/phone |

## Цели Яндекс.Метрики (`ymReachGoal`)

Создать в Метрике цели типа «JavaScript-событие» с идентификаторами:

`add_to_cart`, `buy_now`, `begin_checkout`, `purchase` (параметры
`order_price`, `currency`, `payment_method`), `search`, `click_telegram`,
`click_whatsapp`, `click_vk`, `click_email`, `click_phone`.

Изменения событий проверять в Preview-режиме GTM и в отладке Метрики
(`?_ym_debug=1`), см. `DEVELOPMENT_RULES.md`.
